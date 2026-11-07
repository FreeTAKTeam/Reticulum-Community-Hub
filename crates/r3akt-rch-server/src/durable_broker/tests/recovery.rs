use super::*;

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn worker_setup_recovers_storage_and_imports_without_server_restart() {
    let dir = std::env::temp_dir().join(format!("rch-setup-recovery-{}", Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    let fixture = Fixture::open(&dir.join("daemon.db"));
    let path = dir.join("rch.db");
    let saved = dir.join("saved-rch.db");
    let state = fixture.state(&path, &dir.join("identity"));
    let consumer = open(&state).unwrap().durable_consumer_id().unwrap();
    fixture.inbound(
        "after-storage-recovery",
        state.reticulumd_source.as_deref().unwrap(),
    );

    // Keep the real consumer/identity state, but make the database temporarily
    // unavailable to the worker's first open. The owner lease is a separate file.
    std::fs::rename(&path, &saved).unwrap();
    std::fs::create_dir(&path).unwrap();
    let owner = spawn(state.clone(), Duration::from_millis(50));
    tokio::time::timeout(Duration::from_secs(3), async {
        loop {
            if state
                .reticulumd_inbound_worker_stats
                .read()
                .unwrap()
                .error_total
                > 0
            {
                break;
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .expect("setup failure must be visible");
    let stayed_alive = !owner.is_finished();
    std::fs::remove_dir(&path).unwrap();
    std::fs::rename(&saved, &path).unwrap();

    let recovered = tokio::time::timeout(Duration::from_secs(8), async {
        loop {
            if open(&state)
                .unwrap()
                .inbox_checkpoint(&consumer)
                .unwrap()
                .applied
                == 1
            {
                break;
            }
            tokio::time::sleep(Duration::from_millis(20)).await;
        }
    })
    .await;
    request_runtime_exit(&state);
    tokio::time::timeout(Duration::from_secs(3), owner)
        .await
        .unwrap()
        .unwrap();
    plane(&state).unwrap().shutdown().unwrap();
    assert!(
        stayed_alive,
        "a transient setup failure must retain worker ownership"
    );
    recovered.expect("restored storage must resume real ZeroMQ intake and application");
    assert_eq!(state.messages.read().unwrap().len(), 1);
    let stats = state.reticulumd_inbound_worker_stats.read().unwrap();
    assert_eq!(stats.received_total, 1);
    assert!(stats.last_error.is_none(), "{:?}", stats.last_error);
    drop(stats);
    assert!(
        state
            .broker_lane_errors
            .read()
            .unwrap()
            .iter()
            .all(Option::is_none)
    );
    assert!(
        state
            .durable_broker_worker_stores
            .iter()
            .all(|slot| slot.lock().unwrap().is_none())
    );
    drop(state);
    drop(fixture);
    std::fs::remove_dir_all(dir).unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn terminal_exit_interrupts_worker_setup_retry_without_leaking_stores() {
    let dir = std::env::temp_dir().join(format!("rch-setup-exit-{}", Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    let fixture = Fixture::open(&dir.join("daemon.db"));
    let path = dir.join("rch.db");
    let state = fixture.state(&path, &dir.join("identity"));
    let saved = dir.join("saved-rch.db");
    std::fs::rename(&path, &saved).unwrap();
    std::fs::create_dir(&path).unwrap();
    let owner = spawn(state.clone(), Duration::from_millis(50));
    tokio::time::timeout(Duration::from_secs(4), async {
        loop {
            if state
                .reticulumd_inbound_worker_stats
                .read()
                .unwrap()
                .error_total
                >= 2
            {
                break;
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .expect("setup must retry visibly with backoff");
    request_runtime_exit(&state);
    // The second retry sleeps for a second; exit must wake it rather than wait.
    tokio::time::timeout(Duration::from_millis(500), owner)
        .await
        .unwrap()
        .unwrap();
    assert!(
        !state
            .reticulumd_inbound_worker_stats
            .read()
            .unwrap()
            .running
    );
    assert!(state.broker_lane_errors.read().unwrap()[0].is_some());
    assert!(
        state
            .durable_broker_worker_stores
            .iter()
            .all(|slot| slot.lock().unwrap().is_none())
    );
    std::fs::remove_dir(&path).unwrap();
    std::fs::rename(&saved, &path).unwrap();
    plane(&state).unwrap().shutdown().unwrap();
    drop(state);
    drop(fixture);
    std::fs::remove_dir_all(dir).unwrap();
}

#[test]
fn failed_setup_never_partially_publishes_or_replaces_another_owners_stores() {
    let dir = std::env::temp_dir().join(format!("rch-setup-atomic-{}", Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    let state = AppState::from_sqlite_path(dir.join("rch.db")).unwrap();
    *state.durable_broker_worker_stores[2].lock().unwrap() = Some(open(&state).unwrap());
    let opens = store_open_count(&dir.join("rch.db"));
    assert!(worker_setup::open_stores(&state).is_err());
    assert_eq!(store_open_count(&dir.join("rch.db")), opens);
    assert!(
        state.durable_broker_worker_stores[..2]
            .iter()
            .all(|slot| slot.lock().unwrap().is_none())
    );
    assert!(
        state.durable_broker_worker_stores[2]
            .lock()
            .unwrap()
            .is_some()
    );
    close_worker_stores(&state).unwrap();
    drop(state);
    std::fs::remove_dir_all(dir).unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn initialized_workers_resume_after_sqlite_writer_contention() {
    let dir = std::env::temp_dir().join(format!("rch-runtime-recovery-{}", Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    let fixture = Fixture::open(&dir.join("daemon.db"));
    let path = dir.join("rch.db");
    let state = fixture.state(&path, &dir.join("identity"));
    let owner = spawn(state.clone(), Duration::from_millis(50));
    tokio::time::timeout(Duration::from_secs(5), async {
        while state
            .reticulumd_inbound_worker_stats
            .read()
            .unwrap()
            .event_polls_total
            < 2
        {
            tokio::time::sleep(Duration::from_millis(20)).await;
        }
    })
    .await
    .unwrap();
    let writer = rusqlite::Connection::open(&path).unwrap();
    writer.execute_batch("BEGIN IMMEDIATE;").unwrap();
    fixture.inbound(
        "during-contention",
        state.reticulumd_source.as_deref().unwrap(),
    );
    let stalled = tokio::time::timeout(Duration::from_secs(5), async {
        while state
            .reticulumd_inbound_worker_stats
            .read()
            .unwrap()
            .event_poll_errors_total
            == 0
        {
            tokio::time::sleep(Duration::from_millis(20)).await;
        }
    })
    .await;
    // The independent daemon control operation remains usable while RCH retries
    // its busy local store; it must retain the registered service identity.
    let announced = plane(&state).unwrap().announce_identity();
    writer.execute_batch("ROLLBACK;").unwrap();
    drop(writer);
    fixture.inbound(
        "after-contention",
        state.reticulumd_source.as_deref().unwrap(),
    );
    let recovered = tokio::time::timeout(Duration::from_secs(8), async {
        while state
            .reticulumd_inbound_worker_stats
            .read()
            .unwrap()
            .received_total
            < 2
        {
            tokio::time::sleep(Duration::from_millis(20)).await;
        }
    })
    .await;
    request_runtime_exit(&state);
    tokio::time::timeout(Duration::from_secs(3), owner)
        .await
        .unwrap()
        .unwrap();
    plane(&state).unwrap().shutdown().unwrap();
    stalled.expect("busy writer must exercise the initialized worker error path");
    announced.expect("registered announce remains available during local contention");
    recovered.expect("same worker must import both real broker inputs after writer release");
    assert_eq!(state.messages.read().unwrap().len(), 2);
    assert!(
        state
            .reticulumd_inbound_worker_stats
            .read()
            .unwrap()
            .last_error
            .is_none()
    );
    assert!(
        state
            .broker_lane_errors
            .read()
            .unwrap()
            .iter()
            .all(Option::is_none)
    );
    drop(state);
    drop(fixture);
    std::fs::remove_dir_all(dir).unwrap();
}
