use super::*;

#[test]
fn zmq_announce_sweeps_import_more_than_32_peers_and_replay_after_restart() {
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
                "capabilities":["group_chat"]
            }))
            .unwrap();
            store.insert_announce(&record).unwrap();
        }
    }
    let fixture = Fixture::open(&daemon_path);
    let path = dir.join("rch.db");
    let state = fixture.state(&path, &dir.join("identity"));
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
    let restarted = fixture.state(&path, &dir.join("identity"));
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
