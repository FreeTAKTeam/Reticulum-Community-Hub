#![allow(clippy::too_many_lines)]

use std::path::PathBuf;

use axum::body::Body;
use axum::http::{Method, Request, StatusCode};
use http_body_util::BodyExt;
use r3akt_rch_server::{AppState, create_app_with_state};
use serde_json::{Value, json};
use tower::ServiceExt;
use uuid::Uuid;

const API_KEY: &str = "secret";

#[tokio::test]
async fn major_routes_expose_docs_auth_runtime_and_empty_state() {
    let (_db_path, app) = test_app();

    assert_status(
        &app,
        Method::GET,
        "/openapi.json",
        None,
        false,
        StatusCode::OK,
    )
    .await;
    assert_status(
        &app,
        Method::GET,
        "/openapi.yaml",
        None,
        false,
        StatusCode::OK,
    )
    .await;
    assert_status(&app, Method::GET, "/Help", None, false, StatusCode::OK).await;
    assert_status(&app, Method::GET, "/Examples", None, false, StatusCode::OK).await;
    assert_status(
        &app,
        Method::GET,
        "/api/v1/app/info",
        None,
        false,
        StatusCode::OK,
    )
    .await;

    assert_status(
        &app,
        Method::GET,
        "/Status",
        None,
        false,
        StatusCode::UNAUTHORIZED,
    )
    .await;

    for uri in [
        "/api/v1/auth/validate",
        "/Status",
        "/diagnostics/runtime",
        "/Control/Status",
        "/Events",
        "/Telemetry?since=0",
        "/Reticulum/Discovery",
        "/Reticulum/Interfaces/Capabilities",
        "/Config",
        "/Reticulum/Config",
        "/api/rem/peers",
        "/Client",
        "/Identities",
        "/Topic",
        "/Subscriber",
        "/Chat/Messages",
        "/File",
        "/Image",
        "/checklists",
        "/api/r3akt/events",
        "/api/r3akt/snapshots",
        "/api/r3akt/rights/definitions",
        "/api/r3akt/rights/subjects",
        "/api/r3akt/rights/grants",
        "/api/r3akt/rights/mission-access",
    ] {
        assert_status(&app, Method::GET, uri, None, true, StatusCode::OK).await;
    }

    let (_, validated) = request_text_json(
        &app,
        Method::POST,
        "/Config/Validate",
        "[general]\nname = rch\n",
        true,
    )
    .await;
    assert_eq!(validated.get("valid").and_then(Value::as_bool), Some(true));
}

#[tokio::test]
async fn user_topic_chat_identity_flow_persists_across_restart() {
    let (db_path, app) = test_app();

    post_json_ok(
        &app,
        "/internal/identity-announce",
        json!({
            "Identity": "rem-dest",
            "AnnouncedIdentityHash": "rem-peer",
            "DisplayName": "REM Field Phone",
            "SourceInterface": "tcp_server",
            "AnnounceCapabilities": ["commands", "telephony"],
        }),
        false,
    )
    .await;

    assert_status(
        &app,
        Method::POST,
        "/RTH?identity=generic-peer",
        None,
        true,
        StatusCode::OK,
    )
    .await;

    post_json_ok(
        &app,
        "/Topic",
        json!({
            "TopicID": "ops",
            "TopicName": "Operations",
            "TopicPath": "/ops",
            "TopicDescription": "Operations channel",
        }),
        true,
    )
    .await;

    post_json_ok(
        &app,
        "/Topic/Subscribe",
        json!({
            "TopicID": "ops",
            "Destination": "rem-dest",
            "DisplayName": "REM Field Phone",
        }),
        true,
    )
    .await;

    let (_, message_result) = request_json(
        &app,
        Method::POST,
        "/Message",
        Some(json!({
            "Content": "Topic message through /Message",
            "TopicID": "ops",
        })),
        true,
    )
    .await;
    assert_eq!(
        message_result.get("sent").and_then(Value::as_bool),
        Some(true)
    );

    for payload in [
        json!({
            "Content": "Broadcast hello",
            "Scope": "broadcast",
        }),
        json!({
            "Content": "Topic hello",
            "Scope": "topic",
            "TopicID": "ops",
        }),
        json!({
            "Content": "Direct hello",
            "Scope": "dm",
            "Destination": "rem-dest",
        }),
    ] {
        let (_, created) =
            request_json(&app, Method::POST, "/Chat/Message", Some(payload), true).await;
        assert_eq!(created.get("State").and_then(Value::as_str), Some("queued"));
    }

    let (_, messages) =
        request_json(&app, Method::GET, "/Chat/Messages?limit=10", None, true).await;
    assert_chat_scopes(&messages, ["broadcast", "topic", "dm"]);

    let restarted = create_app_with_state(
        AppState::from_sqlite_path(&db_path)
            .expect("state should reopen persisted sqlite database")
            .with_api_key(API_KEY),
    );

    let (_, peers) = request_json(&restarted, Method::GET, "/api/rem/peers", None, true).await;
    assert!(
        json_len(&peers) >= 1,
        "expected persisted REM peer, got {peers}"
    );

    let (_, clients) = request_json(&restarted, Method::GET, "/Client", None, true).await;
    assert!(
        contains_text(&clients, "generic-peer"),
        "expected RTH client in {clients}"
    );

    let (_, topics) = request_json(&restarted, Method::GET, "/Topic", None, true).await;
    assert!(contains_text(&topics, "ops"), "expected topic in {topics}");

    let (_, subscribers) = request_json(&restarted, Method::GET, "/Subscriber", None, true).await;
    assert!(
        contains_text(&subscribers, "rem-dest"),
        "expected subscriber in {subscribers}"
    );

    let (_, restarted_messages) = request_json(
        &restarted,
        Method::GET,
        "/Chat/Messages?limit=10",
        None,
        true,
    )
    .await;
    assert_chat_scopes(&restarted_messages, ["broadcast", "topic", "dm"]);
}

#[tokio::test]
async fn major_domain_collections_accept_create_and_list_operations() {
    let (_db_path, app) = test_app();

    post_json_status(
        &app,
        "/api/markers",
        json!({
            "type": "marker",
            "symbol": "marker",
            "name": "Forward CP",
            "category": "command",
            "lat": 45.5001,
            "lon": -63.2001,
            "notes": "Release suite marker",
        }),
        true,
        StatusCode::CREATED,
    )
    .await;

    post_json_status(
        &app,
        "/api/zones",
        json!({
            "name": "Primary search zone",
            "points": [
                {"lat": 45.501, "lon": -63.201},
                {"lat": 45.501, "lon": -63.199},
                {"lat": 45.499, "lon": -63.199},
                {"lat": 45.499, "lon": -63.201}
            ],
        }),
        true,
        StatusCode::CREATED,
    )
    .await;

    post_json_ok(
        &app,
        "/checklists/templates",
        json!({
            "template": {
                "uid": "template-1",
                "template_name": "Initial response",
                "description": "Initial response actions",
                "columns": [
                    {
                        "column_name": "Due",
                        "column_type": "RELATIVE_TIME",
                        "column_editable": false,
                        "is_removable": false,
                        "system_key": "DUE_RELATIVE_DTG"
                    },
                    {"name": "Task", "column_type": "SHORT_STRING"}
                ]
            },
        }),
        true,
    )
    .await;

    post_json_ok(
        &app,
        "/Topic",
        json!({
            "TopicID": "ops",
            "TopicName": "Operations",
            "TopicPath": "/ops",
            "TopicDescription": "Operations channel",
        }),
        true,
    )
    .await;

    post_json_ok(
        &app,
        "/api/r3akt/missions",
        json!({
            "uid": "mission-1",
            "mission_name": "Release suite mission",
            "description": "Mission used by release integration tests",
            "topic_id": "ops",
            "default_role": "MISSION_SUBSCRIBER",
        }),
        true,
    )
    .await;

    post_json_ok(
        &app,
        "/checklists/offline",
        json!({
            "checklist_uid": "checklist-1",
            "mission_uid": "mission-1",
            "template_uid": "template-1",
            "origin_type": "BLANK_TEMPLATE",
            "name": "Team alpha response",
            "columns": [
                {
                    "column_name": "Due",
                    "column_type": "RELATIVE_TIME",
                    "column_editable": false,
                    "is_removable": false,
                    "system_key": "DUE_RELATIVE_DTG"
                },
                {"name": "Task", "column_type": "SHORT_STRING"}
            ],
        }),
        true,
    )
    .await;

    post_json_ok(
        &app,
        "/api/r3akt/teams",
        json!({
            "uid": "team-1",
            "mission_uid": "mission-1",
            "team_name": "Alpha",
            "color": "GREEN",
            "team_description": "Release suite team",
        }),
        true,
    )
    .await;

    post_json_ok(
        &app,
        "/api/r3akt/team-members",
        json!({
            "uid": "member-1",
            "team_uid": "team-1",
            "rns_identity": "member-rns-1",
            "display_name": "Responder One",
            "callsign": "Alpha One",
            "role": "TEAM_MEMBER",
        }),
        true,
    )
    .await;

    post_json_ok(
        &app,
        "/api/r3akt/assets",
        json!({
            "asset_uid": "asset-1",
            "team_member_uid": "member-1",
            "name": "Responder vehicle",
            "asset_type": "vehicle",
            "status": "AVAILABLE",
            "notes": "Release suite asset",
        }),
        true,
    )
    .await;

    post_json_ok(
        &app,
        "/api/EmergencyActionMessage",
        json!({
            "callsign": "eam-1",
            "team_member_uid": "member-1",
            "team_uid": "team-1",
            "reported_by": "Release suite",
            "security_status": "Green",
            "capability_status": "Green",
            "preparedness_status": "Green",
        }),
        true,
    )
    .await;

    for (uri, needle) in [
        ("/api/markers", "Forward CP"),
        ("/api/zones", "Primary search zone"),
        ("/checklists/templates", "template-1"),
        ("/checklists", "checklist-1"),
        ("/api/r3akt/missions", "mission-1"),
        ("/api/r3akt/teams", "team-1"),
        ("/api/r3akt/assets", "asset-1"),
        ("/api/EmergencyActionMessage", "eam-1"),
    ] {
        let (_, listed) = request_json(&app, Method::GET, uri, None, true).await;
        assert!(
            contains_text(&listed, needle),
            "expected {needle} in {uri}: {listed}"
        );
    }
}

fn test_app() -> (PathBuf, axum::Router) {
    let db_path =
        std::env::temp_dir().join(format!("r3akt-release-suite-{}.sqlite3", Uuid::new_v4()));
    let state = AppState::from_sqlite_path(&db_path)
        .expect("state should open sqlite database")
        .with_api_key(API_KEY);
    (db_path, create_app_with_state(state))
}

async fn assert_status(
    app: &axum::Router,
    method: Method,
    uri: &str,
    body: Option<Value>,
    auth: bool,
    expected: StatusCode,
) {
    let (status, bytes) = request_bytes(app, method, uri, body, auth).await;
    assert_eq!(
        status,
        expected,
        "{uri} returned {status}; body: {}",
        String::from_utf8_lossy(&bytes)
    );
}

async fn post_json_ok(app: &axum::Router, uri: &str, body: Value, auth: bool) -> Value {
    post_json_status(app, uri, body, auth, StatusCode::OK).await
}

async fn post_json_status(
    app: &axum::Router,
    uri: &str,
    body: Value,
    auth: bool,
    expected: StatusCode,
) -> Value {
    let (status, value) = request_json(app, Method::POST, uri, Some(body), auth).await;
    assert_eq!(status, expected, "{uri} returned {status}; body: {value}");
    value
}

async fn request_json(
    app: &axum::Router,
    method: Method,
    uri: &str,
    body: Option<Value>,
    auth: bool,
) -> (StatusCode, Value) {
    let (status, bytes) = request_bytes(app, method, uri, body, auth).await;
    let value = if bytes.is_empty() {
        Value::Null
    } else {
        serde_json::from_slice(&bytes).unwrap_or_else(|error| {
            panic!(
                "{uri} returned non-JSON body: {error}; body: {}",
                String::from_utf8_lossy(&bytes)
            )
        })
    };
    (status, value)
}

async fn request_text_json(
    app: &axum::Router,
    method: Method,
    uri: &str,
    body: &str,
    auth: bool,
) -> (StatusCode, Value) {
    let mut builder = Request::builder().method(method).uri(uri);
    if auth {
        builder = builder.header("X-API-Key", API_KEY);
    }

    let request = builder
        .header("content-type", "text/plain")
        .body(Body::from(body.to_string()))
        .expect("request should build");

    let response = app
        .clone()
        .oneshot(request)
        .await
        .expect("router request should complete");
    let status = response.status();
    let bytes = response
        .into_body()
        .collect()
        .await
        .expect("response body should collect")
        .to_bytes();
    let value = serde_json::from_slice(&bytes).unwrap_or_else(|error| {
        panic!(
            "{uri} returned non-JSON body: {error}; body: {}",
            String::from_utf8_lossy(&bytes)
        )
    });
    (status, value)
}

async fn request_bytes(
    app: &axum::Router,
    method: Method,
    uri: &str,
    body: Option<Value>,
    auth: bool,
) -> (StatusCode, Vec<u8>) {
    let mut builder = Request::builder().method(method).uri(uri);
    if auth {
        builder = builder.header("X-API-Key", API_KEY);
    }

    let request = if let Some(body) = body {
        builder
            .header("content-type", "application/json")
            .body(Body::from(body.to_string()))
            .expect("request should build")
    } else {
        builder.body(Body::empty()).expect("request should build")
    };

    let response = app
        .clone()
        .oneshot(request)
        .await
        .expect("router request should complete");
    let status = response.status();
    let bytes = response
        .into_body()
        .collect()
        .await
        .expect("response body should collect")
        .to_bytes()
        .to_vec();
    (status, bytes)
}

fn assert_chat_scopes<const N: usize>(messages: &Value, expected_scopes: [&str; N]) {
    for expected_scope in expected_scopes {
        assert!(
            messages
                .as_array()
                .expect("chat messages should be an array")
                .iter()
                .any(|message| message.get("Scope").and_then(Value::as_str) == Some(expected_scope)),
            "expected chat scope {expected_scope} in {messages}"
        );
    }
}

fn json_len(value: &Value) -> usize {
    value.as_array().map_or_else(
        || value.as_object().map_or(0, serde_json::Map::len),
        Vec::len,
    )
}

fn contains_text(value: &Value, needle: &str) -> bool {
    value.to_string().contains(needle)
}
