use super::*;
use r3akt_map_core::{
    sensor::{AltitudeDatum, OriginPosition, RangeKind, SensorState},
    sensor_wire as wire,
};
fn position(time: u64) -> OriginPosition {
    OriginPosition {
        lat: 45.,
        lon: -63.,
        alt_m: Some(500.),
        altitude_datum: AltitudeDatum::Hae,
        fix_at_ms: time,
        speed_mps: Some(20.),
        course_deg: Some(90.),
        accuracy_m: Some(3.),
    }
}
fn sensor(time: u64) -> SensorState {
    SensorState {
        sensor_id: "eo".into(),
        sample_at_ms: time,
        azimuth_deg: Some(0.),
        elevation_deg: Some(-30.),
        roll_deg: None,
        horizontal_fov_deg: Some(20.),
        vertical_fov_deg: Some(10.),
        slant_range_m: Some(2000.),
        image_north_deg: Some(180.),
        range_kind: RangeKind::DisplayLimit,
    }
}
fn fields(
    marker: &r3akt_map_core::MarkerRecord,
    fix: &OriginPosition,
    pose: &SensorState,
) -> serde_json::Value {
    let stream = wire::encode_origin_sensor_stream(
        &marker.object_destination_hash,
        Some(fix),
        std::slice::from_ref(pose),
    )
    .unwrap();
    serde_json::json!({"3":r3akt_map_core::msgpack::to_json(&stream).unwrap(),"13":[{"event_type":"mission.marker.created","payload":marker.api_value()},wire::SensorEvent::OriginFix(wire::OriginFixEvent{origin_id:marker.object_destination_hash.clone(),position:fix.clone()})]})
}
#[test]
fn authenticated_origin_moves_without_mutating_sender_and_cascades_on_delete() {
    let mut store = RchSqliteStore::in_memory().unwrap();
    let writer = "ab".repeat(16);
    let now = u64::try_from(chrono::Utc::now().timestamp_millis()).unwrap();
    let mut core = RchCore::new();
    core.grant_identity_capability(&writer, "mission.content.write");
    store.save_snapshot(&core.snapshot()).unwrap();
    let marker = r3akt_map_core::MarkerRecord::create(
        r3akt_map_core::MarkerDraft {
            marker_type: "uav".into(),
            symbol: "uav".into(),
            name: "Drone B".into(),
            category: "uav".into(),
            position: r3akt_map_core::Position::new(45., -63.).unwrap(),
            notes: None,
            origin_rch: writer.clone(),
        },
        "drone".into(),
        i64::try_from(now).unwrap(),
    );
    let mut unit = store.begin_r3akt_command().unwrap();
    let input = fields(&marker, &position(now), &sensor(now));
    assert_eq!(
        unit.stage_sensor_frame(&writer, &input, now).unwrap(),
        vec![marker.object_destination_hash.clone()]
    );
    unit.commit().unwrap();
    let mut moved = position(now + 1000);
    moved.lat += 0.01;
    let mut unit = store.begin_r3akt_command().unwrap();
    unit.stage_sensor_frame(&writer, &fields(&marker, &moved, &sensor(now)), now + 1000)
        .unwrap();
    let delta = unit.commit_delta().unwrap();
    assert_eq!(delta.after.markers[0].lat, moved.lat);
    let origins = store.sensor_origins().unwrap();
    assert_eq!(origins.len(), 1);
    assert_ne!(origins[0].origin_id, writer);
    wire::validate_position_against_packed(&moved, origins[0].packed_telemeter.as_ref().unwrap())
        .unwrap();
    let mut unit = store.begin_r3akt_command().unwrap();
    let expiry = serde_json::json!({"13":[{"event_type":"mission.registry.sensor.expiry","payload":{"originId":marker.object_destination_hash,"sensorId":"eo","sampleAtMs":now,"expiresAtMs":now+30_000}}]});
    assert_eq!(
        unit.stage_sensor_frame(&writer, &expiry, now + 1000)
            .unwrap(),
        vec![marker.object_destination_hash.clone()]
    );
    unit.commit().unwrap();
    assert_eq!(
        store.sensor_origins().unwrap()[0].sensor_expiry_ms["eo"],
        now + 30_000
    );
    store
        .delete_marker(&marker.object_destination_hash)
        .unwrap();
    assert!(store.sensor_origins().unwrap().is_empty());
    assert!(
        store.upsert_marker(&marker).is_err(),
        "canonical identity cannot be resurrected"
    );
    let mut unit = store.begin_r3akt_command().unwrap();
    assert!(
        unit.stage_sensor_frame(&writer, &input, now + 2000)
            .unwrap()
            .is_empty()
    );
}

#[test]
fn relay_metadata_requires_delivery_and_failed_custody_does_not_confirm() {
    let directory = std::env::temp_dir().join(format!("rch-r3s-receipt-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(&directory).unwrap();
    let mut store = RchSqliteStore::open(directory.join("state.db")).unwrap();
    let id = "ab".repeat(16);
    for (operation, status) in [
        ("failed-packet", "failed"),
        ("delivered-packet", "delivered"),
    ] {
        let intent = crate::DurableOutboundIntent {
            operation_id: operation.into(),
            message: MessageRecord {
                message_id: operation.into(),
                topic_id: None,
                destination: Some("peer".into()),
                sender: "rch".into(),
                content: String::new(),
                delivery_mode: crate::DeliveryMode::Targeted,
                delivery_method: "durable_broker".into(),
                delivery_policy_reason: "relay".into(),
                delivery_state: "broker_pending".into(),
                delivery_metadata: serde_json::json!({"r3s_policy":{"originId":id,"metadataHash":"hash","includeMetadata":true}}),
                created_ts_ms: 1,
                attachments: vec![],
            },
            request: serde_json::json!({"destination":"peer"}),
        };
        let unit = store.begin_outbound_application().unwrap();
        unit.stage_message(&intent.message).unwrap();
        unit.stage_outbound_intent(&intent).unwrap();
        unit.commit().unwrap();
        store.record_broker_admission(operation, operation).unwrap();
        let unit = store.begin_outbound_application().unwrap();
        assert!(unit.sensor_relay_metadata(&id, "peer").unwrap().is_none());
        unit.stage_broker_receipt(operation, status).unwrap();
        assert_eq!(
            unit.sensor_relay_metadata(&id, "peer").unwrap(),
            (status == "delivered").then(|| "hash".into())
        );
        unit.commit().unwrap();
    }
    drop(store);
    std::fs::remove_dir_all(directory).unwrap();
}
