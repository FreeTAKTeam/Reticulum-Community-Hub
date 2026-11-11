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

#[test]
#[ignore = "waits for the paired daemon's five-minute broker session lifetime"]
fn paired_rch_actor_recovers_expired_session_and_durable_custody() {
    let dir = std::env::temp_dir().join(format!("rch-session-expiry-{}", Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    let mut fixture = Fixture::open(&dir.join("daemon.db"));
    let identity = dir.join("identity");
    let restart_db = dir.join("restart.db");
    for _ in 0..3 {
        let restarted = fixture.state(&restart_db, &identity);
        plane(&restarted).unwrap().shutdown().unwrap();
    }

    let idle = fixture.state(&dir.join("idle.db"), &identity);
    fixture.response = endpoint();
    let active = fixture.state(&dir.join("active.db"), &identity);
    let consumer = open(&idle).unwrap().durable_consumer_id().unwrap();
    let destination = idle.reticulumd_source.as_deref().unwrap();
    fixture.inbound("before-session-expiry", destination);
    intake(&idle, &consumer).unwrap();
    assert!(apply(&idle, &consumer).unwrap());
    let before = open(&idle).unwrap().inbox_checkpoint(&consumer).unwrap();
    assert_eq!(before.stored, 1);
    assert_eq!(before.applied, 1);

    let sessions =
        || fixture.daemon.resource_usage_snapshot().unwrap()["durable_broker_sessions"].clone();
    assert_eq!(sessions()["current"], 5);
    assert_eq!(sessions()["expired_total"], 0);

    let active_plane = plane(&active).unwrap();
    for _ in 0..10 {
        std::thread::sleep(Duration::from_secs(30));
        active_plane.broker_announces().unwrap();
    }
    fixture.inbound("after-session-expiry", destination);
    let expired = intake(&idle, &consumer).unwrap_err();
    assert!(matches!(
        expired,
        ApiError::ServiceUnavailable(message) if message.contains("SDK_BROKER_NEGOTIATION_REQUIRED")
    ));
    assert_eq!(sessions()["current"], 1);
    assert_eq!(sessions()["expired_total"], 4);
    active_plane.broker_announces().unwrap();

    // The normal worker must recover using the same actor and local checkpoint.
    tokio::runtime::Builder::new_multi_thread()
        .worker_threads(2)
        .enable_all()
        .build()
        .unwrap()
        .block_on(async {
            let owner = spawn(idle.clone(), Duration::from_millis(50));
            let recovered = tokio::time::timeout(Duration::from_secs(8), async {
                loop {
                    let checkpoint = open(&idle).unwrap().inbox_checkpoint(&consumer).unwrap();
                    let healthy = idle
                        .broker_lane_errors
                        .read()
                        .unwrap()
                        .iter()
                        .all(Option::is_none);
                    if checkpoint.applied == 2 && healthy {
                        break;
                    }
                    tokio::time::sleep(Duration::from_millis(20)).await;
                }
            })
            .await;
            request_runtime_exit(&idle);
            tokio::time::timeout(Duration::from_secs(3), owner)
                .await
                .unwrap()
                .unwrap();
            recovered.expect("normal worker must resume custody after actor restoration");
        });
    let after = open(&idle).unwrap().inbox_checkpoint(&consumer).unwrap();
    assert_eq!(after.journal_id, before.journal_id);
    assert_eq!(after.stored, 2);
    assert_eq!(after.applied, 2);
    let remote = plane(&idle)
        .unwrap()
        .broker_resume(broker::ResumeRequest {
            consumer_id: broker::ConsumerId(consumer),
            identity: String::new(),
            journal_id: after.journal_id.map(broker::JournalId),
            stored: broker::EventPosition(after.stored),
        })
        .unwrap();
    assert_eq!(remote.stored.0, after.stored);
    assert_eq!(idle.messages.read().unwrap().len(), 2);
    assert_eq!(sessions()["current"], 2);
    assert_eq!(sessions()["expired_total"], 4);

    plane(&idle).unwrap().shutdown().unwrap();
    active_plane.shutdown().unwrap();
    drop(idle);
    drop(active);
    drop(fixture);
    std::fs::remove_dir_all(dir).unwrap();
}
