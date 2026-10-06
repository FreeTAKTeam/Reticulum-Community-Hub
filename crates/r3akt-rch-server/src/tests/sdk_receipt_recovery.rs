use crate::*;
use r3akt_transport_rns::LxmfSdkOutboundBatchError;

fn recovery_fixture() -> (AppState, PathBuf) {
    let directory = std::env::temp_dir().join(format!("rch-receipt-recovery-{}", Uuid::new_v4()));
    std::fs::create_dir(&directory).expect("directory");
    let state = AppState::from_sqlite_path(directory.join("state.db")).expect("state");
    (state, directory)
}

fn terminal_target(id: &str, state: &str) -> ReticulumdReceiptTarget {
    let snapshot = serde_json::from_value::<LxmfDeliverySnapshot>(json!({
        "message_id": id,
        "state": state,
        "terminal": true,
        "attempts": 1,
        "last_updated_ms": 1
    }))
    .expect("SDK snapshot");
    ReticulumdReceiptTarget {
        message_id: id.to_string(),
        destination: format!("destination-{id}"),
        status: Some(delivery_snapshot_receipt_status(&snapshot)),
        sdk_snapshot: Some(snapshot),
        last_poll_ts_ms: Some(0),
    }
}

#[test]
fn restart_aggregates_committed_terminal_sdk_snapshots_without_querying_the_daemon() {
    for (sdk_state, expected) in [
        ("delivered", "delivered"),
        ("sent", "sent"),
        ("failed", "failed"),
    ] {
        let (state, directory) = recovery_fixture();
        let message = record_outbound_message_deferred_with_metadata(
            &state,
            "recover committed SDK receipts",
            None,
            Some("destination".to_string()),
            Vec::new(),
            false,
            json!({"max_attempts": 0}),
        )
        .expect("queue message");
        update_outbound_delivery_state(
            &state,
            &message.message_id,
            "queued",
            json!({
                "dispatch_status": "admission_unknown",
                "receipt_pending": true,
                "reticulumd_dispatch_count": 1,
                "reticulumd_receipt_targets": reticulumd_receipt_targets_json(&[
                    terminal_target("child", sdk_state)
                ])
            }),
        )
        .expect("persist child receipt before parent aggregation");
        drop(state);
        let reopened = AppState::from_sqlite_path(directory.join("state.db"))
            .expect("restart")
            .with_reticulumd_rpc("127.0.0.1:1", "source");
        // A query to this unavailable daemon would fail. The committed terminal
        // SDK snapshot is sufficient to finish the interrupted parent projection.
        poll_reticulumd_delivery_receipts(&reopened).expect("aggregate stored receipts");
        let current = message_persistence::current(&reopened, &message.message_id)
            .expect("parent projection");
        assert_eq!(current.delivery_state, expected);
        assert_eq!(current.delivery_metadata["receipt_pending"], false);
        assert!(
            current
                .delivery_metadata
                .get("sdk_reconciliation_error")
                .is_none()
        );
        assert!(!reticulumd_status_poll_candidate(&current));
        drop(reopened);
        let durable = AppState::from_sqlite_path(directory.join("state.db")).expect("reopen");
        assert_eq!(
            message_persistence::current(&durable, &message.message_id)
                .expect("durable projection")
                .delivery_state,
            expected
        );
        drop(durable);
        std::fs::remove_dir_all(directory).expect("cleanup");
    }
}

#[test]
fn display_names_do_not_merge_registered_broadcast_recipients() {
    let (state, directory) = recovery_fixture();
    let now = unix_now_ms();
    for (id, capabilities) in [
        ("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", Vec::new()),
        (
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            vec!["voice".to_string(), "telephony".to_string()],
        ),
    ] {
        let mut client = ClientRecord::new(id.to_string(), now);
        client.display_name = Some("Shared display name".to_string());
        client.announce_capabilities = capabilities;
        state
            .clients
            .write()
            .expect("clients")
            .insert(id.to_string(), client);
    }
    let message = record_outbound_message_deferred_with_metadata(
        &state,
        "broadcast to registered recipients",
        None,
        None,
        Vec::new(),
        false,
        json!({}),
    )
    .expect("queue broadcast");
    assert_eq!(
        outbound_destinations(&state, &message).expect("recipients"),
        [
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa".to_string(),
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb".to_string()
        ]
    );
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[test]
fn delivered_admitted_recipient_does_not_cancel_a_rejected_recipient_retry() {
    let (state, directory) = recovery_fixture();
    let message = record_outbound_message_deferred_with_metadata(
        &state,
        "partial SDK admission",
        None,
        None,
        Vec::new(),
        false,
        json!({"target_destinations": ["accepted", "rejected"]}),
    )
    .expect("queue broadcast");
    let targets = [terminal_target("accepted", "delivered")];
    update_outbound_delivery_state(
        &state,
        &message.message_id,
        "queued",
        json!({
            "dispatch_status": "partially_accepted_retrying",
            "retry_scheduled": true,
            "receipt_pending": false,
            "target_destinations": ["rejected"],
            "reticulumd_dispatch_count": 1,
            "reticulumd_receipt_targets": reticulumd_receipt_targets_json(&targets)
        }),
    )
    .expect("persist partial admission");
    let pending = message_persistence::current(&state, &message.message_id).expect("current");
    assert!(!reticulumd_status_poll_candidate(&pending));
    apply_reticulumd_target_statuses(&state, &pending, &targets, targets.len())
        .expect("project admitted recipient status");
    let current = message_persistence::current(&state, &message.message_id).expect("current");
    assert_eq!(current.delivery_state, "queued");
    assert_eq!(current.delivery_metadata["retry_scheduled"], true);
    assert_eq!(
        current.delivery_metadata["target_destinations"],
        json!(["rejected"])
    );
    update_outbound_delivery_state(
        &state,
        &message.message_id,
        "queued",
        json!({"retry_scheduled": false, "dispatch_status": "in_progress"}),
    )
    .expect("claim rejected recipient retry");
    let claimed = message_persistence::current(&state, &message.message_id).expect("claimed");
    apply_reticulumd_target_statuses(&state, &claimed, &targets, targets.len())
        .expect("accepted recipient receipt during retry submission");
    assert_eq!(
        message_persistence::current(&state, &message.message_id)
            .expect("current")
            .delivery_state,
        "queued"
    );
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[test]
fn successful_retry_retains_permanent_rejection_and_projects_partial_application_success() {
    let (state, directory) = recovery_fixture();
    let permanent = json!({
        "id": "permanent",
        "destination": "destination-permanent",
        "error": LxmfSdkOutboundBatchError {
            code: "SDK_VALIDATION_INVALID_ARGUMENT".to_string(),
            message: "rejected before admission".to_string(),
            category: Some("Validation".to_string()),
            retryable: false,
        }
    });
    let message = record_outbound_message_deferred_with_metadata(
        &state,
        "partial SDK admission",
        None,
        None,
        Vec::new(),
        false,
        json!({"zmq_rejections": [
            permanent.clone(),
            {"id": "retry", "destination": "destination-retry", "error": {
                "code": "SDK_SECURITY_RATE_LIMITED", "retryable": true
            }}
        ]}),
    )
    .expect("queue broadcast");
    let targets = [terminal_target("retry", "delivered")];
    let report = DispatchReport {
        count: 1,
        receipts: targets.to_vec(),
        ..DispatchReport::default()
    };
    update_outbound_delivery_state(
        &state,
        &message.message_id,
        "sent",
        json!({
            "dispatch_status": "partially_accepted",
            "receipt_pending": true,
            "retry_scheduled": false,
            "reticulumd_dispatch_count": 1,
            "reticulumd_receipt_targets": reticulumd_receipt_targets_json(&targets),
            "zmq_rejections": merged_zmq_rejections(&message, &report)
        }),
    )
    .expect("commit retry admission");
    let pending = message_persistence::current(&state, &message.message_id).expect("current");
    apply_reticulumd_target_statuses(&state, &pending, &targets, targets.len())
        .expect("project admitted delivery");
    drop(state);
    let reopened = AppState::from_sqlite_path(directory.join("state.db")).expect("restart");
    let current = message_persistence::current(&reopened, &message.message_id).expect("durable");
    assert_eq!(current.delivery_state, "sent");
    assert_eq!(current.delivery_metadata["acked"], false);
    assert_eq!(current.delivery_metadata["partial_delivery"], true);
    assert_eq!(
        current.delivery_metadata["failed_destinations"],
        json!(["destination-permanent"])
    );
    assert_eq!(
        current.delivery_metadata["zmq_rejections"],
        json!([permanent])
    );
    assert_eq!(current.delivery_metadata["receipt_pending"], false);
    drop(reopened);
    std::fs::remove_dir_all(directory).expect("cleanup");
}
