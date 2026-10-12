//! RCH custody and business completion have independent owning workers and `SQLite` commits.
use super::*;
use r3akt_rch_core::{DurableOutboundIntent, InboxBatch, InboxEvent, RchCommandTransaction};
use r3akt_transport_rns::durable_broker as broker;

fn storage(error: r3akt_rch_core::RchCoreError) -> ApiError {
    ApiError::ServiceUnavailable(error.to_string())
}
fn open(state: &AppState) -> Result<RchSqliteStore, ApiError> {
    ensure_kill_switch_persistence_unlocked(state)?;
    let path = state
        .sqlite_path
        .as_ref()
        .ok_or_else(|| ApiError::ServiceUnavailable("durable broker requires RCH SQLite".into()))?;
    RchSqliteStore::open(path.as_ref()).map_err(storage)
}
fn plane(state: &AppState) -> Result<&ZmqDataPlane, ApiError> {
    state
        .lxmf_zmq_data_plane
        .as_deref()
        .ok_or_else(|| ApiError::ServiceUnavailable("durable ZeroMQ data plane is required".into()))
}

pub(super) fn spawn(state: AppState, interval: Duration) -> tokio::task::JoinHandle<()> {
    tokio::spawn(async move {
        let setup = (|| {
            let path = state.sqlite_path.as_ref().ok_or_else(|| {
                ApiError::ServiceUnavailable("durable broker requires SQLite".into())
            })?;
            let _ = path;
            let lease = state.broker_consumer_lease.clone().ok_or_else(|| {
                ApiError::ServiceUnavailable(
                    "durable consumer ownership was not acquired at startup".into(),
                )
            })?;
            let consumer = open(&state)?.durable_consumer_id().map_err(storage)?;
            plane(&state)?;
            Ok::<_, ApiError>((lease, consumer))
        })();
        let (_lease, consumer) = match setup {
            Ok(value) => value,
            Err(error) => {
                record_reticulumd_inbound_worker_event_error(&state, error.to_string());
                return;
            }
        };
        let mut owners = tokio::task::JoinSet::new();
        for lane in 0..4 {
            let state = state.clone();
            let consumer = consumer.clone();
            owners.spawn(async move {
                let mut failures = 0u32;
                loop {
                    if state.runtime_exit.is_requested() {
                        break;
                    }
                    let mut drain = false;
                    if lane == 0 {
                        set_reticulumd_inbound_worker_running(
                            &state,
                            !runtime_shutdown_requested(&state),
                            interval,
                        );
                    }
                    if !runtime_shutdown_requested(&state) {
                        let task_state = state.clone();
                        let task_consumer = consumer.clone();
                        // Keep the completion owner: an external timeout must not detach a database write.
                        let result = tokio::task::spawn_blocking(move || match lane {
                            0 => intake(&task_state, &task_consumer).map(|()| false),
                            1 => apply(&task_state, &task_consumer),
                            2 => dispatch(&task_state),
                            _ => announces(&task_state).map(|()| false),
                        })
                        .await;
                        let error = match result {
                            Ok(Ok(work)) => {
                                drain = work;
                                None
                            }
                            Ok(Err(error)) => Some(error.to_string()),
                            Err(error) => Some(error.to_string()),
                        };
                        failures = if error.is_some() {
                            failures.saturating_add(1)
                        } else {
                            0
                        };
                        if let Some(error) = &error {
                            record_reticulumd_inbound_worker_event_error(&state, error.clone());
                        }
                        match state.broker_lane_errors.write() {
                            Ok(mut errors) => errors[lane] = error,
                            Err(error) => {
                                eprintln!("broker lane error state poisoned: {error}");
                            }
                        }
                    }
                    if drain {
                        tokio::task::yield_now().await;
                        continue;
                    }
                    state
                        .runtime_exit
                        .sleep(if failures > 0 {
                            retry_delay(failures)
                        } else if lane == 0 {
                            interval.max(Duration::from_millis(50))
                        } else if lane == 3 {
                            Duration::from_secs(30)
                        } else {
                            Duration::from_millis(50)
                        })
                        .await;
                }
            });
        }
        set_reticulumd_inbound_worker_running(&state, true, interval);
        while let Some(result) = owners.join_next().await {
            if let Err(error) = result {
                record_reticulumd_inbound_worker_event_error(&state, error.to_string());
            }
        }
        set_reticulumd_inbound_worker_running(&state, false, interval);
    })
}

fn intake(state: &AppState, consumer: &str) -> Result<(), ApiError> {
    let _quiescence = state
        .broker_work_gate
        .read()
        .map_err(|e| ApiError::Internal(e.to_string()))?;
    ensure_kill_switch_persistence_unlocked(state)?;
    let mut store = open(state)?;
    let checkpoint = store.inbox_checkpoint(consumer).map_err(storage)?;
    let plane = plane(state)?;
    let remote = plane
        .broker_resume(broker::ResumeRequest {
            consumer_id: broker::ConsumerId(consumer.into()),
            identity: String::new(),
            journal_id: checkpoint.journal_id.map(broker::JournalId),
            stored: broker::EventPosition(checkpoint.stored),
        })
        .map_err(|e| ApiError::ServiceUnavailable(e.to_string()))?;
    if remote.stored.0 < checkpoint.stored {
        let (journal, end, receipt) = store
            .inbox_ack_receipt(consumer)
            .map_err(storage)?
            .ok_or_else(|| {
                ApiError::ServiceUnavailable(
                    "recovery required: stored inbox has no authenticated receipt".into(),
                )
            })?;
        plane
            .broker_ack_stored(broker::AckStoredRequest {
                consumer_id: broker::ConsumerId(consumer.into()),
                identity: String::new(),
                journal_id: broker::JournalId(journal),
                end: broker::EventPosition(end),
                receipt: broker::StoredReceipt(receipt),
            })
            .map_err(|e| ApiError::ServiceUnavailable(e.to_string()))?;
    }
    let batch = plane
        .broker_fetch(broker::FetchRequest {
            consumer_id: broker::ConsumerId(consumer.into()),
            identity: String::new(),
            max_events: 128,
            max_bytes: broker::MAX_BATCH_BYTES,
        })
        .map_err(|e| ApiError::ServiceUnavailable(e.to_string()))?;
    if batch.end == batch.start {
        record_reticulumd_inbound_worker_event_poll(state, 0, 0, 0, None, None, None);
        return Ok(());
    }
    let local = InboxBatch {
        journal_id: batch.journal_id.0.clone(),
        consumer_id: consumer.into(),
        start: batch.start.0,
        end: batch.end.0,
        receipt: batch.receipt.0.clone(),
        events: batch
            .events
            .into_iter()
            .map(|e| InboxEvent {
                version: e.version,
                position: e.position.0,
                created_at: e.created_at,
                event_type: e.event_type,
                payload: e.payload,
            })
            .collect(),
    };
    store.store_inbox_batch(&local).map_err(storage)?;
    plane
        .broker_ack_stored(broker::AckStoredRequest {
            consumer_id: batch.consumer_id,
            identity: String::new(),
            journal_id: batch.journal_id,
            end: batch.end,
            receipt: batch.receipt,
        })
        .map_err(|e| ApiError::ServiceUnavailable(e.to_string()))?;
    record_reticulumd_inbound_worker_event_poll(state, 0, 0, 0, None, None, None);
    Ok(())
}

fn announces(state: &AppState) -> Result<(), ApiError> {
    let _quiescence = state
        .broker_work_gate
        .read()
        .map_err(|e| ApiError::Internal(e.to_string()))?;
    ensure_kill_switch_persistence_unlocked(state)?;
    let result = plane(state)?
        .broker_announces()
        .map_err(|e| ApiError::ServiceUnavailable(e.to_string()))?;
    let records: Vec<ReticulumdAnnounceRecord> = serde_json::from_value(
        result
            .get("announces")
            .cloned()
            .ok_or_else(|| ApiError::Internal("SDK projection lacks announces".into()))?,
    )
    .map_err(|e| ApiError::Internal(e.to_string()))?;
    if records.len() > 32 {
        return Err(ApiError::ServiceUnavailable(
            "SDK announce projection exceeds count bound".into(),
        ));
    }
    import_reticulumd_announce_batch(state, &records, false)?;
    Ok(())
}

pub(super) fn diagnostics(state: &AppState) -> Result<Value, ApiError> {
    if state.sqlite_path.is_none() {
        return Ok(json!({"configured":false,"healthy":false}));
    }
    let errors = state
        .broker_lane_errors
        .read()
        .map_err(|e| ApiError::Internal(e.to_string()))?
        .clone();
    let mut store = open(state)?;
    let consumer = store.durable_consumer_id().map_err(storage)?;
    let checkpoint = store.inbox_checkpoint(&consumer).map_err(storage)?;
    let storage = store.durable_broker_diagnostics().map_err(storage)?;
    Ok(
        json!({"ack_meaning":"stored","checkpoint":checkpoint,"storage":storage,"lanes":["intake","application","dispatch","announces"],"errors":errors,"healthy":errors.iter().all(Option::is_none)}),
    )
}

pub(super) fn bound_presentation(messages: &mut Vec<OutboundMessageRecord>) {
    let size = super::message_residency::estimated_bytes;
    let mut bytes = messages
        .iter()
        .fold(0usize, |n, m| n.saturating_add(size(m)));
    let mut remove = 0;
    while messages.len() - remove > r3akt_rch_core::RECENT_MESSAGE_COUNT
        || bytes > r3akt_rch_core::RECENT_MESSAGE_BYTES
    {
        bytes = bytes.saturating_sub(size(&messages[remove]));
        remove += 1;
    }
    if remove > 0 {
        messages.drain(..remove);
    }
}

mod application;
mod chat_presentation;
mod envelope;
mod inbound_attachments;
mod outbound;
use application::apply;
use outbound::dispatch;
pub(super) use outbound::queue_northbound;

fn retry_delay(failures: u32) -> Duration {
    Duration::from_millis(500u64.saturating_mul(1u64 << failures.saturating_sub(1).min(6)))
        .min(Duration::from_secs(30))
}

/// Test seam: commits daemon message records to the local durable inbox the way
/// `intake` does, then runs the production ordered application until idle.
#[cfg(test)]
pub(crate) fn apply_inbound_messages_for_test(
    state: &AppState,
    messages: &[Value],
) -> Result<usize, ApiError> {
    let mut store = open(state)?;
    let consumer = store.durable_consumer_id().map_err(storage)?;
    let checkpoint = store.inbox_checkpoint(&consumer).map_err(storage)?;
    let start = checkpoint.stored;
    let end = start + messages.len() as u64;
    let created_at = unix_now_ms() / 1000;
    store
        .store_inbox_batch(&InboxBatch {
            journal_id: checkpoint
                .journal_id
                .unwrap_or_else(|| "test-journal".to_string()),
            consumer_id: consumer.clone(),
            start,
            end,
            receipt: format!("test-receipt-{end}"),
            events: messages
                .iter()
                .zip(start + 1..)
                .map(|(message, position)| InboxEvent {
                    version: 1,
                    position,
                    created_at,
                    event_type: "inbound".to_string(),
                    payload: json!({ "message": message }),
                })
                .collect(),
        })
        .map_err(storage)?;
    drop(store);
    let mut applied = 0;
    while apply(state, &consumer)? {
        applied += 1;
    }
    Ok(applied)
}

#[cfg(test)]
mod tests;

mod telemetry_collector;

#[cfg(test)]
mod telemetry_compatibility_tests;
