//! RCH #258 stage A fixtures through the shared telemetry decoder.

use base64::Engine as _;
use base64::engine::general_purpose::STANDARD;
use r3akt_map_core::telemetry;
use serde_json::{Value, json};

fn fixture() -> Value {
    serde_json::from_str(include_str!("fixtures/columba_2_2_6.json")).unwrap()
}

#[test]
fn columba_packed_telemeter_decodes_signed_readings_and_keeps_bytes() {
    let packed = fixture()["packed_telemeter_b64"].clone();
    let checked = telemetry::decode_field(&packed).unwrap();
    let location = &checked.telemetry["location"];
    assert_eq!(location["latitude"], 0.0);
    assert_eq!(location["altitude"], -12.5);
    assert_eq!(location["speed"], 1.25);
    assert_eq!(location["bearing"], -1.5);
    assert_eq!(location["accuracy"], 5.0);
    assert_eq!(checked.timestamp_s, Some(1_700_000_000));
    assert_eq!(
        checked.packed_telemeter.unwrap(),
        STANDARD.decode(packed.as_str().unwrap()).unwrap()
    );
}

#[test]
fn daemon_flat_projection_normalizes_to_the_map_shape() {
    let checked = telemetry::decode_field(&fixture()["daemon_fields"]["2"]).unwrap();
    assert_eq!(checked.telemetry["location"]["latitude"], 0.0);
    assert_eq!(checked.telemetry["location"]["altitude"], -12.5);
    assert_eq!(checked.timestamp_s, Some(1_700_000_000));
    assert!(checked.packed_telemeter.is_none());
}

#[test]
fn optional_and_unknown_sensors_are_preserved() {
    let checked = telemetry::decode_field(&fixture()["optional_telemeter_b64"]).unwrap();
    assert!(checked.telemetry.get("location").is_some());
    let checked =
        telemetry::decode_field(&json!({"1":1_700_000_000,"2":null,"7":21.5,"200":{"x":true}}))
            .unwrap();
    assert!(checked.telemetry.get("location").is_none());
    assert_eq!(checked.telemetry["temperature"]["c"], 21.5);
    assert_eq!(checked.telemetry["200"]["x"], true);
}

#[test]
fn malformed_truncated_nonfinite_and_versioned_payloads_are_rejected() {
    let good = STANDARD
        .decode(fixture()["packed_telemeter_b64"].as_str().unwrap())
        .unwrap();
    let mut trailing = good.clone();
    trailing.push(0);
    let mut nonfinite = vec![0x81, 0x01, 0xcb];
    nonfinite.extend(f64::NAN.to_be_bytes());
    let mut cases: Vec<Value> = vec![
        json!(trailing),
        json!(nonfinite),
        json!([0xdd, 255, 255, 255, 255]),
        json!({"1": true}),
        json!({"location": {"latitude": 91.0, "longitude": 0.0}}),
        json!({"location": {"latitude": "private-position", "longitude": 0.0}}),
        json!({"schema_version": 99, "location": {"latitude": 0, "longitude": 0}}),
        json!({"version": 99, "lat": 0, "lon": 0}),
        json!([1, 2, 3]),
        json!(vec![0; 1024 * 1024 + 1]),
    ];
    cases.extend((0..good.len()).map(|n| json!(good[..n].to_vec())));
    for payload in cases {
        let error = telemetry::decode_field(&payload).unwrap_err();
        assert!(error.contains("FIELD_TELEMETRY"), "{error}");
        assert!(!error.contains("private-position"));
    }
}
