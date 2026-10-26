use axum::Router;
use axum::body::Body;
use axum::http::{Request, StatusCode};
use http_body_util::BodyExt;
use r3akt_rch_server::{AppState, create_app_with_state};
use serde_json::{Value, json};
use tower::ServiceExt;

async fn call(app: &Router, method: &str, path: &str, body: String) -> (StatusCode, Value) {
    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(method)
                .uri(path)
                .header("X-API-Key", "fixture-key")
                .header("Content-Type", "application/json")
                .body(Body::from(body))
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
async fn toml_setup_and_config_routes_reject_ini_before_changing_files_or_enrollment() {
    let directory = std::env::temp_dir().join(format!("rch-toml-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(&directory).expect("directory");
    let hub_path = directory.join("config.ini");
    let daemon_path = directory.join("reticulumd.toml");
    let original = "interfaces = []\n[reticulum]\nshare_instance = false\n";
    let hub_original = "[hub]\ndisplay_name = original\n";
    std::fs::write(&hub_path, hub_original).expect("hub config");
    std::fs::write(&daemon_path, original).expect("daemon config");
    let app = create_app_with_state(
        AppState::from_sqlite_path(directory.join("state.sqlite3"))
            .expect("state")
            .with_api_key("fixture-key")
            .with_config_path(&hub_path)
            .with_reticulum_config_path(&daemon_path),
    );
    let ini =
        "[reticulum]\nenable_transport = yes\n[interfaces]\n[[TCP]]\ntype = TCPClientInterface\n";
    let setup = |config: &str| {
        json!({
            "hub_name": "Fixture Hub",
            "remote_password": "fixture-password",
            "kill_switch_pin": "123456",
            "reticulum_config_text": config,
        })
        .to_string()
    };
    let (status, validation) = call(&app, "POST", "/Reticulum/Config/Validate", ini.into()).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(validation["valid"], false);
    assert!(
        validation["errors"][0]
            .as_str()
            .expect("error")
            .contains("TOML")
    );
    for (method, route, body) in [
        ("PUT", "/Reticulum/Config", ini.to_string()),
        ("POST", "/api/r3akt/setup/complete", setup(ini)),
    ] {
        assert_eq!(
            call(&app, method, route, body).await.0,
            StatusCode::BAD_REQUEST
        );
    }
    let backup = directory.join("invalid-backup");
    std::fs::write(&backup, ini).expect("backup");
    assert_eq!(
        call(
            &app,
            "POST",
            "/Reticulum/Config/Rollback",
            json!({"backup_path": backup}).to_string(),
        )
        .await
        .0,
        StatusCode::BAD_REQUEST
    );
    assert_eq!(
        std::fs::read_to_string(&hub_path).expect("hub"),
        hub_original
    );
    assert_eq!(
        std::fs::read_to_string(&daemon_path).expect("daemon"),
        original
    );
    let (_, status) = call(&app, "GET", "/api/r3akt/setup/status", String::new()).await;
    assert_eq!(status["setup_required"], true);
    assert_eq!(status["reticulum_config_format"], "toml");

    let toml = "[[interfaces]]\nname = \"Fixture TCP\"\ntype = \"tcp_client\"\nenabled = true\nhost = \"127.0.0.1\"\nport = 4242\n[reticulum]\nenable_transport = true\nshare_instance = false\n";
    let (status, validation) = call(&app, "POST", "/Reticulum/Config/Validate", toml.into()).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(validation["valid"], true);
    assert_eq!(
        call(&app, "PUT", "/Reticulum/Config", toml.into()).await.0,
        StatusCode::OK
    );
    let (status, enrolled) = call(&app, "POST", "/api/r3akt/setup/complete", setup(toml)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(enrolled["setup_required"], false);
    let saved = std::fs::read_to_string(&daemon_path).expect("saved TOML");
    let parsed: toml::Table = toml::from_str(&saved).expect("parse saved TOML");
    assert_eq!(parsed["interfaces"][0]["port"].as_integer(), Some(4242));
    drop(app);
    std::fs::remove_dir_all(directory).expect("cleanup");
}
