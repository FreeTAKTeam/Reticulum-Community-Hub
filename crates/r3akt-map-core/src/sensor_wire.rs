//! Bounded R3S/1 SID 128 codec and typed origin events. Ordinary SID 2 is unchanged.

use crate::sensor::{self, OriginPosition, RangeKind, SensorManifest, SensorState};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

pub const SENSOR_ID: u8 = 128;
pub const ORIGIN_FIX_EVENT: &str = "mission.registry.origin.telemetry.upsert";
pub const MANIFEST_EVENT: &str = "mission.registry.sensor_manifest.upsert";
pub const SENSOR_REMOVE_EVENT: &str = "mission.registry.sensor.remove";
pub const ORIGIN_REMOVE_EVENT: &str = "mission.registry.origin.remove";

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "event_type", content = "payload")]
pub enum SensorEvent {
    #[serde(rename = "mission.registry.origin.telemetry.upsert")]
    OriginFix(OriginFixEvent),
    #[serde(rename = "mission.registry.sensor_manifest.upsert")]
    Manifest(ManifestEvent),
    #[serde(rename = "mission.registry.sensor.remove")]
    SensorRemoved(SensorRemovedEvent),
    #[serde(rename = "mission.registry.origin.remove")]
    OriginRemoved(OriginRemovedEvent),
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct OriginFixEvent {
    pub origin_id: String,
    pub position: OriginPosition,
}
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ManifestEvent {
    pub origin_id: String,
    pub manifest: SensorManifest,
    pub updated_at_ms: u64,
}
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct SensorRemovedEvent {
    pub origin_id: String,
    pub sensor_id: String,
    pub deleted_at_ms: u64,
}
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct OriginRemovedEvent {
    pub origin_id: String,
    pub deleted_at_ms: u64,
}

impl SensorEvent {
    #[must_use]
    pub fn origin_id(&self) -> &str {
        match self {
            Self::OriginFix(e) => &e.origin_id,
            Self::Manifest(e) => &e.origin_id,
            Self::SensorRemoved(e) => &e.origin_id,
            Self::OriginRemoved(e) => &e.origin_id,
        }
    }
    /// # Errors
    /// Rejects invalid origin identity, source time or event payload.
    pub fn validate(&self) -> Result<(), &'static str> {
        crate::marker::object_destination_hash(self.origin_id())
            .map_err(|_| "invalid sensor origin")?;
        match self {
            Self::OriginFix(e) => e.position.validate(),
            Self::Manifest(e) => {
                sensor::valid_time(e.updated_at_ms)?;
                e.manifest.validate()
            }
            Self::SensorRemoved(e) => {
                sensor::sensor_id(&e.sensor_id)?;
                sensor::valid_time(e.deleted_at_ms)
            }
            Self::OriginRemoved(e) => sensor::valid_time(e.deleted_at_ms),
        }
    }
}

fn scaled(value: Option<f64>, scale: f64) -> Result<Value, &'static str> {
    value.map_or(Ok(Value::Null), |v| {
        (v * scale)
            .round()
            .to_string()
            .parse::<i64>()
            .map(Value::from)
            .map_err(|_| "sensor integer overflow")
    })
}

/// Produces the exact array value stored at numeric SID 128.
/// # Errors
/// Rejects invalid, duplicate, oversized or unrepresentable sensor readings.
pub fn encode_value(sensors: &[SensorState]) -> Result<Value, &'static str> {
    if sensors.is_empty() || sensors.len() > sensor::MAX_SENSORS {
        return Err("invalid sensor count");
    }
    let mut ids = std::collections::HashSet::new();
    let mut readings = Vec::new();
    for s in sensors {
        s.validate()?;
        if !ids.insert(&s.sensor_id) {
            return Err("duplicate sensor ID");
        }
        readings.push(json!([
            s.sensor_id,
            scaled(s.azimuth_deg, 100.0)?,
            scaled(s.elevation_deg, 100.0)?,
            scaled(s.roll_deg, 100.0)?,
            scaled(s.horizontal_fov_deg, 100.0)?,
            scaled(s.vertical_fov_deg, 100.0)?,
            scaled(s.slant_range_m, 100.0)?,
            scaled(s.image_north_deg, 100.0)?,
            s.sample_at_ms,
            match s.range_kind {
                RangeKind::Unknown => 0,
                RangeKind::MeasuredTarget => 1,
                RangeKind::DisplayLimit => 2,
            }
        ]));
    }
    let value = json!([1, readings]);
    if rmp_serde::to_vec(&value)
        .map_err(|_| "sensor encoding failed")?
        .len()
        > sensor::MAX_EXTENSION_BYTES
    {
        return Err("sensor extension byte limit exceeded");
    }
    // Quantization must not round a valid endpoint into an invalid wire angle.
    decode_value(&value)?;
    Ok(value)
}

fn reading(value: &Value, scale: f64) -> Result<Option<f64>, &'static str> {
    if value.is_null() {
        return Ok(None);
    }
    value
        .as_i64()
        .filter(|v| (-18_000..=i64::from(u32::MAX)).contains(v))
        .and_then(|_| value.as_f64())
        .map(|v| Some(v / scale))
        .ok_or("sensor reading must be an integer or nil")
}

/// # Errors
/// Rejects unsupported versions, invalid types, limits and sensor ranges.
pub fn decode_value(value: &Value) -> Result<Vec<SensorState>, &'static str> {
    let encoded = rmp_serde::to_vec(value).map_err(|_| "invalid sensor extension")?;
    if encoded.len() > sensor::MAX_EXTENSION_BYTES {
        return Err("sensor extension byte limit exceeded");
    }
    let envelope = value
        .as_array()
        .filter(|a| a.len() == 2)
        .ok_or("invalid sensor envelope")?;
    if envelope[0].as_u64() != Some(1) {
        return Err("unsupported R3S version");
    }
    let readings = envelope[1]
        .as_array()
        .filter(|a| !a.is_empty() && a.len() <= sensor::MAX_SENSORS)
        .ok_or("invalid sensor count")?;
    let mut sensors = Vec::new();
    let mut ids = std::collections::HashSet::new();
    for value in readings {
        let a = value
            .as_array()
            .filter(|a| a.len() == 10)
            .ok_or("sensor reading requires ten fields")?;
        let state = SensorState {
            sensor_id: a[0].as_str().ok_or("invalid sensor ID")?.to_string(),
            azimuth_deg: reading(&a[1], 100.0)?,
            elevation_deg: reading(&a[2], 100.0)?,
            roll_deg: reading(&a[3], 100.0)?,
            horizontal_fov_deg: reading(&a[4], 100.0)?,
            vertical_fov_deg: reading(&a[5], 100.0)?,
            slant_range_m: reading(&a[6], 100.0)?,
            image_north_deg: reading(&a[7], 100.0)?,
            sample_at_ms: a[8].as_u64().ok_or("invalid sensor source time")?,
            range_kind: match a[9].as_u64() {
                Some(0) => RangeKind::Unknown,
                Some(1) => RangeKind::MeasuredTarget,
                Some(2) => RangeKind::DisplayLimit,
                _ => return Err("invalid range kind"),
            },
        };
        state.validate()?;
        if !ids.insert(state.sensor_id.clone()) {
            return Err("duplicate sensor ID");
        }
        sensors.push(state);
    }
    Ok(sensors)
}

/// Invalid optional geometry returns a diagnostic independently of valid position readings.
/// # Errors
/// Returns a privacy-safe diagnostic for malformed or excessive optional geometry.
pub fn decode_packed(bytes: &[u8]) -> Result<Option<Vec<SensorState>>, &'static str> {
    if bytes.len() > crate::telemetry::MAX_SENSOR_BYTES {
        return Err("packed telemetry limit exceeded");
    }
    let value = crate::msgpack::telemetry_to_json(bytes).ok_or("invalid packed telemetry")?;
    if crate::msgpack::telemetry_sensor_bytes(bytes, SENSOR_ID)
        .is_some_and(|v| v.len() > sensor::MAX_EXTENSION_BYTES)
    {
        return Err("sensor extension byte limit exceeded");
    }
    if value.get("128").is_some()
        && crate::msgpack::telemetry_sensor_bytes(bytes, SENSOR_ID).is_none()
    {
        return Err("R3S sensor ID must be numeric");
    }
    value.get("128").map(decode_value).transpose()
}

/// Adds SID 128 while preserving the original standard sensor values.
/// # Errors
/// Rejects invalid standard location data or invalid geometry.
pub fn encode_packed(
    timestamp_s: u64,
    position: Option<&OriginPosition>,
    sensors: &[SensorState],
) -> Result<Vec<u8>, &'static str> {
    let location = position
        .map(|p| {
            p.validate()?;
            Ok::<_, &'static str>(match (p.alt_m, p.speed_mps, p.course_deg, p.accuracy_m) {
                (Some(altitude), Some(speed), Some(bearing), Some(accuracy)) => {
                    Some(crate::telemetry_encode::Location {
                        latitude: p.lat,
                        longitude: p.lon,
                        altitude,
                        speed: speed * 3.6,
                        bearing,
                        accuracy,
                        updated_at_s: p.fix_at_ms / 1000,
                    })
                }
                _ => None,
            })
        })
        .transpose()?
        .flatten();
    let standard = crate::telemetry_encode::encode(timestamp_s, location, None)?;
    // Preserve binary SID 2 slots: JSON conversion would change them into numeric arrays.
    let extension =
        rmp_serde::to_vec(&encode_value(sensors)?).map_err(|_| "sensor encoding failed")?;
    let count = standard[0].checked_add(1).ok_or("sensor map overflow")?;
    let mut out = standard;
    out[0] = count;
    out.extend_from_slice(&[0xcc, SENSOR_ID]);
    out.extend_from_slice(&extension);
    Ok(out)
}

/// The nullable sidecar is canonical; a redundant standard fix must agree exactly after wire rounding.
/// # Errors
/// Rejects malformed standard telemetry or a conflicting sidecar/location pair.
pub fn validate_position_against_packed(
    position: &OriginPosition,
    packed: &[u8],
) -> Result<(), &'static str> {
    position.validate()?;
    let actual = crate::telemetry::decode_field(&serde_json::json!(packed))?;
    let Some(location) = actual.telemetry.get("location") else {
        return Ok(());
    };
    let (Some(altitude), Some(speed), Some(bearing), Some(accuracy)) = (
        position.alt_m,
        position.speed_mps,
        position.course_deg,
        position.accuracy_m,
    ) else {
        return Err("standard location conflicts with nullable origin fix");
    };
    let expected = crate::telemetry_encode::encode(
        position.fix_at_ms / 1000,
        Some(crate::telemetry_encode::Location {
            latitude: position.lat,
            longitude: position.lon,
            altitude,
            speed: speed * 3.6,
            bearing,
            accuracy,
            updated_at_s: position.fix_at_ms / 1000,
        }),
        None,
    )?;
    let expected = crate::telemetry::decode_field(&serde_json::json!(expected))?;
    if location != &expected.telemetry["location"] {
        return Err("standard location conflicts with origin fix");
    }
    Ok(())
}

#[derive(Serialize)]
struct Binary<'a>(#[serde(with = "binary")] &'a [u8]);
mod binary {
    use serde::Serializer;
    pub fn serialize<S: Serializer>(v: &&[u8], s: S) -> Result<S::Ok, S::Error> {
        s.serialize_bytes(v)
    }
}

/// Field-3 origin identity stays distinct from the authenticated LXMF sender.
/// # Errors
/// Rejects invalid origin identity, source time, location or geometry.
pub fn encode_origin_sensor_stream(
    origin_id: &str,
    position: Option<&OriginPosition>,
    sensors: &[SensorState],
) -> Result<Vec<u8>, &'static str> {
    let id =
        crate::marker::object_destination_hash(origin_id).map_err(|_| "invalid sensor origin")?;
    let hash = (0..32)
        .step_by(2)
        .map(|i| u8::from_str_radix(&id[i..i + 2], 16))
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| "invalid sensor origin")?;
    let time = sensors
        .iter()
        .map(|s| s.sample_at_ms)
        .max()
        .ok_or("missing sensors")?
        .max(position.map_or(0, |p| p.fix_at_ms));
    let packed = encode_packed(time / 1000, position, sensors)?;
    rmp_serde::to_vec(&vec![(
        Binary(&hash),
        time / 1000,
        Binary(&packed),
        ("camera", Binary(&[255, 255, 255]), Binary(&[48, 96, 160])),
    )])
    .map_err(|_| "origin stream encoding failed")
}

/// Materializes every accepted sensor while preserving unchanged packets and unknown SID bytes.
/// # Errors
/// Rejects invalid state or malformed cached sensor packets.
pub fn current_packet(
    original: Option<&[u8]>,
    position: Option<&OriginPosition>,
    sensors: &[SensorState],
) -> Result<Vec<u8>, &'static str> {
    let timestamp = sensors
        .iter()
        .map(|s| s.sample_at_ms)
        .chain(position.iter().map(|p| p.fix_at_ms))
        .max()
        .ok_or("missing source state")?;
    if let Some(original) = original {
        let mut current = sensors.to_vec();
        current.sort_by(|a, b| a.sensor_id.cmp(&b.sensor_id));
        let mut cached = decode_packed(original)?.ok_or("missing cached sensor extension")?;
        cached.sort_by(|a, b| a.sensor_id.cmp(&b.sensor_id));
        let valid_position = position.is_some_and(|p| {
            let representable = p.alt_m.is_some()
                && p.speed_mps.is_some()
                && p.course_deg.is_some()
                && p.accuracy_m.is_some();
            (!representable || crate::msgpack::telemetry_sensor_bytes(original, 2).is_some())
                && validate_position_against_packed(p, original).is_ok()
        }) || position.is_none()
            && crate::msgpack::telemetry_sensor_bytes(original, 2).is_none();
        if current == cached && valid_position {
            return Ok(original.to_vec());
        }
        let generated = encode_packed(timestamp / 1000, position, sensors)?;
        let updated = crate::msgpack::replace_sensor(
            original,
            2,
            crate::msgpack::telemetry_sensor_bytes(&generated, 2),
        )?;
        crate::msgpack::replace_sensor(
            &updated,
            SENSOR_ID,
            crate::msgpack::telemetry_sensor_bytes(&generated, SENSOR_ID),
        )
    } else {
        encode_packed(timestamp / 1000, position, sensors)
    }
}
