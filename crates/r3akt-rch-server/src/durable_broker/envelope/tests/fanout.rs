use super::*;

fn seed_chat_recipients(store: &mut RchSqliteStore, count: usize) {
    let mut unit = store.begin_r3akt_command().unwrap();
    for index in 1..=count {
        unit.stage_client(&r3akt_rch_core::ClientRecord {
            identity: format!("{index:032x}"),
            first_seen_ts_ms: 100_000,
            last_seen_ts_ms: 100_000,
            nickname: None,
            role: "member".into(),
            paused: false,
            text_only: false,
            last_chat_ts_ms: None,
        })
        .unwrap();
    }
    unit.commit().unwrap();
}

fn chat_with_attachment() -> ProtocolEnvelope {
    envelope(Payload::TopicMessage(TopicMessage {
        body: "fanout boundary".into(),
        content_type: "text/plain".into(),
        correlation_id: None,
        attachments: vec![attachment(vec![1; 8])],
    }))
}

#[test]
fn chat_fanout_accepts_256_recipients_with_stable_ids_after_retry() {
    let dir = temp_dir();
    let path = dir.join("rch.db");
    let mut store = RchSqliteStore::open(&path).unwrap();
    seed_chat_recipients(&mut store, 256);
    store.store_inbox_batch(&batch()).unwrap();
    let event = store.next_inbox_event("rch").unwrap().unwrap();
    let input = chat_with_attachment();
    let mut previous_ids = None;
    for commit in [false, true] {
        let mut unit = store.begin_inbox_application("rch", &event, false).unwrap();
        let mut published = vec![];
        apply_envelope(
            &mut unit,
            &event,
            &input,
            false,
            &mut published,
            &mut vec![],
            None,
        )
        .unwrap();
        assert_eq!(
            published.len(),
            257,
            "inbound display does not use a recipient slot"
        );
        assert_eq!(unit.staged_outbound_intent_count(), 256);
        let ids = published
            .iter()
            .map(|r| r.message_id.clone())
            .collect::<Vec<_>>();
        if let Some(previous) = &previous_ids {
            assert_eq!(&ids, previous, "retry keeps operation identifiers stable");
        }
        previous_ids = Some(ids);
        if commit {
            unit.commit().unwrap();
        }
    }
    let conn = rusqlite::Connection::open(&path).unwrap();
    assert_eq!(
        conn.query_row("SELECT COUNT(*) FROM rch_broker_dispatch", [], |r| r
            .get::<_, i64>(0))
            .unwrap(),
        256
    );
    assert_eq!(
        conn.query_row("SELECT COUNT(*) FROM rch_messages", [], |r| r
            .get::<_, i64>(0))
            .unwrap(),
        257
    );
    assert_eq!(store.inbox_checkpoint("rch").unwrap().applied, 1);
    drop(conn);
    drop(store);
    std::fs::remove_dir_all(dir).unwrap();
}

#[test]
fn chat_fanout_rejects_257_recipients_without_blocking_next_input() {
    let dir = temp_dir();
    let path = dir.join("rch.db");
    let mut store = RchSqliteStore::open(&path).unwrap();
    seed_chat_recipients(&mut store, 257);
    store.store_inbox_batch(&batch()).unwrap();
    let event = store.next_inbox_event("rch").unwrap().unwrap();
    let mut unit = store.begin_inbox_application("rch", &event, false).unwrap();
    let mut published = vec![];
    apply_envelope(
        &mut unit,
        &event,
        &chat_with_attachment(),
        false,
        &mut published,
        &mut vec![],
        None,
    )
    .unwrap();
    assert!(published.is_empty());
    assert_eq!(unit.staged_outbound_intent_count(), 0);
    unit.commit().unwrap();
    let conn = rusqlite::Connection::open(&path).unwrap();
    for table in [
        "rch_messages",
        "rch_file_attachments",
        "rch_broker_dispatch",
    ] {
        assert_eq!(
            conn.query_row(&format!("SELECT COUNT(*) FROM {table}"), [], |r| r
                .get::<_, i64>(0))
                .unwrap(),
            0,
            "rejection left effects in {table}"
        );
    }
    let (status, error, payload): (String, String, String) = conn
        .query_row(
            "SELECT status,error,payload FROM rch_broker_inbox WHERE position=1",
            [],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
        )
        .unwrap();
    assert_eq!(status, "rejected");
    assert!(error.contains("fanout byte/count budget exceeded"));
    assert!(!payload.is_empty(), "retain the original rejected input");
    assert_eq!(
        store.load_r3akt_read_snapshot().unwrap().clients.len(),
        257,
        "rejected sender presence must roll back"
    );
    let event = store.next_inbox_event("rch").unwrap().unwrap();
    assert_eq!(event.position, 2);
    let mut unit = store.begin_inbox_application("rch", &event, false).unwrap();
    let help = envelope(Payload::Command(Command {
        name: "help".into(),
        args: json!({}),
        correlation_id: None,
    }));
    apply_envelope(
        &mut unit,
        &event,
        &help,
        false,
        &mut published,
        &mut vec![],
        None,
    )
    .unwrap();
    unit.commit().unwrap();
    assert_eq!(published.len(), 1);
    assert_eq!(store.inbox_checkpoint("rch").unwrap().applied, 2);
    assert!(store.next_inbox_event("rch").unwrap().is_none());
    drop(conn);
    drop(store);
    std::fs::remove_dir_all(dir).unwrap();
}

#[test]
fn overflowing_chat_rolls_back_its_copies_and_keeps_independent_envelopes() {
    let dir = temp_dir();
    let path = dir.join("rch.db");
    let mut store = RchSqliteStore::open(&path).unwrap();
    seed_chat_recipients(&mut store, 256);
    store.store_inbox_batch(&batch()).unwrap();
    let event = store.next_inbox_event("rch").unwrap().unwrap();
    let mut unit = store.begin_inbox_application("rch", &event, false).unwrap();
    let mut published = vec![];
    let create_topic = |topic: &str| {
        envelope(Payload::Command(Command {
            name: "topic.create".into(),
            args: json!({"topic_id":topic,"topic_name":topic,"topic_path":topic}),
            correlation_id: None,
        }))
    };
    apply_envelope(
        &mut unit,
        &event,
        &create_topic("before"),
        false,
        &mut published,
        &mut vec![],
        None,
    )
    .unwrap();
    let accepted_ids = published
        .iter()
        .map(|r| r.message_id.clone())
        .collect::<Vec<_>>();
    let count = unit.staged_outbound_intent_count();
    assert!(count > 0);
    let mut rejected = chat_with_attachment();
    rejected.source = NodeId::new("ffffffffffffffffffffffffffffffff");
    apply_envelope(
        &mut unit,
        &event,
        &rejected,
        false,
        &mut published,
        &mut vec![],
        None,
    )
    .unwrap();
    assert_eq!(unit.staged_outbound_intent_count(), count);
    assert_eq!(
        published
            .iter()
            .map(|r| r.message_id.clone())
            .collect::<Vec<_>>(),
        accepted_ids
    );
    apply_envelope(
        &mut unit,
        &event,
        &create_topic("after"),
        false,
        &mut published,
        &mut vec![],
        None,
    )
    .unwrap();
    let final_count = unit.staged_outbound_intent_count();
    assert!(final_count > count);
    unit.commit().unwrap();
    let conn = rusqlite::Connection::open(&path).unwrap();
    assert_eq!(
        conn.query_row("SELECT COUNT(*) FROM rch_broker_dispatch", [], |r| r
            .get::<_, i64>(0))
            .unwrap(),
        i64::try_from(final_count).unwrap()
    );
    assert_eq!(
        conn.query_row("SELECT COUNT(*) FROM rch_file_attachments", [], |r| r
            .get::<_, i64>(0))
            .unwrap(),
        0
    );
    let snapshot = store.load_snapshot().unwrap().unwrap();
    assert!(
        snapshot
            .messages
            .iter()
            .all(|record| !record.content.contains("fanout boundary"))
    );
    assert!(snapshot.topics.iter().any(|r| r.topic_id == "before"));
    assert!(snapshot.topics.iter().any(|r| r.topic_id == "after"));
    assert!(
        !snapshot
            .clients
            .iter()
            .any(|r| r.identity == rejected.source.as_str())
    );
    assert_eq!(store.durable_broker_diagnostics().unwrap()["rejected"], 1);
    assert_eq!(store.inbox_checkpoint("rch").unwrap().applied, 1);
    drop(conn);
    drop(store);
    std::fs::remove_dir_all(dir).unwrap();
}
