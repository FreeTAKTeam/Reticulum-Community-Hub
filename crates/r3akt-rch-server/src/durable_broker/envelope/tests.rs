use super::*;
use r3akt_profile_rch::{MissionCommandEnvelope, RchSource};
use r3akt_protocol::{Command, NodeId, Topic, TopicAttachment, TopicMessage};
fn batch() -> InboxBatch {
    InboxBatch {
        journal_id: "journal".into(),
        consumer_id: "rch".into(),
        start: 0,
        end: 2,
        receipt: "receipt".into(),
        events: (1..=2)
            .map(|position| InboxEvent {
                version: 1,
                position,
                created_at: 100,
                event_type: "inbound".into(),
                payload: json!({"id":position}),
            })
            .collect(),
    }
}
fn envelope(payload: Payload) -> ProtocolEnvelope {
    ProtocolEnvelope::new(
        NodeId::new("00112233445566778899aabbccddeeff"),
        Destination::Node(NodeId::new("hub")),
        Topic::new("direct"),
        payload,
    )
}
fn seed(unit: &mut RchCommandTransaction<'_>, kind: &str, args: Value) {
    let replies = unit
        .core_mut()
        .handle_mission_sync_command(&MissionCommandEnvelope {
            command_id: Uuid::new_v4().to_string(),
            source: RchSource {
                rns_identity: "seed".into(),
                display_name: None,
            },
            timestamp: "2026-10-09T12:00:00Z".into(),
            command_type: kind.into(),
            args,
            correlation_id: None,
            topics: vec![],
        });
    assert!(
        !replies
            .iter()
            .any(|r| r.results_field().is_some_and(|v| v["status"] == "rejected")),
        "{replies:?}"
    );
}
#[test]
fn mission_event_stages_primary_only_member_destination_in_same_commit() {
    let dir = temp_dir();
    let path = dir.join("rch.db");
    let mut store = RchSqliteStore::open(&path).unwrap();
    let mut unit = store.begin_r3akt_command().unwrap();
    seed(
        &mut unit,
        "mission.registry.mission.upsert",
        json!({"uid":"mission","mission_name":"Mission"}),
    );
    seed(
        &mut unit,
        "mission.registry.team.upsert",
        json!({"uid":"team","team_name":"Team","mission_uid":"mission"}),
    );
    let primary = "11223344556677889900aabbccddeeff";
    seed(
        &mut unit,
        "mission.registry.team_member.upsert",
        json!({"uid":"member","team_uid":"team","rns_identity":primary,"display_name":"Member"}),
    );
    unit.commit().unwrap();
    store.store_inbox_batch(&batch()).unwrap();
    let event = store.next_inbox_event("rch").unwrap().unwrap();
    let mut unit = store.begin_inbox_application("rch", &event, false).unwrap();
    assert!(
        unit.core_mut()
            .snapshot()
            .team_member_client_links
            .is_empty()
    );
    let input = envelope(Payload::Command(Command {
        name: "mission.registry.mission.patch".into(),
        args: json!({"mission_uid":"mission","patch":{"mission_name":"Changed"}}),
        correlation_id: None,
    }));
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
    assert!(
        published
            .iter()
            .any(|r| r.destination.as_deref() == Some(primary))
    );
    unit.commit().unwrap();
    let conn = rusqlite::Connection::open(&path).unwrap();
    assert!(
        conn.query_row("SELECT COUNT(*) FROM rch_broker_dispatch", [], |r| r
            .get::<_, i64>(0))
            .unwrap()
            >= 2
    );
    assert_eq!(
        store.load_r3akt_read_snapshot().unwrap().missions[0].mission_name,
        "Changed"
    );
    drop(conn);
    drop(store);
    std::fs::remove_dir_all(dir).unwrap();
}
#[test]
fn oversized_attachment_is_rejected_before_sql_effects_and_next_input_can_apply() {
    let dir = temp_dir();
    let path = dir.join("rch.db");
    let mut store = RchSqliteStore::open(&path).unwrap();
    store.store_inbox_batch(&batch()).unwrap();
    for (index, attachments) in [
        vec![
            attachment(vec![1; 8]),
            attachment(vec![2; r3akt_rch_core::MAX_DURABLE_ATTACHMENT_BYTES + 1]),
        ],
        vec![attachment(vec![3; 8])],
    ]
    .into_iter()
    .enumerate()
    {
        let event = store.next_inbox_event("rch").unwrap().unwrap();
        let mut unit = store.begin_inbox_application("rch", &event, false).unwrap();
        let input = envelope(Payload::TopicMessage(TopicMessage {
            body: "Test1234".into(),
            content_type: "text/plain".into(),
            correlation_id: None,
            attachments,
        }));
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
        unit.commit().unwrap();
        let conn = rusqlite::Connection::open(&path).unwrap();
        assert_eq!(
            conn.query_row("SELECT COUNT(*) FROM rch_file_attachments", [], |r| r
                .get::<_, i64>(0))
                .unwrap(),
            i64::try_from(index).unwrap()
        );
        if index == 0 {
            assert!(published.is_empty());
            assert_eq!(store.durable_broker_diagnostics().unwrap()["rejected"], 1);
        }
    }
    assert!(store.next_inbox_event("rch").unwrap().is_none());
    assert_eq!(store.inbox_checkpoint("rch").unwrap().applied, 2);
    drop(store);
    std::fs::remove_dir_all(dir).unwrap();
}
fn attachment(data: Vec<u8>) -> TopicAttachment {
    TopicAttachment {
        name: "test.bin".into(),
        data,
        media_type: None,
        category: "file".into(),
    }
}
fn temp_dir() -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("rch-envelope-{}", Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

#[test]
fn message_command_persists_requested_delivery_with_business_completion() {
    let dir = temp_dir();
    let path = dir.join("rch.db");
    let mut store = RchSqliteStore::open(&path).unwrap();
    store.store_inbox_batch(&batch()).unwrap();
    let event = store.next_inbox_event("rch").unwrap().unwrap();
    let mut unit = store.begin_inbox_application("rch", &event, false).unwrap();
    let destination = "11223344556677889900aabbccddeeff";
    let input = envelope(Payload::Command(Command {
        name: "mission.message.send".into(),
        args: json!({"content":"Test1234","destination":destination}),
        correlation_id: None,
    }));
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
    unit.commit().unwrap();
    assert!(published.iter().any(|r| r.content == "Test1234"
        && r.destination.as_deref() == Some(destination)
        && r.delivery_state == "broker_pending"));
    let conn = rusqlite::Connection::open(&path).unwrap();
    let mut stmt = conn
        .prepare("SELECT payload FROM rch_broker_dispatch")
        .unwrap();
    let intents = stmt
        .query_map([], |r| r.get::<_, String>(0))
        .unwrap()
        .map(|r| serde_json::from_str::<Value>(&r.unwrap()).unwrap())
        .collect::<Vec<_>>();
    assert!(intents.iter().any(
        |v| v["request"]["destination"] == destination && v["request"]["content"] == "Test1234"
    ));
    assert_eq!(store.inbox_checkpoint("rch").unwrap().applied, 1);
    drop(stmt);
    drop(conn);
    drop(store);
    std::fs::remove_dir_all(dir).unwrap();
}
#[test]
fn different_sources_can_reuse_command_id_without_colliding_delivery_intents() {
    let directory = temp_dir();
    let path = directory.join("rch.db");
    let mut store = RchSqliteStore::open(&path).unwrap();
    store.store_inbox_batch(&batch()).unwrap();
    let destination = "11223344556677889900aabbccddeeff";
    for (source, content) in [
        ("00112233445566778899aabbccddeeff", "first"),
        ("22334455667788990011aabbccddeeff", "second"),
    ] {
        let event = store.next_inbox_event("rch").unwrap().unwrap();
        let mut unit = store.begin_inbox_application("rch", &event, false).unwrap();
        let mut input = envelope(Payload::Command(Command {
            name: "mission.message.send".into(),
            args: json!({"content":content,"destination":destination}),
            correlation_id: Some("same-command".into()),
        }));
        input.source = NodeId::new(source);
        apply_envelope(
            &mut unit,
            &event,
            &input,
            false,
            &mut vec![],
            &mut vec![],
            None,
        )
        .unwrap();
        unit.commit().unwrap();
    }
    assert_eq!(store.inbox_checkpoint("rch").unwrap().applied, 2);
    let conn = rusqlite::Connection::open(&path).unwrap();
    let count:i64=conn.query_row("SELECT COUNT(*) FROM rch_broker_dispatch WHERE json_extract(payload,'$.request.destination')=?1",[destination],|r|r.get(0)).unwrap();
    assert_eq!(count, 2);
    let count:i64=conn.query_row("SELECT COUNT(DISTINCT operation_id) FROM rch_broker_dispatch WHERE json_extract(payload,'$.request.destination')=?1",[destination],|r|r.get(0)).unwrap();
    assert_eq!(count, 2);
    drop(conn);
    drop(store);
    std::fs::remove_dir_all(directory).unwrap();
}
