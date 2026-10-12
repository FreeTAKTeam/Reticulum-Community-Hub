use crate::*;

fn routing_fixture() -> (AppState, PathBuf) {
    let directory = std::env::temp_dir().join(format!("rch-routing-{}", Uuid::new_v4()));
    std::fs::create_dir(&directory).expect("directory");
    let state = AppState::from_sqlite_path(directory.join("state.db")).expect("state");
    (state, directory)
}

#[test]
fn targeted_and_explicit_recipient_sends_never_decode_100001_history_rows() {
    let (state, directory) = routing_fixture();
    let database = rusqlite::Connection::open(directory.join("state.db")).expect("DB");
    // Every payload is malformed. Any historical route/alias read must fail this test,
    // even if it is changed from a full scan to a keyed lookup for this recipient.
    database.execute(
        "WITH RECURSIVE rows(n) AS (VALUES(0) UNION ALL SELECT n+1 FROM rows WHERE n<100000)
         INSERT INTO rch_identity_announces (destination_hash,payload,last_seen_ts_ms,normalized_destination_hash)
         SELECT printf('%032x',n),X'C1',0,printf('%032x',n) FROM rows", [],
    ).expect("100001 corrupt announce payloads");
    let destination = format!("{:032x}", 1);
    let message = record_outbound_message_with_metadata(
        &state,
        "test",
        None,
        Some(destination.clone()),
        Vec::new(),
        false,
        json!({}),
    )
    .expect("targeted admission independent of history");
    assert_eq!(
        outbound_destinations(&state, &message).expect("recipients"),
        [destination.clone()]
    );
    assert_eq!(message.delivery_method, "durable_broker");
    assert_eq!(message.delivery_policy_reason, "sdk_owned");
    let second = format!("{:032x}", 2);
    let batch = record_outbound_message_with_metadata(
        &state,
        "test",
        Some("topic".to_string()),
        None,
        Vec::new(),
        false,
        json!({"target_destinations": [destination, second]}),
    )
    .expect("explicit recipients independent of history");
    assert_eq!(
        outbound_destinations(&state, &batch).expect("recipients"),
        [format!("{:032x}", 1), format!("{:032x}", 2)]
    );
    assert!(
        command_fanout_recipients_for_state(&state)
            .expect("empty application roster does not load history")
            .is_empty()
    );
    assert_eq!(
        database
            .query_row("SELECT COUNT(*) FROM rch_identity_announces", [], |row| row
                .get::<_, i64>(0))
            .expect("count"),
        100_001
    );
    drop(database);
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}
