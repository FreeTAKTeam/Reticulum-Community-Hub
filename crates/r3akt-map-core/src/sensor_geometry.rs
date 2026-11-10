//! ATAK-like planar display sectors, never terrain-intersected footprints.

use crate::sensor::{OriginPosition, POSITION_SKEW_MS, SensorState};
use serde_json::{Value, json};

pub(crate) const EARTH_RADIUS_M: f64 = 6_371_008.8;
const MAX_STEPS: u32 = 72;

/// Great-circle destination for a true bearing and distance in metres.
/// The returned longitude is normalized to [-180, 180].
///
/// # Errors
/// Rejects non-finite bearings and distances outside the shortest half-circle.
pub fn destination(
    origin: crate::Position,
    bearing_deg: f64,
    distance_m: f64,
) -> Result<crate::Position, &'static str> {
    if !bearing_deg.is_finite()
        || !distance_m.is_finite()
        || !(0.0..=std::f64::consts::PI * EARTH_RADIUS_M).contains(&distance_m)
    {
        return Err("invalid bearing or distance");
    }
    if distance_m == 0.0 {
        return Ok(origin);
    }
    let [lon, lat] = destination_unwrapped(
        origin.lat(),
        origin.lon(),
        bearing_deg.rem_euclid(360.0),
        distance_m,
    );
    crate::Position::new(lat, (lon + 180.0).rem_euclid(360.0) - 180.0)
        .map_err(|_| "invalid destination")
}

fn destination_unwrapped(lat: f64, lon: f64, bearing: f64, distance: f64) -> [f64; 2] {
    let origin_lon = lon;
    let lat = lat.to_radians();
    let lon = lon.to_radians();
    let bearing = bearing.to_radians();
    let arc = distance / EARTH_RADIUS_M;
    let target_lat = (lat.sin() * arc.cos() + lat.cos() * arc.sin() * bearing.cos())
        .clamp(-1.0, 1.0)
        .asin();
    let target_lon = lon
        + (bearing.sin() * arc.sin() * lat.cos()).atan2(arc.cos() - lat.sin() * target_lat.sin());
    let mut lon = target_lon.to_degrees();
    while lon - origin_lon > 180.0 {
        lon -= 360.0;
    }
    while lon - origin_lon < -180.0 {
        lon += 360.0;
    }
    [lon, target_lat.to_degrees()]
}

fn clip(points: &[[f64; 2]], boundary: f64, keep_left: bool) -> Vec<[f64; 2]> {
    let mut result = Vec::new();
    for pair in points.windows(2) {
        let [a, b] = [pair[0], pair[1]];
        let inside = |p: [f64; 2]| {
            if keep_left {
                p[0] <= boundary
            } else {
                p[0] >= boundary
            }
        };
        if inside(a) {
            result.push(a);
        }
        if inside(a) != inside(b) {
            let t = (boundary - a[0]) / (b[0] - a[0]);
            result.push([boundary, a[1] + t * (b[1] - a[1])]);
        }
    }
    if let Some(first) = result.first().copied() {
        result.push(first);
    }
    result
}

fn polygon(points: &[[f64; 2]]) -> Value {
    // Cut at the antimeridian instead of drawing a wedge across the whole world.
    let mut polygons = Vec::new();
    for shift in [-360.0, 0.0, 360.0] {
        let ring = points
            .iter()
            .map(|p| [p[0] + shift, p[1]])
            .collect::<Vec<_>>();
        let ring = clip(&clip(&ring, -180.0, false), 180.0, true);
        if ring.len() >= 4 {
            polygons.push(vec![ring]);
        }
    }
    json!({"type":"MultiPolygon","coordinates":polygons})
}

/// Projects only checked, current, synchronized source samples. UI callers
/// render this result; they do not independently decide freshness or skew.
/// # Errors
/// Rejects invalid source positions or sensor state.
pub fn project(
    origin_id: &str,
    position: Option<&OriginPosition>,
    sensor: &SensorState,
    moving: bool,
    now_ms: u64,
    ttl_ms: u64,
) -> Result<Value, &'static str> {
    sensor.validate()?;
    if let Some(position) = position {
        position.validate()?;
    }
    let stale = now_ms.saturating_sub(sensor.sample_at_ms) > ttl_ms
        || sensor.sample_at_ms > now_ms.saturating_add(crate::sensor::FUTURE_SKEW_MS);
    let position_stale =
        position.is_none_or(|p| now_ms.saturating_sub(p.fix_at_ms) > ttl_ms && moving);
    let unsynchronized = moving
        && position.is_some_and(|p| p.fix_at_ms.abs_diff(sensor.sample_at_ms) > POSITION_SKEW_MS);
    let mut features = Vec::new();
    let properties = json!({"originId":origin_id,"sensorId":sensor.sensor_id,
        "azimuthDeg":sensor.azimuth_deg,"stale":stale,"unsynchronized":unsynchronized,
        "rangeKind":sensor.range_kind,"displayOnly":true,"headingVisible":!stale&&!position_stale&&!unsynchronized&&sensor.azimuth_deg.is_some()&&sensor.elevation_deg.is_none_or(|v|v.abs()<89.5)});
    if let Some(position) = position {
        features.push(json!({"type":"Feature","properties":properties,
            "geometry":{"type":"Point","coordinates":[position.lon,position.lat]}}));
        if !stale
            && !position_stale
            && !unsynchronized
            && let (Some(azimuth), Some(fov), Some(elevation), Some(range)) = (
                sensor.azimuth_deg,
                sensor.horizontal_fov_deg,
                sensor.elevation_deg,
                sensor.slant_range_m,
            )
        {
            let ground = range * elevation.to_radians().cos();
            if fov > 0.0 && range > 0.0 && ground > 0.5 && elevation.abs() < 89.5 {
                let steps = (2..=MAX_STEPS)
                    .find(|steps| f64::from(*steps) * 5.0 >= fov)
                    .unwrap_or(MAX_STEPS);
                let mut ring = vec![[position.lon, position.lat]];
                for step in 0..=steps {
                    ring.push(destination_unwrapped(
                        position.lat,
                        position.lon,
                        azimuth - fov / 2.0 + fov * f64::from(step) / f64::from(steps),
                        ground,
                    ));
                }
                ring.push([position.lon, position.lat]);
                features.push(
                    json!({"type":"Feature","properties":properties,"geometry":polygon(&ring)}),
                );
                let end = destination_unwrapped(position.lat, position.lon, azimuth, ground);
                // Split arrows that cross the antimeridian as well as sector polygons.
                let line = clip_line([position.lon, position.lat], end);
                features.push(json!({"type":"Feature","properties":properties,"geometry":line}));
            }
        }
    }
    Ok(
        json!({"originId":origin_id,"sensorId":sensor.sensor_id,"stale":stale,
        "positionStale":position_stale,"unsynchronized":unsynchronized,
        "rangeUnknown":sensor.slant_range_m.is_none(),"sampleAtMs":sensor.sample_at_ms,
        "geojson":{"type":"FeatureCollection","features":features}}),
    )
}

fn clip_line(start: [f64; 2], end: [f64; 2]) -> Value {
    if (-180.0..=180.0).contains(&end[0]) {
        return json!({"type":"LineString","coordinates":[start,end]});
    }
    let boundary = if end[0] > 180.0 { 180.0 } else { -180.0 };
    let lat = start[1] + (end[1] - start[1]) * (boundary - start[0]) / (end[0] - start[0]);
    let shift = if boundary > 0.0 { -360.0 } else { 360.0 };
    json!({"type":"MultiLineString","coordinates":[[start,[boundary,lat]],
        [[boundary+shift,lat],[end[0]+shift,end[1]]]]})
}
