use super::*;

#[test]
fn accepted_envelope_survives_a_later_rejected_command_in_same_input() {
    let directory = std::env::temp_dir().join(format!("rch-envelope-isolation-{}", Uuid::new_v4()));
    std::fs::create_dir(&directory).unwrap();
    let mut store = RchSqliteStore::open(directory.join("state.db")).unwrap();
    let event = InboxEvent {
        version: 1,
        position: 1,
        created_at: 100,
        event_type: "inbound".into(),
        payload: json!({}),
    };
    store
        .store_inbox_batch(&InboxBatch {
            journal_id: "test".into(),
            consumer_id: "rch".into(),
            start: 0,
            end: 1,
            receipt: "stored".into(),
            events: vec![event.clone()],
        })
        .unwrap();
    let mut unit = store.begin_inbox_application("rch", &event, false).unwrap();
    let mut published = vec![];
    let mut telemetry = vec![];
    for (name, args) in [
        (
            "topic.create",
            json!({"topic_id":"kept","topic_name":"Kept","topic_path":"kept"}),
        ),
        ("mission.unknown", json!({})),
    ] {
        let envelope = ProtocolEnvelope::new(
            r3akt_protocol::NodeId::new("peer"),
            r3akt_protocol::Destination::Node(r3akt_protocol::NodeId::new("rch")),
            r3akt_protocol::Topic::new("direct"),
            Payload::Command(r3akt_protocol::Command {
                name: name.into(),
                args,
                correlation_id: None,
            }),
        );
        envelope::apply_envelope(
            &mut unit,
            &event,
            &envelope,
            false,
            &mut published,
            &mut telemetry,
            None,
        )
        .unwrap();
    }
    unit.commit().unwrap();
    assert_eq!(
        store.load_snapshot().unwrap().unwrap().topics[0].topic_id,
        "kept"
    );
    assert!(
        published.len() >= 3,
        "accepted and rejected responses persist independently"
    );
    assert!(store.pending_broker_intent().unwrap().is_some());
    drop(store);
    std::fs::remove_dir_all(directory).unwrap();
}
