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

#[tokio::test]
async fn ui_roster_reads_ignore_unrelated_stale_corruption_but_preserve_raw_history() {
    let (state, directory) = fixture();
    corrupt_announce(&directory);
    assert!(list_identities(State(state.clone())).await.is_ok());
    assert!(rem_peer_registry_payload_for_state(&state, None).is_ok());
    let database = Connection::open(directory.join("state.db")).expect("DB");
    let bytes: Vec<u8> = database
        .query_row(
            "SELECT payload FROM rch_identity_announces WHERE destination_hash='unrelated'",
            [],
            |row| row.get(0),
        )
        .expect("history");
    assert_eq!(bytes, [0xc1]);
    drop(database);
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[test]
fn indexed_rem_registry_matches_full_reader_order_moderation_modes_and_runtime_cutoff() {
    let (state, directory) = fixture();
    let mut store = RchSqliteStore::open(directory.join("state.db")).expect("store");
    let now = unix_now_ms();
    let make = |destination: &str, owner: &str, age, source: &str| {
        r3akt_rch_core::IdentityAnnounceRecord {
            destination_hash: destination.into(),
            announced_identity_hash: Some(owner.into()),
            display_name: Some(destination.into()),
            source_interface: Some(source.into()),
            announce_capabilities: vec![],
            client_type: " ReM ".into(),
            first_seen_ts_ms: now - age,
            last_seen_ts_ms: now - age,
        }
    };
    let announces = vec![
        make("a-old", " Owner ", 1000, "identity"),
        make("z-new", "owner", 0, "identity"),
        make("a-alias", "owner2", 0, "identity"),
        make("z-destination", "OWNER2", 1000, " Destination "),
        make("banned", "banned", 0, "destination"),
        make("blocked", "blocked", 0, "destination"),
        make(
            "stale",
            "stale",
            REM_PEER_ACTIVE_WINDOW_MS + 1000,
            "destination",
        ),
    ];
    let mut snapshot = RchCore::new().snapshot();
    snapshot.identity_announces = announces;
    for (identity, banned, blackholed) in [("banned", true, false), ("blocked", false, true)] {
        snapshot
            .identity_states
            .push(r3akt_rch_core::IdentityStateRecord {
                identity: identity.into(),
                is_banned: banned,
                is_blackholed: blackholed,
                updated_ts_ms: now,
            });
    }
    snapshot
        .identity_rem_modes
        .push(r3akt_rch_core::IdentityRemModeRecord {
            identity: "owner".into(),
            mode: " connected ".into(),
            updated_ts_ms: now,
        });
    snapshot
        .identity_rem_modes
        .push(r3akt_rch_core::IdentityRemModeRecord {
            identity: "owner2".into(),
            mode: " ".into(),
            updated_ts_ms: now,
        });
    store.save_snapshot(&snapshot).expect("save");
    let announces = store.load_identity_announces().expect("full reader");
    for runtime in [None, Some(now - 500)] {
        let expected = rem_peer_registry_payload_from_records(
            &announces,
            &snapshot.identity_states,
            &snapshot.identity_rem_modes,
            runtime,
        );
        let actual =
            rem_peer_registry_payload_for_state(&state, runtime).expect("indexed registry");
        assert_eq!(actual, expected);
        let items = actual["items"].as_array().expect("items");
        assert_eq!(items.len(), 2);
        if runtime.is_none() {
            assert!(items.iter().any(|item| item["display_name"] == "a-old"));
            assert!(
                items
                    .iter()
                    .any(|item| item["destination_hash"] == "z-destination")
            );
        }
    }
    drop(store);
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[tokio::test]
async fn moderation_response_preserves_annotation_without_decoding_unrelated_history() {
    let (state, directory) = fixture();
    let mut core = RchCore::new();
    core.record_identity_announce(
        "peer",
        None,
        Some("Peer REM".into()),
        Some("identity".into()),
        vec!["r3akt".into()],
    )
    .expect("announce");
    core.save_to_sqlite(&mut RchSqliteStore::open(directory.join("state.db")).expect("store"))
        .expect("save");
    corrupt_announce(&directory);
    let Json(payload) = upsert_identity_status(state.clone(), " PEER ".into(), Some(true), None)
        .await
        .expect("ban");
    assert_eq!(payload["IsBanned"], true);
    assert_eq!(payload["DisplayName"], "Peer REM");
    assert_eq!(payload["IsAnnounced"], true);
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[tokio::test]
async fn identity_reader_keeps_alias_metadata_and_voice_owners_absent_from_state_rows() {
    let (state, directory) = fixture();
    let now = unix_now_ms();
    let mut owner = ClientRecord::new("owner".into(), now);
    owner.metadata = json!({"voice":{"destination_hash":"voice"}});
    state
        .clients
        .write()
        .expect("clients")
        .insert("owner".into(), owner);
    for identity in ["voice", " AaBb "] {
        state.identity_states.write().expect("states").insert(
            identity.into(),
            IdentityStatusRecord {
                identity: identity.into(),
                is_banned: false,
                is_blackholed: false,
                updated_ts_ms: now,
            },
        );
    }
    let mut store = RchSqliteStore::open(directory.join("state.db")).expect("store");
    store
        .upsert_identity_announces(&[r3akt_rch_core::IdentityAnnounceRecord {
            destination_hash: " DDEE ".into(),
            announced_identity_hash: Some(" AaBb ".into()),
            display_name: Some("Alias display".into()),
            source_interface: Some("destination".into()),
            announce_capabilities: vec![],
            client_type: "generic_lxmf".into(),
            first_seen_ts_ms: now,
            last_seen_ts_ms: now,
        }])
        .expect("alias");
    corrupt_announce(&directory);
    let Json(payload) = list_identities(State(state.clone()))
        .await
        .expect("identities");
    let items = payload.as_array().expect("rows");
    assert_eq!(items.len(), 1);
    assert_eq!(items[0]["Identity"], " AaBb ");
    assert_eq!(items[0]["DisplayName"], "Alias display");
    drop(store);
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}
