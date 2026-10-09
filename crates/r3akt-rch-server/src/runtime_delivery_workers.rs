#[cfg(test)]
use super::{
    ApiError, Arc, OUTBOUND_RETRY_WORKER_POLL_MS, OUTBOUND_RETRY_WORKER_TICK_TIMEOUT_MS,
    OutboundRetryWorkerReport, process_outbound_delivery_worker_tick,
    record_outbound_retry_worker_report, runtime_shutdown_requested,
    set_outbound_retry_worker_running,
};

#[cfg(test)]
pub fn spawn_outbound_delivery_worker(state: AppState) -> tokio::task::JoinHandle<()> {
    spawn_outbound_delivery_worker_with_interval(
        state,
        Duration::from_millis(OUTBOUND_RETRY_WORKER_POLL_MS),
    )
}

#[cfg(test)]
pub fn spawn_outbound_delivery_worker_with_interval(
    state: AppState,
    poll_interval: Duration,
) -> tokio::task::JoinHandle<()> {
    spawn_outbound_with_tick(
        state,
        poll_interval,
        Duration::from_millis(OUTBOUND_RETRY_WORKER_TICK_TIMEOUT_MS),
        process_outbound_delivery_worker_tick,
    )
}

#[cfg(test)]
pub(super) fn spawn_outbound_with_tick<F>(
    state: AppState,
    poll_interval: Duration,
    tick_timeout: Duration,
    tick: F,
) -> tokio::task::JoinHandle<()>
where
    F: Fn(&AppState) -> Result<OutboundRetryWorkerReport, ApiError> + Send + Sync + 'static,
{
    let tick = Arc::new(tick);
    tokio::spawn(async move {
        let poll_interval = poll_interval.max(Duration::from_millis(10));
        set_outbound_retry_worker_running(&state, false, poll_interval);
        loop {
            if state.runtime_exit.is_requested() {
                break;
            }
            if runtime_shutdown_requested(&state) {
                set_outbound_retry_worker_running(&state, false, poll_interval);
                state.runtime_exit.sleep(poll_interval).await;
                continue;
            }
            set_outbound_retry_worker_running(&state, true, poll_interval);
            let worker_state = state.clone();
            let tick = Arc::clone(&tick);
            let mut worker_task = tokio::task::spawn_blocking(move || tick(&worker_state));
            // A timeout does not cancel spawn_blocking. Retain and join the same
            // task before another tick or SDK/daemon cleanup can begin.
            let outcome = if let Ok(result) =
                tokio::time::timeout(tick_timeout, &mut worker_task).await
            {
                result
            } else {
                record_outbound_retry_worker_report(
                    &state,
                    OutboundRetryWorkerReport::default(),
                    Some(
                        "outbound retry worker tick timed out; waiting for active work".to_string(),
                    ),
                );
                worker_task.await
            };
            match outcome {
                Ok(Ok(_report)) => {}
                Ok(Err(error)) => record_outbound_retry_worker_report(
                    &state,
                    OutboundRetryWorkerReport::default(),
                    Some(error.to_string()),
                ),
                Err(error) => record_outbound_retry_worker_report(
                    &state,
                    OutboundRetryWorkerReport::default(),
                    Some(error.to_string()),
                ),
            }
            state.runtime_exit.sleep(poll_interval).await;
        }
        set_outbound_retry_worker_running(&state, false, poll_interval);
    })
}

use super::{AppState, Duration, RETICULUMD_INBOUND_WORKER_POLL_MS};

pub fn spawn_reticulumd_inbound_worker(state: AppState) -> tokio::task::JoinHandle<()> {
    spawn_reticulumd_inbound_worker_with_interval(
        state,
        Duration::from_millis(RETICULUMD_INBOUND_WORKER_POLL_MS),
    )
}

pub fn spawn_reticulumd_inbound_worker_with_interval(
    state: AppState,
    poll_interval: Duration,
) -> tokio::task::JoinHandle<()> {
    super::durable_broker::spawn(state, poll_interval)
}
