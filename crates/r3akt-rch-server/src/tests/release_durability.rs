use super::*;
use crate::*;

fn fixture() -> (AppState, PathBuf) {
    let directory = std::env::temp_dir().join(format!("rch-durability-{}", Uuid::new_v4()));
    std::fs::create_dir(&directory).expect("directory");
    let state = AppState::from_sqlite_path(directory.join("state.db")).expect("state");
    (state, directory)
}

fn deny_inserts(state: &AppState, table: &str) {
    Connection::open(state.sqlite_path.as_ref().expect("database").as_ref()).expect("connection")
        .execute_batch(&format!("CREATE TRIGGER deny_insert BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT, 'fixture failure'); END;"))
        .expect("failure trigger");
}

#[tokio::test]
async fn failed_topic_write_does_not_publish_a_projection() {
    let (state, directory) = fixture();
    deny_inserts(&state, "rch_topics");
    let result = create_topic(
        State(state.clone()),
        Json(
            serde_json::from_value(json!({
                "TopicID": "ops", "TopicName": "Ops", "TopicPath": "ops"
            }))
            .expect("payload"),
        ),
    )
    .await;
    assert!(result.is_err());
    assert!(state.topics.read().expect("topics").is_empty());
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[tokio::test]
async fn failed_marker_and_zone_writes_do_not_publish_projections() {
    for table in ["rch_markers", "rch_zones"] {
        let (state, directory) = fixture();
        deny_inserts(&state, table);
        if table == "rch_markers" {
            assert!(
                create_marker(
                    State(state.clone()),
                    Json(json!({
                        "marker_type": "marker", "symbol": "marker", "lat": 1.0, "lon": 1.0
                    }))
                )
                .await
                .is_err()
            );
            assert!(state.markers.read().expect("markers").is_empty());
        } else {
            assert!(
                create_zone(
                    State(state.clone()),
                    Json(json!({ "name": "Area", "points": [
                {"lat": 1.0, "lon": 1.0}, {"lat": 1.0, "lon": 2.0}, {"lat": 2.0, "lon": 1.0}
            ] }))
                )
                .await
                .is_err()
            );
            assert!(state.zones.read().expect("zones").is_empty());
        }
        std::fs::remove_dir_all(directory).expect("cleanup");
    }
}

#[test]
fn failed_telemetry_or_system_event_write_does_not_publish() {
    for table in ["rch_telemetry_records", "rch_system_events"] {
        let (state, directory) = fixture();
        deny_inserts(&state, table);
        if table == "rch_telemetry_records" {
            assert!(
                state
                    .record_telemetry("peer", json!({"latitude": 1}), 1, None)
                    .is_err()
            );
            assert!(
                state
                    .telemetry_records
                    .read()
                    .expect("telemetry")
                    .is_empty()
            );
        } else {
            assert!(record_system_event(&state, "test", "test", json!({})).is_err());
            assert!(state.system_events.read().expect("events").is_empty());
        }
        std::fs::remove_dir_all(directory).expect("cleanup");
    }
}

#[test]
fn rejected_message_admission_cannot_remain_eligible_for_dispatch() {
    let (state, directory) = fixture();
    deny_inserts(&state, "rch_messages");
    assert!(
        record_outbound_message_deferred_with_metadata(
            &state,
            "fixture",
            None,
            Some("00112233445566778899aabbccddeeff".to_string()),
            Vec::new(),
            false,
            json!({})
        )
        .is_err()
    );
    assert!(state.messages.read().expect("messages").is_empty());
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[test]
fn failed_delivery_metadata_write_keeps_the_committed_projection() {
    for start_attempt in [true, false] {
        let (state, directory) = fixture();
        let admitted = record_outbound_message_deferred_with_metadata(
            &state,
            "fixture",
            None,
            Some("00112233445566778899aabbccddeeff".to_string()),
            Vec::new(),
            false,
            json!({}),
        )
        .expect("admitted");
        deny_inserts(&state, "rch_messages");
        let result = if start_attempt {
            mark_outbound_attempt_started(&state, &admitted.message_id, unix_now_ms()).map(|_| ())
        } else {
            update_outbound_delivery_state(
                &state,
                &admitted.message_id,
                "delivered",
                json!({"acked": true}),
            )
        };
        assert!(result.is_err());
        let current = state.messages.read().expect("messages")[0].clone();
        assert_eq!(current.delivery_state, admitted.delivery_state);
        assert_eq!(current.delivery_metadata, admitted.delivery_metadata);
        std::fs::remove_dir_all(directory).expect("cleanup");
    }
}

fn domain_command(kind: &str, args: Value) -> MissionCommandEnvelope {
    MissionCommandEnvelope {
        command_id: Uuid::new_v4().to_string(),
        source: RchSource::new("fixture"),
        timestamp: Utc::now().to_rfc3339(),
        command_type: kind.to_string(),
        args,
        correlation_id: None,
        topics: Vec::new(),
    }
}

#[test]
fn competing_mission_mutations_read_inside_the_write_transaction() {
    let (state, directory) = fixture();
    command_persistence::mutate(&state, false, |core| {
        r3akt_command_outcome_value(core.handle_command(&domain_command(
            "mission.registry.mission.upsert",
            json!({"uid": "mission", "mission_name": "Original", "description": "Original"}),
        )))
        .map(|result| (result, true))
    })
    .expect("create");
    let second = AppState::from_sqlite_path(directory.join("state.db")).expect("second state");
    let (entered, observed) = std::sync::mpsc::channel();
    let (release, wait) = std::sync::mpsc::channel();
    let first = std::thread::spawn(move || {
        command_persistence::mutate(&state, false, |core| {
            entered.send(()).expect("entered");
            wait.recv().expect("release");
            r3akt_command_outcome_value(core.handle_command(&domain_command(
                "mission.registry.mission.patch",
                json!({"mission_uid": "mission", "patch": {"mission_name": "Accepted name"}}),
            )))
            .map(|result| (result, true))
        })
    });
    observed
        .recv_timeout(Duration::from_secs(2))
        .expect("first loaded");
    let (second_entered, second_observed) = std::sync::mpsc::channel();
    let second = std::thread::spawn(move || {
        command_persistence::mutate(&second, false, |core| {
            second_entered.send(()).expect("second entered");
            r3akt_command_outcome_value(core.handle_command(&domain_command(
                "mission.registry.mission.patch",
                json!({"mission_uid": "mission", "patch": {"description": "Accepted description"}}),
            )))
            .map(|result| (result, true))
        })
    });
    // The old owner loads a stale snapshot here. The corrected owner waits for the first commit.
    let _ = second_observed.recv_timeout(Duration::from_millis(150));
    release.send(()).expect("release");
    first.join().expect("first join").expect("first accepted");
    second
        .join()
        .expect("second join")
        .expect("second accepted");
    let snapshot = RchSqliteStore::open(directory.join("state.db"))
        .expect("reopen")
        .load_r3akt_read_snapshot()
        .expect("snapshot");
    assert_eq!(snapshot.missions[0].mission_name, "Accepted name");
    assert_eq!(snapshot.missions[0].description, "Accepted description");
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[test]
fn stale_telemetry_from_an_independent_state_cannot_replace_a_newer_record() {
    let (first, directory) = fixture();
    let second = AppState::from_sqlite_path(directory.join("state.db")).expect("second");
    first
        .record_telemetry(
            "00112233445566778899aabbccddeeff",
            json!({"latitude": 10}),
            10,
            None,
        )
        .expect("newer");
    second
        .record_telemetry(
            "00112233445566778899aabbccddeeff",
            json!({"latitude": 1}),
            1,
            None,
        )
        .expect("older input");
    let reopened = AppState::from_sqlite_path(directory.join("state.db")).expect("reopen");
    assert_eq!(
        reopened.telemetry_records.read().expect("records")[0].timestamp_s,
        10
    );
    std::fs::remove_dir_all(directory).expect("cleanup");
}

fn attachment_fixture(state: &AppState, directory: &std::path::Path) -> FileAttachmentRecord {
    let path = directory.join("original.bin");
    std::fs::write(&path, b"original bytes").expect("bytes");
    let record = FileAttachmentRecord {
        file_id: 1,
        name: "original.bin".to_string(),
        path: path.to_string_lossy().to_string(),
        category: "file".to_string(),
        size: 14,
        media_type: None,
        topic_id: None,
        created_ts_ms: 1,
        updated_ts_ms: 1,
    };
    persist_file_attachment_row(state, &record).expect("persist");
    record
}

#[test]
fn failed_attachment_delete_preserves_durable_row_and_original_bytes() {
    let (state, directory) = fixture();
    let record = attachment_fixture(&state, &directory);
    Connection::open(directory.join("state.db")).expect("DB").execute_batch(
        "CREATE TRIGGER deny_delete BEFORE DELETE ON rch_file_attachments BEGIN SELECT RAISE(ABORT, 'fixture failure'); END;"
    ).expect("trigger");
    assert!(delete_attachment_record(&state, 1, "file").is_err());
    assert_eq!(
        get_attachment_record(&state, 1, "file").expect("row"),
        record
    );
    assert_eq!(
        std::fs::read(&record.path).expect("original file remains"),
        b"original bytes"
    );
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[tokio::test]
async fn rejected_unban_keeps_policy_and_durable_ban() {
    let (state, directory) = fixture();
    let _response = upsert_identity_status(state.clone(), "peer".to_string(), Some(true), None)
        .await
        .expect("ban");
    deny_inserts(&state, "rch_identity_states");
    assert!(
        upsert_identity_status(state.clone(), "peer".to_string(), Some(false), None)
            .await
            .is_err()
    );
    assert!(inbound_identity_blocked(&state, "peer").expect("current policy"));
    let reopened = AppState::from_sqlite_path(directory.join("state.db")).expect("reopen");
    assert!(inbound_identity_blocked(&reopened, "peer").expect("durable policy"));
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[test]
fn malformed_attachment_snapshot_is_an_observable_error() {
    let (state, directory) = fixture();
    attachment_fixture(&state, &directory);
    let database = Connection::open(directory.join("state.db")).expect("DB");
    database
        .execute(
            "UPDATE rch_file_attachments SET payload = ?1",
            [vec![0xc1_u8]],
        )
        .expect("corrupt fixture");
    let store = RchSqliteStore::open(directory.join("state.db")).expect("store");
    assert!(
        store.load_snapshot().is_err(),
        "malformed attachments cannot become successful empty data"
    );
    assert_eq!(
        database
            .query_row("SELECT COUNT(*) FROM rch_file_attachments", [], |row| row
                .get::<_, u64>(
                0
            ))
            .expect("rows"),
        1
    );
    drop(store);
    drop(database);
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[test]
fn receipt_after_candidate_collection_prevents_redispatch_and_stale_retry() {
    let (state, directory) = fixture();
    let mut candidate = record_outbound_message_deferred_with_metadata(
        &state,
        "fixture",
        None,
        Some("00112233445566778899aabbccddeeff".to_string()),
        Vec::new(),
        false,
        json!({}),
    )
    .expect("admit");
    candidate.delivery_method = "direct".to_string();
    {
        let mut messages = state.messages.write().expect("messages");
        messages[0] = candidate.clone();
    }
    update_outbound_delivery_state(
        &state,
        &candidate.message_id,
        "delivered",
        json!({"acked": true}),
    )
    .expect("receipt");
    mark_outbound_attempt_started(&state, &candidate.message_id, unix_now_ms())
        .expect("late attempt");
    schedule_zmq_pre_admission_retry(&state, &candidate, &DispatchReport::default())
        .expect("late retry");
    assert_eq!(
        state.messages.read().expect("messages")[0].delivery_state,
        "delivered"
    );
    let reopened = AppState::from_sqlite_path(directory.join("state.db")).expect("reopen");
    assert_eq!(
        reopened.messages.read().expect("messages")[0].delivery_state,
        "delivered"
    );
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[test]
fn receipt_after_attempt_validation_wins_over_dispatch_completion() {
    let (state, directory) = fixture();
    let admitted = record_outbound_message_deferred_with_metadata(
        &state,
        "fixture",
        None,
        Some("00112233445566778899aabbccddeeff".to_string()),
        Vec::new(),
        false,
        json!({}),
    )
    .expect("admit");
    let now = unix_now_ms();
    let attempted = claim_outbound_attempt(&state, &admitted.message_id, Some(&admitted), now)
        .expect("claim")
        .expect("eligible");
    assert!(outbound_dispatch_attempt_still_current(&state, &attempted, now).expect("validated"));
    update_outbound_delivery_state(
        &state,
        &attempted.message_id,
        "delivered",
        json!({"acked": true}),
    )
    .expect("receipt");
    assert!(
        update_dispatch_delivery_state(&state, &attempted, "sent", json!({"acked": false}))
            .expect("late completion")
            .is_none()
    );
    assert!(
        schedule_zmq_pre_admission_retry(&state, &attempted, &DispatchReport::default())
            .expect("late retry")
            .is_none()
    );
    let failed = mark_outbound_dispatch_failed(&state, &attempted, "send_error".to_string())
        .expect("late failure");
    assert_eq!(failed.delivery_state, "delivered");
    assert!(failed.delivery_metadata["acked"].as_bool().expect("ack"));
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[tokio::test]
async fn separate_states_preserve_disjoint_marker_and_zone_patches() {
    let (first, directory) = fixture();
    create_marker(
        State(first.clone()),
        Json(json!({
            "marker_type": "marker", "symbol": "marker", "name": "Original", "lat": 1.0, "lon": 1.0
        })),
    )
    .await
    .expect("marker");
    create_zone(
        State(first.clone()),
        Json(json!({ "name": "Original", "points": [
        {"lat": 1.0, "lon": 1.0}, {"lat": 1.0, "lon": 2.0}, {"lat": 2.0, "lon": 1.0}
    ] })),
    )
    .await
    .expect("zone");
    let second = AppState::from_sqlite_path(directory.join("state.db")).expect("second");
    let marker_id = first
        .markers
        .read()
        .expect("markers")
        .keys()
        .next()
        .expect("marker ID")
        .clone();
    let zone_id = first
        .zones
        .read()
        .expect("zones")
        .keys()
        .next()
        .expect("zone ID")
        .clone();
    let _response = patch_marker(
        Path(marker_id.clone()),
        State(second.clone()),
        Json(MarkerUpdatePayload {
            name: "Accepted name".to_string(),
        }),
    )
    .await
    .expect("rename");
    let _response = patch_marker_position(
        Path(marker_id.clone()),
        State(first.clone()),
        Json(MarkerPositionPayload { lat: 5.0, lon: 6.0 }),
    )
    .await
    .expect("position");
    let _response = patch_zone(
        Path(zone_id.clone()),
        State(second.clone()),
        Json(json!({"name": "Accepted area"})),
    )
    .await
    .expect("rename zone");
    let _response = patch_zone(
        Path(zone_id.clone()),
        State(first.clone()),
        Json(json!({"points": [
            {"lat": 5.0, "lon": 1.0}, {"lat": 5.0, "lon": 2.0}, {"lat": 6.0, "lon": 1.0}
        ]})),
    )
    .await
    .expect("points");
    let reopened = AppState::from_sqlite_path(directory.join("state.db")).expect("reopen");
    assert_eq!(
        reopened.markers.read().expect("markers")[&marker_id].name,
        "Accepted name"
    );
    assert_eq!(
        reopened.zones.read().expect("zones")[&zone_id].name,
        "Accepted area"
    );
    let _response = delete_marker(Path(marker_id.clone()), State(second))
        .await
        .expect("delete");
    assert!(
        patch_marker_position(
            Path(marker_id),
            State(first),
            Json(MarkerPositionPayload { lat: 7.0, lon: 8.0 })
        )
        .await
        .is_err()
    );
    assert!(
        AppState::from_sqlite_path(directory.join("state.db"))
            .expect("reopen")
            .markers
            .read()
            .expect("markers")
            .is_empty()
    );
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[test]
fn deleted_attachment_cannot_be_recreated_by_a_stale_topic_patch() {
    let (state, directory) = fixture();
    let original = attachment_fixture(&state, &directory);
    let mut other = RchSqliteStore::open(directory.join("state.db")).expect("other owner");
    other
        .take_file_attachment(original.file_id, "file")
        .expect("delete")
        .expect("row");
    assert!(
        patch_attachment_topic(&state, original.file_id, "file", Some("ops".to_string())).is_err()
    );
    assert!(
        other
            .load_file_attachment(original.file_id, "file")
            .expect("read")
            .is_none()
    );
    drop(other);
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[test]
fn command_commit_failure_rolls_back_and_releases_the_reservation() {
    let (state, directory) = fixture();
    let database = Connection::open(directory.join("state.db")).expect("DB");
    database.execute_batch("CREATE TABLE fixture_parent (id INTEGER PRIMARY KEY);
        CREATE TABLE fixture_commit_fault (parent INTEGER REFERENCES fixture_parent(id) DEFERRABLE INITIALLY DEFERRED);
        CREATE TRIGGER fail_commit AFTER INSERT ON rch_missions BEGIN INSERT INTO fixture_commit_fault VALUES (1); END;").expect("commit failure fixture");
    let mut store = RchSqliteStore::open(directory.join("state.db")).expect("store");
    let mut transaction = store.begin_r3akt_command().expect("reserved");
    r3akt_command_outcome_value(transaction.core_mut().handle_command(&domain_command(
        "mission.registry.mission.upsert",
        json!({"uid": "uncommitted", "mission_name": "Rejected at commit"}),
    )))
    .expect("valid domain mutation");
    assert!(
        transaction.commit().is_err(),
        "deferred constraint fails at COMMIT"
    );
    assert!(
        store
            .load_r3akt_read_snapshot()
            .expect("read after failed commit")
            .missions
            .is_empty()
    );
    assert_eq!(
        database
            .query_row("SELECT COUNT(*) FROM fixture_commit_fault", [], |row| row
                .get::<_, u64>(
                0
            ))
            .expect("rolled back"),
        0
    );
    drop(
        store
            .begin_r3akt_command()
            .expect("next reservation succeeds"),
    );
    drop(store);
    drop(database);
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}

async fn idempotent_marker_request(
    state: &AppState,
    key: &str,
    latitude: f64,
) -> (StatusCode, Value) {
    let response = create_app_with_state(state.clone().with_api_key("fixture-key")).oneshot(
        axum::http::Request::builder().method(Method::POST).uri("/api/markers")
            .header("X-API-Key", "fixture-key").header("Idempotency-Key", key)
            .header("Content-Type", "application/json").body(Body::from(json!({
                "marker_type": "marker", "symbol": "marker", "name": "TAK fixture", "lat": latitude, "lon": 2.0
            }).to_string())).expect("request")).await.expect("response");
    let status = response.status();
    let body = serde_json::from_slice(
        &response
            .into_body()
            .collect()
            .await
            .expect("body")
            .to_bytes(),
    )
    .expect("JSON");
    (status, body)
}

#[tokio::test]
async fn marker_replay_after_committed_response_loss_and_restart_creates_one_record_and_activity() {
    let (first, directory) = fixture();
    let (status, committed) = idempotent_marker_request(&first, "stable-cot-fixture", 1.0).await;
    assert_eq!(status, StatusCode::CREATED);
    // The bridge did not receive this committed response. It retries through a
    // fresh runtime, so an in-memory request cache cannot satisfy the contract.
    let activity_count = first.system_events.read().expect("events").len();
    let second = AppState::from_sqlite_path(directory.join("state.db")).expect("restart");
    let (status, replayed) = idempotent_marker_request(&second, "stable-cot-fixture", 1.0).await;
    assert_eq!(status, StatusCode::CREATED);
    assert_eq!(replayed, committed);
    assert_eq!(second.markers.read().expect("markers").len(), 1);
    assert_eq!(
        second.system_events.read().expect("events").len(),
        activity_count
    );
    let (status, _) = idempotent_marker_request(&second, "stable-cot-fixture", 9.0).await;
    assert_eq!(
        status,
        StatusCode::CONFLICT,
        "a key cannot be reused for a different operation"
    );
    let reopened = AppState::from_sqlite_path(directory.join("state.db")).expect("reopen");
    assert_eq!(reopened.markers.read().expect("markers").len(), 1);
    assert_eq!(
        reopened
            .markers
            .read()
            .expect("markers")
            .values()
            .next()
            .expect("marker")
            .lat
            .to_bits(),
        1.0_f64.to_bits()
    );
    std::fs::remove_dir_all(directory).expect("cleanup");
}

async fn inline_receipt_during_dispatch(fail_dispatch: bool) {
    let (state, directory) = fixture();
    let listener = StdTcpListener::bind("127.0.0.1:0").expect("listener");
    let endpoint = listener.local_addr().expect("address").to_string();
    let (entered, observed) = std::sync::mpsc::channel();
    let (release, wait) = std::sync::mpsc::channel();
    let rpc = std::thread::spawn(move || {
        let (mut stream, _) = listener.accept().expect("accept");
        stream
            .set_read_timeout(Some(Duration::from_secs(2)))
            .expect("timeout");
        let request = read_http_request(&mut stream);
        let decoded: ReticulumdRpcRequest = decode_reticulumd_frame(&parse_http_body(&request));
        entered.send(()).expect("dispatch started");
        wait.recv_timeout(Duration::from_secs(2))
            .expect("release dispatch");
        let response = ReticulumdRpcResponse {
            id: decoded.id,
            result: (!fail_dispatch).then(|| json!({"message_id": "fixture"})),
            error: fail_dispatch.then(|| ReticulumdRpcError {
                code: "SEND_ERROR".to_string(),
                message: "fixture send error".to_string(),
                ..ReticulumdRpcError::default()
            }),
        };
        let body = encode_reticulumd_frame(&response);
        stream.write_all(format!("HTTP/1.1 200 OK\r\nContent-Type: application/msgpack\r\nContent-Length: {}\r\n\r\n", body.len()).as_bytes()).expect("headers");
        stream.write_all(&body).expect("response");
    });
    let state = state.with_reticulumd_rpc(endpoint, "fixture-source");
    let destination = "00112233445566778899aabbccddeeff";
    let sender = state.clone();
    let send = std::thread::spawn(move || {
        record_outbound_message_with_metadata_mode(
            &sender,
            "receipt barrier",
            None,
            Some(destination.to_string()),
            Vec::new(),
            false,
            json!({"max_attempts": 0}),
            OutboundDispatchMode::Inline,
        )
    });
    observed
        .recv_timeout(Duration::from_secs(2))
        .expect("dispatch blocks");
    let message_id = state.messages.read().expect("messages")[0]
        .message_id
        .clone();
    mark_reticulumd_status_delivery_receipt(&state, &message_id, "delivered")
        .expect("SDK receipt projection");
    release.send(()).expect("release");
    let completed = send.join().expect("send thread");
    rpc.join().expect("RPC thread");
    let current = state.messages.read().expect("messages")[0].clone();
    assert_eq!(
        current.delivery_state, "delivered",
        "late inline result cannot downgrade a receipt"
    );
    assert_eq!(current.delivery_metadata["acked"], true);
    assert_eq!(
        completed.expect("already delivered send").delivery_state,
        "delivered"
    );
    assert!(
        !state
            .system_events
            .read()
            .expect("events")
            .iter()
            .any(|event| matches!(
                event.event_type.as_str(),
                "message_delivery_failed" | "message_delivery_retrying"
            ))
    );
    let reopened = AppState::from_sqlite_path(directory.join("state.db")).expect("restart");
    assert_eq!(
        reopened.messages.read().expect("durable messages")[0].delivery_state,
        "delivered"
    );
    drop(reopened);
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[tokio::test]
async fn inline_success_cannot_overwrite_a_receipt_during_dispatch() {
    inline_receipt_during_dispatch(false).await;
}

#[tokio::test]
async fn inline_error_cannot_overwrite_a_receipt_during_dispatch() {
    inline_receipt_during_dispatch(true).await;
}

#[tokio::test]
async fn accepted_moderation_reports_success_when_optional_enrichment_is_malformed() {
    let (state, directory) = fixture();
    let database = Connection::open(directory.join("state.db")).expect("DB");
    database
        .execute(
            "INSERT INTO rch_identity_announces (destination_hash, payload, last_seen_ts_ms, normalized_destination_hash) VALUES (?1, ?2, 0, ?1)",
            rusqlite::params!["peer", vec![0xc1_u8]],
        )
        .expect("malformed relevant annotation");
    let Json(response) =
        upsert_identity_status(state.clone(), "peer".to_string(), Some(true), None)
            .await
            .expect("accepted ban");
    assert_eq!(response["IsBanned"], true);
    assert!(inbound_identity_blocked(&state, "peer").expect("policy"));
    let store = RchSqliteStore::open(directory.join("state.db")).expect("reopen");
    assert!(store.load_identity_states().expect("durable states")[0].is_banned);
    assert!(
        state
            .system_events
            .read()
            .expect("events")
            .iter()
            .any(|event| event.event_type == "identity_annotation_failed")
    );
    drop(store);
    drop(database);
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[tokio::test]
async fn mixed_case_roster_leave_removes_the_durable_client() {
    let (state, directory) = fixture();
    let _response = join_client(
        State(state.clone()),
        Query(IdentityQuery {
            identity: "PeEr".to_string(),
        }),
    )
    .await
    .expect("join");
    let Json(removed) = leave_client(
        State(state.clone()),
        Query(IdentityQuery {
            identity: "PeEr".to_string(),
        }),
    )
    .await
    .expect("leave");
    assert!(removed);
    let reopened = AppState::from_sqlite_path(directory.join("state.db")).expect("restart");
    assert!(
        reopened.clients.read().expect("clients").is_empty(),
        "a removed mixed-case identity cannot reappear after restart"
    );
    drop(reopened);
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[tokio::test]
async fn roster_whitespace_uses_the_same_key_before_and_after_restart() {
    for identity in ["\tPeEr\n", "\u{2003}PeEr\u{00a0}"] {
        let (state, directory) = fixture();
        let _response = join_client(
            State(state.clone()),
            Query(IdentityQuery {
                identity: identity.to_string(),
            }),
        )
        .await
        .expect("join");
        let Json(removed) = leave_client(
            State(state.clone()),
            Query(IdentityQuery {
                identity: "peer".to_string(),
            }),
        )
        .await
        .expect("leave");
        assert!(removed);
        let reopened = AppState::from_sqlite_path(directory.join("state.db")).expect("restart");
        assert!(
            reopened.clients.read().expect("clients").is_empty(),
            "whitespace aliases cannot resurrect"
        );
        drop(reopened);
        drop(state);
        std::fs::remove_dir_all(directory).expect("cleanup");
    }
}

#[tokio::test]
async fn roster_upsert_and_delete_coalesce_legacy_whitespace_aliases() {
    for update in [true, false] {
        let (state, directory) = fixture();
        let database = Connection::open(directory.join("state.db")).expect("DB");
        for identity in ["peer", "\tPeEr\n", "\u{2003}PEER\u{00a0}"] {
            let record = CoreClientRecord::from(ClientRecord::new(identity.to_string(), 1));
            database
                .execute(
                    "INSERT INTO rch_clients (identity, payload) VALUES (?1, ?2)",
                    rusqlite::params![identity, rmp_serde::to_vec_named(&record).expect("payload")],
                )
                .expect("legacy alias");
        }
        let mut store = RchSqliteStore::open(directory.join("state.db")).expect("store");
        if update {
            let record = CoreClientRecord::from(ClientRecord::new("\tPeEr\n".to_string(), 2));
            store.upsert_client(&record).expect("update aliases");
        } else {
            store.delete_client("peer").expect("delete aliases");
        }
        assert_eq!(
            database
                .query_row("SELECT COUNT(*) FROM rch_clients", [], |row| row
                    .get::<_, u64>(0))
                .expect("row count"),
            u64::from(update)
        );
        drop(store);
        drop(database);
        let reopened = AppState::from_sqlite_path(directory.join("state.db")).expect("restart");
        assert_eq!(
            reopened.clients.read().expect("clients").len(),
            usize::from(update)
        );
        drop(reopened);
        drop(state);
        std::fs::remove_dir_all(directory).expect("cleanup");
    }
}
