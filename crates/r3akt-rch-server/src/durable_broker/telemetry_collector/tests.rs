use super::*;
const PEER: &str = "00112233445566778899aabbccddeeff";
const OTHER: &str = "11223344556677889900aabbccddeeff";
const HUB: &str = "ffeeddccbbaa00998877665544332211";
fn fixture() -> Value {
    serde_json::from_str(include_str!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../r3akt-transport-rns/tests/fixtures/collector_stream.json"
    )))
    .unwrap()
}
fn setup() -> (PathBuf, AppState) {
    let dir = std::env::temp_dir().join(format!("rch-collector-{}", Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    let mut state = AppState::from_sqlite_path(dir.join("rch.db")).unwrap();
    state.reticulumd_source = Some(Arc::new(HUB.into()));
    (dir, state)
}
fn store_message(state: &AppState, id: &str, position: u64, fields: Value) {
    let mut store = open(state).unwrap();
    let consumer = store.durable_consumer_id().unwrap();
    store.store_inbox_batch(&InboxBatch {
        journal_id:"collector-journal".into(), consumer_id:consumer,
        start:position-1,end:position,receipt:format!("receipt:{position}"),
        events:vec![InboxEvent { version:1,position,created_at:1_700_000_100,event_type:"inbound".into(),
            payload:json!({"message":{"id":id,"direction":"in","source":PEER,"destination":HUB,"content":"","timestamp":1_700_000_000,"fields":fields}}) }],
    }).unwrap();
}
fn apply(state: &AppState) {
    let consumer = open(state).unwrap().durable_consumer_id().unwrap();
    assert!(super::super::application::apply(state, &consumer).unwrap());
}
fn assert_reply(state: &AppState, key: &str) {
    let intent = open(state)
        .unwrap()
        .pending_broker_intent()
        .unwrap()
        .unwrap();
    assert_eq!(intent.request["destination"], PEER);
    assert_eq!(
        intent.request["fields"]["_lxmf_fields_msgpack_b64"],
        fixture()[key]
    );
}
#[test]
fn upload_query_restart_and_replay_commit_one_binary_stream_reply() {
    let (dir, state) = setup();
    store_message(
        &state,
        "upload-query",
        1,
        json!({"2":fixture()["packed_telemeter_b64"],"9":[{"1":[0,true]}]}),
    );
    apply(&state);
    assert_reply(&state, "global_fields_b64");
    assert_eq!(
        state.telemetry_records.read().unwrap()[0].telemetry["location"]["latitude"],
        44.0
    );
    // Both telemetry and reply intent survive restart. Repeated logical input
    // at another broker position advances custody without a second reply.
    let mut restarted = AppState::from_sqlite_path(dir.join("rch.db")).unwrap();
    restarted.reticulumd_source = Some(Arc::new(HUB.into()));
    assert_reply(&restarted, "global_fields_b64");
    store_message(
        &restarted,
        "upload-query",
        2,
        json!({"2":fixture()["packed_telemeter_b64"],"9":[{"1":[0,true]}]}),
    );
    apply(&restarted);
    let conn = rusqlite::Connection::open(dir.join("rch.db")).unwrap();
    assert_eq!(
        conn.query_row("SELECT count(*) FROM rch_broker_dispatch", [], |r| r
            .get::<_, i64>(0))
            .unwrap(),
        1
    );
    assert_eq!(
        conn.query_row("SELECT count(*) FROM rch_telemetry_records", [], |r| r
            .get::<_, i64>(0))
            .unwrap(),
        1
    );
    std::fs::remove_dir_all(dir).unwrap();
}
#[test]
fn legacy_scalar_topic_scope_filters_other_peers_and_denies_unsubscribed_sender() {
    for subscribed in [true, false] {
        let (dir, state) = setup();
        let mut store = open(&state).unwrap();
        store
            .upsert_topic(&r3akt_rch_core::TopicRecord {
                topic_id: "ops".into(),
                topic_name: "Ops".into(),
                topic_path: "ops".into(),
                topic_description: String::new(),
                retention: r3akt_rch_core::RetentionPolicy::Persistent,
                visibility: r3akt_rch_core::Visibility::Restricted,
                created_ts_ms: 0,
                last_activity_ts_ms: 0,
            })
            .unwrap();
        if subscribed {
            store
                .upsert_subscriber(&r3akt_rch_core::SubscriberRecord {
                    node_id: PEER.into(),
                    topic_id: "ops".into(),
                    first_seen_ts_ms: 0,
                    last_seen_ts_ms: 0,
                    reject_tests: None,
                    metadata: json!({}),
                })
                .unwrap();
        }
        let decoded=r3akt_transport_rns::reticulumd_message_to_payloads(&json!({"direction":"in","source":PEER,"destination":HUB,"fields":{"2":fixture()["packed_telemeter_b64"]}}),HUB).unwrap();
        let Payload::TelemetrySample(t) = &decoded.envelopes[0].payload else {
            panic!("telemetry");
        };
        for peer in [PEER, OTHER] {
            store
                .insert_telemetry_record(&TelemetryRecord {
                    packed_telemeter: t.packed_telemeter.clone(),
                    peer_destination: peer.into(),
                    timestamp_s: 1_700_000_000,
                    telemetry: t.telemetry.clone(),
                    display_name: None,
                    identity_label: None,
                })
                .unwrap();
        }
        drop(store);
        store_message(
            &state,
            "topic-query",
            1,
            json!({"9":[{"1":0,"TopicID":"ops"}]}),
        );
        apply(&state);
        if subscribed {
            assert_reply(&state, "topic_fields_b64");
        } else {
            let intent = open(&state)
                .unwrap()
                .pending_broker_intent()
                .unwrap()
                .unwrap();
            assert_eq!(intent.request["fields"]["13"]["status"], "denied");
            assert!(intent.request["fields"].get("3").is_none());
            assert!(
                intent.request["fields"]
                    .get("_lxmf_fields_msgpack_b64")
                    .is_none()
            );
        }
        std::fs::remove_dir_all(dir).unwrap();
    }
}
#[test]
fn valid_upload_survives_bad_and_unsupported_metadata_and_all_queries_run() {
    let (dir, state) = setup();
    store_message(
        &state,
        "mixed",
        1,
        json!({"2":fixture()["packed_telemeter_b64"],"9":[{"1":[0,"private-value"]},{"t":"T1","a":{}},{"1":0},{"1":[0,false]}]}),
    );
    apply(&state);
    let conn = rusqlite::Connection::open(dir.join("rch.db")).unwrap();
    assert_eq!(
        conn.query_row("SELECT count(*) FROM rch_telemetry_records", [], |r| r
            .get::<_, i64>(0))
            .unwrap(),
        1
    );
    assert_eq!(
        conn.query_row("SELECT count(*) FROM rch_broker_dispatch", [], |r| r
            .get::<_, i64>(0))
            .unwrap(),
        2
    );
    assert!(
        state
            .system_events
            .read()
            .unwrap()
            .iter()
            .any(|e| e.event_type == "lxmf_command_diagnostic")
    );
    let snapshot = open(&state).unwrap().load_snapshot().unwrap().unwrap();
    let diagnostic = snapshot
        .system_events
        .iter()
        .find(|e| e.event_type == "lxmf_command_diagnostic")
        .unwrap();
    assert!(diagnostic.message.contains("malformed") && diagnostic.message.contains("unsupported"));
    assert!(!diagnostic.message.contains("private-value"));
    std::fs::remove_dir_all(dir).unwrap();
}
#[test]
fn older_humanized_records_are_reported_unavailable_without_inventing_wire_data() {
    let (dir, state) = setup();
    state
        .record_telemetry(
            PEER,
            json!({"time":{"timestamp":1_700_000_000},"location":{"latitude":44,"longitude":-63}}),
            1_700_000_000,
            None,
        )
        .unwrap();
    store_message(&state, "old-record-query", 1, json!({"9":[{"1":0}]}));
    apply(&state);
    assert_reply(&state, "unavailable_fields_b64");
    std::fs::remove_dir_all(dir).unwrap();
}

#[test]
fn invalid_outer_topic_preserves_upload_without_becoming_a_global_query() {
    let (dir, state) = setup();
    store_message(
        &state,
        "bad-topic",
        1,
        json!({"2":fixture()["packed_telemeter_b64"],"TopicID":42,"9":[{"1":0}]}),
    );
    apply(&state);
    assert_eq!(state.telemetry_records.read().unwrap().len(), 1);
    assert!(
        open(&state)
            .unwrap()
            .pending_broker_intent()
            .unwrap()
            .is_none()
    );
    assert!(
        state
            .system_events
            .read()
            .unwrap()
            .iter()
            .any(|e| e.event_type == "lxmf_command_diagnostic")
    );
    std::fs::remove_dir_all(dir).unwrap();
}

#[test]
fn oversized_collector_reply_does_not_block_later_inbox_work() {
    let (dir, state) = setup();
    open(&state)
        .unwrap()
        .insert_telemetry_record(&TelemetryRecord {
            packed_telemeter: Some(vec![0; 1024 * 1024 + 1]),
            peer_destination: PEER.into(),
            timestamp_s: 1,
            telemetry: json!({"location":{"latitude":44,"longitude":-63}}),
            display_name: None,
            identity_label: None,
        })
        .unwrap();
    store_message(&state, "oversized-query", 1, json!({"9":[{"1":0}]}));
    apply(&state);
    let intent = open(&state)
        .unwrap()
        .pending_broker_intent()
        .unwrap()
        .unwrap();
    assert_eq!(intent.request["fields"]["13"]["status"], "unavailable");
    store_message(
        &state,
        "fresh-upload",
        2,
        json!({"2":fixture()["packed_telemeter_b64"]}),
    );
    apply(&state);
    assert_eq!(
        state.telemetry_records.read().unwrap()[0].timestamp_s,
        1_700_000_000
    );
    std::fs::remove_dir_all(dir).unwrap();
}
