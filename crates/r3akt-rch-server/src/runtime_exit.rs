use super::{
    AppState, Duration, OUTBOUND_RETRY_WORKER_POLL_MS, Ordering, RETICULUMD_INBOUND_WORKER_POLL_MS,
    set_outbound_retry_worker_running, set_reticulumd_inbound_worker_running, unix_now_ms,
};
use std::sync::atomic::AtomicBool;

/// Process exit is irreversible. `/Control/Stop` is a resumable pause and has
/// its own existing control state; it must never terminate worker ownership.
#[derive(Default)]
pub(super) struct RuntimeExit {
    requested: AtomicBool,
    wake: tokio::sync::Notify,
}

impl RuntimeExit {
    pub(super) fn is_requested(&self) -> bool {
        self.requested.load(Ordering::Acquire)
    }

    fn request(&self) {
        self.requested.store(true, Ordering::Release);
        self.wake.notify_waiters();
    }

    /// Register before observing the flag so a concurrent exit cannot leave a
    /// worker asleep for a long announce interval. Notify is only a wakeup;
    /// the atomic flag owns the persistent decision, including late workers.
    pub(super) async fn until(&self, ready: impl std::future::Future) -> bool {
        let exiting = self.wake.notified();
        if self.is_requested() {
            return false;
        }
        tokio::select! {
            biased;
            () = exiting => false,
            _ = ready => !self.is_requested(),
        }
    }

    pub(super) async fn sleep(&self, duration: Duration) -> bool {
        self.until(tokio::time::sleep(duration)).await
    }
}

/// Wake workers and prevent new delivery work. The runtime owner then joins
/// them before releasing the SDK and managed daemon with the cleanup function.
pub fn request_runtime_exit(state: &AppState) {
    state.runtime_exit.request();
}

/// The caller must first request exit and join workers. Attempt every owned
/// cleanup even when another step failed, and report all failures together.
pub fn shutdown_runtime_for_exit(state: &AppState) -> Result<(), String> {
    request_runtime_exit(state);
    let mut errors = Vec::new();
    match state.runtime_control.write() {
        Ok(mut control) => {
            control.status = "stopping".to_string();
            control.shutdown_requested = true;
            control.last_stop_ts_ms = Some(unix_now_ms());
        }
        Err(error) => errors.push(format!("runtime control: {error}")),
    }
    set_outbound_retry_worker_running(
        state,
        false,
        Duration::from_millis(OUTBOUND_RETRY_WORKER_POLL_MS),
    );
    set_reticulumd_inbound_worker_running(
        state,
        false,
        Duration::from_millis(RETICULUMD_INBOUND_WORKER_POLL_MS),
    );
    if let Some(data_plane) = &state.lxmf_zmq_data_plane {
        if let Err(error) = data_plane.shutdown() {
            errors.push(format!("LXMF SDK: {error}"));
        }
    }
    if let Err(error) = state.stop_managed_reticulumd() {
        errors.push(format!("managed reticulumd: {error}"));
    }
    if errors.is_empty() {
        Ok(())
    } else {
        Err(errors.join("; "))
    }
}
