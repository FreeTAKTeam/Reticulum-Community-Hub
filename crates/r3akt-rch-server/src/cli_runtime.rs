use r3akt_rch_server::{AppState, request_runtime_exit, shutdown_runtime_for_exit};
use tokio::task::JoinHandle;

pub(super) fn cleanup_after_startup_failure(state: &AppState, phase: &str) {
    if let Err(error) = shutdown_runtime_for_exit(state) {
        eprintln!("runtime cleanup after {phase} failure: {error}");
    }
}

/// Drain the CLI's owned workers before releasing the SDK and managed daemon.
pub(super) async fn finish(
    state: &AppState,
    workers: [(&str, JoinHandle<()>); 3],
) -> Result<(), String> {
    // Also covers a serve failure without a shutdown signal. Each worker retains
    // its active blocking job until this join completes.
    request_runtime_exit(state);
    let mut errors = Vec::new();
    for (name, worker) in workers {
        if let Err(error) = worker.await {
            errors.push(format!("{name} worker join: {error}"));
        }
    }
    if let Err(error) = shutdown_runtime_for_exit(state) {
        errors.push(error);
    }
    if errors.is_empty() {
        Ok(())
    } else {
        Err(errors.join("; "))
    }
}
