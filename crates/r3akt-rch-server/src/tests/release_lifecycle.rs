use crate::*;

#[cfg(unix)]
#[test]
fn poisoned_control_does_not_skip_owned_daemon_cleanup() {
    let state = AppState::default();
    let child = Command::new("sleep")
        .arg("60")
        .spawn()
        .expect("owned child");
    *state.managed_reticulumd_process.lock().expect("child lock") = Some(child);
    let poison = state.clone();
    assert!(
        std::thread::spawn(move || {
            let _guard = poison.runtime_control.write().expect("control lock");
            panic!("fixture poisons control");
        })
        .join()
        .is_err()
    );
    let result = shutdown_runtime_for_exit(&state);
    let cleaned = state
        .managed_reticulumd_process
        .lock()
        .expect("process")
        .is_none();
    // Clean up even when proving the old defective behavior.
    state.stop_managed_reticulumd().expect("fixture cleanup");
    assert!(result.is_err(), "control failure must remain observable");
    assert!(
        cleaned,
        "an unrelated cleanup failure must not leave the owned process running"
    );
}

#[tokio::test]
async fn terminal_exit_wakes_long_periodic_waits_and_late_workers() {
    let state = AppState::default();
    let announce = spawn_rch_identity_announce_worker(state.clone(), Duration::from_secs(3600));
    let sampler = spawn_local_telemetry_sampler_with_interval(
        state.clone(),
        "peer",
        Duration::from_secs(3600),
    );
    tokio::time::sleep(Duration::from_millis(10)).await;
    request_runtime_exit(&state);
    tokio::time::timeout(Duration::from_secs(1), announce)
        .await
        .expect("announce wakes")
        .expect("announce joins");
    tokio::time::timeout(Duration::from_secs(1), sampler)
        .await
        .expect("sampler wakes")
        .expect("sampler joins");
    let late =
        spawn_reticulumd_inbound_worker_with_interval(state.clone(), Duration::from_secs(3600));
    tokio::time::timeout(Duration::from_secs(1), late)
        .await
        .expect("late worker exits")
        .expect("late joins");
}

#[tokio::test]
async fn control_pause_does_not_terminate_periodic_announce_owner() {
    let state = AppState::default();
    state
        .runtime_control
        .write()
        .expect("control")
        .shutdown_requested = true;
    let worker = spawn_rch_identity_announce_worker(state.clone(), Duration::from_millis(10));
    tokio::time::sleep(Duration::from_millis(40)).await;
    assert!(
        !worker.is_finished(),
        "Control/Start needs the existing announce worker"
    );
    state
        .runtime_control
        .write()
        .expect("control")
        .shutdown_requested = false;
    request_runtime_exit(&state);
    worker.await.expect("announce join");
}

#[cfg(unix)]
#[test]
fn sdk_shutdown_failure_does_not_skip_owned_daemon_cleanup() {
    let mut state = AppState::default();
    let sdk = ZmqDataPlane::new_with_timeout(
        "tcp://127.0.0.1:19997",
        "tcp://127.0.0.1:19998",
        Duration::from_millis(30),
    )
    .expect("SDK actor");
    sdk.shutdown().expect("first SDK shutdown");
    state.lxmf_zmq_data_plane = Some(Arc::new(sdk));
    *state.managed_reticulumd_process.lock().expect("process") = Some(
        Command::new("sleep")
            .arg("60")
            .spawn()
            .expect("owned child"),
    );
    let result = shutdown_runtime_for_exit(&state);
    let cleaned = state
        .managed_reticulumd_process
        .lock()
        .expect("process")
        .is_none();
    state.stop_managed_reticulumd().expect("fixture cleanup");
    assert!(
        result
            .expect_err("SDK failure is reported")
            .contains("LXMF SDK")
    );
    assert!(cleaned);
}
