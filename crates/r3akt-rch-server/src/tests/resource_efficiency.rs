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

fn history_fingerprint(path: &std::path::Path) -> String {
    let database = Connection::open(path).expect("DB");
    let mut statement = database
        .prepare(
            "SELECT destination_hash,payload FROM rch_identity_announces ORDER BY destination_hash",
        )
        .expect("history");
    let mut rows = statement.query([]).expect("rows");
    let mut digest = Sha256::new();
    while let Some(row) = rows.next().expect("row") {
        let key: String = row.get(0).expect("key");
        let payload: Vec<u8> = row.get(1).expect("payload");
        digest.update(key.as_bytes());
        digest.update(&payload);
    }
    format!("{digest:x}", digest = digest.finalize())
}

#[test]
#[ignore = "explicit release-mode 100k-row performance qualification"]
fn profile_remaining_announce_paths() {
    let (state, directory) = fixture();
    let mut store = RchSqliteStore::open(directory.join("state.db")).expect("store");
    let now = unix_now_ms();
    let records = (0..100_000)
        .map(|index| r3akt_rch_core::IdentityAnnounceRecord {
            destination_hash: format!("{index:032x}"),
            announced_identity_hash: Some(format!("{:032x}", index + 200_000)),
            display_name: Some(format!("Preserved synthetic peer {index:06}")),
            source_interface: Some("destination".to_string()),
            announce_capabilities: vec!["lxmf".to_string(), format!("name=fixture-peer-{index}")],
            client_type: "generic_lxmf".to_string(),
            first_seen_ts_ms: 1,
            last_seen_ts_ms: now,
        })
        .collect::<Vec<_>>();
    store.upsert_identity_announces(&records).expect("history");
    drop(records);
    let original_digest = history_fingerprint(&directory.join("state.db"));
    let identity = format!("{:032x}", 299_999);
    state
        .clients
        .write()
        .expect("clients")
        .insert(identity.clone(), ClientRecord::new(identity.clone(), now));
    let mut times = Vec::new();
    for _ in 0..11 {
        let start = std::time::Instant::now();
        assert_eq!(client_records_for_state(&state).expect("roster").len(), 1);
        times.push(start.elapsed().as_secs_f64() * 1000.0);
    }
    times.sort_by(f64::total_cmp);
    println!("client_roster: median_ms={} max_ms={}", times[5], times[10]);
    let mut times = Vec::new();
    for _ in 0..11 {
        let start = std::time::Instant::now();
        assert!(
            outbound_destination_has_announce_since_for_any(&state, &[&identity], now)
                .expect("fresh")
        );
        times.push(start.elapsed().as_secs_f64() * 1000.0);
    }
    times.sort_by(f64::total_cmp);
    println!(
        "freshness_lookup: median_ms={} max_ms={}",
        times[5], times[10]
    );
    assert_eq!(
        store.identity_announce_summary(now).expect("history").total,
        100_000
    );
    assert_eq!(
        history_fingerprint(&directory.join("state.db")),
        original_digest
    );
    drop(store);
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}

fn saved_announce(
    destination: &str,
    identity: Option<&str>,
    timestamp: i64,
) -> r3akt_rch_core::IdentityAnnounceRecord {
    r3akt_rch_core::IdentityAnnounceRecord {
        destination_hash: destination.to_string(),
        announced_identity_hash: identity.map(str::to_string),
        display_name: Some(format!("peer {destination}")),
        source_interface: Some("identity".to_string()),
        announce_capabilities: Vec::new(),
        client_type: "rem".to_string(),
        first_seen_ts_ms: 1,
        last_seen_ts_ms: timestamp,
    }
}

#[test]
fn client_roster_indexed_annotations_preserve_shared_alias_source_precedence_and_empty_rosters() {
    let (state, directory) = fixture();
    let mut store = RchSqliteStore::open(directory.join("state.db")).expect("store");
    let now = unix_now_ms();
    let mut records = vec![
        saved_announce("a", Some(" SHARED "), now + 100),
        saved_announce("b", Some("shared"), now),
        saved_announce("c", Some("shared"), now + 200),
        saved_announce("\u{2003}MiXeD\u{2003}", Some(" "), now),
        saved_announce("other", Some("unlisted"), now),
    ];
    records[1].source_interface = Some(" Destination ".to_string());
    records[2].source_interface = Some("destination".to_string());
    store.upsert_identity_announces(&records).expect("history");
    let baseline = rem_annotations_for_state(&state).expect("full reference");
    let identities = ["shared", "mixed", "missing"].map(str::to_string);
    let actual =
        rem_annotations_for_client_identities(&state, &identities).expect("bounded annotations");
    for identity in &identities {
        assert_eq!(actual.get(identity), baseline.get(identity));
    }
    assert_eq!(actual["shared"].destination_hash, "b");
    let mut expected = Vec::new();
    for identity in &identities {
        let mut client = ClientRecord::new(identity.clone(), now);
        state
            .clients
            .write()
            .expect("clients")
            .insert(identity.clone(), client.clone());
        if let Some(annotation) = baseline.get(identity) {
            client.apply_rem_annotation(annotation);
        }
        expected.push(client);
    }
    expected.sort_by(|left, right| left.identity.cmp(&right.identity));
    assert_eq!(client_records_for_state(&state).expect("roster"), expected);
    let database = Connection::open(directory.join("state.db")).expect("DB");
    database.execute(
        "INSERT INTO rch_identity_announces (destination_hash,payload,last_seen_ts_ms,normalized_destination_hash) VALUES ('corrupt',X'C1',0,'corrupt')", [],
    ).expect("unrelated corrupt fixture");
    assert_eq!(
        client_records_for_state(&state).expect("isolated roster"),
        expected
    );
    state.clients.write().expect("clients").clear();
    assert!(
        client_records_for_state(&state)
            .expect("empty roster")
            .is_empty()
    );
    drop(database);
    drop(store);
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[test]
fn indexed_relay_display_names_preserve_timestamp_ties_and_aliases() {
    let (state, directory) = fixture();
    let mut store = RchSqliteStore::open(directory.join("state.db")).expect("store");
    let now = unix_now_ms();
    let records = [
        saved_announce("a", Some(" ALIAS "), now),
        saved_announce("z", Some("alias"), now),
        saved_announce(
            "stale",
            None,
            now - r3akt_rch_core::RECENT_ANNOUNCE_WINDOW_MS - 1_000,
        ),
        saved_announce("source", None, now),
    ];
    store.upsert_identity_announces(&records).expect("history");
    assert_eq!(
        relay_sender_display_name(&state, " ALIAS ").expect("relay name"),
        "peer z"
    );
    let mut expected = records.to_vec();
    expected.sort_by(|left, right| left.destination_hash.cmp(&right.destination_hash));
    assert_eq!(store.load_identity_announces().expect("retained"), expected);
    drop(store);
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[test]
fn relay_display_name_reports_corrupt_matching_announce() {
    let (state, directory) = fixture();
    let database = Connection::open(directory.join("state.db")).expect("DB");
    database.execute("INSERT INTO rch_identity_announces (destination_hash,payload,last_seen_ts_ms,normalized_destination_hash) VALUES ('target',X'C1',0,'target')", []).expect("corrupt display record");
    assert!(relay_sender_display_name(&state, "target").is_err());
    drop(database);
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}
