//! Presentation budgeting and durable history; active delivery stays in the broker ledger.
use super::{
    ApiError, AppState, ChatAttachmentRecord, Duration, Instant, Ordering, OutboundMessageRecord,
    RchSqliteStore, Value, json,
};

pub(super) fn estimated_bytes(message: &OutboundMessageRecord) -> usize {
    let mut bytes = [
        &message.message_id,
        &message.sender,
        &message.content,
        &message.delivery_method,
        &message.delivery_policy_reason,
        &message.delivery_state,
    ]
    .iter()
    .fold(4096_usize, |bytes, text| {
        bytes.saturating_add(text.capacity())
    });
    for text in [&message.topic_id, &message.destination]
        .into_iter()
        .flatten()
    {
        bytes = bytes.saturating_add(text.capacity());
    }
    bytes = bytes.saturating_add(r3akt_rch_core::json_resident_bytes(
        &message.delivery_metadata,
    ));
    bytes = bytes.saturating_add(
        message
            .attachments
            .capacity()
            .saturating_mul(std::mem::size_of::<ChatAttachmentRecord>()),
    );
    for item in &message.attachments {
        bytes = bytes
            .saturating_add(item.category.capacity())
            .saturating_add(item.name.capacity())
            .saturating_add(item.media_type.as_ref().map_or(0, String::capacity));
    }
    bytes
}

pub(super) fn record_command(state: &AppState, delta: &r3akt_rch_core::CommandDelta) {
    let metrics = &state.runtime_metrics;
    metrics.command_rows_read.fetch_add(
        u64::try_from(delta.rows_read).unwrap_or(u64::MAX),
        Ordering::Relaxed,
    );
    metrics.command_payload_bytes.fetch_add(
        u64::try_from(delta.payload_bytes_read).unwrap_or(u64::MAX),
        Ordering::Relaxed,
    );
    metrics
        .command_rows_written
        .fetch_add(delta.rows_written, Ordering::Relaxed);
    metrics
        .command_duration_us
        .fetch_add(delta.duration_us, Ordering::Relaxed);
}

pub(super) fn diagnostics(state: &AppState) -> Result<Value, ApiError> {
    let mut messages = state
        .messages
        .write()
        .map_err(|e| ApiError::Internal(e.to_string()))?;
    bound(state, &mut messages, &[])?;
    let resident_bytes = messages.iter().fold(0_usize, |bytes, message| {
        bytes.saturating_add(estimated_bytes(message))
    });
    let resident_count = messages.len();
    drop(messages);
    let durable = state
        .sqlite_path
        .as_ref()
        .map(|path| {
            RchSqliteStore::open_read_only(path.as_ref())
                .and_then(|store| store.message_history_counts())
        })
        .transpose()
        .map_err(|e| ApiError::Internal(e.to_string()))?;
    let metrics = &state.runtime_metrics;
    Ok(
        json!({"resident_count":resident_count,"estimated_resident_bytes":resident_bytes,"max_idle_ms":r3akt_rch_core::RECENT_MESSAGE_IDLE_MS,"max_count":r3akt_rch_core::RECENT_MESSAGE_COUNT,"max_estimated_bytes":r3akt_rch_core::RECENT_MESSAGE_BYTES,"history_count":durable.as_ref().map(|v|v.0),"active_delivery_count":durable.as_ref().map(|v|v.1),"hydrations_total":metrics.message_hydrations.load(Ordering::Relaxed),"evictions_total":metrics.message_evictions.load(Ordering::Relaxed),"command_rows_read_total":metrics.command_rows_read.load(Ordering::Relaxed),"command_payload_bytes_read_total":metrics.command_payload_bytes.load(Ordering::Relaxed),"command_rows_written_total":metrics.command_rows_written.load(Ordering::Relaxed),"command_duration_us_total":metrics.command_duration_us.load(Ordering::Relaxed)}),
    )
}

pub(super) fn bound(
    state: &AppState,
    messages: &mut Vec<OutboundMessageRecord>,
    touched: &[&str],
) -> Result<(), ApiError> {
    bound_at(state, messages, touched, Instant::now())
}

pub(super) fn bound_at(
    state: &AppState,
    messages: &mut Vec<OutboundMessageRecord>,
    touched: &[&str],
    now: Instant,
) -> Result<(), ApiError> {
    let before = messages.len();
    let mut activity = state
        .message_cache_activity
        .write()
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    let hydrated = messages
        .iter()
        .filter(|message| !activity.contains_key(&message.message_id))
        .count();
    state.runtime_metrics.message_hydrations.fetch_add(
        u64::try_from(hydrated).unwrap_or(u64::MAX),
        Ordering::Relaxed,
    );
    for id in touched {
        activity.insert((*id).to_string(), now);
    }
    let idle = Duration::from_millis(r3akt_rch_core::RECENT_MESSAGE_IDLE_MS as u64);
    messages.retain(|message| {
        let last = activity.entry(message.message_id.clone()).or_insert(now);
        now.saturating_duration_since(*last) < idle
    });
    super::durable_broker::bound_presentation(messages);
    let retained = messages
        .iter()
        .map(|message| message.message_id.as_str())
        .collect::<std::collections::HashSet<_>>();
    activity.retain(|id, _| retained.contains(id.as_str()));
    state.runtime_metrics.message_evictions.fetch_add(
        u64::try_from(before - messages.len()).unwrap_or(u64::MAX),
        Ordering::Relaxed,
    );
    Ok(())
}

/// Owned alongside transport workers and joined by the existing shutdown path.
pub fn spawn_message_cache_maintenance(state: AppState) -> tokio::task::JoinHandle<()> {
    tokio::spawn(async move {
        while !state.runtime_exit.is_requested() {
            if let Err(error) = (|| {
                let mut messages = state
                    .messages
                    .write()
                    .map_err(|error| ApiError::Internal(error.to_string()))?;
                bound(&state, &mut messages, &[])
            })() {
                eprintln!("message cache maintenance failed: {error}");
            }
            state.runtime_exit.sleep(Duration::from_secs(30)).await;
        }
    })
}
