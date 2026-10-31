use r3akt_map_core::{sensor::*, sensor_geometry as geometry, sensor_wire as wire, telemetry};
use serde_json::json;

fn state() -> SensorState {
    SensorState {
        sensor_id: "eo-main".into(),
        sample_at_ms: 1_793_440_000_000,
        azimuth_deg: Some(0.0),
        elevation_deg: Some(0.0),
        roll_deg: Some(0.0),
        horizontal_fov_deg: Some(20.0),
        vertical_fov_deg: Some(60.0),
        slant_range_m: Some(500.0),
        image_north_deg: Some(227.0),
        range_kind: RangeKind::MeasuredTarget,
    }
}
fn position() -> OriginPosition {
    OriginPosition {
        lat: 38.889,
        lon: -77.01399,
        alt_m: None,
        altitude_datum: AltitudeDatum::Unknown,
        fix_at_ms: 1_793_440_000_000,
        speed_mps: None,
        course_deg: None,
        accuracy_m: None,
    }
}

#[test]
fn deterministic_v1_nullable_codec_and_limits() {
    let value = wire::encode_value(&[state()]).unwrap();
    assert_eq!(
        value,
        json!([
            1,
            [[
                "eo-main",
                0,
                0,
                0,
                2000,
                6000,
                50000,
                22700,
                1_793_440_000_000_u64,
                1
            ]]
        ])
    );
    assert_eq!(wire::decode_value(&value).unwrap(), vec![state()]);
    let mut s = state();
    s.slant_range_m = None;
    s.azimuth_deg = None;
    s.range_kind = RangeKind::Unknown;
    assert_eq!(
        wire::decode_value(&wire::encode_value(&[s.clone()]).unwrap()).unwrap(),
        vec![s]
    );
    assert!(wire::encode_value(&[state(), state()]).is_err());
    for (index, value) in [
        (1, json!(36000)),
        (2, json!(9001)),
        (3, json!(-18000)),
        (4, json!(36000)),
        (6, json!(-1)),
        (7, json!(36000)),
        (8, json!(0)),
        (9, json!(3)),
        (1, json!(1.5)),
    ] {
        let mut bad = wire::encode_value(&[state()]).unwrap();
        bad[1][0][index] = value;
        assert!(wire::decode_value(&bad).is_err(), "{index}");
    }
    for valid in [-90.0, 90.0] {
        let mut s = state();
        s.elevation_deg = Some(valid);
        assert!(s.validate().is_ok());
    }
    for valid in [0.0, 359.99] {
        let mut s = state();
        s.azimuth_deg = Some(valid);
        assert!(wire::encode_value(&[s]).is_ok());
    }
    let mut bad = state();
    bad.roll_deg = Some(f64::NAN);
    assert!(bad.validate().is_err());
    let mut bad = state();
    bad.sensor_id = "x".repeat(33);
    assert!(bad.validate().is_err());
    let mut bad = wire::encode_value(&[state()]).unwrap();
    bad[0] = json!(2);
    assert!(wire::decode_value(&bad).is_err());
}

#[test]
fn optional_extension_does_not_poison_position_or_change_standard_bytes() {
    let known = OriginPosition {
        alt_m: Some(30.0),
        speed_mps: Some(2.0),
        course_deg: Some(180.0),
        accuracy_m: Some(3.0),
        ..position()
    };
    let packed = wire::encode_packed(known.fix_at_ms / 1000, Some(&known), &[state()]).unwrap();
    let ordinary = telemetry::decode_field(&json!(packed)).unwrap();
    assert_eq!(ordinary.telemetry["location"]["latitude"], known.lat);
    assert_eq!(ordinary.telemetry["location"]["speed"], 7.2);
    assert_eq!(wire::decode_packed(&packed).unwrap(), Some(vec![state()]));
    let raw = telemetry::parse_payload(&json!(packed)).unwrap();
    let mut map = raw.as_object().unwrap().clone();
    map.insert("128".into(), json!([9, []]));
    assert!(telemetry::decode_field(&json!(map)).is_ok());
    // A NaN in optional SID 128 remains a sensor diagnostic, not a lost parent fix.
    let standard = r3akt_map_core::telemetry_encode::encode(
        1_793_440_000,
        Some(r3akt_map_core::telemetry_encode::Location {
            latitude: known.lat,
            longitude: known.lon,
            altitude: 30.0,
            speed: 7.2,
            bearing: 180.0,
            accuracy: 3.0,
            updated_at_s: 1_793_440_000,
        }),
        None,
    )
    .unwrap();
    let mut malformed = standard.clone();
    malformed[0] += 1;
    malformed.extend([0xcc, 128, 0xcb]);
    malformed.extend(f64::NAN.to_be_bytes());
    assert!(telemetry::decode_field(&json!(malformed)).is_ok());
    assert!(wire::decode_packed(&malformed).is_err());
    assert!(r3akt_map_core::msgpack::to_json(&malformed).is_none());
    assert_eq!(&packed[..standard.len()], &{
        let mut b = standard;
        b[0] += 1;
        b
    });
}

#[test]
fn remote_stream_preserves_origin_and_omits_unknown_location_instead_of_zero() {
    let id = "ab".repeat(16);
    let stream = wire::encode_origin_sensor_stream(&id, Some(&position()), &[state()]).unwrap();
    let value = r3akt_map_core::msgpack::to_json(&stream).unwrap();
    let decoded = r3akt_map_core::sensor_stream::decode(&value).unwrap();
    assert_eq!(decoded.len(), 1);
    assert_eq!(decoded[0].origin_id, id);
    assert_eq!(decoded[0].sensors, vec![state()]);
    assert_eq!(value[0][0], json!(vec![171; 16]));
    let packed = value[0][2]
        .as_array()
        .unwrap()
        .iter()
        .map(|n| u8::try_from(n.as_u64().unwrap()).unwrap())
        .collect::<Vec<_>>();
    let parsed = telemetry::decode_field(&json!(packed)).unwrap();
    assert!(parsed.telemetry.get("location").is_none());
    assert_eq!(wire::decode_packed(&packed).unwrap(), Some(vec![state()]));
    let event = wire::SensorEvent::OriginFix(wire::OriginFixEvent {
        origin_id: id,
        position: position(),
    });
    assert!(event.validate().is_ok());
    assert!(serde_json::to_value(event).unwrap()["payload"]["position"]["altM"].is_null());
}

#[test]
fn geometry_uses_boresight_and_source_freshness_not_course_or_image_north() {
    let p = position();
    let s = state();
    let value = geometry::project("origin", Some(&p), &s, true, s.sample_at_ms, 60_000).unwrap();
    let ring = &value["geojson"]["features"][1]["geometry"]["coordinates"][0][0];
    assert!(
        ring.as_array()
            .unwrap()
            .iter()
            .skip(1)
            .take(5)
            .all(|point| point[1].as_f64().unwrap() > p.lat)
    );
    let mut s2 = s.clone();
    s2.image_north_deg = Some(10.0);
    s2.roll_deg = Some(45.0);
    assert_eq!(
        value["geojson"],
        geometry::project("origin", Some(&p), &s2, true, s.sample_at_ms, 60_000).unwrap()["geojson"]
    );
    for (now, fix, moving) in [
        (s.sample_at_ms + 60_001, p.clone(), true),
        (
            s.sample_at_ms,
            OriginPosition {
                fix_at_ms: p.fix_at_ms - 2001,
                ..p.clone()
            },
            true,
        ),
    ] {
        assert_eq!(geometry::project("origin",Some(&fix),&s,moving,now,60_000).unwrap()["geojson"]["features"].as_array().unwrap().len(),1);
    }
    let mut down = s.clone();
    down.elevation_deg = Some(-90.0);
    assert_eq!(geometry::project("origin",Some(&p),&down,true,s.sample_at_ms,60_000).unwrap()["geojson"]["features"].as_array().unwrap().len(),1);
    assert!(geometry::project("origin",None,&s,true,s.sample_at_ms,60_000).unwrap()["geojson"]["features"].as_array().unwrap().is_empty());
}

#[test]
fn antimeridian_and_wide_north_crossing_sectors_stay_bounded() {
    let p = OriginPosition {
        lat: 0.0,
        lon: 179.999,
        ..position()
    };
    let mut s = state();
    s.azimuth_deg = Some(90.0);
    s.horizontal_fov_deg = Some(359.99);
    let value = geometry::project("origin", Some(&p), &s, true, s.sample_at_ms, 60_000).unwrap();
    let polygons = value["geojson"]["features"][1]["geometry"]["coordinates"]
        .as_array()
        .unwrap();
    assert!(polygons.len() >= 2);
    for polygon in polygons {
        for ring in polygon.as_array().unwrap() {
            let points = ring.as_array().unwrap();
            assert!(points.len() <= 80);
            for point in points {
                assert!((-180.0..=180.0).contains(&point[0].as_f64().unwrap()));
            }
        }
    }
}

#[cfg(feature = "sqlite")]
#[test]
fn origin_writer_binding_four_sensors_and_tombstones() {
    use r3akt_map_core::sensor_store as store;
    let db = rusqlite::Connection::open_in_memory().unwrap();
    store::ensure_schema(&db).unwrap();
    let id = "ab".repeat(16);
    let writer = "cd".repeat(16);
    let now = state().sample_at_ms;
    assert!(store::upsert_sensors(&db, &id, &writer, &[state()], now).is_err());
    store::bind_origin(&db, &id, &writer, "uav", "Camera").unwrap();
    assert!(store::bind_origin(&db, &id, &"ef".repeat(16), "uav", "Camera").is_err());
    let sensors = (0..4)
        .map(|i| SensorState {
            sensor_id: format!("sensor-{i}"),
            ..state()
        })
        .collect::<Vec<_>>();
    store::upsert_sensors(&db, &id, &writer, &sensors, now).unwrap();
    let mut update = sensors[0].clone();
    update.sample_at_ms += 1;
    update.azimuth_deg = Some(20.0);
    store::upsert_sensors(&db, &id, &writer, &[update.clone()], now + 1).unwrap();
    assert_eq!(store::get(&db, &id).unwrap().unwrap().sensors.len(), 4);
    assert!(!store::upsert_sensors(&db, &id, &writer, &[sensors[0].clone()], now + 1).unwrap());
    let mut conflict = update.clone();
    conflict.azimuth_deg = Some(30.0);
    assert!(store::upsert_sensors(&db, &id, &writer, &[conflict], now + 1).is_err());
    assert!(
        store::upsert_sensors(
            &db,
            &id,
            &writer,
            &[SensorState {
                sample_at_ms: now + 30_001,
                ..state()
            }],
            now
        )
        .is_err()
    );
    store::remove_sensor(&db, &id, &writer, &update.sensor_id, now + 2, now + 2).unwrap();
    store::ensure_schema(&db).unwrap();
    assert!(!store::upsert_sensors(&db, &id, &writer, &[update], now + 3).unwrap());
    store::remove_origin(&db, &id, &writer, now + 4, now + 4).unwrap();
    assert!(store::list(&db).unwrap().is_empty());
    assert!(store::bind_origin(&db, &id, &writer, "uav", "Camera").is_err());
    assert!(!store::upsert_sensors(&db, &id, &writer, &sensors, now + 5).unwrap());
}

#[test]
fn malformed_optional_shapes_leave_the_valid_location_usable() {
    let standard = r3akt_map_core::telemetry_encode::encode(
        1_793_440_000,
        Some(r3akt_map_core::telemetry_encode::Location {
            latitude: 38.889,
            longitude: -77.01399,
            altitude: 40.0,
            speed: 0.0,
            bearing: 0.0,
            accuracy: 5.0,
            updated_at_s: 1_793_440_000,
        }),
        None,
    )
    .unwrap();
    let mut deep = vec![0x91; 40];
    deep.push(0);
    for invalid in [
        vec![0x81, 0xc0, 0],
        vec![0x82, 1, 0, 1, 0],
        vec![0xd4, 0, 1],
        vec![0xc1],
        deep,
    ] {
        let mut packed = standard.clone();
        packed[0] += 1;
        packed.extend([0xcc, 128]);
        packed.extend(invalid);
        let checked = telemetry::decode_field(&json!(packed)).unwrap();
        assert_eq!(checked.telemetry["location"]["latitude"], 38.889);
        assert!(wire::decode_packed(&packed).is_err());
        assert_eq!(checked.packed_telemeter.as_ref(), Some(&packed));
    }
    let mut string_key = standard;
    string_key[0] += 1;
    string_key.extend([0xa3, b'1', b'2', b'8']);
    string_key.extend(rmp_serde::to_vec(&wire::encode_value(&[state()]).unwrap()).unwrap());
    assert_eq!(
        wire::decode_packed(&string_key).unwrap_err(),
        "R3S sensor ID must be numeric"
    );
    assert!(telemetry::decode_field(&json!(string_key)).is_ok());
}

#[test]
fn manifests_reject_credentials_tokens_and_invalid_optics() {
    let mut manifest = SensorManifest {
        sensor_id: "eo-main".into(),
        label: None,
        sensor_type: Some("r-e".into()),
        model: Some("Drone Camera".into()),
        mount_id: None,
        intrinsics: None,
        video: None,
    };
    assert!(manifest.validate().is_ok());
    for endpoint in [
        "rtsp://user:password@camera/live",
        "rtsp://camera/live?token=secret",
        "rtsp://camera/live#token",
        "rtsp://camera/\nsecret",
        "rtsp://camera/%40secret",
    ] {
        manifest.video = Some(VideoDescriptor {
            protocol: "rtsp".into(),
            sensor_id: "eo-main".into(),
            endpoint_ref: endpoint.into(),
        });
        assert!(manifest.validate().is_err());
    }
    manifest.video = Some(VideoDescriptor {
        protocol: "rtsp".into(),
        sensor_id: "eo-main".into(),
        endpoint_ref: "rtsp://camera/live".into(),
    });
    assert!(manifest.validate().is_ok());
    manifest.model = Some("é".repeat(33));
    assert!(manifest.validate().is_err());
}

#[cfg(feature = "sqlite")]
#[test]
fn writer_position_original_bytes_and_deletions_survive_database_restart() {
    use r3akt_map_core::sensor_store as store;
    let path = std::env::temp_dir().join(format!("r3s-contract-{}.sqlite", uuid::Uuid::new_v4()));
    let id = "ab".repeat(16);
    let writer = "cd".repeat(16);
    let now = state().sample_at_ms;
    {
        let db = rusqlite::Connection::open(&path).unwrap();
        store::ensure_schema(&db).unwrap();
        store::bind_origin(&db, &id, &writer, "uav", "Camera").unwrap();
        store::upsert_position(&db, &id, &writer, &position(), now).unwrap();
        store::upsert_sensors(&db, &id, &writer, &[state()], now).unwrap();
        store::retain_packed(
            &db,
            &id,
            &writer,
            &wire::encode_packed(now / 1000, Some(&position()), &[state()]).unwrap(),
            now,
            now,
        )
        .unwrap();
        store::remove_sensor(&db, &id, &writer, "eo-main", now + 1, now + 1).unwrap();
    }
    {
        let db = rusqlite::Connection::open(&path).unwrap();
        store::ensure_schema(&db).unwrap();
        let origin = store::get(&db, &id).unwrap().unwrap();
        assert_eq!(origin.writer_id, writer);
        assert_eq!(origin.position, Some(position()));
        assert_eq!(origin.packed_telemeter, None);
        assert!(origin.sensors.is_empty());
        assert!(!store::upsert_sensors(&db, &id, &writer, &[state()], now + 2).unwrap());
        assert!(store::upsert_sensors(&db, &id, &"ef".repeat(16), &[state()], now + 2).is_err());
    }
    std::fs::remove_file(path).unwrap();
}

#[test]
fn collector_nil_appearance_and_original_bytes_decode() {
    let packed =
        wire::encode_packed(state().sample_at_ms / 1000, Some(&position()), &[state()]).unwrap();
    let stream =
        serde_json::json!([[vec![0xab_u8; 16], state().sample_at_ms / 1000, packed, null]]);
    let decoded = r3akt_map_core::sensor_stream::decode(&stream).unwrap();
    assert_eq!(decoded[0].sensors, vec![state()]);
    assert_eq!(decoded[0].packed_telemeter, packed);
}

#[test]
fn ordinary_collector_removes_only_optional_extension_bytes() {
    let packed =
        wire::encode_packed(state().sample_at_ms / 1000, Some(&position()), &[state()]).unwrap();
    let ordinary = r3akt_map_core::msgpack::without_sensor(&packed, 128).unwrap();
    assert!(wire::decode_packed(&ordinary).unwrap().is_none());
    assert_eq!(
        r3akt_map_core::msgpack::telemetry_sensor_bytes(&packed, 2),
        r3akt_map_core::msgpack::telemetry_sensor_bytes(&ordinary, 2)
    );
}

#[cfg(feature = "sqlite")]
#[test]
fn source_expiry_and_position_only_updates_survive_storage() {
    use r3akt_map_core::sensor_expiry::{self, SensorExpiry};
    use r3akt_map_core::sensor_store as store;
    let db = rusqlite::Connection::open_in_memory().unwrap();
    store::ensure_schema(&db).unwrap();
    let id = "ac".repeat(16);
    let writer = "bd".repeat(16);
    let now = state().sample_at_ms;
    store::bind_origin(&db, &id, &writer, "uav", "Drone").unwrap();
    let first = position();
    store::upsert_position(&db, &id, &writer, &first, now).unwrap();
    store::upsert_sensors(&db, &id, &writer, &[state()], now).unwrap();
    let original = wire::encode_packed(now / 1000, Some(&first), &[state()]).unwrap();
    store::retain_packed(&db, &id, &writer, &original, now, now).unwrap();
    let expiry = SensorExpiry {
        origin_id: id.clone(),
        sensor_id: state().sensor_id,
        sample_at_ms: now,
        expires_at_ms: now + 500,
    };
    assert!(sensor_expiry::store(&db, &writer, &expiry).unwrap());
    assert!(
        store::get(&db, &id)
            .unwrap()
            .unwrap()
            .projection(now + 501, 60_000)
            .unwrap()["sensors"][0]["display"]["stale"]
            .as_bool()
            .unwrap()
    );
    let mut moved = first;
    moved.lat += 0.001;
    moved.fix_at_ms += 1000;
    store::upsert_position(&db, &id, &writer, &moved, now + 1000).unwrap();
    let latest = wire::encode_packed((now + 1000) / 1000, Some(&moved), &[state()]).unwrap();
    assert!(store::retain_packed(&db, &id, &writer, &latest, now, now + 1000).unwrap());
    let retained = store::get(&db, &id).unwrap().unwrap();
    assert_eq!(retained.packed_telemeter.as_ref(), Some(&latest));
    wire::validate_position_against_packed(&moved, &retained.packed_telemeter.unwrap()).unwrap();
}
