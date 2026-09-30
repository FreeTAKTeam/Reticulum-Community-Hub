use crate::{
    AppState, create_app_with_state, message_persistence,
    record_outbound_message_deferred_with_metadata, update_outbound_delivery_state,
};
use axum::{
    body::Body,
    http::{Method, StatusCode},
};
use http_body_util::BodyExt;
use serde_json::{Value, json};
use std::path::PathBuf;
use tokio::sync::broadcast;
use tower::ServiceExt;
use uuid::Uuid;

fn fixture() -> (AppState, PathBuf) {
    let directory = std::env::temp_dir().join(format!("rch-receipt-callbacks-{}", Uuid::new_v4()));
    std::fs::create_dir(&directory).expect("directory");
    let state = AppState::from_sqlite_path(directory.join("state.db")).expect("state");
    (state, directory)
}

async fn delivery_callback(state: &AppState, route: &str, payload: Value) -> (StatusCode, Value) {
    let response = create_app_with_state(state.clone().with_api_key("fixture-key"))
        .oneshot(
            axum::http::Request::builder()
                .method(Method::POST)
                .uri(route)
                .header("X-API-Key", "fixture-key")
                .header("Content-Type", "application/json")
                .body(Body::from(payload.to_string()))
                .expect("request"),
        )
        .await
        .expect("response");
    let status = response.status();
    let body = serde_json::from_slice(
        &response
            .into_body()
            .collect()
            .await
            .expect("body")
            .to_bytes(),
    )
    .expect("JSON");
    (status, body)
}

async fn assert_stale_delivery_callback_preserves_receipt(route: &str) {
    for terminal in ["delivered", "propagated"] {
        let (state, directory) = fixture();
        let message = record_outbound_message_deferred_with_metadata(
            &state,
            "fixture",
            None,
            Some("00112233445566778899aabbccddeeff".to_string()),
            Vec::new(),
            false,
            json!({"max_attempts": 0}),
        )
        .expect("admit");
        update_outbound_delivery_state(
            &state,
            &message.message_id,
            terminal,
            json!({"acked": true}),
        )
        .expect("receipt");
        let settled = message_persistence::current(&state, &message.message_id).expect("message");
        let expected = serde_json::to_value(&settled).expect("record");
        let events = state.system_events.read().expect("events").len();
        let mut updates = state.message_events.subscribe();
        let (status, response) = delivery_callback(
            &state,
            route,
            json!({
                "message_id": message.message_id, "reason": "late callback", "attempts": 3
            }),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(
            response["status"], terminal,
            "{route} must preserve a receipt"
        );
        assert_eq!(response["message"], expected);
        assert_eq!(state.system_events.read().expect("events").len(), events);
        assert!(matches!(
            updates.try_recv(),
            Err(broadcast::error::TryRecvError::Empty)
        ));
        let reopened = AppState::from_sqlite_path(directory.join("state.db")).expect("restart");
        assert_eq!(
            serde_json::to_value(&reopened.messages.read().expect("messages")[0]).expect("record"),
            expected
        );
        drop(reopened);
        drop(state);
        std::fs::remove_dir_all(directory).expect("cleanup");
    }
}

#[tokio::test]
async fn stale_delivery_retry_callback_preserves_receipts() {
    assert_stale_delivery_callback_preserves_receipt("/internal/delivery-retry").await;
}

#[tokio::test]
async fn stale_delivery_propagation_callback_preserves_receipts() {
    assert_stale_delivery_callback_preserves_receipt("/internal/delivery-propagation").await;
}

#[tokio::test]
async fn stale_delivery_drop_callback_preserves_receipts() {
    assert_stale_delivery_callback_preserves_receipt("/internal/delivery-drop").await;
}

#[tokio::test]
async fn stale_delivery_attempt_callback_preserves_receipts() {
    assert_stale_delivery_callback_preserves_receipt("/internal/delivery-attempt").await;
}

async fn assert_destination_callback_skips_settled_history(route: &str) {
    for terminal in ["delivered", "propagated"] {
        let (state, directory) = fixture();
        let destination = "00112233445566778899aabbccddeeff";
        let settled = record_outbound_message_deferred_with_metadata(
            &state,
            "settled",
            None,
            Some(destination.to_string()),
            Vec::new(),
            false,
            json!({}),
        )
        .expect("first admission");
        update_outbound_delivery_state(
            &state,
            &settled.message_id,
            terminal,
            json!({"acked": true}),
        )
        .expect("receipt");
        let settled = message_persistence::current(&state, &settled.message_id).expect("message");
        let expected = serde_json::to_value(&settled).expect("record");
        let pending = record_outbound_message_deferred_with_metadata(
            &state,
            "pending",
            None,
            Some(destination.to_string()),
            Vec::new(),
            false,
            json!({}),
        )
        .expect("second admission");
        let (status, response) =
            delivery_callback(&state, route, json!({"destination": destination})).await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(
            response["message"]["message_id"], pending.message_id,
            "{route} must select eligible work rather than settled history"
        );
        let reopened = AppState::from_sqlite_path(directory.join("state.db")).expect("restart");
        let stored = reopened
            .messages
            .read()
            .expect("messages")
            .iter()
            .find(|message| message.message_id == settled.message_id)
            .cloned()
            .expect("settled");
        assert_eq!(serde_json::to_value(stored).expect("record"), expected);
        drop(reopened);
        drop(state);
        std::fs::remove_dir_all(directory).expect("cleanup");
    }
}

#[tokio::test]
async fn destination_delivery_propagation_skips_settled_history() {
    assert_destination_callback_skips_settled_history("/internal/delivery-propagation").await;
}

#[tokio::test]
async fn destination_delivery_drop_skips_settled_history() {
    assert_destination_callback_skips_settled_history("/internal/delivery-drop").await;
}

#[tokio::test]
async fn destination_delivery_attempt_skips_settled_history() {
    assert_destination_callback_skips_settled_history("/internal/delivery-attempt").await;
}

#[tokio::test]
async fn late_propagation_receipt_cannot_downgrade_confirmed_delivery() {
    let (state, directory) = fixture();
    let message = record_outbound_message_deferred_with_metadata(
        &state,
        "fixture",
        None,
        Some("00112233445566778899aabbccddeeff".to_string()),
        Vec::new(),
        false,
        json!({}),
    )
    .expect("admit");
    let (_, confirmed) = delivery_callback(
        &state,
        "/internal/delivery-receipt",
        json!({
            "message_id": message.message_id, "acknowledgement_type": "delivery"
        }),
    )
    .await;
    let events = state.system_events.read().expect("events").len();
    let mut updates = state.message_events.subscribe();
    let (status, response) = delivery_callback(
        &state,
        "/internal/delivery-receipt",
        json!({
            "message_id": message.message_id, "acknowledgement_type": "propagation_acceptance"
        }),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(response["status"], "delivered");
    assert_eq!(response["message"], confirmed["message"]);
    assert_eq!(state.system_events.read().expect("events").len(), events);
    assert!(matches!(
        updates.try_recv(),
        Err(broadcast::error::TryRecvError::Empty)
    ));
    let reopened = AppState::from_sqlite_path(directory.join("state.db")).expect("restart");
    assert_eq!(
        serde_json::to_value(&reopened.messages.read().expect("messages")[0]).expect("record"),
        confirmed["message"]
    );
    drop(reopened);
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[tokio::test]
async fn delivery_receipt_upgrades_acknowledged_propagation() {
    let (state, directory) = fixture();
    let message = record_outbound_message_deferred_with_metadata(
        &state,
        "fixture",
        None,
        Some("00112233445566778899aabbccddeeff".to_string()),
        Vec::new(),
        false,
        json!({}),
    )
    .expect("admit");
    let (status, propagated) = delivery_callback(
        &state,
        "/internal/delivery-receipt",
        json!({
            "message_id": message.message_id, "acknowledgement_type": "propagation_acceptance"
        }),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(propagated["status"], "propagated");
    let (status, delivered) = delivery_callback(
        &state,
        "/internal/delivery-receipt",
        json!({
            "message_id": message.message_id, "acknowledgement_type": "delivery"
        }),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(delivered["status"], "delivered");
    assert_eq!(delivered["message"]["delivery_metadata"]["acked"], true);
    let reopened = AppState::from_sqlite_path(directory.join("state.db")).expect("restart");
    assert_eq!(
        serde_json::to_value(&reopened.messages.read().expect("messages")[0]).expect("record"),
        delivered["message"]
    );
    drop(reopened);
    drop(state);
    std::fs::remove_dir_all(directory).expect("cleanup");
}
