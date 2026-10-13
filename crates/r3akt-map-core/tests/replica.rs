//! Marker replication: API representation round trip and convergence.

use r3akt_map_core::marker::MarkerError;
use r3akt_map_core::replica::{self, DELETE_EVENT, UPSERT_EVENTS};
use r3akt_map_core::{MarkerDraft, MarkerRecord, Position};
use serde_json::json;

const ID: &str = "0123456789abcdef0123456789abcdef";

fn record(updated_ts_ms: i64) -> MarkerRecord {
    let draft = MarkerDraft {
        marker_type: "fire".into(),
        symbol: "fire".into(),
        name: "Ridge".into(),
        category: "incident".into(),
        position: Position::new(44.5, -1.25).expect("position"),
        notes: Some("north slope".into()),
        origin_rch: "abcdef".into(),
    };
    let mut marker =
        MarkerRecord::create_with_id(draft, ID.into(), "sender".into(), 1_700_000_000_123);
    marker.updated_ts_ms = updated_ts_ms;
    marker
}

#[test]
fn api_value_round_trips_through_shared_validation() {
    let original = record(1_700_000_005_456);
    let replica =
        replica::from_api_value(&original.api_value(), "receiver".into()).expect("replica");
    assert_eq!(replica.local_id, "receiver");
    assert_eq!(
        MarkerRecord {
            local_id: original.local_id.clone(),
            ..replica
        },
        original
    );
    assert!(UPSERT_EVENTS.contains(&"mission.marker.position.updated"));
    assert_eq!(DELETE_EVENT, "mission.marker.deleted");
}

#[test]
fn replicas_are_rejected_like_local_input() {
    let valid = record(1).api_value();
    let cases = [
        (
            "object_destination_hash",
            json!("short"),
            MarkerError::Identifier,
        ),
        (
            "object_destination_hash",
            json!(null),
            MarkerError::Missing("object_destination_hash"),
        ),
        ("symbol", json!("spaceship"), MarkerError::UnsupportedSymbol),
        ("type", json!("spaceship"), MarkerError::UnsupportedType),
        (
            "position",
            json!({"lat": 91.0, "lon": 0.0}),
            MarkerError::Latitude,
        ),
        ("position", json!({"lat": 0.0}), MarkerError::Longitude),
        (
            "updated_at",
            json!("yesterday"),
            MarkerError::Missing("updated_at"),
        ),
    ];
    for (key, value, expected) in cases {
        let mut payload = valid.clone();
        payload[key] = value;
        assert_eq!(
            replica::from_api_value(&payload, String::new()),
            Err(expected),
            "{key}"
        );
    }
    let mut aliased = valid.clone();
    aliased["symbol"] = json!("Wildfire");
    assert_eq!(
        replica::from_api_value(&aliased, String::new())
            .expect("alias")
            .symbol,
        "fire"
    );
}

#[test]
fn newest_update_wins_and_ties_keep_the_stored_copy() {
    let stored = record(2_000);
    assert!(replica::supersedes(&record(2_001), Some(&stored)));
    assert!(!replica::supersedes(&record(2_000), Some(&stored)));
    assert!(!replica::supersedes(&record(1_999), Some(&stored)));
    assert!(replica::supersedes(&record(1), None));
}
