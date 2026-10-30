use base64::Engine as _;
use r3akt_map_core::{
    telemetry,
    telemetry_encode::{self, Location},
};
use serde_json::Value;

#[test]
fn sideband_and_pyxis_golden_bytes_roundtrip_in_both_directions() {
    // Imported unchanged from Pyxis 5181fdd7; its reference tests execute
    // Sideband 2000d81a's Telemeter.packed and Location.pack against these bytes.
    let fixture: Value =
        serde_json::from_str(include_str!("fixtures/sideband_pyxis.json")).unwrap();
    for vector in fixture["vectors"].as_array().unwrap() {
        let number = |key: &str| vector[key].as_f64().unwrap();
        let encoded = telemetry_encode::encode(
            vector["sensor_timestamp_seconds"].as_u64().unwrap(),
            Some(Location {
                latitude: number("latitude"),
                longitude: number("longitude"),
                altitude: number("altitude"),
                speed: number("speed_kmh"),
                bearing: number("bearing"),
                accuracy: number("accuracy"),
                updated_at_s: vector["location_timestamp_seconds"].as_u64().unwrap(),
            }),
            None,
        )
        .unwrap();
        let hex = vector["packed_hex"].as_str().unwrap();
        let expected: Vec<u8> = (0..hex.len())
            .step_by(2)
            .map(|index| u8::from_str_radix(&hex[index..index + 2], 16).unwrap())
            .collect();
        assert_eq!(encoded, expected, "{}", vector["name"]);
        let decoded = telemetry::decode_field(&serde_json::json!(encoded)).unwrap();
        let location = &decoded.telemetry["location"];
        assert_eq!(location["altitude"], vector["altitude"]);
        assert_eq!(location["speed"], vector["speed_kmh"]);
        assert_eq!(
            location["last_update_timestamp"].as_f64(),
            Some(number("location_timestamp_seconds"))
        );
    }
}

#[test]
fn columba_226_golden_bytes_require_explicit_mps_profile() {
    let fixture: Value = serde_json::from_str(include_str!("fixtures/columba_2_2_6.json")).unwrap();
    let encoded = telemetry_encode::encode(
        1_700_000_000,
        Some(Location {
            latitude: 0.0,
            longitude: 0.0,
            altitude: -12.5,
            // Columba's historical codec copies m/s into the wire speed slot.
            speed: 1.25,
            bearing: -1.5,
            accuracy: 5.0,
            updated_at_s: 1_700_000_000,
        }),
        None,
    )
    .unwrap();
    assert_eq!(
        base64::engine::general_purpose::STANDARD.encode(encoded),
        fixture["packed_telemeter_b64"]
    );
}

#[test]
fn invalid_readings_fail_instead_of_wrapping() {
    let location = Location {
        latitude: 0.0,
        longitude: 0.0,
        altitude: -12.5,
        speed: 4.5,
        bearing: 1.0,
        accuracy: 5.0,
        updated_at_s: 1,
    };
    for invalid in [
        Location {
            latitude: 91.0,
            ..location
        },
        Location {
            altitude: f64::NAN,
            ..location
        },
        Location {
            speed: -1.0,
            ..location
        },
        Location {
            accuracy: 655.36,
            ..location
        },
    ] {
        assert!(telemetry_encode::encode(1, Some(invalid), None).is_err());
    }
    assert!(telemetry_encode::encode(1, None, Some((101.0, false))).is_err());
    let bytes = telemetry_encode::encode(2, None, Some((76.0, true))).unwrap();
    assert_eq!(
        telemetry::decode_field(&serde_json::json!(bytes))
            .unwrap()
            .telemetry["battery"]["charge_percent"],
        76.0
    );
}
