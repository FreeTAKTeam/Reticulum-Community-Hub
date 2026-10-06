use crate::*;
use rusqlite::Connection;

fn fixture() -> (AppState, PathBuf) {
    let directory = std::env::temp_dir().join(format!("rch-memory-{}", Uuid::new_v4()));
    std::fs::create_dir(&directory).expect("directory");
    let state = AppState::from_sqlite_path(directory.join("state.db")).expect("state");
    (state, directory)
}

fn corrupt_announce(directory: &FsPath) {
    Connection::open(directory.join("state.db"))
        .expect("DB")
        .execute(
            "INSERT INTO rch_identity_announces
             (destination_hash,payload,last_seen_ts_ms) VALUES ('unrelated',X'C1',0)",
            [],
        )
        .expect("unrelated malformed history");
}

#[test]
fn startup_and_http_registry_reads_do_not_decode_unrelated_announce_history() {
    let (state, directory) = fixture();
    corrupt_announce(&directory);
    let restored = AppState::from_sqlite_path(directory.join("state.db")).expect("restart");
    assert!(restored.messages.read().expect("messages").is_empty());
    assert!(
        r3akt_command(
            &restored,
            "mission.registry.rights.subjects.list",
            json!({})
        )
        .is_ok()
    );
    let database = Connection::open(directory.join("state.db")).expect("DB");
    let bytes: Vec<u8> = database
        .query_row(
            "SELECT payload FROM rch_identity_announces WHERE destination_hash='unrelated'",
            [],
            |row| row.get(0),
        )
        .expect("raw history");
    assert_eq!(bytes, [0xc1]);
    drop(database);
    drop(restored);
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[tokio::test]
async fn permission_reads_preserve_normalization_without_loading_other_history() {
    let (state, directory) = fixture();
    let mut core = RchCore::new();
    core.grant_identity_capability(" AaBb ", "r3akt");
    core.grant_operation_right("identity", " AaBb ", "mission.read", "global", "")
        .expect("right");
    core.save_to_sqlite(&mut RchSqliteStore::open(directory.join("state.db")).expect("store"))
        .expect("save");
    corrupt_announce(&directory);
    Connection::open(directory.join("state.db"))
        .expect("DB")
        .execute(
            "INSERT INTO rch_topics(topic_id,payload) VALUES ('bad',X'C1')",
            [],
        )
        .expect("unrelated malformed topic");
    let Json(payload) = get_r3akt_identity_capabilities(State(state.clone()), Path("AABB".into()))
        .await
        .expect("capabilities");
    assert_eq!(payload["capabilities"], json!(["mission.read", "r3akt"]));
    assert_eq!(payload["grants"].as_array().expect("grants").len(), 1);
    let Json(rights) = list_r3akt_operation_rights(State(state.clone()), Query(HashMap::new()))
        .await
        .expect("rights");
    assert_eq!(rights.as_array().expect("rights").len(), 1);
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}

fn message(id: &str, timestamp: i64) -> OutboundMessageRecord {
    OutboundMessageRecord {
        message_id: id.into(),
        topic_id: Some("ops".into()),
        destination: Some("peer".into()),
        sender: "northbound".into(),
        content: id.into(),
        delivery_mode: DeliveryMode::Targeted,
        delivery_method: "auto".into(),
        delivery_policy_reason: "sdk_owned".into(),
        delivery_state: "delivered".into(),
        delivery_metadata: json!({}),
        created_ts_ms: timestamp,
        attachments: Vec::new(),
    }
}

#[tokio::test]
async fn limited_chat_keeps_filters_stable_timestamp_ties_visibility_and_attachments() {
    let state = AppState::default();
    let mut first = message("first", 10);
    first.attachments.push(ChatAttachmentRecord {
        file_id: 7,
        category: "file".into(),
        name: "kept.txt".into(),
        size: 11,
        media_type: Some("text/plain".into()),
    });
    let mut inbound = message("inbound", 30);
    inbound.delivery_metadata = json!({"direction":"inbound"});
    let mut hidden = message("hidden", 40);
    hidden.delivery_metadata = json!({"fanout_channel":"rem_checklist_command"});
    let mut other_topic = message("other-topic", 50);
    other_topic.topic_id = Some("other".into());
    let mut other_source = message("other-source", 60);
    other_source.sender = "other".into();
    let mut other_destination = message("other-destination", 70);
    other_destination.destination = Some("other".into());
    state.messages.write().expect("messages").extend([
        first,
        message("second", 10),
        message("old", 1),
        inbound,
        hidden,
        other_topic,
        other_source,
        other_destination,
    ]);
    let query: ChatListQuery = serde_json::from_value(json!({
        "limit":2,"direction":" outbound ","topic_id":"ops",
        "destination":"peer","source":"northbound"
    }))
    .expect("query");
    let Json(payload) = list_chat_messages(State(state.clone()), Query(query))
        .await
        .expect("chat");
    let rows = payload.as_array().expect("rows");
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0]["MessageID"], "first");
    assert_eq!(rows[1]["MessageID"], "second");
    assert!(rows[0]["Attachments"].to_string().contains("kept.txt"));
    assert_eq!(state.messages.read().expect("history retained").len(), 8);
}

#[test]
fn announce_free_http_commands_are_explicit_and_do_not_include_rem() {
    assert!(r3akt_http_read_without_announces(
        "mission.registry.skill.list"
    ));
    assert!(!r3akt_http_read_without_announces("rem.team.list"));
    assert!(!r3akt_http_read_without_announces(
        "rem.registry.peers.list"
    ));
    assert!(!r3akt_http_read_without_announces("future.list"));
}
