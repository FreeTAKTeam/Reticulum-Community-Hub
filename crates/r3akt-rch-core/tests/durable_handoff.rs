use r3akt_rch_core::*;
use serde_json::json;
fn db() -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("rch-inbox-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    dir.join("rch.db")
}
fn batch() -> InboxBatch {
    InboxBatch {
        journal_id: "journal-one".into(),
        consumer_id: "rch".into(),
        start: 0,
        end: 2,
        receipt: "authenticated-range".into(),
        events: vec![InboxEvent {
            version: 1,
            position: 1,
            created_at: 100,
            event_type: "inbound".into(),
            payload: json!({"content":"Test1234"}),
        }],
    }
}
fn intent() -> DurableOutboundIntent {
    DurableOutboundIntent {
        operation_id: "reply-operation".into(),
        message: MessageRecord {
            message_id: "reply-operation".into(),
            topic_id: None,
            destination: Some("sender".into()),
            sender: "rch".into(),
            content: "Test1234".into(),
            delivery_mode: DeliveryMode::Targeted,
            delivery_method: "durable_broker".into(),
            delivery_policy_reason: "reply".into(),
            delivery_state: "broker_pending".into(),
            delivery_metadata: json!({}),
            created_ts_ms: 100,
            attachments: vec![],
        },
        request: json!({"content":"Test1234"}),
    }
}
#[test]
fn inbox_commit_precedes_business_and_outbox_commits_atomically() {
    let path = db();
    let mut store = RchSqliteStore::open(&path).unwrap();
    let batch = batch();
    store.store_inbox_batch(&batch).unwrap();
    assert_eq!(store.inbox_checkpoint("rch").unwrap().stored, 2);
    assert_eq!(store.inbox_checkpoint("rch").unwrap().applied, 0);
    let event = store.next_inbox_event("rch").unwrap().unwrap();
    {
        let mut unit = store.begin_inbox_application("rch", &event, false).unwrap();
        unit.stage_client(&ClientRecord {
            identity: "sender".into(),
            first_seen_ts_ms: 1,
            last_seen_ts_ms: 1,
            nickname: None,
            role: "member".into(),
            paused: false,
            text_only: false,
            last_chat_ts_ms: None,
        })
        .unwrap();
        unit.stage_outbound_intent(&intent()).unwrap();
    }
    drop(store);
    let mut store = RchSqliteStore::open(&path).unwrap();
    assert!(store.pending_broker_intent().unwrap().is_none());
    assert!(store.load_r3akt_read_snapshot().unwrap().clients.is_empty());
    assert_eq!(store.inbox_checkpoint("rch").unwrap().applied, 0);
    let conn = rusqlite::Connection::open(&path).unwrap();
    conn.execute_batch("CREATE TRIGGER crash_at_marker BEFORE UPDATE OF status ON rch_broker_inbox BEGIN SELECT RAISE(ABORT,'injected marker failure');END;").unwrap();
    {
        let mut unit = store.begin_inbox_application("rch", &event, false).unwrap();
        unit.stage_client(&ClientRecord {
            identity: "sender".into(),
            first_seen_ts_ms: 1,
            last_seen_ts_ms: 1,
            nickname: None,
            role: "member".into(),
            paused: false,
            text_only: false,
            last_chat_ts_ms: None,
        })
        .unwrap();
        unit.stage_outbound_intent(&intent()).unwrap();
        assert!(unit.commit().is_err());
    }
    assert!(store.pending_broker_intent().unwrap().is_none());
    assert!(store.load_r3akt_read_snapshot().unwrap().clients.is_empty());
    conn.execute_batch("DROP TRIGGER crash_at_marker").unwrap();
    let mut unit = store.begin_inbox_application("rch", &event, false).unwrap();
    assert!(
        unit.claim_logical_input("sender", "message-one", &json!({"text":"Test1234"}))
            .unwrap()
    );
    unit.stage_client(&ClientRecord {
        identity: "sender".into(),
        first_seen_ts_ms: 1,
        last_seen_ts_ms: 1,
        nickname: None,
        role: "member".into(),
        paused: false,
        text_only: false,
        last_chat_ts_ms: None,
    })
    .unwrap();
    unit.stage_outbound_intent(&intent()).unwrap();
    unit.commit().unwrap();
    assert_eq!(store.inbox_checkpoint("rch").unwrap().applied, 2);
    assert!(store.next_inbox_event("rch").unwrap().is_none());
    assert_eq!(
        store
            .pending_broker_intent()
            .unwrap()
            .unwrap()
            .message
            .content,
        "Test1234"
    );
    assert_eq!(store.load_r3akt_read_snapshot().unwrap().clients.len(), 1);
    store.store_inbox_batch(&batch).unwrap();
    assert!(store.next_inbox_event("rch").unwrap().is_none());
    let mut conflicting = batch.clone();
    conflicting.events[0].payload = json!({"content":"changed"});
    assert!(store.store_inbox_batch(&conflicting).is_err());
    let connection = rusqlite::Connection::open(&path).unwrap();
    assert_eq!(
        connection
            .query_row("SELECT sqlite_version()", [], |r| r.get::<_, String>(0))
            .unwrap(),
        "3.53.2"
    );
    assert_eq!(
        store.inbox_ack_receipt("rch").unwrap().unwrap().2,
        "authenticated-range"
    );
}
#[test]
fn exclusive_process_lease_and_consumer_binding_fail_closed() {
    let path = db();
    let _lease = RchConsumerLease::acquire(&path).unwrap();
    assert!(RchConsumerLease::acquire(&path).is_err());
    let mut store = RchSqliteStore::open(&path).unwrap();
    let id = store.durable_consumer_id().unwrap();
    assert_eq!(store.durable_consumer_id().unwrap(), id);
    store.store_inbox_batch(&batch()).unwrap();
    let mut other = batch();
    other.consumer_id = "other-installation".into();
    assert!(store.store_inbox_batch(&other).is_err());
}
#[test]
fn rejected_input_keeps_bytes_and_unknown_status_cannot_be_skipped() {
    let path = db();
    let mut store = RchSqliteStore::open(&path).unwrap();
    store.store_inbox_batch(&batch()).unwrap();
    let event = store.next_inbox_event("rch").unwrap().unwrap();
    let conn = rusqlite::Connection::open(&path).unwrap();
    conn.execute("UPDATE rch_broker_inbox SET status='upgrade_required'", [])
        .unwrap();
    assert!(store.begin_inbox_application("rch", &event, false).is_err());
    assert_eq!(store.next_inbox_event("rch").unwrap().unwrap().position, 1);
    conn.execute("UPDATE rch_broker_inbox SET status='stored'", [])
        .unwrap();
    let mut unit = store.begin_inbox_application("rch", &event, false).unwrap();
    unit.reject("malformed supported input").unwrap();
    unit.commit().unwrap();
    assert_eq!(store.inbox_checkpoint("rch").unwrap().applied, 2);
    assert_eq!(
        conn.query_row("SELECT status,payload FROM rch_broker_inbox", [], |r| Ok((
            r.get::<_, String>(0)?,
            r.get::<_, String>(1)?
        )))
        .unwrap()
        .0,
        "rejected"
    );
    assert!(
        !conn
            .query_row("SELECT payload FROM rch_broker_inbox", [], |r| r
                .get::<_, String>(0))
            .unwrap()
            .is_empty()
    );
}

#[test]
fn fanout_receipts_are_monotonic_and_keep_daemon_reason() {
    let path = db();
    let mut store = RchSqliteStore::open(&path).unwrap();
    let mut first = intent();
    first.request = json!({"destination":"a","content":"Test1234"});
    let mut second = first.clone();
    second.operation_id = "second-recipient".into();
    second.request["destination"] = json!("b");
    let unit = store.begin_outbound_application().unwrap();
    unit.stage_outbound_intent(&first).unwrap();
    unit.stage_outbound_intent(&second).unwrap();
    unit.commit().unwrap();
    store
        .record_broker_admission(&first.operation_id, "daemon-a")
        .unwrap();
    store
        .record_broker_admission(&second.operation_id, "daemon-b")
        .unwrap();
    let unit = store.begin_outbound_application().unwrap();
    let sent = unit
        .stage_broker_receipt("daemon-a", " Sent: direct ")
        .unwrap()
        .unwrap();
    assert_eq!(sent.delivery_state, "sent");
    assert_eq!(
        sent.delivery_metadata["last_broker_receipt"],
        " Sent: direct "
    );
    unit.commit().unwrap();
    let unit = store.begin_outbound_application().unwrap();
    let partial = unit
        .stage_broker_receipt("daemon-a", "delivered")
        .unwrap()
        .unwrap();
    assert_ne!(partial.delivery_state, "delivered");
    unit.stage_broker_receipt("daemon-b", "delivered").unwrap();
    unit.commit().unwrap();
    let unit = store.begin_outbound_application().unwrap();
    let final_message = unit
        .stage_broker_receipt("daemon-a", "sending")
        .unwrap()
        .unwrap();
    assert_eq!(final_message.delivery_state, "delivered");
    unit.commit().unwrap();
    let unit = store.begin_outbound_application().unwrap();
    assert!(
        unit.stage_broker_receipt("daemon-a", "arbitrary-state")
            .is_err()
    );
}

#[test]
fn inbox_registry_mode_survives_restart() {
    let path = db();
    let mut store = RchSqliteStore::open(&path).unwrap();
    store.store_inbox_batch(&batch()).unwrap();
    let event = store.next_inbox_event("rch").unwrap().unwrap();
    let mut unit = store.begin_inbox_application("rch", &event, false).unwrap();
    unit.core_mut()
        .set_identity_rem_mode("00112233445566778899aabbccddeeff", "connected")
        .unwrap();
    unit.commit().unwrap();
    drop(store);
    let store = RchSqliteStore::open(&path).unwrap();
    assert_eq!(store.load_identity_rem_modes().unwrap().len(), 1);
}

#[test]
fn crash_child() {
    let Some(path) = std::env::var_os("RCH_DURABLE_CRASH_DATABASE") else {
        return;
    };
    let phase = std::env::var("RCH_DURABLE_CRASH_PHASE").unwrap();
    let mut store = RchSqliteStore::open(&path).unwrap();
    if phase != "before_custody" {
        store.store_inbox_batch(&batch()).unwrap();
    }
    if phase == "during_apply" || phase == "after_apply" {
        let event = store.next_inbox_event("rch").unwrap().unwrap();
        let mut unit = store.begin_inbox_application("rch", &event, false).unwrap();
        unit.stage_client(&ClientRecord {
            identity: "sender".into(),
            first_seen_ts_ms: 1,
            last_seen_ts_ms: 1,
            nickname: None,
            role: "member".into(),
            paused: false,
            text_only: false,
            last_chat_ts_ms: None,
        })
        .unwrap();
        unit.stage_outbound_intent(&intent()).unwrap();
        if phase == "after_apply" {
            unit.commit().unwrap();
        } else {
            std::fs::write(
                std::path::PathBuf::from(&path).with_extension("ready"),
                "ready",
            )
            .unwrap();
            loop {
                std::thread::sleep(std::time::Duration::from_secs(1));
            }
        }
    }
    std::fs::write(
        std::path::PathBuf::from(&path).with_extension("ready"),
        "ready",
    )
    .unwrap();
    loop {
        std::thread::sleep(std::time::Duration::from_secs(1));
    }
}

#[test]
fn real_process_kill_preserves_custody_and_atomic_application() {
    use std::time::{Duration, Instant};
    for phase in [
        "before_custody",
        "after_custody",
        "during_apply",
        "after_apply",
    ] {
        let path = db();
        let ready = path.with_extension("ready");
        let mut child = std::process::Command::new(std::env::current_exe().unwrap())
            .args(["--exact", "crash_child", "--nocapture"])
            .env("RCH_DURABLE_CRASH_DATABASE", &path)
            .env("RCH_DURABLE_CRASH_PHASE", phase)
            .stdout(std::process::Stdio::null())
            .spawn()
            .unwrap();
        let deadline = Instant::now() + Duration::from_secs(15);
        while !ready.exists() {
            assert!(
                child.try_wait().unwrap().is_none(),
                "child failed before {phase}"
            );
            assert!(Instant::now() < deadline, "child stalled before {phase}");
            std::thread::sleep(Duration::from_millis(10));
        }
        child.kill().unwrap();
        assert!(!child.wait().unwrap().success());
        let mut store = RchSqliteStore::open(&path).unwrap();
        let checkpoint = store.inbox_checkpoint("rch").unwrap();
        assert_eq!(
            checkpoint.stored,
            if phase == "before_custody" { 0 } else { 2 }
        );
        assert_eq!(
            checkpoint.applied,
            if phase == "after_apply" { 2 } else { 0 }
        );
        assert_eq!(
            store.pending_broker_intent().unwrap().is_some(),
            phase == "after_apply"
        );
        assert_eq!(
            store.load_r3akt_read_snapshot().unwrap().clients.len(),
            usize::from(phase == "after_apply")
        );
        if phase == "during_apply" {
            let event = store.next_inbox_event("rch").unwrap().unwrap();
            store
                .begin_inbox_application("rch", &event, false)
                .unwrap()
                .commit()
                .unwrap();
            assert_eq!(store.inbox_checkpoint("rch").unwrap().applied, 2);
        }
        drop(store);
        std::fs::remove_dir_all(path.parent().unwrap()).unwrap();
    }
}

#[test]
fn inbox_snapshot_keeps_primary_only_rem_member_announces_without_history_expansion() {
    use r3akt_profile_rch::{MissionCommandEnvelope, RchSource};
    let path = db();
    let mut store = RchSqliteStore::open(&path).unwrap();
    let mut core = RchCore::new();
    let team = "d6b6e188b910d6bdd24d04b7a7ec5444";
    let command = |kind: &str, args| MissionCommandEnvelope {
        command_id: uuid::Uuid::new_v4().to_string(),
        source: RchSource {
            rns_identity: "seed".into(),
            display_name: None,
        },
        timestamp: "2026-10-09T12:00:00Z".into(),
        command_type: kind.into(),
        args,
        correlation_id: None,
        topics: vec![],
    };
    core.handle_command(&command(
        "mission.registry.team.upsert",
        json!({"uid":team,"team_name":"Yellow"}),
    ));
    let caller = "11111111111111111111111111111111";
    let peer = "22222222222222222222222222222222";
    for (uid, identity) in [("caller", caller), ("peer", peer)] {
        core.handle_command(&command(
            "mission.registry.team_member.upsert",
            json!({"uid":uid,"team_uid":team,"rns_identity":identity,"display_name":uid}),
        ));
        core.record_identity_announce(
            identity,
            None,
            None,
            Some("identity".into()),
            vec![
                "r3akt".into(),
                "EmergencyMessages".into(),
                "Telemetry".into(),
            ],
        )
        .unwrap();
    }
    core.save_to_sqlite(&mut store).unwrap();
    store.store_inbox_batch(&batch()).unwrap();
    let event = store.next_inbox_event("rch").unwrap().unwrap();
    let mut unit = store.begin_inbox_application("rch", &event, false).unwrap();
    assert!(
        unit.core_mut()
            .rem_team_routing_destinations(caller, team)
            .contains(&peer.to_string())
    );
    drop(unit);
    drop(store);
    std::fs::remove_dir_all(path.parent().unwrap()).unwrap();
}
