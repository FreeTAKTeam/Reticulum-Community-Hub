use std::net::SocketAddr;
use std::sync::Arc;

use axum::body::Body;
use axum::extract::connect_info::ConnectInfo;
use axum::http::{Method, Request, StatusCode};
use http_body_util::BodyExt;
use r3akt_rch_core::RchSqliteStore;
use serde_json::Value;
use tower::ServiceExt;
use uuid::Uuid;

#[tokio::test]
async fn http_auth_throttles_each_remote_client_and_returns_retry_after() {
    let remote_addr = SocketAddr::from(([198, 51, 100, 20], 50_000));
    let other_addr = SocketAddr::from(([198, 51, 100, 21], 50_000));
    let db_path = std::env::temp_dir().join(format!("r3akt-rch-throttle-{}.db", Uuid::new_v4()));
    let app = crate::create_app_with_state(
        crate::AppState::from_sqlite_path(&db_path)
            .expect("state")
            .with_api_key("secret"),
    );

    for attempt in 1..=5 {
        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method(Method::GET)
                    .uri("/Status")
                    .header("X-API-Key", "wrong")
                    .extension(ConnectInfo(remote_addr))
                    .body(Body::empty())
                    .expect("request"),
            )
            .await
            .expect("auth response");
        if attempt < 5 {
            assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        } else {
            assert_eq!(response.status(), StatusCode::TOO_MANY_REQUESTS);
            assert_eq!(
                response.headers().get(axum::http::header::RETRY_AFTER),
                Some(&axum::http::HeaderValue::from_static("300"))
            );
        }
    }

    let other_response = app
        .oneshot(
            Request::builder()
                .method(Method::GET)
                .uri("/Status")
                .header("X-API-Key", "wrong")
                .extension(ConnectInfo(other_addr))
                .body(Body::empty())
                .expect("request"),
        )
        .await
        .expect("other client response");
    assert_eq!(other_response.status(), StatusCode::UNAUTHORIZED);
    std::fs::remove_file(db_path).expect("remove throttle database");
}

#[tokio::test]
async fn successful_http_authentication_resets_failure_counter() {
    let remote_addr = SocketAddr::from(([198, 51, 100, 22], 50_000));
    let db_path = std::env::temp_dir().join(format!("r3akt-rch-auth-reset-{}.db", Uuid::new_v4()));
    let app = crate::create_app_with_state(
        crate::AppState::from_sqlite_path(&db_path)
            .expect("state")
            .with_api_key("secret"),
    );

    for credential in ["wrong", "wrong", "wrong", "wrong", "secret", "wrong"] {
        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method(Method::GET)
                    .uri("/Status")
                    .header("X-API-Key", credential)
                    .extension(ConnectInfo(remote_addr))
                    .body(Body::empty())
                    .expect("request"),
            )
            .await
            .expect("auth response");
        let expected = if credential == "secret" {
            StatusCode::OK
        } else {
            StatusCode::UNAUTHORIZED
        };
        assert_eq!(response.status(), expected);
    }
    std::fs::remove_file(db_path).expect("remove auth reset database");
}

#[test]
fn legacy_password_hash_is_verified_and_upgraded_to_argon2id() {
    let db_path =
        std::env::temp_dir().join(format!("r3akt-rch-auth-migration-{}.db", Uuid::new_v4()));
    let salt = "legacy-preview-salt";
    let created_at = 1_700_000_000_000_i64;
    let store = RchSqliteStore::open(&db_path).expect("store");
    store
        .set_setting_value(crate::REMOTE_ACCESS_PASSWORD_SALT_SETTING, salt)
        .expect("legacy salt");
    store
        .set_setting_value(
            crate::REMOTE_ACCESS_PASSWORD_HASH_SETTING,
            &crate::password_hash(salt, "preview-password"),
        )
        .expect("legacy hash");
    store
        .set_setting_value(
            crate::REMOTE_ACCESS_PASSWORD_CREATED_AT_SETTING,
            &created_at.to_string(),
        )
        .expect("legacy timestamp");
    drop(store);

    let state = crate::AppState::from_sqlite_path(&db_path).expect("state");
    assert!(
        state
            .validate_stored_remote_password(Some("preview-password"))
            .expect("legacy validation")
    );
    let upgraded = crate::load_stored_remote_password(&state)
        .expect("load upgraded secret")
        .expect("stored secret");
    assert!(upgraded.hash.starts_with("$argon2id$v=19$"));
    assert_eq!(upgraded.created_at_ts_ms, created_at);
    assert!(
        state
            .validate_stored_remote_password(Some("preview-password"))
            .expect("upgraded validation")
    );
    std::fs::remove_file(db_path).expect("remove auth migration database");
}

#[tokio::test]
async fn legacy_kill_switch_pin_is_verified_and_upgraded_to_argon2id() {
    let db_path =
        std::env::temp_dir().join(format!("r3akt-rch-pin-migration-{}.db", Uuid::new_v4()));
    let salt = "legacy-preview-pin-salt";
    let created_at = 1_700_000_000_001_i64;
    let store = RchSqliteStore::open(&db_path).expect("store");
    store
        .set_setting_value(crate::KILL_SWITCH_PIN_SALT_SETTING, salt)
        .expect("legacy PIN salt");
    store
        .set_setting_value(
            crate::KILL_SWITCH_PIN_HASH_SETTING,
            &crate::password_hash(salt, "123456"),
        )
        .expect("legacy PIN hash");
    store
        .set_setting_value(
            crate::KILL_SWITCH_PIN_CREATED_AT_SETTING,
            &created_at.to_string(),
        )
        .expect("legacy PIN timestamp");
    drop(store);

    let state = crate::AppState::from_sqlite_path(&db_path).expect("state");
    {
        let mut runtime = state.kill_switch.write().expect("kill switch state");
        runtime.arm_a = true;
        runtime.arm_b = true;
        runtime.mode = crate::KillSwitchRuntimeMode::Armed;
    }
    let _authorized = crate::kill_switch_authorize(
        axum::extract::State(state.clone()),
        None,
        axum::Json(crate::KillSwitchAuthorizePayload {
            pin: "123456".to_string(),
        }),
    )
    .await
    .expect("legacy PIN authorization");

    let upgraded = crate::load_kill_switch_pin(&state)
        .expect("load upgraded PIN")
        .expect("stored PIN");
    assert!(upgraded.hash.starts_with("$argon2id$v=19$"));
    assert_eq!(upgraded.created_at_ts_ms, created_at);
    std::fs::remove_file(db_path).expect("remove PIN migration database");
}

#[tokio::test]
async fn authentication_storage_failure_is_sanitized_as_internal_error() {
    let remote_addr = SocketAddr::from(([198, 51, 100, 23], 50_000));
    let state = crate::AppState {
        sqlite_path: Some(Arc::new(std::path::PathBuf::from(
            "/proc/rch-auth-storage-unavailable.db",
        ))),
        ..crate::AppState::default()
    };
    let response = crate::create_app_with_state(state)
        .oneshot(
            Request::builder()
                .method(Method::GET)
                .uri("/Status")
                .header("X-API-Key", "credential")
                .extension(ConnectInfo(remote_addr))
                .body(Body::empty())
                .expect("request"),
        )
        .await
        .expect("storage failure response");
    assert_eq!(response.status(), StatusCode::INTERNAL_SERVER_ERROR);
    assert!(response.headers().contains_key("x-request-id"));
    let body = response
        .into_body()
        .collect()
        .await
        .expect("body")
        .to_bytes();
    let payload: Value = serde_json::from_slice(&body).expect("json");
    assert_eq!(payload["detail"], "An unexpected server error occurred");
    assert!(!body.as_ref().windows(5).any(|window| window == b"/proc"));
}

#[test]
fn malformed_authentication_records_are_storage_errors_not_missing_credentials() {
    let db_path = std::env::temp_dir().join(format!(
        "r3akt-rch-malformed-auth-record-{}.db",
        Uuid::new_v4()
    ));
    let store = RchSqliteStore::open(&db_path).expect("store");
    store
        .set_setting_value(crate::REMOTE_ACCESS_PASSWORD_HASH_SETTING, "partial")
        .expect("partial password record");
    store
        .set_setting_value(crate::KILL_SWITCH_PIN_SALT_SETTING, "partial")
        .expect("partial PIN record");
    drop(store);

    let state = crate::AppState::from_sqlite_path(&db_path).expect("state");
    assert!(matches!(
        crate::load_stored_remote_password(&state),
        Err(crate::ApiError::Internal(detail))
            if detail.contains("incomplete remote password")
    ));
    assert!(matches!(
        crate::load_kill_switch_pin(&state),
        Err(crate::ApiError::Internal(detail))
            if detail.contains("incomplete kill switch PIN")
    ));
    std::fs::remove_file(db_path).expect("remove malformed auth database");
}
