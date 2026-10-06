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
    let message = record_outbound_message_with_metadata_mode(
        &state,
        "test",
        None,
        Some(destination.clone()),
        Vec::new(),
        false,
        json!({}),
        OutboundDispatchMode::Inline,
    )
    .expect("targeted admission independent of history");
    assert_eq!(
        outbound_destinations(&state, &message).expect("recipients"),
        [destination.clone()]
    );
    assert_eq!(message.delivery_method, "auto");
    assert_eq!(message.delivery_policy_reason, "sdk_owned");
    let second = format!("{:032x}", 2);
    let batch = record_outbound_message_with_metadata_mode(
        &state,
        "test",
        Some("topic".to_string()),
        None,
        Vec::new(),
        false,
        json!({"target_destinations": [destination, second]}),
        OutboundDispatchMode::Inline,
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
                .get::<_, u64>(0))
            .expect("count"),
        100_001
    );
    drop(database);
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}

fn target_snapshot(
    id: &str,
    state: &str,
    terminal: bool,
    reason: Option<&str>,
) -> LxmfDeliverySnapshot {
    serde_json::from_value(json!({"message_id":id,"state":state,"terminal":terminal,"attempts":1,"last_updated_ms":1,"reason_code":reason})).expect("snapshot")
}

#[test]
fn sdk_nonterminal_sent_survives_reopen_and_old_receipt_deadline_then_delivers() {
    let (state, directory) = routing_fixture();
    let mut message = record_outbound_message_deferred_with_metadata(
        &state,
        "test",
        None,
        Some("00112233445566778899aabbccddeeff".to_string()),
        Vec::new(),
        false,
        json!({}),
    )
    .expect("admit");
    let target = ReticulumdReceiptTarget {
        message_id: "sdk-owned".to_string(),
        destination: message.destination.clone().expect("destination"),
        status: Some("sent".to_string()),
        sdk_snapshot: Some(target_snapshot("sdk-owned", "sent", false, None)),
        last_poll_ts_ms: None,
    };
    message.delivery_method = "propagated".to_string(); // stale local transport hint
    message.delivery_state = "sent".to_string();
    message.delivery_metadata = json!({"reticulumd_dispatch_count":1,"reticulumd_receipt_targets":reticulumd_receipt_targets_json(&[target]),"receipt_pending":true,"receipt_deadline_ts_ms":0,"receipt_active_extension_count":10});
    persist_outbound_message_row(&state, &message).expect("persist");
    let reopened = AppState::from_sqlite_path(directory.join("state.db")).expect("reopen");
    let loaded = reopened.messages.read().expect("messages")[0].clone();
    assert!(reticulumd_status_poll_candidate(&loaded));
    let targets = reticulumd_receipt_targets_for_message(&loaded);
    assert!(!reticulumd_receipt_target_terminal(&targets[0]));
    apply_reticulumd_target_statuses(&reopened, &loaded, &targets, 1)
        .expect("nonterminal observation");
    assert_eq!(
        reopened.messages.read().expect("messages")[0].delivery_state,
        "sent"
    );
    let delivered = ReticulumdReceiptTarget {
        sdk_snapshot: Some(target_snapshot("sdk-owned", "delivered", true, None)),
        status: Some("delivered".to_string()),
        ..targets[0].clone()
    };
    update_reticulumd_receipt_target_statuses(&reopened, &loaded.message_id, &[delivered.clone()])
        .expect("update");
    apply_reticulumd_target_statuses(&reopened, &loaded, &[delivered], 1).expect("receipt");
    let final_message = reopened.messages.read().expect("messages")[0].clone();
    assert_eq!(final_message.delivery_state, "delivered");
    assert!(!reticulumd_status_poll_candidate(&final_message));
    assert!(!outbound_retry_due(&final_message, unix_now_ms()));
    drop(reopened);
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[test]
fn terminal_peer_not_announced_is_preserved_and_active_fanout_targets_are_not_pruned() {
    let (state, directory) = routing_fixture();
    let mut message = record_outbound_message_deferred_with_metadata(
        &state,
        "test",
        Some("topic".to_string()),
        None,
        Vec::new(),
        false,
        json!({}),
    )
    .expect("admit");
    let targets = vec![
        ReticulumdReceiptTarget {
            message_id: "one".to_string(),
            destination: "00000000000000000000000000000001".to_string(),
            status: Some("sent".to_string()),
            sdk_snapshot: Some(target_snapshot("one", "sent", true, None)),
            last_poll_ts_ms: None,
        },
        ReticulumdReceiptTarget {
            message_id: "two".to_string(),
            destination: "00000000000000000000000000000002".to_string(),
            status: Some("sending".to_string()),
            sdk_snapshot: Some(target_snapshot("two", "in_flight", false, None)),
            last_poll_ts_ms: None,
        },
    ];
    message.delivery_state = "propagated".to_string();
    message.delivery_method = "propagated".to_string();
    message.delivery_metadata = json!({"reticulumd_dispatch_count":2,"reticulumd_receipt_targets":reticulumd_receipt_targets_json(&targets)});
    persist_outbound_message_row(&state, &message).expect("persist");
    let reopened = AppState::from_sqlite_path(directory.join("state.db")).expect("reopen");
    let loaded = reopened.messages.read().expect("messages")[0].clone();
    assert_eq!(reticulumd_receipt_targets_for_message(&loaded), targets);
    let failed = ReticulumdReceiptTarget {
        status: Some("failed: peer not announced".to_string()),
        sdk_snapshot: Some(target_snapshot(
            "two",
            "failed",
            true,
            Some("peer_not_announced"),
        )),
        ..targets[1].clone()
    };
    update_reticulumd_receipt_target_statuses(&reopened, &loaded.message_id, &[failed.clone()])
        .expect("terminal status");
    let current = reopened.messages.read().expect("messages")[0].clone();
    let saved = reticulumd_receipt_targets_for_message(&current);
    assert_eq!(saved[1], failed);
    assert!(reticulumd_receipt_target_failure_terminal(&saved[1]));
    assert_eq!(
        propagated_fanout_partial_success_metadata(&current)["failed_destinations"],
        json!([failed.destination])
    );
    drop(reopened);
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[test]
fn recipient_keys_use_complete_destination_and_survive_retry_narrowing() {
    let (state, directory) = routing_fixture();
    let message = record_outbound_message_deferred_with_metadata(
        &state,
        "test",
        Some("topic".to_string()),
        None,
        Vec::new(),
        false,
        json!({}),
    )
    .expect("admit");
    let one = "00112233445500000000000000000001";
    let two = "00112233445500000000000000000002";
    let first = outbound_dispatch_message_id(&message, one, 0, true);
    let second = outbound_dispatch_message_id(&message, two, 1, true);
    assert_ne!(first, second);
    assert_eq!(
        second,
        outbound_dispatch_message_id(&message, two, 0, false)
    );
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}
