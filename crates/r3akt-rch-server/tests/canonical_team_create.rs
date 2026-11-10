use axum::{
    Router,
    body::Body,
    http::{Method, Request, StatusCode},
};
use http_body_util::BodyExt;
use r3akt_profile_rch::teams::CANONICAL_TEAMS;
use serde_json::{Value, json};
use tower::ServiceExt;

fn make_app(path: &std::path::Path) -> Router {
    r3akt_rch_server::create_app_with_state(
        r3akt_rch_server::AppState::from_sqlite_path(path)
            .expect("sqlite state")
            .with_api_key("secret"),
    )
}

async fn create_team(app: &Router, payload: Value) -> Value {
    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/r3akt/teams")
                .header("X-API-Key", "secret")
                .header("content-type", "application/json")
                .body(Body::from(payload.to_string()))
                .expect("request"),
        )
        .await
        .expect("response");
    assert_eq!(response.status(), StatusCode::OK);
    let bytes = response
        .into_body()
        .collect()
        .await
        .expect("body")
        .to_bytes();
    serde_json::from_slice(&bytes).expect("JSON")
}

#[tokio::test]
async fn color_only_team_is_canonical_and_reuses_persisted_record() {
    let path = std::env::temp_dir().join(format!("rch-team-312-{}.db", uuid::Uuid::new_v4()));
    let blue = "43341e5c822d99857fa6e8641f2ca9c0";
    let app = make_app(&path);
    let first = create_team(&app, json!({"color": "blue", "team_description": "keep"})).await;
    assert_eq!(first["uid"], blue);
    assert_eq!(first["team_name"], "BLUE");
    drop(app);

    let app = make_app(&path);
    let repeated = create_team(&app, json!({"color": "BLUE", "team_name": null})).await;
    assert_eq!(repeated["uid"], blue);
    assert_eq!(repeated["team_description"], "keep");
    let custom = create_team(&app, json!({"color": "BLUE", "team_name": "Rescue"})).await;
    assert_ne!(custom["uid"], blue);
    assert_eq!(custom["team_name"], "Rescue");
    let explicit = create_team(&app, json!({"uid": "custom-blue", "color": "BLUE"})).await;
    assert_eq!(explicit["uid"], "custom-blue");
    let named = create_team(&app, json!({"color": "GREEN", "team_name": "RED"})).await;
    assert_eq!(named["uid"], "65ce79a3a3e4b51ec0ec52d1d3d2b0b9");
    let invalid = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/r3akt/teams")
                .header("X-API-Key", "secret")
                .header("content-type", "application/json")
                .body(Body::from(r#"{"color":"PINK"}"#))
                .expect("request"),
        )
        .await
        .expect("response");
    assert_eq!(invalid.status(), StatusCode::BAD_REQUEST);
    let body = invalid
        .into_body()
        .collect()
        .await
        .expect("body")
        .to_bytes();
    let error: Value = serde_json::from_slice(&body).expect("JSON");
    assert_eq!(
        error["detail"],
        "color must be one of: YELLOW, RED, BLUE, ORANGE, MAGENTA, MAROON, PURPLE, DARK_BLUE, CYAN, TEAL, GREEN, DARK_GREEN, BROWN"
    );
    drop(app);
    std::fs::remove_file(path).expect("cleanup database");
}

#[tokio::test]
async fn every_shared_canonical_color_creates_the_corresponding_team() {
    let path = std::env::temp_dir().join(format!("rch-colors-312-{}.db", uuid::Uuid::new_v4()));
    let app = make_app(&path);
    for &(uid, color) in CANONICAL_TEAMS {
        let created = create_team(&app, json!({"color": color})).await;
        assert_eq!(created["uid"], uid);
        assert_eq!(created["team_name"], color);
    }
    drop(app);
    std::fs::remove_file(path).expect("cleanup database");
}
