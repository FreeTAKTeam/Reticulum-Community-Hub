use super::*;
use std::path::PathBuf;

fn local_peer() -> SocketAddr {
    SocketAddr::from(([127, 0, 0, 1], 50_000))
}

fn remote_peer() -> SocketAddr {
    SocketAddr::from(([198, 51, 100, 50], 50_000))
}

fn setup_state() -> (crate::AppState, PathBuf) {
    let dir = std::env::temp_dir().join(format!("rch-release-security-{}", Uuid::new_v4()));
    std::fs::create_dir_all(&dir).expect("fixture directory");
    let config = dir.join("config.ini");
    std::fs::write(&config, "[hub]\nname = Original\n").expect("fixture config");
    let state = crate::AppState::from_sqlite_path(dir.join("state.db"))
        .expect("fixture state")
        .with_config_path(config);
    (state, dir)
}

fn setup_payload(name: &str) -> Value {
    json!({"hub_name": name, "remote_password": "fixture-password", "kill_switch_pin": "123456"})
}

#[tokio::test]
async fn setup_password_minimum_counts_unicode_characters_before_enrollment() {
    let (state, dir) = setup_state();
    let app = crate::create_app_with_state(state.clone().with_api_key("secret"));
    for password in ["😀😀", "ééééééé"] {
        let mut payload = setup_payload("Unicode password fixture");
        payload["remote_password"] = json!(password);
        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/r3akt/setup/complete")
                    .header("X-API-Key", "secret")
                    .header("content-type", "application/json")
                    .body(Body::from(payload.to_string()))
                    .expect("request"),
            )
            .await
            .expect("response");
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert!(
            crate::load_stored_remote_password(&state)
                .expect("credential")
                .is_none()
        );
        assert!(crate::load_kill_switch_pin(&state).expect("PIN").is_none());
        assert_eq!(
            std::fs::read_to_string(dir.join("config.ini")).expect("config"),
            "[hub]\nname = Original\n"
        );
    }
    let password = "éééééééé";
    let mut payload = setup_payload("Unicode password fixture");
    payload["remote_password"] = json!(password);
    let response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/r3akt/setup/complete")
                .header("X-API-Key", "secret")
                .header("content-type", "application/json")
                .body(Body::from(payload.to_string()))
                .expect("request"),
        )
        .await
        .expect("response");
    assert_eq!(response.status(), StatusCode::OK);
    assert!(
        state
            .validate_stored_remote_password(Some(password))
            .expect("password accepted")
    );
    drop(state);
    std::fs::remove_dir_all(dir).expect("cleanup");
}

#[tokio::test]
async fn served_ui_and_error_responses_enforce_browser_security_headers() {
    let (state, directory) = setup_state();
    let ui = directory.join("ui");
    std::fs::create_dir(&ui).expect("UI directory");
    std::fs::write(
        ui.join("index.html"),
        "<!doctype html><title>fixture</title>",
    )
    .expect("UI");
    let app = crate::create_app_with_state_and_ui_dist_path(state, ui);
    for path in ["/", "/Status"] {
        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .uri(path)
                    .header(
                        "accept",
                        if path == "/" {
                            "text/html"
                        } else {
                            "application/json"
                        },
                    )
                    .header("x-forwarded-proto", "https")
                    .body(Body::empty())
                    .expect("request"),
            )
            .await
            .expect("response");
        assert_eq!(response.headers()["x-content-type-options"], "nosniff");
        assert_eq!(response.headers()["referrer-policy"], "no-referrer");
        assert!(
            response
                .headers()
                .get("strict-transport-security")
                .is_none()
        );
        if path == "/" {
            assert_eq!(response.status(), StatusCode::OK);
            let csp = response.headers()["content-security-policy"]
                .to_str()
                .expect("CSP");
            assert!(csp.contains("script-src 'self'"));
            assert!(csp.contains("worker-src 'self' blob:"));
            assert!(csp.contains("object-src 'none'"));
            assert!(!csp.contains("unsafe-eval"));
            assert_eq!(
                response.headers()["cross-origin-opener-policy"],
                "same-origin"
            );
        } else {
            assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        }
    }
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[tokio::test]
async fn protected_routes_require_credentials_even_before_setup_and_on_loopback() {
    for peer in [None, Some(local_peer()), Some(remote_peer())] {
        for state in [
            crate::AppState::default(),
            crate::AppState::default().with_api_key("secret"),
        ] {
            let mut request = Request::builder().uri("/Status");
            if let Some(peer) = peer {
                request = request.extension(ConnectInfo(peer));
            }
            let response = crate::create_app_with_state(state)
                .oneshot(request.body(Body::empty()).expect("request"))
                .await
                .expect("response");
            assert_eq!(response.status(), StatusCode::UNAUTHORIZED, "peer {peer:?}");
        }
    }
}

#[tokio::test]
async fn internal_route_family_requires_authority_before_handlers_run() {
    for (method, path) in [
        (Method::GET, "/internal/topics"),
        (Method::GET, "/internal/topics/ops/subscribers"),
        (Method::GET, "/internal/nodes/node"),
        (Method::POST, "/internal/message"),
        (Method::POST, "/internal/delivery-receipt"),
        (Method::POST, "/internal/delivery-failure"),
        (Method::POST, "/internal/delivery-retry"),
        (Method::POST, "/internal/delivery-propagation"),
        (Method::POST, "/internal/delivery-drop"),
        (Method::POST, "/internal/delivery-attempt"),
        (Method::GET, "/internal/rch/announce-capabilities"),
        (Method::POST, "/internal/identity-announce"),
        (Method::GET, "/internal/events/stream"),
    ] {
        let response =
            crate::create_app_with_state(crate::AppState::default().with_api_key("secret"))
                .oneshot(
                    Request::builder()
                        .method(method)
                        .uri(path)
                        .extension(ConnectInfo(remote_peer()))
                        .header("content-type", "application/json")
                        .body(Body::from("{}"))
                        .expect("request"),
                )
                .await
                .expect("response");
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED, "path {path}");
    }
}

#[tokio::test]
async fn hostile_browser_origin_is_denied_with_a_valid_credential() {
    for path in [
        "/Status",
        "/events/system",
        "/telemetry/stream",
        "/messages/stream",
        "/api/r3akt/setup/complete",
    ] {
        let response = crate::create_app_with_state(
            crate::AppState::default()
                .with_api_key("secret")
                .with_api_bind(SocketAddr::from(([127, 0, 0, 1], 8000))),
        )
        .oneshot(
            Request::builder()
                .uri(path)
                .extension(ConnectInfo(local_peer()))
                .header("origin", "https://hostile.example")
                .header("X-API-Key", "secret")
                .body(Body::empty())
                .expect("request"),
        )
        .await
        .expect("response");
        assert_eq!(response.status(), StatusCode::FORBIDDEN, "path {path}");
    }
}

#[tokio::test]
async fn setup_cannot_be_claimed_by_a_remote_uncredentialed_peer() {
    let (state, dir) = setup_state();
    let response = crate::create_app_with_state(state.clone())
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/r3akt/setup/complete")
                .extension(ConnectInfo(remote_peer()))
                .header("content-type", "application/json")
                .body(Body::from(setup_payload("Remote takeover").to_string()))
                .expect("request"),
        )
        .await
        .expect("response");
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    assert!(
        crate::load_kill_switch_pin(&state)
            .expect("PIN record")
            .is_none()
    );
    assert!(
        crate::load_stored_remote_password(&state)
            .expect("password record")
            .is_none()
    );
    assert_eq!(
        std::fs::read_to_string(dir.join("config.ini")).expect("config"),
        "[hub]\nname = Original\n"
    );
    std::fs::remove_dir_all(dir).expect("fixture cleanup");
}

#[tokio::test]
async fn configured_api_key_also_protects_local_setup() {
    let (state, dir) = setup_state();
    let response = crate::create_app_with_state(state.with_api_key("secret"))
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/r3akt/setup/complete")
                .extension(ConnectInfo(local_peer()))
                .header("content-type", "application/json")
                .body(Body::from(setup_payload("Local takeover").to_string()))
                .expect("request"),
        )
        .await
        .expect("response");
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    std::fs::remove_dir_all(dir).expect("fixture cleanup");
}

#[tokio::test]
async fn unauthenticated_setup_status_returns_only_bootstrap_state() {
    let (state, dir) = setup_state();
    let response = crate::create_app_with_state(state.with_api_key("secret"))
        .oneshot(
            Request::builder()
                .uri("/api/r3akt/setup/status")
                .extension(ConnectInfo(remote_peer()))
                .body(Body::empty())
                .expect("request"),
        )
        .await
        .expect("response");
    assert_eq!(response.status(), StatusCode::OK);
    let body = response
        .into_body()
        .collect()
        .await
        .expect("body")
        .to_bytes();
    let body: Value = serde_json::from_slice(&body).expect("JSON");
    assert_eq!(body, json!({"setup_required": true}));
    std::fs::remove_dir_all(dir).expect("fixture cleanup");
}

#[tokio::test]
async fn setup_rejects_multiline_config_values_without_changing_records() {
    let (state, dir) = setup_state();
    let response = crate::create_app_with_state(state.clone().with_api_key("secret"))
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/r3akt/setup/complete")
                .extension(ConnectInfo(local_peer()))
                .header("X-API-Key", "secret")
                .header("content-type", "application/json")
                .body(Body::from(
                    setup_payload("hub\n[security]\napi_key_env = INJECTED").to_string(),
                ))
                .expect("request"),
        )
        .await
        .expect("response");
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    assert!(
        crate::load_kill_switch_pin(&state)
            .expect("PIN record")
            .is_none()
    );
    assert_eq!(
        std::fs::read_to_string(dir.join("config.ini")).expect("config"),
        "[hub]\nname = Original\n"
    );
    std::fs::remove_dir_all(dir).expect("fixture cleanup");
}

#[test]
fn websocket_authority_has_no_loopback_or_unknown_peer_bypass() {
    for peer in [None, Some(local_peer()), Some(remote_peer())] {
        let state = crate::AppState::default().with_api_key("secret");
        assert!(
            !state
                .validate_ws_credentials(None, None, peer)
                .expect("validation")
        );
        assert!(
            state
                .validate_ws_credentials(Some("secret"), None, peer)
                .expect("validation")
        );
    }
}

#[tokio::test]
async fn bootstrap_rejects_a_rebound_host_without_an_origin() {
    let (state, dir) = setup_state();
    let app =
        crate::create_app_with_state(state.with_api_bind("127.0.0.1:8000".parse().expect("bind")));
    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .uri("/api/r3akt/setup/status")
                .extension(ConnectInfo(local_peer()))
                .header("host", "attacker.example:8000")
                .header("sec-fetch-site", "same-origin")
                .body(Body::empty())
                .expect("request"),
        )
        .await
        .expect("response");
    let payload: Value = serde_json::from_slice(
        &response
            .into_body()
            .collect()
            .await
            .expect("body")
            .to_bytes(),
    )
    .expect("JSON");
    assert_eq!(payload, json!({"setup_required": true}));
    let response = app
        .oneshot(
            Request::builder()
                .uri("/api/r3akt/setup/status")
                .extension(ConnectInfo(local_peer()))
                .header("host", "localhost:8000")
                .header("sec-fetch-site", "same-origin")
                .body(Body::empty())
                .expect("request"),
        )
        .await
        .expect("response");
    let payload: Value = serde_json::from_slice(
        &response
            .into_body()
            .collect()
            .await
            .expect("body")
            .to_bytes(),
    )
    .expect("JSON");
    assert_eq!(
        payload["config_path"],
        dir.join("config.ini").display().to_string()
    );
    std::fs::remove_dir_all(dir).expect("cleanup");
}

#[tokio::test]
async fn public_app_metadata_redacts_paths_but_authenticated_metadata_keeps_its_shape() {
    let (state, dir) = setup_state();
    let app = crate::create_app_with_state(state.with_api_key("secret"));
    for authorized in [false, true] {
        let mut request = Request::builder()
            .uri("/api/v1/app/info")
            .extension(ConnectInfo(remote_peer()));
        if authorized {
            request = request.header("X-API-Key", "secret");
        }
        let response = app
            .clone()
            .oneshot(request.body(Body::empty()).expect("request"))
            .await
            .expect("response");
        assert_eq!(response.status(), StatusCode::OK);
        let payload: Value = serde_json::from_slice(
            &response
                .into_body()
                .collect()
                .await
                .expect("body")
                .to_bytes(),
        )
        .expect("JSON");
        assert_eq!(payload["name"], "ReticulumCommunityHub");
        for key in [
            "database_path",
            "reticulum_config_path",
            "storage_path",
            "file_storage_path",
            "image_storage_path",
            "storage_paths",
        ] {
            assert_eq!(payload[key].is_null(), !authorized, "{key}");
        }
    }
    std::fs::remove_dir_all(dir).expect("cleanup");
}

#[test]
fn corrupt_hash_records_are_storage_errors_and_wrong_passwords_are_normal_failures() {
    let valid = crate::argon2id_hash("correct-password").expect("hash");
    assert!(!crate::verify_versioned_secret("salt", &valid, "wrong-password").expect("valid hash"));
    for invalid in [
        valid.replace("v=19", "v=99"),
        valid.replace("m=19456", "m=1"),
        valid.rsplit_once('$').expect("output").0.to_string(),
        "invalid-legacy-hash".to_string(),
    ] {
        assert!(
            matches!(
                crate::verify_versioned_secret("salt", &invalid, "correct-password"),
                Err(crate::ApiError::Internal(_))
            ),
            "{invalid}"
        );
    }
}

#[test]
fn failed_legacy_password_migration_preserves_the_complete_old_credential() {
    let (state, dir) = setup_state();
    let original_hash = crate::password_hash("original-salt", "correct-password");
    crate::with_required_core_store_write(&state, |store| {
        store.set_setting_values_atomic(&[
            (crate::REMOTE_ACCESS_PASSWORD_SALT_SETTING, "original-salt"),
            (crate::REMOTE_ACCESS_PASSWORD_HASH_SETTING, &original_hash),
            (crate::REMOTE_ACCESS_PASSWORD_CREATED_AT_SETTING, "1234"),
        ])
    })
    .expect("legacy credential");
    let connection = rusqlite::Connection::open(dir.join("state.db")).expect("DB");
    connection.execute_batch("CREATE TRIGGER reject_password_migration BEFORE INSERT ON rch_settings WHEN NEW.setting_key = 'remote_access_password_hash' BEGIN SELECT RAISE(ABORT, 'injected credential write failure'); END;").expect("fault trigger");
    assert!(matches!(
        state.validate_stored_remote_password(Some("correct-password")),
        Err(crate::ApiError::Internal(_))
    ));
    let original = crate::load_stored_remote_password(&state)
        .expect("record")
        .expect("credential");
    assert_eq!(original.salt, "original-salt");
    assert_eq!(original.hash, original_hash);
    assert_eq!(original.created_at_ts_ms, 1234);
    connection
        .execute_batch("DROP TRIGGER reject_password_migration;")
        .expect("clear fault");
    assert!(
        state
            .validate_stored_remote_password(Some("correct-password"))
            .expect("retry")
    );
    assert!(
        crate::load_stored_remote_password(&state)
            .expect("record")
            .expect("credential")
            .hash
            .starts_with("$argon2id$")
    );
    std::fs::remove_dir_all(dir).expect("cleanup");
}

#[tokio::test]
async fn setup_database_abort_leaves_no_partial_credentials_or_configuration() {
    let (state, dir) = setup_state();
    let connection = rusqlite::Connection::open(dir.join("state.db")).expect("DB");
    connection.execute_batch("CREATE TRIGGER reject_pin BEFORE INSERT ON rch_settings WHEN NEW.setting_key = 'kill_switch_pin_hash' BEGIN SELECT RAISE(ABORT, 'injected enrollment failure'); END;").expect("fault trigger");
    let response = crate::create_app_with_state(state.clone().with_api_key("secret"))
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/r3akt/setup/complete")
                .header("X-API-Key", "secret")
                .header("content-type", "application/json")
                .body(Body::from(setup_payload("New name").to_string()))
                .expect("request"),
        )
        .await
        .expect("response");
    assert_eq!(response.status(), StatusCode::INTERNAL_SERVER_ERROR);
    assert!(
        crate::load_stored_remote_password(&state)
            .expect("password")
            .is_none()
    );
    assert!(crate::load_kill_switch_pin(&state).expect("PIN").is_none());
    assert_eq!(
        std::fs::read_to_string(dir.join("config.ini")).expect("config"),
        "[hub]\nname = Original\n"
    );
    std::fs::remove_dir_all(dir).expect("cleanup");
}

#[tokio::test]
async fn competing_setup_instances_commit_one_coherent_enrollment() {
    let (state, dir) = setup_state();
    let other = crate::AppState::from_sqlite_path(dir.join("state.db"))
        .expect("second instance")
        .with_config_path(dir.join("config.ini"));
    let request = |name| {
        Request::builder()
            .method(Method::POST)
            .uri("/api/r3akt/setup/complete")
            .header("X-API-Key", "secret")
            .header("content-type", "application/json")
            .body(Body::from(setup_payload(name).to_string()))
            .expect("request")
    };
    let (first, second) = tokio::join!(
        crate::create_app_with_state(state.clone().with_api_key("secret"))
            .oneshot(request("First")),
        crate::create_app_with_state(other.with_api_key("secret")).oneshot(request("Second"))
    );
    let statuses = [
        first.expect("first response").status(),
        second.expect("second response").status(),
    ];
    assert!(statuses.contains(&StatusCode::OK));
    assert!(statuses.contains(&StatusCode::CONFLICT));
    let name = crate::with_required_core_store_write(&state, |store| {
        store.setting_value(crate::HUB_NAME_SETTING)
    })
    .expect("record")
    .expect("name");
    assert_eq!(
        std::fs::read_to_string(dir.join("config.ini")).expect("config"),
        format!("[hub]\nname = {name}\n")
    );
    assert!(
        state
            .validate_stored_remote_password(Some("fixture-password"))
            .expect("enrolled credential")
    );
    std::fs::remove_dir_all(dir).expect("cleanup");
}

#[tokio::test]
async fn setup_commit_failure_after_file_install_restores_everything_and_can_retry() {
    let (state, dir) = setup_state();
    let connection = rusqlite::Connection::open(dir.join("state.db")).expect("DB");
    connection.execute_batch("CREATE TABLE setup_fault_parent(id INTEGER PRIMARY KEY); CREATE TABLE setup_fault_child(id INTEGER REFERENCES setup_fault_parent(id) DEFERRABLE INITIALLY DEFERRED); CREATE TRIGGER reject_setup_commit AFTER INSERT ON rch_settings WHEN NEW.setting_key = 'kill_switch_pin_hash' BEGIN INSERT INTO setup_fault_child VALUES(999); END;").expect("deferred commit fault");
    let app = crate::create_app_with_state(state.clone().with_api_key("secret"));
    let request = || {
        Request::builder()
            .method(Method::POST)
            .uri("/api/r3akt/setup/complete")
            .header("X-API-Key", "secret")
            .header("content-type", "application/json")
            .body(Body::from(setup_payload("Updated name").to_string()))
            .expect("request")
    };
    let response = app.clone().oneshot(request()).await.expect("response");
    assert_eq!(response.status(), StatusCode::INTERNAL_SERVER_ERROR);
    assert!(
        crate::load_stored_remote_password(&state)
            .expect("password")
            .is_none()
    );
    assert!(crate::load_kill_switch_pin(&state).expect("PIN").is_none());
    assert_eq!(
        std::fs::read_to_string(dir.join("config.ini")).expect("restored config"),
        "[hub]\nname = Original\n"
    );
    assert_eq!(
        connection
            .query_row("SELECT COUNT(*) FROM setup_fault_child", [], |row| row
                .get::<_, i64>(0))
            .expect("rolled back fault"),
        0
    );
    connection
        .execute_batch("DROP TRIGGER reject_setup_commit;")
        .expect("clear fault");
    let response = app.oneshot(request()).await.expect("retry");
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        std::fs::read_to_string(dir.join("config.ini")).expect("committed config"),
        "[hub]\nname = Updated name\n"
    );
    assert!(
        state
            .validate_stored_remote_password(Some("fixture-password"))
            .expect("password")
    );
    std::fs::remove_dir_all(dir).expect("cleanup");
}
