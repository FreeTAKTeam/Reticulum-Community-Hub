//! Marker domain rules, compared with the pre-extraction RCH behavior.

use r3akt_map_core::marker::{self, MarkerError};
use r3akt_map_core::{MarkerDraft, MarkerRecord, Position, idempotency, symbols};
use serde_json::json;
use sha2::{Digest, Sha256};

fn draft() -> MarkerDraft {
    MarkerDraft {
        marker_type: "vehicle".into(),
        symbol: "vehicle".into(),
        name: "Truck 1".into(),
        category: "vehicle".into(),
        position: Position::new(45.5, -73.5).unwrap(),
        notes: Some("synthetic".into()),
        origin_rch: String::new(),
    }
}

/// The server's former HTTP normalizer, kept as an oracle for unification.
fn legacy_http_normalize(symbol: &str) -> Option<String> {
    let raw = symbol.trim().to_ascii_lowercase();
    let parts = raw
        .split('.')
        .map(|part| {
            let mut out = String::new();
            let mut pending = false;
            for c in part.trim().chars().flat_map(char::to_lowercase) {
                if c.is_ascii_alphanumeric() {
                    if pending && !out.is_empty() {
                        out.push('-');
                    }
                    out.push(c);
                    pending = false;
                } else {
                    pending = true;
                }
            }
            out.trim_matches('-').to_string()
        })
        .filter(|s| !s.is_empty())
        .collect::<Vec<_>>();
    if parts.is_empty() {
        return None;
    }
    let joined = parts.join(".");
    let canonical = symbols::ALIASES
        .iter()
        .find(|(alias, _)| *alias == joined)
        .map_or(joined.as_str(), |(_, c)| c);
    Some(canonical.to_string())
}

#[test]
fn normalization_matches_former_http_and_core_rules() {
    for input in [
        "",
        "  ",
        "...",
        "Pin",
        "CAR",
        " Truck ",
        "UAV",
        "Group / Community",
        "vehicle--sensor",
        "Vehicle Sensor",
        "a.b",
        ".x.",
        "Ünknown",
        "fire!!",
        "medic",
        "team",
        "assignment",
        "radar",
        "9lives",
        "x_y.z w",
    ] {
        assert_eq!(
            symbols::normalize(input),
            legacy_http_normalize(input),
            "{input:?}"
        );
    }
    assert_eq!(symbols::normalize("Pin").as_deref(), Some("marker"));
    assert_eq!(
        symbols::normalize("group community").as_deref(),
        Some("group")
    );
    assert!(
        symbols::ALIASES
            .iter()
            .all(|(_, c)| symbols::is_supported(c))
    );
}

#[test]
fn catalog_json_is_unchanged() {
    let legacy = json!([
        {"id": "marker", "set": "mdi", "mdi": "map-marker", "description": "Marker", "tak": null, "category": "general"},
        {"id": "friendly", "set": "mdi", "mdi": "rectangle", "description": "Friendly", "tak": null, "category": "nato"},
        {"id": "hostile", "set": "mdi", "mdi": "rhombus", "description": "Hostile", "tak": null, "category": "nato"},
        {"id": "neutral", "set": "mdi", "mdi": "square", "description": "Neutral", "tak": null, "category": "nato"},
        {"id": "unknown", "set": "mdi", "mdi": "clover", "description": "Unknown", "tak": null, "category": "nato"},
        {"id": "vehicle", "set": "mdi", "mdi": "car", "description": "Vehicle", "tak": null, "category": "mobility"},
        {"id": "drone", "set": "mdi", "mdi": "drone", "description": "Drone", "tak": null, "category": "mobility"},
        {"id": "animal", "set": "mdi", "mdi": "paw", "description": "Animal", "tak": null, "category": "wildlife"},
        {"id": "sensor", "set": "mdi", "mdi": "radar", "description": "Sensor", "tak": null, "category": "equipment"},
        {"id": "radio", "set": "mdi", "mdi": "radio", "description": "Radio", "tak": null, "category": "equipment"},
        {"id": "antenna", "set": "mdi", "mdi": "antenna", "description": "Antenna", "tak": null, "category": "equipment"},
        {"id": "camera", "set": "mdi", "mdi": "camera", "description": "Camera", "tak": null, "category": "equipment"},
        {"id": "fire", "set": "mdi", "mdi": "fire", "description": "Fire", "tak": null, "category": "incident"},
        {"id": "flood", "set": "mdi", "mdi": "home-flood", "description": "Flood", "tak": null, "category": "incident"},
        {"id": "person", "set": "mdi", "mdi": "account", "description": "Person", "tak": null, "category": "people"},
        {"id": "group", "set": "mdi", "mdi": "account-group", "description": "Group / Community", "tak": null, "category": "people"},
        {"id": "infrastructure", "set": "mdi", "mdi": "office-building", "description": "Infrastructure", "tak": null, "category": "infrastructure"},
        {"id": "medic", "set": "mdi", "mdi": "hospital", "description": "Medic", "tak": null, "category": "medical"},
        {"id": "alert", "set": "mdi", "mdi": "alert", "description": "Alert", "tak": null, "category": "incident"},
        {"id": "task", "set": "mdi", "mdi": "clipboard-check", "description": "Task", "tak": null, "category": "task"}
    ]);
    assert_eq!(symbols::catalog_json(), legacy);
}

#[test]
fn coordinates_and_symbols_are_validated() {
    for (lat, lon) in [(90.0, 180.0), (-90.0, -180.0), (0.0, 0.0)] {
        assert!(Position::new(lat, lon).is_ok());
    }
    for (lat, lon, error) in [
        (90.01, 0.0, MarkerError::Latitude),
        (f64::NAN, 0.0, MarkerError::Latitude),
        (f64::INFINITY, 0.0, MarkerError::Latitude),
        (0.0, -180.01, MarkerError::Longitude),
        (0.0, f64::NAN, MarkerError::Longitude),
    ] {
        assert_eq!(Position::new(lat, lon), Err(error));
    }
    assert_eq!(
        MarkerError::Latitude.to_string(),
        "lat must be between -90 and 90"
    );
    assert_eq!(marker::marker_type("Car").as_deref(), Ok("vehicle"));
    assert_eq!(
        marker::marker_type("!!").unwrap_err().to_string(),
        "marker_type is required"
    );
    assert_eq!(
        marker::marker_type("spaceship"),
        Err(MarkerError::UnsupportedType)
    );
    assert_eq!(
        marker::marker_symbol("").unwrap_err().to_string(),
        "symbol is required"
    );
    assert_eq!(
        marker::marker_symbol("spaceship"),
        Err(MarkerError::UnsupportedSymbol)
    );
    assert_eq!(marker::normalize_name("  Alpha "), Some("Alpha".into()));
    assert_eq!(marker::normalize_name("   "), None);
}

#[test]
fn create_move_rename_and_api_representation() {
    let mut marker = MarkerRecord::create(draft(), "local-1".into(), 1_700_000_000_000);
    assert_eq!(marker.object_destination_hash.len(), 32);
    assert_eq!(marker.created_ts_ms, marker.updated_ts_ms);
    marker.move_to(Position::new(-12.25, 100.5).unwrap(), 1_700_000_001_500);
    marker.rename("Truck 2".into(), 1_700_000_002_000);
    marker.object_destination_hash = "abc".into();
    assert_eq!(
        marker.api_value(),
        json!({
            "object_destination_hash": "abc",
            "origin_rch": "",
            "type": "vehicle",
            "name": "Truck 2",
            "category": "vehicle",
            "symbol": "vehicle",
            "notes": "synthetic",
            "position": {"lat": -12.25, "lon": 100.5},
            "time": "2023-11-14T22:13:22Z",
            "stale_at": "2023-11-14T22:13:22Z",
            "created_at": "2023-11-14T22:13:20Z",
            "updated_at": "2023-11-14T22:13:22Z",
        })
    );
}

#[test]
fn idempotency_keys_and_fingerprints_are_stable() {
    assert!(idempotency::validate_key("abc-123").is_ok());
    for key in ["", "has space", "é", &"x".repeat(129)] {
        assert!(idempotency::validate_key(key).is_err(), "{key:?}");
    }
    assert!(idempotency::validate_key(&"x".repeat(128)).is_ok());
    let marker = MarkerRecord::create(draft(), "local".into(), 1);
    let payload = json!({"marker_type": marker.marker_type, "symbol": marker.symbol,
        "name": marker.name, "category": marker.category, "lat": marker.lat,
        "lon": marker.lon, "notes": marker.notes});
    let expected = format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(&payload).unwrap())
    );
    assert_eq!(idempotency::creation_fingerprint(&marker), expected);
    let mut other = marker.clone();
    other.object_destination_hash = "different".into();
    other.created_ts_ms = 99;
    assert_eq!(idempotency::creation_fingerprint(&other), expected);
    other.name = "Different".into();
    assert_ne!(idempotency::creation_fingerprint(&other), expected);
    assert!(idempotency::command_id("k").starts_with("rch/http/marker/"));
    assert_ne!(idempotency::command_id("k"), idempotency::command_id("k2"));
}
