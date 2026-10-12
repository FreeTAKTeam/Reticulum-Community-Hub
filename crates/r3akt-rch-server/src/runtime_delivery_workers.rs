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
