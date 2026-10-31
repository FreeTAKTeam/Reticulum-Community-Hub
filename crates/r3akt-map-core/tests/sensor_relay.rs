#![cfg(feature = "sqlite")]
use r3akt_map_core::{sensor::*, sensor_marker, sensor_store as store, sensor_wire as wire};

fn pose(id: &str, time: u64) -> SensorState {
    SensorState {
        sensor_id: id.into(),
        sample_at_ms: time,
        azimuth_deg: Some(0.),
        elevation_deg: Some(-30.),
        roll_deg: None,
        horizontal_fov_deg: Some(20.),
        vertical_fov_deg: None,
        slant_range_m: Some(2000.),
        image_north_deg: None,
        range_kind: RangeKind::DisplayLimit,
    }
}
fn position(time: u64) -> OriginPosition {
    OriginPosition {
        lat: 45.,
        lon: -63.,
        alt_m: Some(500.),
        altitude_datum: AltitudeDatum::Hae,
        fix_at_ms: time,
        speed_mps: Some(10.),
        course_deg: Some(90.),
        accuracy_m: Some(3.),
    }
}
fn packet(origin: &store::SensorOrigin) -> Vec<u8> {
    wire::current_packet(
        origin.packed_telemeter.as_deref(),
        origin.position.as_ref(),
        &origin.sensors.values().cloned().collect::<Vec<_>>(),
    )
    .unwrap()
}
#[test]
fn collector_materializes_partial_updates_and_surviving_sensors() {
    let db = rusqlite::Connection::open_in_memory().unwrap();
    store::ensure_schema(&db).unwrap();
    let id = "ab".repeat(16);
    let writer = "cd".repeat(16);
    let now = 1_793_440_000_000;
    let fix = position(now);
    store::bind_origin(&db, &id, &writer, "uav", "Drone B").unwrap();
    store::upsert_position(&db, &id, &writer, &fix, now).unwrap();
    let initial = vec![pose("eo", now), pose("ir", now)];
    store::upsert_sensors(&db, &id, &writer, &initial, now).unwrap();
    let original = wire::encode_packed(now / 1000, Some(&fix), &initial).unwrap();
    store::retain_packed(&db, &id, &writer, &original, now, now).unwrap();
    assert_eq!(packet(&store::get(&db, &id).unwrap().unwrap()), original);
    let updated = pose("eo", now + 1000);
    store::upsert_sensors(
        &db,
        &id,
        &writer,
        std::slice::from_ref(&updated),
        now + 1000,
    )
    .unwrap();
    let partial = wire::encode_packed(
        (now + 1000) / 1000,
        Some(&fix),
        std::slice::from_ref(&updated),
    )
    .unwrap();
    store::retain_packed(&db, &id, &writer, &partial, now + 1000, now + 1000).unwrap();
    let complete = packet(&store::get(&db, &id).unwrap().unwrap());
    assert_eq!(
        wire::decode_packed(&complete).unwrap().unwrap(),
        vec![updated, pose("ir", now)]
    );
    store::remove_sensor(&db, &id, &writer, "eo", now + 1001, now + 1001).unwrap();
    let survivor = packet(&store::get(&db, &id).unwrap().unwrap());
    assert_eq!(
        wire::decode_packed(&survivor).unwrap().unwrap(),
        vec![pose("ir", now)]
    );
}
#[test]
fn canonical_marker_move_rebuilds_packet_without_inventing_altitude() {
    let db = rusqlite::Connection::open_in_memory().unwrap();
    store::ensure_schema(&db).unwrap();
    let now = u64::try_from(chrono::Utc::now().timestamp_millis()).unwrap();
    let writer = "cd".repeat(16);
    let mut marker = r3akt_map_core::MarkerRecord::create(
        r3akt_map_core::MarkerDraft {
            marker_type: "uav".into(),
            symbol: "uav".into(),
            category: "uav".into(),
            name: "Drone B".into(),
            notes: None,
            origin_rch: writer.clone(),
            position: r3akt_map_core::Position::new(45., -63.).unwrap(),
        },
        "drone".into(),
        i64::try_from(now).unwrap(),
    );
    let id = &marker.object_destination_hash;
    store::bind_origin(&db, id, &writer, "uav", "Drone B").unwrap();
    let fix = position(now);
    let sensors = vec![pose("eo", now)];
    store::upsert_position(&db, id, &writer, &fix, now).unwrap();
    store::upsert_sensors(&db, id, &writer, &sensors, now).unwrap();
    let raw = wire::encode_packed(now / 1000, Some(&fix), &sensors).unwrap();
    store::retain_packed(&db, id, &writer, &raw, now, now).unwrap();
    marker.lat += 0.01;
    marker.updated_ts_ms += 1000;
    sensor_marker::updated(&db, &marker).unwrap();
    let origin = store::get(&db, id).unwrap().unwrap();
    assert_eq!(origin.position.as_ref().unwrap().lat, marker.lat);
    assert_eq!(origin.position.as_ref().unwrap().alt_m, None);
    let relayed = packet(&origin);
    assert!(r3akt_map_core::msgpack::telemetry_sensor_bytes(&relayed, 2).is_none());
    wire::validate_position_against_packed(origin.position.as_ref().unwrap(), &relayed).unwrap();
    assert_eq!(wire::decode_packed(&relayed).unwrap().unwrap(), sensors);
    marker.name = "Renamed drone".into();
    sensor_marker::updated(&db, &marker).unwrap();
    assert_eq!(store::get(&db, id).unwrap().unwrap().label, "Renamed drone");
}

#[test]
fn standard_fix_bootstraps_without_sidecar_and_becomes_available_after_unknowns() {
    let now = 1_793_440_000_000;
    let source = "ab".repeat(16);
    let mut fix = position(now);
    let sensors = vec![pose("eo", now)];
    let packed = wire::encode_packed(now / 1000, Some(&fix), &sensors).unwrap();
    let frame =
        r3akt_map_core::sensor_frame::decode_json(&serde_json::json!({"2":packed}), &source)
            .unwrap();
    let wire::SensorEvent::OriginFix(event) = &frame.events[0] else {
        panic!("standard fix");
    };
    assert_eq!(event.origin_id, source);
    assert_eq!(event.position.fix_at_ms, now);
    assert_eq!(event.position.speed_mps, Some(10.));
    fix.alt_m = None;
    fix.altitude_datum = AltitudeDatum::Unknown;
    let unknown = wire::encode_packed(now / 1000, Some(&fix), &sensors).unwrap();
    let current =
        wire::current_packet(Some(&unknown), Some(&position(now + 1000)), &sensors).unwrap();
    assert!(r3akt_map_core::msgpack::telemetry_sensor_bytes(&current, 2).is_some());
    wire::validate_position_against_packed(&position(now + 1000), &current).unwrap();
}
