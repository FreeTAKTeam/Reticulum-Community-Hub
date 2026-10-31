use super::{pending_broker_requests, test_client};
use crate::*;
use axum::http::{Method, Request};
use tower::ServiceExt;

#[tokio::test]
async fn marker_position_metadata_is_atomic_and_preserves_operator_fields() {
    for persistent in [false, true] {
        let directory =
            std::env::temp_dir().join(format!("rch-marker-metadata-{}", Uuid::new_v4()));
        std::fs::create_dir(&directory).expect("directory");
        let db = directory.join("state.db");
        let state = if persistent {
            AppState::from_sqlite_path(&db).expect("state")
        } else {
            AppState::default()
        };
        create_marker(
            State(state.clone()),
            Json(json!({
                "type": "friendly", "symbol": "friendly", "name": "Operator label",
                "category": "tak", "lat": 45.0, "lon": -63.0, "notes": "old observation"
            })),
        )
        .await
        .expect("create");
        let id = state
            .markers
            .read()
            .expect("markers")
            .keys()
            .next()
            .expect("id")
            .clone();
        let patch = serde_json::from_value(json!({
            "lat": 46.0, "lon": -64.0, "type": "hostile", "symbol": "hostile",
            "notes": "new observation"
        }))
        .expect("payload");
        let _response = patch_marker_position(Path(id.clone()), State(state.clone()), Json(patch))
            .await
            .expect("update");
        let state = if persistent {
            AppState::from_sqlite_path(&db).expect("restart")
        } else {
            state
        };
        let marker = state.markers.read().expect("markers")[&id].clone();
        assert_eq!(marker.name, "Operator label");
        assert_eq!(marker.category, "tak");
        assert_eq!(marker.marker_type, "hostile");
        assert_eq!(marker.symbol, "hostile");
        assert_eq!(marker.notes.as_deref(), Some("new observation"));
        assert!((marker.lat - 46.0).abs() < f64::EPSILON);
        assert!((marker.lon + 64.0).abs() < f64::EPSILON);
        for invalid in [
            json!({"lat": 44.0, "lon": -62.0, "type": "invalid", "symbol": "friendly", "notes": "bad"}),
            json!({"lat": 44.0, "lon": -62.0, "type": "friendly", "symbol": "invalid", "notes": "bad"}),
            json!({"lat": 91.0, "lon": -62.0, "type": "friendly", "symbol": "friendly", "notes": "bad"}),
        ] {
            assert!(
                patch_marker_position(
                    Path(id.clone()),
                    State(state.clone()),
                    Json(serde_json::from_value(invalid).expect("payload"))
                )
                .await
                .is_err()
            );
            assert_eq!(state.markers.read().expect("markers")[&id], marker);
        }
        let old_payload =
            serde_json::from_value(json!({"lat": 47.0, "lon": -65.0})).expect("old payload");
        let _response =
            patch_marker_position(Path(id.clone()), State(state.clone()), Json(old_payload))
                .await
                .expect("old lat/lon-only update");
        let latest = state.markers.read().expect("markers")[&id].clone();
        assert_eq!(latest.name, marker.name);
        assert_eq!(latest.symbol, marker.symbol);
        assert_eq!(latest.notes, marker.notes);
        std::fs::remove_dir_all(directory).expect("cleanup");
    }
}

#[tokio::test]
async fn failed_marker_metadata_write_does_not_publish_any_partial_change() {
    let directory = std::env::temp_dir().join(format!("rch-marker-write-{}", Uuid::new_v4()));
    std::fs::create_dir(&directory).expect("directory");
    let db = directory.join("state.db");
    let state = AppState::from_sqlite_path(&db).expect("state");
    create_marker(
        State(state.clone()),
        Json(json!({
            "type": "friendly", "symbol": "friendly", "lat": 45.0, "lon": -63.0
        })),
    )
    .await
    .expect("create");
    let before = state
        .markers
        .read()
        .expect("markers")
        .values()
        .next()
        .expect("marker")
        .clone();
    rusqlite::Connection::open(&db).expect("connection").execute_batch(
        "CREATE TRIGGER deny_marker_update BEFORE UPDATE ON rch_markers BEGIN SELECT RAISE(ABORT, 'fixture failure'); END;"
    ).expect("trigger");
    let payload = serde_json::from_value(json!({
        "lat": 46.0, "lon": -64.0, "type": "hostile", "symbol": "hostile", "notes": "new"
    }))
    .expect("payload");
    assert!(
        patch_marker_position(
            Path(before.object_destination_hash.clone()),
            State(state.clone()),
            Json(payload)
        )
        .await
        .is_err()
    );
    assert_eq!(
        state.markers.read().expect("markers")[&before.object_destination_hash],
        before
    );
    let reopened = AppState::from_sqlite_path(&db).expect("reopen");
    assert_eq!(
        reopened.markers.read().expect("markers")[&before.object_destination_hash],
        before
    );
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[tokio::test]
async fn metadata_position_patch_keeps_authorized_rem_replication() {
    let directory = std::env::temp_dir().join(format!("rch-marker-replication-{}", Uuid::new_v4()));
    std::fs::create_dir(&directory).expect("directory");
    let db = directory.join("state.db");
    let now = unix_now_ms();
    let rem = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    let generic = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    let mut snapshot = r3akt_rch_core::RchCore::new().snapshot();
    snapshot.clients = vec![test_client(rem, now), test_client(generic, now)];
    snapshot.identity_announces = [(rem, "rem"), (generic, "generic_lxmf")]
        .into_iter()
        .map(
            |(identity, client_type)| r3akt_rch_core::IdentityAnnounceRecord {
                destination_hash: identity.to_string(),
                announced_identity_hash: None,
                display_name: None,
                source_interface: Some("identity".to_string()),
                announce_capabilities: if client_type == "rem" {
                    vec!["r3akt".to_string(), "emergencymessages".to_string()]
                } else {
                    vec!["group_chat".to_string()]
                },
                client_type: client_type.to_string(),
                first_seen_ts_ms: now,
                last_seen_ts_ms: now,
            },
        )
        .collect();
    let original = MarkerRecord::create(
        r3akt_map_core::MarkerDraft {
            marker_type: "friendly".to_string(),
            symbol: "friendly".to_string(),
            name: "Operator label".to_string(),
            category: "tak".to_string(),
            position: r3akt_map_core::Position::new(45.0, -63.0).expect("position"),
            notes: None,
            origin_rch: "rch-origin".to_string(),
        },
        "local-marker".to_string(),
        now,
    );
    snapshot.markers = vec![original.clone()];
    let mut store = r3akt_rch_core::RchSqliteStore::open(&db).expect("store");
    store.save_snapshot(&snapshot).expect("save snapshot");
    let state = AppState::from_sqlite_path(&db)
        .expect("state")
        .with_api_key("secret")
        .with_test_reticulumd_source("source-destination");
    let app = create_app_with_state(state.clone());
    let notes = "rch-tak-uid-sha256:peer rch-tak-time:2026-05-11T00:02:00Z TAK CoT type=a-h-G-U-C";
    let payload =
        json!({"lat": 46.0, "lon": -64.0, "type": "hostile", "symbol": "hostile", "notes": notes});
    for authorized in [false, true] {
        let mut request = Request::builder()
            .method(Method::PATCH)
            .uri(format!(
                "/api/markers/{}/position",
                original.object_destination_hash
            ))
            .header("Content-Type", "application/json");
        if authorized {
            request = request.header("X-API-Key", "secret");
        }
        let response = app
            .clone()
            .oneshot(
                request
                    .body(Body::from(payload.to_string()))
                    .expect("request"),
            )
            .await
            .expect("response");
        assert_eq!(
            response.status(),
            if authorized {
                StatusCode::OK
            } else {
                StatusCode::UNAUTHORIZED
            }
        );
        if !authorized {
            assert_eq!(
                state.markers.read().expect("markers")[&original.object_destination_hash],
                original
            );
            assert!(pending_broker_requests(&db).is_empty());
        }
    }
    let updated = state.markers.read().expect("markers")[&original.object_destination_hash].clone();
    assert_eq!(updated.name, original.name);
    assert_eq!(updated.category, original.category);
    assert_eq!(updated.origin_rch, original.origin_rch);
    let requests = pending_broker_requests(&db);
    assert_eq!(
        requests.len(),
        2,
        "REM and generic peers receive marker updates"
    );
    let rem_request = requests
        .iter()
        .find(|request| request["destination"] == rem)
        .unwrap();
    let generic_request = requests
        .iter()
        .find(|request| request["destination"] == generic)
        .unwrap();
    let fields = &rem_request["fields"];
    assert_eq!(generic_request["fields"]["3"], fields["3"]);
    assert!(generic_request["fields"].get("9").is_none());
    let telemetry =
        r3akt_map_core::telemetry::decode_field(&generic_request["fields"]["3"][0][2]).unwrap();
    assert_eq!(telemetry.telemetry["location"]["latitude"], 46.0);
    assert_eq!(telemetry.telemetry["location"]["longitude"], -64.0);
    let event = &fields[r3akt_profile_rch::FIELD_EVENT.to_string()];
    assert_eq!(event["event_type"], "mission.marker.updated");
    assert_eq!(event["payload"], updated.api_value());
    let replica = r3akt_map_core::replica::from_api_value(&event["payload"], "rem".to_string())
        .expect("replica");
    assert_eq!(
        replica.object_destination_hash,
        original.object_destination_hash
    );
    assert_eq!(replica.symbol, "hostile");
    assert_eq!(replica.notes.as_deref(), Some(notes));
    let legacy = &fields[FIELD_COMMANDS.to_string()][0]["args"];
    assert_eq!(legacy["marker_type"], "hostile");
    assert_eq!(legacy["symbol"], "hostile");
    assert_eq!(legacy["notes"], notes);
    drop(store);
    std::fs::remove_dir_all(directory).expect("cleanup");
}
