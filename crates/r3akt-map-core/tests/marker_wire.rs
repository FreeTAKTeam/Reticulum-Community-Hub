use r3akt_map_core::{
    MarkerDraft, MarkerRecord, Position, marker_wire, msgpack, replica, telemetry,
};
use serde_json::json;
use std::fmt::Write as _;

fn marker() -> MarkerRecord {
    MarkerRecord::create_with_id(
        MarkerDraft {
            marker_type: "fire".into(),
            symbol: "fire".into(),
            name: "Ridge".into(),
            category: "incident".into(),
            position: Position::new(44.5, -1.25).unwrap(),
            notes: Some("Synthetic marker".into()),
            origin_rch: "rch".into(),
        },
        "0123456789abcdef0123456789abcdef".into(),
        "local".into(),
        1_700_000_000_123,
    )
}

#[test]
fn marker_stream_and_replica_identify_the_object_not_the_sender() {
    let marker = marker();
    let packed =
        marker_wire::encode_fields("mission.marker.created", &marker, "sender", None).unwrap();
    let fields = msgpack::to_json(&packed).unwrap();
    assert!(
        fields.get("2").is_none(),
        "a marker must not overwrite the sender's GPS position"
    );
    let entry = &fields["3"][0];
    assert_eq!(
        entry[0],
        json!([
            1, 35, 69, 103, 137, 171, 205, 239, 1, 35, 69, 103, 137, 171, 205, 239
        ])
    );
    assert_eq!(entry[1], 1_700_000_000);
    assert_eq!(entry[3], json!(["fire", [255, 255, 255], [48, 96, 160]]));
    let decoded = telemetry::decode_field(&entry[2]).unwrap();
    assert_eq!(decoded.telemetry["location"]["latitude"], 44.5);
    assert_eq!(decoded.telemetry["location"]["longitude"], -1.25);
    let replica = replica::from_api_value(&fields["13"]["payload"], "receiver".into()).unwrap();
    assert_eq!(
        replica.object_destination_hash,
        marker.object_destination_hash
    );
    assert_eq!(replica.updated_ts_ms, marker.updated_ts_ms);
    // Binary types must survive the wire, not just a JSON projection.
    let (msgpack::Value::Map(map), consumed) = msgpack::parse_value(&packed).unwrap() else {
        panic!("map");
    };
    assert_eq!(consumed, packed.len());
    let msgpack::Value::Array(entries) = &map[0].1 else {
        panic!("stream array");
    };
    let msgpack::Value::Array(entry) = &entries[0] else {
        panic!("entry array");
    };
    assert!(matches!(&entry[0], msgpack::Value::Bytes(value) if value.len() == 16));
    assert!(matches!(&entry[2], msgpack::Value::Bytes(_)));
}

#[test]
fn marker_updates_keep_identity_and_deletes_do_not_publish_a_live_location() {
    let mut marker = marker();
    marker.move_to(Position::new(-12.5, 179.9).unwrap(), 1_700_000_100_000);
    let packed =
        marker_wire::encode_fields("mission.marker.updated", &marker, "rem", None).unwrap();
    let fields = msgpack::to_json(&packed).unwrap();
    assert_eq!(fields["3"][0][1], 1_700_000_100);
    assert_eq!(
        fields["13"]["payload"]["object_destination_hash"],
        marker.object_destination_hash
    );
    let packed = marker_wire::encode_fields(replica::DELETE_EVENT, &marker, "rem", None).unwrap();
    let fields = msgpack::to_json(&packed).unwrap();
    assert!(fields.get("3").is_none());
    assert_eq!(fields["13"]["event_type"], replica::DELETE_EVENT);
    assert!(marker_wire::encode_fields("unknown", &marker, "rem", None).is_err());
    marker.updated_ts_ms = -1;
    assert!(marker_wire::packed_telemeter(&marker).is_err());
}

#[test]
fn marker_sensor_bytes_match_sideband_reference_fixture() {
    let fixture: serde_json::Value =
        serde_json::from_str(include_str!("fixtures/marker_stream.json")).unwrap();
    let packed = marker_wire::packed_telemeter(&marker()).unwrap();
    let hex: String = packed.iter().fold(String::new(), |mut output, byte| {
        write!(output, "{byte:02x}").unwrap();
        output
    });
    assert_eq!(hex, fixture["packed_telemeter_hex"].as_str().unwrap());
    let wire =
        marker_wire::encode_fields("mission.marker.created", &marker(), "rch", None).unwrap();
    let wire_hex: String = wire.iter().fold(String::new(), |mut output, byte| {
        write!(output, "{byte:02x}").unwrap();
        output
    });
    assert!(wire_hex.starts_with(&format!(
        "8203{}0d",
        fixture["stream_hex"].as_str().unwrap()
    )));
}
