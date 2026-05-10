use axum::body::Body;
use axum::http::{Method, Request, StatusCode};
use http_body_util::BodyExt;
use serde_json::Value;
use tokio::net::TcpListener;
use tower::ServiceExt;
use uuid::Uuid;

#[path = "../src/sar_seed.rs"]
#[allow(dead_code)]
mod sar_seed;

use sar_seed::{SarSeedOptions, seed_sar_scenario};

#[tokio::test]
#[allow(clippy::too_many_lines)]
async fn sar_http_seeder_primes_rust_server_and_is_idempotent() {
    let db_path = std::env::temp_dir().join(format!("r3akt-sar-seed-{}.db", Uuid::new_v4()));
    let state = r3akt_rch_server::AppState::from_sqlite_path(&db_path)
        .expect("sqlite state")
        .with_api_key("secret");
    let app = r3akt_rch_server::create_app_with_state(state);
    let listener = TcpListener::bind("127.0.0.1:0").await.expect("bind");
    let addr = listener.local_addr().expect("addr");
    let server = tokio::spawn(async move {
        axum::serve(
            listener,
            app.into_make_service_with_connect_info::<std::net::SocketAddr>(),
        )
        .await
    });

    let options = SarSeedOptions {
        base_url: format!("http://{addr}"),
        api_key: Some("secret".to_string()),
    };
    let first = tokio::task::spawn_blocking({
        let options = options.clone();
        move || seed_sar_scenario(&options)
    })
    .await
    .expect("first join")
    .expect("first seed");
    assert!(first.upserted.values().sum::<usize>() > 0);
    assert!(first.created.get("markers").copied().unwrap_or_default() > 0);
    assert!(
        first
            .created
            .get("attachments")
            .copied()
            .unwrap_or_default()
            > 0
    );

    let second = tokio::task::spawn_blocking({
        let options = options.clone();
        move || seed_sar_scenario(&options)
    })
    .await
    .expect("second join")
    .expect("second seed");
    assert_eq!(
        second.created.get("markers").copied().unwrap_or_default(),
        0
    );
    assert_eq!(second.created.get("zones").copied().unwrap_or_default(), 0);
    assert_eq!(
        second
            .created
            .get("attachments")
            .copied()
            .unwrap_or_default(),
        0
    );
    assert!(second.found.get("attachments").copied().unwrap_or_default() >= 5);

    let verify_app = r3akt_rch_server::create_app_with_state(
        r3akt_rch_server::AppState::from_sqlite_path(&db_path)
            .expect("restart state")
            .with_api_key("secret"),
    );
    assert_json_len(&verify_app, "/Topic", 5).await;
    assert_json_len(&verify_app, "/Subscriber", 6).await;
    assert_json_len(&verify_app, "/api/markers", 6).await;
    assert_json_len(&verify_app, "/api/zones", 5).await;
    assert_json_len(&verify_app, "/File", 5).await;
    assert_json_len(&verify_app, "/checklists/templates", 5).await;
    assert_json_len(&verify_app, "/checklists", 5).await;
    assert_json_len(&verify_app, "/api/r3akt/teams", 5).await;
    assert_json_len(&verify_app, "/api/r3akt/team-members", 6).await;
    assert_json_len(&verify_app, "/api/r3akt/assets", 7).await;
    assert_json_len(&verify_app, "/api/r3akt/skills", 5).await;
    assert_json_len(&verify_app, "/api/r3akt/assignments", 3).await;
    assert_json_len(&verify_app, "/api/EmergencyActionMessage", 6).await;

    let status = get_json(&verify_app, "/Status").await;
    assert!(status.is_object());
    let events = get_json(&verify_app, "/api/r3akt/events?limit=10").await;
    assert!(events.as_array().expect("events").len() >= 10);

    let mission = get_json(
        &verify_app,
        "/api/r3akt/missions/sar-spruce-ridge-2026?expand=all",
    )
    .await;
    assert_eq!(mission["uid"], "sar-spruce-ridge-2026");
    assert_eq!(mission["mission_name"], "SAR - Spruce Ridge Missing Hiker");
    assert_eq!(mission["teams"].as_array().expect("teams").len(), 5);
    assert_eq!(
        mission["team_members"]
            .as_array()
            .expect("team members")
            .len(),
        6
    );
    assert_eq!(mission["assets"].as_array().expect("assets").len(), 7);
    assert_eq!(
        mission["assignments"]
            .as_array()
            .expect("assignments")
            .len(),
        3
    );
    assert_eq!(
        mission["checklists"].as_array().expect("checklists").len(),
        5
    );
    assert!(
        mission["mission_changes"]
            .as_array()
            .expect("changes")
            .len()
            >= 5
    );
    assert!(mission["log_entries"].as_array().expect("logs").len() >= 5);
    assert_eq!(mission["mission_rde"]["role"], "MISSION_OWNER");

    server.abort();
    let _ = std::fs::remove_file(db_path);
}

async fn assert_json_len(app: &axum::Router, uri: &str, expected_len: usize) {
    let payload = get_json(app, uri).await;
    let actual_len = payload
        .as_array()
        .map(Vec::len)
        .or_else(|| payload.get("items").and_then(Value::as_array).map(Vec::len))
        .or_else(|| {
            payload
                .as_object()
                .and_then(|object| object.values().find_map(Value::as_array))
                .map(Vec::len)
        })
        .unwrap_or_else(|| panic!("{uri}: expected array-like response, got {payload}"));
    assert_eq!(actual_len, expected_len, "{uri}: {payload}");
}

async fn get_json(app: &axum::Router, uri: &str) -> Value {
    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::GET)
                .uri(uri)
                .header("X-API-Key", "secret")
                .body(Body::empty())
                .expect("request"),
        )
        .await
        .expect("response");
    let status = response.status();
    let body = response
        .into_body()
        .collect()
        .await
        .expect("body")
        .to_bytes();
    assert_eq!(status, StatusCode::OK, "{}", String::from_utf8_lossy(&body));
    serde_json::from_slice(&body).expect("json")
}
