use super::*;
use axum::http::{Method, Request, StatusCode};
use http_body_util::BodyExt;
use tower::ServiceExt;

async fn request(
    state: &AppState,
    method: Method,
    path: &str,
    body: String,
) -> (StatusCode, Value) {
    let response = crate::create_app_with_state(state.clone().with_api_key("secret"))
        .oneshot(
            Request::builder()
                .method(method)
                .uri(path)
                .header("X-API-Key", "secret")
                .header(
                    "Content-Type",
                    if path.ends_with("complete") || path.ends_with("Rollback") {
                        "application/json"
                    } else {
                        "text/plain"
                    },
                )
                .body(Body::from(body))
                .unwrap(),
        )
        .await
        .unwrap();
    let status = response.status();
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    (status, serde_json::from_slice(&bytes).unwrap())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn hub_name_http_renames_reloads_rolls_back_and_retries_failed_publication() {
    let dir = std::env::temp_dir().join(format!("rch-name-sdk-{}", Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    let fixture = Fixture::open(&dir.join("daemon.db"));
    let identity_path = dir.join("identity");
    let state = fixture
        .state_with_timeout(
            &dir.join("rch.db"),
            &identity_path,
            Some(Duration::from_secs(3)),
        )
        .with_config_path(dir.join("config.ini"));
    let keys = std::fs::read(&identity_path).unwrap();
    let source = state.reticulumd_source.clone();
    state.reconcile_hub_display_name().unwrap();

    // An existing installation with a stale daemon/INI name is repaired from SQLite.
    with_core_store_write(&state, |store| {
        store.set_setting_value(HUB_NAME_SETTING, "Saved Hub")
    })
    .unwrap();
    std::fs::write(
        dir.join("config.ini"),
        "[hub]\ndisplay_name = R3AKT server\nname = stale\n",
    )
    .unwrap();
    let (status, info) =
        request(&state, Method::POST, "/Command/ReloadConfig", String::new()).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(info["hub_display_name"], "Saved Hub");

    for (body, expected) in [
        (
            "[hub]\nname = Saved Hub\ndisplay_name = Renamed Display\n",
            "Renamed Display",
        ),
        (
            "[hub]\nname = Renamed Name\ndisplay_name = Renamed Display\n",
            "Renamed Name",
        ),
    ] {
        let (status, saved) = request(&state, Method::PUT, "/Config", body.to_string()).await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(saved["identity_announce_update_pending"], false);
        assert_eq!(crate::hub_name::resolve(&state).unwrap(), expected);
    }
    let backup = dir.join("old-name.ini");
    std::fs::write(
        &backup,
        "[hub]\ndisplay_name = ignored\nname = Restored Hub\n",
    )
    .unwrap();
    let (status, _) = request(
        &state,
        Method::POST,
        "/Config/Rollback",
        json!({"backup_path":backup}).to_string(),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(crate::hub_name::resolve(&state).unwrap(), "Restored Hub");

    fixture
        .identity_bridge
        .reject_announce
        .store(true, Ordering::Release);
    let (status, error) = request(
        &state,
        Method::PUT,
        "/Config",
        "[hub]\nname = Pending Hub\n".to_string(),
    )
    .await;
    assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);
    assert!(error.to_string().contains("Hub name saved"));
    assert_eq!(crate::hub_name::resolve(&state).unwrap(), "Pending Hub");
    let diagnostics = crate::runtime_diagnostics_payload(&state).unwrap();
    assert_eq!(diagnostics["identity_announce_update_pending"], true);
    assert!(
        diagnostics["last_identity_announce_update_error"]
            .as_str()
            .unwrap()
            .contains("pending")
    );

    fixture
        .identity_bridge
        .reject_announce
        .store(false, Ordering::Release);
    assert_eq!(
        request(&state, Method::POST, "/Command/ReloadConfig", String::new())
            .await
            .0,
        StatusCode::OK
    );
    let diagnostics = crate::runtime_diagnostics_payload(&state).unwrap();
    assert_eq!(diagnostics["identity_announce_update_pending"], false);
    assert!(diagnostics["last_identity_announce_update_error"].is_null());
    let (_, setup) = request(
        &state,
        Method::GET,
        "/api/r3akt/setup/status",
        String::new(),
    )
    .await;
    assert_eq!(setup["hub_name"], "Pending Hub");

    // Concurrent saves are serialized through persistence and publication.
    let (first, second) = tokio::join!(
        request(
            &state,
            Method::PUT,
            "/Config",
            "[hub]\nname = Concurrent A\n".into()
        ),
        request(
            &state,
            Method::PUT,
            "/Config",
            "[hub]\nname = Concurrent B\n".into()
        ),
    );
    assert_eq!(first.0, StatusCode::OK);
    assert_eq!(second.0, StatusCode::OK);
    let final_name = crate::hub_name::resolve(&state).unwrap();
    let published = fixture.identity_bridge.published.lock().unwrap().clone();
    assert_eq!(
        published.last().unwrap().display_name.as_deref(),
        Some(final_name.as_str())
    );
    assert_eq!(
        published
            .iter()
            .map(|record| record.display_name.as_deref().unwrap())
            .take(5)
            .collect::<Vec<_>>(),
        [
            "RCH",
            "Saved Hub",
            "Renamed Display",
            "Renamed Name",
            "Restored Hub"
        ]
    );
    assert!(
        published
            .iter()
            .all(|record| record.identity == published[0].identity
                && record.delivery_destination == published[0].delivery_destination)
    );
    assert_eq!(std::fs::read(&identity_path).unwrap(), keys);
    assert_eq!(state.reticulumd_source, source);
    state
        .lxmf_zmq_data_plane
        .as_ref()
        .unwrap()
        .shutdown()
        .unwrap();
    drop(state);
    let restored = AppState::from_sqlite_path(dir.join("rch.db"))
        .unwrap()
        .with_config_path(dir.join("config.ini"));
    assert_eq!(restored.reconcile_hub_display_name().unwrap(), final_name);
    drop(fixture);
    std::fs::remove_dir_all(dir).unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn hub_name_setup_publishes_and_reports_committed_enrollment_when_announce_fails() {
    for fail in [false, true] {
        let dir = std::env::temp_dir().join(format!("rch-name-setup-{}", Uuid::new_v4()));
        std::fs::create_dir_all(&dir).unwrap();
        let fixture = Fixture::open(&dir.join("daemon.db"));
        let state = fixture
            .state_with_timeout(
                &dir.join("rch.db"),
                &dir.join("identity"),
                Some(Duration::from_secs(3)),
            )
            .with_config_path(dir.join("config.ini"));
        fixture
            .identity_bridge
            .reject_announce
            .store(fail, Ordering::Release);
        let (status, enrolled) = request(&state, Method::POST, "/api/r3akt/setup/complete", json!({
            "hub_name":"Setup Hub", "remote_password":"setup-password", "kill_switch_pin":"123456"
        }).to_string()).await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(enrolled["setup_required"], false);
        assert_eq!(enrolled["hub_name"], "Setup Hub");
        assert_eq!(enrolled["identity_announce_update_pending"], fail);
        assert_eq!(
            enrolled["last_identity_announce_update_error"].is_string(),
            fail
        );
        assert_eq!(
            crate::app_info_payload(&state).unwrap()["hub_display_name"],
            "Setup Hub"
        );
        if !fail {
            assert_eq!(
                fixture
                    .identity_bridge
                    .published
                    .lock()
                    .unwrap()
                    .last()
                    .unwrap()
                    .display_name
                    .as_deref(),
                Some("Setup Hub")
            );
        }
        state
            .lxmf_zmq_data_plane
            .as_ref()
            .unwrap()
            .shutdown()
            .unwrap();
        drop(state);
        drop(fixture);
        std::fs::remove_dir_all(dir).unwrap();
    }
}
