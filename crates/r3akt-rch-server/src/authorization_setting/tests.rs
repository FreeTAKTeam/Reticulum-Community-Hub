use crate::AppState;
use axum::body::Body;
use axum::http::{Method, Request, StatusCode};
use http_body_util::BodyExt;
use serde_json::{Value, json};
use tower::ServiceExt;

const PATH: &str = "/api/r3akt/settings/authorization";

fn fixture() -> (std::path::PathBuf, AppState) {
    let dir = std::env::temp_dir().join(format!("rch-auth-setting-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(&dir).expect("temp dir");
    let state = AppState::from_sqlite_path(dir.join("rch.db"))
        .expect("state")
        .with_api_key("secret");
    (dir, state)
}

async fn call(
    state: &AppState,
    method: Method,
    body: Option<Value>,
    api_key: Option<&str>,
) -> (StatusCode, Value) {
    let mut builder = Request::builder()
        .method(method)
        .uri(PATH)
        .header("Content-Type", "application/json");
    if let Some(key) = api_key {
        builder = builder.header("X-API-Key", key);
    }
    let body = body.map_or_else(Body::empty, |value| Body::from(value.to_string()));
    let response = crate::create_app_with_state(state.clone())
        .oneshot(builder.body(body).expect("request"))
        .await
        .expect("response");
    let status = response.status();
    let bytes = response
        .into_body()
        .collect()
        .await
        .expect("body")
        .to_bytes();
    let value = serde_json::from_slice(&bytes).unwrap_or(Value::Null);
    (status, value)
}

#[tokio::test]
async fn authorization_setting_reads_default_persists_changes_and_validates_input() {
    let (dir, state) = fixture();
    let key = Some("secret");

    let (status, body) = call(&state, Method::GET, None, key).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body, json!({ "authorization_required": false }));

    let (status, body) = call(
        &state,
        Method::PUT,
        Some(json!({ "authorization_required": true })),
        key,
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body, json!({ "authorization_required": true }));

    // A restarted server reads the persisted value.
    let restarted = AppState::from_sqlite_path(dir.join("rch.db"))
        .expect("state")
        .with_api_key("secret");
    let (status, body) = call(&restarted, Method::GET, None, key).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body, json!({ "authorization_required": true }));

    for invalid in [json!({}), json!({ "authorization_required": "true" })] {
        let (status, _) = call(&state, Method::PUT, Some(invalid), key).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
    }
    let (_, body) = call(&state, Method::GET, None, key).await;
    assert_eq!(body, json!({ "authorization_required": true }));

    std::fs::remove_dir_all(dir).ok();
}

#[tokio::test]
async fn authorization_setting_requires_http_authentication() {
    let (dir, state) = fixture();
    let (status, _) = call(&state, Method::GET, None, None).await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    let (status, _) = call(
        &state,
        Method::PUT,
        Some(json!({ "authorization_required": true })),
        None,
    )
    .await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    let store = r3akt_rch_core::RchSqliteStore::open_read_only(dir.join("rch.db")).expect("store");
    assert!(!store.authorization_required().expect("setting"));
    drop(store);
    std::fs::remove_dir_all(dir).ok();
}
