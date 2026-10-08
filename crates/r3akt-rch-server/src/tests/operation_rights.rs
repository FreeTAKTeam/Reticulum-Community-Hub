use crate::*;
use axum::{
    body::Body,
    http::{Method, Request, StatusCode},
};
use http_body_util::BodyExt;
use rusqlite::Connection;
use tower::ServiceExt;

fn fixture() -> (AppState, PathBuf) {
    let directory = std::env::temp_dir().join(format!("rch-right-http-{}", Uuid::new_v4()));
    std::fs::create_dir(&directory).expect("directory");
    let state = AppState::from_sqlite_path(directory.join("state.db"))
        .expect("state")
        .with_api_key("right-test");
    (state, directory)
}

async fn request(
    state: &AppState,
    method: Method,
    path: &str,
    payload: Value,
    key: &str,
) -> (StatusCode, Value) {
    let response = create_app_with_state(state.clone())
        .oneshot(
            Request::builder()
                .method(method)
                .uri(path)
                .header("X-API-Key", key)
                .header("Content-Type", "application/json")
                .body(Body::from(payload.to_string()))
                .expect("request"),
        )
        .await
        .expect("response");
    let status = response.status();
    let bytes = response
        .into_body()
        .collect()
        .await
        .expect("body")
        .to_bytes();
    (
        status,
        serde_json::from_slice(&bytes).expect("JSON response"),
    )
}

#[tokio::test]
async fn actual_permission_adapters_do_not_decode_or_change_unrelated_history() {
    let (state, directory) = fixture();
    let connection = Connection::open(directory.join("state.db")).expect("database");
    connection.execute_batch(
        "WITH RECURSIVE ids(id) AS (VALUES(1) UNION ALL SELECT id+1 FROM ids WHERE id<100000)
         INSERT INTO rch_identity_announces(destination_hash,payload,last_seen_ts_ms)
         SELECT 'history-'||id,X'C1',0 FROM ids;
         INSERT INTO rch_topics(topic_id,payload) VALUES ('unrelated',X'C1');
         WITH RECURSIVE ids(id) AS (VALUES(1) UNION ALL SELECT id+1 FROM ids WHERE id<10000)
         INSERT INTO rch_subject_operation_rights(subject_type,subject_id,operation,scope_type,scope_id,payload)
         SELECT 'identity','unrelated-'||id,'mission.read','global','',X'C1' FROM ids;"
    ).expect("large malformed history");
    let capability_path = "/api/r3akt/capabilities/AABB/mission.read";
    let (status, granted) = request(
        &state,
        Method::PUT,
        capability_path,
        json!({}),
        "right-test",
    )
    .await;
    assert_eq!(status, StatusCode::OK, "{granted}");
    assert_eq!(granted["identity"], "aabb");
    assert_eq!(granted["capability"], "mission.read");
    assert_eq!(granted["granted"], true);
    let (status, noop) = request(
        &state,
        Method::PUT,
        capability_path,
        json!({}),
        "right-test",
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(noop, granted);
    let (status, revoked) = request(
        &state,
        Method::DELETE,
        capability_path,
        json!({}),
        "right-test",
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(revoked["grant_uid"], granted["grant_uid"]);
    assert_eq!(revoked["granted"], false);
    let payload = json!({"subject_type":" TEAM_MEMBER ","subject_id":" Member-A ",
        "operation":" mission.Read ","scope_type":" MISSION ","scope_id":" Mission-A "});
    let (status, granted) = request(
        &state,
        Method::PUT,
        "/api/r3akt/rights/grants",
        payload.clone(),
        "right-test",
    )
    .await;
    assert_eq!(status, StatusCode::OK, "{granted}");
    assert_eq!(granted["subject_type"], "team_member");
    assert_eq!(granted["subject_id"], "Member-A");
    assert_eq!(granted["operation"], "mission.Read");
    assert_eq!(granted["scope_id"], "Mission-A");
    let (status, noop) = request(
        &state,
        Method::PUT,
        "/api/r3akt/rights/grants",
        payload.clone(),
        "right-test",
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(noop, granted);
    let (status, revoked) = request(
        &state,
        Method::DELETE,
        "/api/r3akt/rights/grants",
        payload,
        "right-test",
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(revoked["grant_uid"], granted["grant_uid"]);
    assert_eq!(revoked["granted"], false);
    let metrics = sqlite_runtime_metrics(&state);
    let rights = &metrics["operation_rights"];
    assert_eq!(rights["committed"], 6);
    assert_eq!(rights["matching_rows_read"], 4);
    assert_eq!(rights["changed_rows_written"], 4);
    assert!(rights["max_decoded_payload_bytes"].as_u64().expect("bytes") < 1024);
    let counts: (i64, i64, i64, i64) = connection
        .query_row(
            "SELECT (SELECT COUNT(*) FROM rch_identity_announces WHERE payload=X'C1'),
         (SELECT COUNT(*) FROM rch_subject_operation_rights WHERE payload=X'C1'),
         (SELECT COUNT(*) FROM rch_identity_capabilities),
         (SELECT COUNT(*) FROM rch_command_results)",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .expect("unchanged unrelated rows");
    assert_eq!(counts, (100_000, 10_000, 0, 0));
    drop(connection);
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[tokio::test]
async fn permission_errors_preserve_http_status_and_commit_boundary() {
    let (state, directory) = fixture();
    let path = "/api/r3akt/rights/grants";
    let valid = json!({"subject_type":"identity","subject_id":"aabb","operation":"mission.read"});
    let (status, _) = request(&state, Method::PUT, path, valid.clone(), "wrong").await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    let mut invalid = valid.clone();
    invalid["subject_type"] = json!("team");
    let (status, _) = request(&state, Method::PUT, path, invalid, "right-test").await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
    let (status, _) = request(&state, Method::PUT, path, valid.clone(), "right-test").await;
    assert_eq!(status, StatusCode::OK);
    let connection = Connection::open(directory.join("state.db")).expect("database");
    connection
        .execute("UPDATE rch_subject_operation_rights SET payload=X'C1'", [])
        .expect("corrupt target");
    let (status, _) = request(&state, Method::DELETE, path, valid, "right-test").await;
    assert_eq!(status, StatusCode::INTERNAL_SERVER_ERROR);
    let committed = sqlite_runtime_metrics(&state)["operation_rights"]["committed"].clone();
    assert_eq!(committed, 1);
    let bytes: Vec<u8> = connection
        .query_row(
            "SELECT payload FROM rch_subject_operation_rights",
            [],
            |row| row.get(0),
        )
        .expect("retained target");
    assert_eq!(bytes, [0xc1]);
    connection
        .execute_batch(
            "DELETE FROM rch_subject_operation_rights;
         CREATE TABLE parent(id INTEGER PRIMARY KEY);
         CREATE TABLE child(id INTEGER REFERENCES parent(id) DEFERRABLE INITIALLY DEFERRED);
         CREATE TRIGGER fail_commit AFTER INSERT ON rch_subject_operation_rights
         BEGIN INSERT INTO child VALUES(42); END;",
        )
        .expect("commit failure");
    let (status, _) = request(
        &state,
        Method::PUT,
        "/api/r3akt/capabilities/aabb/read",
        json!({}),
        "right-test",
    )
    .await;
    assert_eq!(status, StatusCode::INTERNAL_SERVER_ERROR);
    let count: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM rch_subject_operation_rights",
            [],
            |row| row.get(0),
        )
        .expect("rolled back");
    assert_eq!(count, 0);
    assert_eq!(
        sqlite_runtime_metrics(&state)["operation_rights"]["committed"],
        committed
    );
    drop(connection);
    state.kill_switch.write().expect("kill switch").mode = KillSwitchRuntimeMode::Deleting;
    let (status, _) = request(
        &state,
        Method::PUT,
        "/api/r3akt/capabilities/aabb/read",
        json!({}),
        "right-test",
    )
    .await;
    assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}
