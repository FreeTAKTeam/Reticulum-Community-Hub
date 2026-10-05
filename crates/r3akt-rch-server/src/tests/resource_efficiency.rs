use crate::*;
use rusqlite::Connection;

fn fixture() -> (AppState, PathBuf) {
    let directory = std::env::temp_dir().join(format!("rch-resource-{}", Uuid::new_v4()));
    std::fs::create_dir(&directory).expect("directory");
    let state = AppState::from_sqlite_path(directory.join("state.db")).expect("state");
    (state, directory)
}

fn announce(timestamp: i64) -> ReticulumdAnnounceRecord {
    serde_json::from_value(json!({
        "id": format!("announce-{timestamp}"), "peer": " TARGET ", "timestamp": timestamp,
        "first_seen": 1, "seen_count": 1,
        "name": "REM peer", "name_source": "test", "app_data_hex": null,
        "capabilities": ["R3AKT", "EmergencyMessages"], "rssi": null, "snr": null, "q": null,
        "stamp_cost_flexibility": null, "peering_cost": null
    }))
    .expect("announce")
}

#[test]
fn batch_import_reads_only_its_peers_and_preserves_history_first_seen_and_classification() {
    let (state, directory) = fixture();
    let mut store = RchSqliteStore::open(directory.join("state.db")).expect("store");
    let prior = r3akt_rch_core::IdentityAnnounceRecord {
        destination_hash: "target".to_string(),
        announced_identity_hash: Some("alias".to_string()),
        display_name: Some("old name".to_string()),
        source_interface: None,
        announce_capabilities: Vec::new(),
        client_type: "generic_lxmf".to_string(),
        first_seen_ts_ms: 123,
        last_seen_ts_ms: 5_000,
    };
    store.upsert_identity_announces(&[prior]).expect("prior");
    // A corrupt unrelated payload makes a full-table import read fail. A peer-key
    // import must leave it untouched; corruption of the requested peer still errors.
    let database = Connection::open(directory.join("state.db")).expect("DB");
    database.execute(
        "INSERT INTO rch_identity_announces (destination_hash,payload,last_seen_ts_ms) VALUES ('unrelated',X'C1',0)", [],
    ).expect("unrelated fixture");
    assert_eq!(
        import_reticulumd_announce_batch(
            &state,
            &[announce(11), announce(10), announce(11)],
            false
        )
        .expect("import")
        .0,
        2
    );
    let records = store
        .load_identity_announces_by_destination_hashes(&["target".to_string()])
        .expect("target");
    assert_eq!(records.len(), 1);
    assert_eq!(records[0].first_seen_ts_ms, 123);
    assert_eq!(records[0].last_seen_ts_ms, 11_000);
    assert_eq!(records[0].client_type, "rem");
    assert_eq!(records[0].announced_identity_hash.as_deref(), Some("alias"));
    assert_eq!(
        import_reticulumd_announce_batch(&state, &[announce(11)], false)
            .expect("unchanged")
            .0,
        0
    );
    let bytes: Vec<u8> = database
        .query_row(
            "SELECT payload FROM rch_identity_announces WHERE destination_hash='unrelated'",
            [],
            |row| row.get(0),
        )
        .expect("unrelated bytes");
    assert_eq!(bytes, [0xc1]);
    database
        .execute(
            "UPDATE rch_identity_announces SET payload=X'C1' WHERE destination_hash='target'",
            [],
        )
        .expect("corrupt target");
    assert!(import_reticulumd_announce_batch(&state, &[announce(12)], false).is_err());
    drop(database);
    drop(store);
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[test]
fn diagnostics_preserves_alias_membership_and_ten_record_contract_with_large_history() {
    let (state, directory) = fixture();
    let mut store = RchSqliteStore::open(directory.join("state.db")).expect("store");
    let now = unix_now_ms();
    let records = (0..10_000)
        .map(|index| r3akt_rch_core::IdentityAnnounceRecord {
            destination_hash: format!("peer-{index:08}"),
            announced_identity_hash: Some(format!(" Alias-{index} ")),
            display_name: None,
            source_interface: None,
            announce_capabilities: Vec::new(),
            client_type: "generic_lxmf".to_string(),
            first_seen_ts_ms: 1,
            last_seen_ts_ms: if index < 20 {
                now
            } else {
                now - r3akt_rch_core::RECENT_ANNOUNCE_WINDOW_MS - 1_000
            },
        })
        .collect::<Vec<_>>();
    store.upsert_identity_announces(&records).expect("history");
    for (index, destination) in [" ALIAS-9999 ", " PEER-00000000 ", "absent", ""]
        .iter()
        .enumerate()
    {
        state.subscribers.write().expect("subscribers").insert(
            index.to_string(),
            SubscriberRecord {
                subscriber_id: index.to_string(),
                destination: (*destination).to_string(),
                topic_id: "ops".to_string(),
                reject_tests: None,
                metadata: json!({}),
            },
        );
    }
    let diagnostics = runtime_diagnostics_payload(&state).expect("diagnostics");
    assert_eq!(diagnostics["missing_subscriber_identity_count"], 2);
    let summary = &diagnostics["announce_cache"];
    assert_eq!(summary["total"], 10_000);
    assert_eq!(summary["fresh"], 20);
    assert_eq!(summary["stale"], 9_980);
    assert_eq!(summary["records"].as_array().expect("records").len(), 10);
    assert_eq!(summary["last_seen_destination"], "peer-00000000");
    assert_eq!(summary["oldest_stale_destination"], "peer-00000020");
    assert_eq!(
        store.load_identity_announces().expect("retained history"),
        records
    );
    drop(store);
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}
