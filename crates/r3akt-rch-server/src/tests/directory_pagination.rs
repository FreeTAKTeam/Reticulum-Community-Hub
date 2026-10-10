use super::*;

#[tokio::test]
async fn identity_pagination_bounds_large_inventory_without_changing_legacy_shape() {
    let state = crate::AppState::default().with_api_key("secret");
    {
        let mut records = state.identity_states.write().expect("identities");
        for index in 0..30_001 {
            let identity = format!("{index:032x}");
            records.insert(
                identity.clone(),
                crate::IdentityStatusRecord {
                    identity,
                    is_banned: false,
                    is_blackholed: false,
                    updated_ts_ms: 0,
                },
            );
        }
    }
    let app = crate::create_app_with_state(state);
    let request = |uri: &str| {
        Request::builder()
            .uri(uri)
            .header("X-API-Key", "secret")
            .body(Body::empty())
            .expect("request")
    };
    let legacy = app
        .clone()
        .oneshot(request("/Identities"))
        .await
        .expect("legacy");
    let body = legacy.into_body().collect().await.expect("body").to_bytes();
    assert!(
        body.len() > 8 * 1024 * 1024,
        "regression fixture exceeds UI response limit"
    );
    let legacy: Value = serde_json::from_slice(&body).expect("legacy array");
    assert_eq!(legacy.as_array().expect("array").len(), 30_001);
    let mut collected = Vec::new();
    for page in 1..=301 {
        let response = app
            .clone()
            .oneshot(request(&format!("/Identities?page={page}&per_page=100")))
            .await
            .expect("page");
        assert_eq!(response.status(), StatusCode::OK);
        let body = response
            .into_body()
            .collect()
            .await
            .expect("body")
            .to_bytes();
        assert!(body.len() < 8 * 1024 * 1024);
        let payload: Value = serde_json::from_slice(&body).expect("page json");
        assert_eq!(payload["total"], 30_001);
        assert_eq!(payload["total_pages"], 301);
        assert_eq!(payload["has_next"], page < 301);
        collected.extend(payload["items"].as_array().expect("items").iter().cloned());
    }
    assert_eq!(Value::Array(collected), legacy);
    let response = app
        .clone()
        .oneshot(request("/Identities?page=302&per_page=100"))
        .await
        .expect("empty page");
    let payload: Value = serde_json::from_slice(
        &response
            .into_body()
            .collect()
            .await
            .expect("body")
            .to_bytes(),
    )
    .expect("json");
    assert_eq!(payload["items"], json!([]));
    for uri in [
        "/Identities?page=0",
        "/Identities?per_page=-1",
        "/Identities?per_page=501",
    ] {
        assert_eq!(
            app.clone()
                .oneshot(request(uri))
                .await
                .expect("invalid page")
                .status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
    }
}
