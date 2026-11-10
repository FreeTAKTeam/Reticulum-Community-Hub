use super::*;

#[test]
fn zmq_announce_sweeps_skip_malformed_capabilities_and_replay_after_restart() {
    let dir = std::env::temp_dir().join(format!("rch-announce-sweep-{}", Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    let daemon_path = dir.join("daemon.db");
    {
        let store = MessagesStore::open(&daemon_path).unwrap();
        for i in 1..=75 {
            let record: rns_rpc::AnnounceRecord = serde_json::from_value(json!({
                "id": format!("announce-{i:04}"), "peer": format!("{i:032x}"),
                "timestamp": 1000+i, "name": format!("peer-{i}"),
                "name_source":"announce", "first_seen":1000, "seen_count":1,
                "capabilities": if [1, 32, 33, 64, 75].contains(&i) { json!([]) } else { json!(["group_chat"]) },
                "app_data_hex": if [1, 32, 33, 64, 75].contains(&i) { Some("dd41dcc148") } else { None }
            }))
            .unwrap();
            store.insert_announce(&record).unwrap();
        }
    }
    let fixture = Fixture::open(&daemon_path);
    let path = dir.join("rch.db");
    // Use the production handshake budget while other tests saturate SQLite/CPU.
    let state =
        fixture.state_with_timeout(&path, &dir.join("identity"), Some(Duration::from_secs(3)));
    let cursor = Mutex::new(None);
    assert!(announce_sync::poll(&state, &cursor).unwrap());
    assert!(announce_sync::poll(&state, &cursor).unwrap());
    assert!(!announce_sync::poll(&state, &cursor).unwrap());
    assert_eq!(*cursor.lock().unwrap(), None);
    let check = || {
        let conn = rusqlite::Connection::open(&path).unwrap();
        let count: i64 = conn
            .query_row("SELECT COUNT(*) FROM rch_identity_announces", [], |row| {
                row.get(0)
            })
            .unwrap();
        assert_eq!(count, 75);
        let payload: Vec<u8> = conn
            .query_row(
                "SELECT payload FROM rch_identity_announces WHERE destination_hash=?1",
                [format!("{:032x}", 74)],
                |row| row.get(0),
            )
            .unwrap();
        let record: r3akt_rch_core::IdentityAnnounceRecord =
            rmp_serde::from_slice(&payload).unwrap();
        assert_eq!(record.announce_capabilities, vec!["group_chat"]);
        let oldest: i64 = conn
            .query_row(
                "SELECT last_seen_ts_ms FROM rch_identity_announces WHERE destination_hash=?1",
                [format!("{:032x}", 1)],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(oldest, 1_001_000);
    };
    check();
    plane(&state).unwrap().shutdown().unwrap();
    drop(state);
    let restarted =
        fixture.state_with_timeout(&path, &dir.join("identity"), Some(Duration::from_secs(3)));
    let cursor = Mutex::new(None);
    for expected in [true, true, false] {
        assert_eq!(announce_sync::poll(&restarted, &cursor).unwrap(), expected);
    }
    check();
    plane(&restarted).unwrap().shutdown().unwrap();
    drop(restarted);
    drop(fixture);
    std::fs::remove_dir_all(dir).unwrap();
}
