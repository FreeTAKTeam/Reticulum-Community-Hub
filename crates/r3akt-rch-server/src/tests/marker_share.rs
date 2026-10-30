use super::pending_broker_requests;
use crate::*;
use axum::http::Request;
use tower::ServiceExt;

#[tokio::test]
async fn marker_share_keeps_destination_policy_and_binary_object_identity() {
    let directory = std::env::temp_dir().join(format!("rch-marker-share-{}", Uuid::new_v4()));
    std::fs::create_dir(&directory).unwrap();
    let db = directory.join("state.db");
    let destination = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    let state = AppState::from_sqlite_path(&db)
        .unwrap()
        .with_api_key("test-key")
        .with_test_reticulumd_source("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
        .with_outbound_identity_allowlist([destination]);
    create_marker(
        State(state.clone()),
        Json(json!({
            "type":"fire", "symbol":"fire", "name":"Ridge", "lat":44.5, "lon":-1.25,
        })),
    )
    .await
    .unwrap();
    let marker = state
        .markers
        .read()
        .unwrap()
        .values()
        .next()
        .unwrap()
        .clone();
    let app = create_app_with_state(state.clone());
    for (id, recipient, authenticated, expected) in [
        (
            marker.object_destination_hash.as_str(),
            destination,
            false,
            StatusCode::UNAUTHORIZED,
        ),
        (
            marker.object_destination_hash.as_str(),
            "bad",
            true,
            StatusCode::UNPROCESSABLE_ENTITY,
        ),
        (
            marker.object_destination_hash.as_str(),
            "cccccccccccccccccccccccccccccccc",
            true,
            StatusCode::FORBIDDEN,
        ),
        (
            "ffffffffffffffffffffffffffffffff",
            destination,
            true,
            StatusCode::NOT_FOUND,
        ),
    ] {
        let mut request = Request::builder()
            .method("POST")
            .uri(format!("/api/markers/{id}/share"))
            .header("content-type", "application/json");
        if authenticated {
            request = request.header("X-API-Key", "test-key");
        }
        let response = app
            .clone()
            .oneshot(
                request
                    .body(Body::from(json!({"destination":recipient}).to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), expected);
        assert!(pending_broker_requests(&db).is_empty());
    }
    let response = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri(format!(
                    "/api/markers/{}/share",
                    marker.object_destination_hash
                ))
                .header("content-type", "application/json")
                .header("X-API-Key", "test-key")
                .body(Body::from(json!({"destination":destination}).to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::ACCEPTED);
    let requests = pending_broker_requests(&db);
    assert_eq!(requests.len(), 1);
    assert_eq!(requests[0]["destination"], destination);
    let fields = &requests[0]["fields"];
    assert!(fields.get("2").is_none());
    assert_eq!(fields["13"]["payload"], marker.api_value());
    assert_eq!(fields["3"][0][1], marker.updated_ts_ms / 1000);
    let entry = r3akt_map_core::telemetry::decode_field(&fields["3"][0][2]).unwrap();
    assert_eq!(entry.telemetry["location"]["latitude"], 44.5);
    assert_eq!(entry.telemetry["location"]["longitude"], -1.25);
    std::fs::remove_dir_all(directory).unwrap();
}
