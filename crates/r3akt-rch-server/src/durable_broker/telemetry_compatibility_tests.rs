use super::*;
use axum::{
    body::Body,
    http::{Method, Request, StatusCode},
};
use base64::{Engine as _, engine::general_purpose::STANDARD};
use http_body_util::BodyExt as _;
use tower::ServiceExt as _;

fn fixture() -> Value {
    serde_json::from_str(include_str!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../r3akt-transport-rns/tests/fixtures/columba_2_2_6.json"
    )))
    .unwrap()
}
fn setup() -> (PathBuf, AppState) {
    let dir = std::env::temp_dir().join(format!("rch-258-{}", Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    let mut state = AppState::from_sqlite_path(dir.join("rch.db"))
        .unwrap()
        .with_api_key("synthetic-test-key");
    state.reticulumd_source = Some(Arc::new(fixture()["destination"].as_str().unwrap().into()));
    (dir, state)
}
fn store_event(state: &AppState, position: u64, event_type: &str, payload: Value) {
    let mut store = open(state).unwrap();
    let consumer = store.durable_consumer_id().unwrap();
    store
        .store_inbox_batch(&InboxBatch {
            journal_id: "synthetic-telemetry-journal".into(),
            consumer_id: consumer.clone(),
            start: position - 1,
            end: position,
            receipt: format!("synthetic-receipt:{position}"),
            events: vec![InboxEvent {
                version: 1,
                position,
                created_at: 1_700_000_100,
                event_type: event_type.into(),
                payload,
            }],
        })
        .unwrap();
    drop(store);
    assert!(super::application::apply(state, &consumer).unwrap());
}
fn upload(raw: bool) -> Value {
    let f = fixture();
    let mut payload = json!({"message":{"id":f["optional_frame"]["id"],"source":f["source"],"destination":f["destination"],"direction":"in","content":"","timestamp":1_700_000_100,"fields":f["daemon_fields"]}});
    if raw {
        payload["lxmf_bytes_hex"] = f["optional_frame"]["wire_hex"].clone();
    }
    payload
}
#[tokio::test]
async fn actual_codec_journal_persists_restarts_and_projects_normal_telemetry_api() {
    for raw in [false, true] {
        let (dir, state) = setup();
        store_event(
            &state,
            1,
            if raw { "inbound" } else { "bootstrap_message" },
            upload(raw),
        );
        let persisted = open(&state).unwrap().load_snapshot().unwrap().unwrap();
        assert_eq!(persisted.telemetry_records.len(), 1);
        let record = &persisted.telemetry_records[0];
        assert_eq!(record.timestamp_s, 1_700_000_000);
        assert_eq!(record.telemetry["location"]["altitude"], -12.5);
        if raw {
            assert_eq!(
                record.packed_telemeter.as_ref().unwrap(),
                &STANDARD
                    .decode(fixture()["optional_telemeter_b64"].as_str().unwrap())
                    .unwrap()
            );
            assert_eq!(record.telemetry["temperature"]["c"], 21.5);
            assert_eq!(record.telemetry["200"]["synthetic"], true);
        } else {
            assert!(record.packed_telemeter.is_none());
        }
        let restarted = AppState::from_sqlite_path(dir.join("rch.db"))
            .unwrap()
            .with_api_key("synthetic-test-key");
        let response = create_app_with_state(restarted)
            .oneshot(
                Request::builder()
                    .method(Method::GET)
                    .uri("/Telemetry?since=0")
                    .header("X-API-Key", "synthetic-test-key")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = response.into_body().collect().await.unwrap().to_bytes();
        let payload: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(payload["entries"].as_array().unwrap().len(), 1);
        assert_eq!(
            payload["entries"][0]["telemetry"]["location"]["latitude"],
            0.0
        );
        assert_eq!(
            payload["entries"][0]["telemetry"]["location"]["longitude"],
            0.0
        );
        assert_eq!(
            payload["entries"][0]["telemetry"]["location"]["bearing"],
            -1.5
        );
        assert!(payload["entries"][0].get("packed_telemeter").is_none());
        std::fs::remove_dir_all(dir).unwrap();
    }
}
#[test]
fn malformed_sensor_diagnostic_is_durable_without_losing_valid_collector_command() {
    let (dir, state) = setup();
    let mut payload = upload(false);
    payload["message"]["fields"] = json!({"2":{"location":{"latitude":"private-synthetic-reading","longitude":0}},"9":[{"1":0}]});
    store_event(&state, 1, "inbound", payload);
    assert!(state.telemetry_records.read().unwrap().is_empty());
    assert!(
        open(&state)
            .unwrap()
            .pending_broker_intent()
            .unwrap()
            .is_some()
    );
    let restored = AppState::from_sqlite_path(dir.join("rch.db")).unwrap();
    let events = restored.system_events.read().unwrap();
    let diagnostic = events
        .iter()
        .find(|e| e.event_type == "lxmf_telemetry_diagnostic")
        .unwrap();
    assert!(diagnostic.message.contains("coordinates"));
    assert!(!diagnostic.message.contains("private-synthetic-reading"));
    assert!(
        !diagnostic
            .message
            .contains(fixture()["source"].as_str().unwrap())
    );
    drop(events);
    std::fs::remove_dir_all(dir).unwrap();
}
