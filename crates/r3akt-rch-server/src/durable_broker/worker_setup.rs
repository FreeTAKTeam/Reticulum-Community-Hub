//! Keep worker ownership across transient storage outages without publishing partial setup.
use super::{
    ApiError, AppState, Duration, ensure_kill_switch_persistence_unlocked, open,
    persistence_locked_for_purge, plane, record_reticulumd_inbound_worker_event_error, retry_delay,
    set_reticulumd_inbound_worker_running, storage,
};

pub(super) async fn prepare(state: &AppState, interval: Duration) -> Option<String> {
    set_reticulumd_inbound_worker_running(state, false, interval);
    // These requirements cannot recover without a new AppState. Preserve the
    // existing unconfigured-worker behavior rather than retrying configuration.
    let configured = (|| {
        if state.sqlite_path.is_none() {
            return Err(ApiError::ServiceUnavailable(
                "durable broker requires SQLite".into(),
            ));
        }
        if state.broker_consumer_lease.is_none() {
            return Err(ApiError::ServiceUnavailable(
                "durable consumer ownership was not acquired at startup".into(),
            ));
        }
        plane(state).map(|_| ())
    })();
    if let Err(error) = configured {
        report_failure(state, error.to_string());
        return None;
    }
    let mut failures = 0u32;
    while !state.runtime_exit.is_requested() {
        // Purge owns the gate and must never be undone by a recovering opener.
        if persistence_locked_for_purge(state) {
            state.runtime_exit.sleep(retry_delay(1)).await;
            continue;
        }
        let setup_state = state.clone();
        // Await completion even during exit: never detach an opener or its DB writes.
        let error = match tokio::task::spawn_blocking(move || open_stores(&setup_state)).await {
            Ok(Ok(consumer)) => {
                set_lane_error(state, None);
                return Some(consumer);
            }
            Ok(Err(error)) => error.to_string(),
            Err(error) => error.to_string(),
        };
        failures = failures.saturating_add(1);
        report_failure(state, error);
        state.runtime_exit.sleep(retry_delay(failures)).await;
    }
    None
}

fn report_failure(state: &AppState, error: String) {
    let error = format!("durable broker worker setup failed: {error}");
    record_reticulumd_inbound_worker_event_error(state, error.clone());
    set_lane_error(state, Some(error));
}

fn set_lane_error(state: &AppState, error: Option<String>) {
    match state.broker_lane_errors.write() {
        Ok(mut errors) => errors[0] = error,
        Err(error) => eprintln!("broker setup error state poisoned: {error}"),
    }
}

pub(super) fn open_stores(state: &AppState) -> Result<String, ApiError> {
    let _quiescence = state
        .broker_work_gate
        .read()
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    ensure_kill_switch_persistence_unlocked(state)?;
    // Acquire and validate every slot before opening or publishing any store.
    // A later lock/ownership failure must not strand earlier slots on retries.
    let mut slots = state
        .durable_broker_worker_stores
        .iter()
        .map(|slot| {
            slot.lock()
                .map_err(|error| ApiError::Internal(error.to_string()))
        })
        .collect::<Result<Vec<_>, _>>()?;
    if slots.iter().any(|slot| slot.is_some()) {
        return Err(ApiError::Internal(
            "durable broker worker stores already have an owner".into(),
        ));
    }
    let mut stores = Vec::with_capacity(slots.len());
    for _ in 0..slots.len() {
        stores.push(open(state)?);
    }
    let consumer = stores[0].durable_consumer_id().map_err(storage)?;
    for (slot, store) in slots.iter_mut().zip(stores) {
        **slot = Some(store);
    }
    Ok(consumer)
}
