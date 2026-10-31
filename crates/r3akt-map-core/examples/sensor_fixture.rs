//! Reproducible native map projections for the REM and RCH browser acceptance tests.
use r3akt_map_core::{
    sensor::{AltitudeDatum, OriginPosition, RangeKind, SensorState},
    sensor_store::SensorOrigin,
};
use std::collections::BTreeMap;
fn origin(id: &str, kind: &str, label: &str, lon: f64, now: u64, count: usize) -> SensorOrigin {
    SensorOrigin {
        origin_id: id.repeat(16),
        writer_id: "aa".repeat(16),
        origin_kind: kind.into(),
        label: label.into(),
        position: Some(OriginPosition {
            lat: 45.,
            lon,
            alt_m: None,
            altitude_datum: AltitudeDatum::Unknown,
            fix_at_ms: now,
            speed_mps: Some(15.),
            course_deg: Some(90.),
            accuracy_m: None,
        }),
        sensors: (0..count)
            .map(|i| {
                let id = format!("camera-{}", i + 1);
                (
                    id.clone(),
                    SensorState {
                        sensor_id: id,
                        sample_at_ms: now,
                        azimuth_deg: Some(f64::from(u32::try_from(i).unwrap()) * 90.),
                        elevation_deg: Some(-30.),
                        roll_deg: Some(12.),
                        horizontal_fov_deg: Some(20.),
                        vertical_fov_deg: Some(10.),
                        slant_range_m: Some(2000.),
                        image_north_deg: Some(180.),
                        range_kind: RangeKind::DisplayLimit,
                    },
                )
            })
            .collect(),
        sensor_expiry_ms: BTreeMap::new(),
        manifests: BTreeMap::new(),
        manifest_times: BTreeMap::new(),
        sensor_tombstones: BTreeMap::new(),
        deleted_at_ms: None,
        packed_telemeter: None,
        packed_at_ms: 0,
    }
}
fn main() {
    let now = 1_793_440_000_000;
    let origins = [
        origin("aa", "device", "Controller A", -63.006, now, 1),
        origin("bb", "uav", "Drone B", -63., now, 4),
    ];
    let project = |time| serde_json::json!({"observedAtMs":time,"ttlMs":300_000,"items":origins.iter().map(|o|o.projection(time,300_000).unwrap()).collect::<Vec<_>>()});
    let antimeridian = origin("cc", "uav", "Dateline camera", 179.999, now, 4)
        .projection(now, 300_000)
        .unwrap();
    println!("{}",serde_json::to_string_pretty(&serde_json::json!({"fresh":project(now),"stale":project(now+300_001),"antimeridian":antimeridian})).unwrap());
}
