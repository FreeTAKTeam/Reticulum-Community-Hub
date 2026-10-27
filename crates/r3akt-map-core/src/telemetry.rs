//! LXMF `FIELD_TELEMETRY` (0x02) Telemeter payloads.
//!
//! The verified receive contract (RCH #258): field 2 carries `MessagePack` bytes
//! for a numeric sensor map. Sensor 1 is epoch seconds; location sensor 2 has
//! seven readings (signed i32 latitude/longitude in millionths of a degree,
//! signed i32 altitude in centimetres, u32 speed in cm/s, signed i32 bearing in
//! hundredths of a degree, u16 accuracy in centimetres, numeric last update).
//! There is no schema/version negotiation; explicit version envelopes are
//! unsupported. Unknown numeric sensors are preserved as extension data.
//!
//! Diagnostics name the field and failure stage but never sensor values.

use serde_json::Value as JsonValue;

use crate::bytes::json_bytes;
use crate::msgpack;

/// Packed sensor ceiling, matching the collector's 1 MiB bound.
pub const MAX_SENSOR_BYTES: usize = 1024 * 1024;
const MAX_TIMESTAMP: f64 = 253_402_300_800.0;

/// A validated, normalized telemetry sample.
#[derive(Debug, Clone, PartialEq)]
pub struct CheckedTelemetry {
    /// Original packed sensor bytes, when the payload carried them.
    pub packed_telemeter: Option<Vec<u8>>,
    /// Humanized sensor map (`time`, `location`, named sensors, unknown IDs).
    pub telemetry: JsonValue,
    /// Sensor time in epoch seconds, when present.
    pub timestamp_s: Option<i64>,
}

/// Decodes and validates a `FIELD_TELEMETRY` value from a JSON projection:
/// packed bytes, a numeric sensor map, or a daemon location projection.
///
/// # Errors
/// A privacy-safe diagnostic for oversized, malformed or unsupported payloads.
pub fn decode_field(payload: &JsonValue) -> Result<CheckedTelemetry, &'static str> {
    if payload
        .as_str()
        .is_some_and(|s| s.len() > MAX_SENSOR_BYTES * 2)
        || payload
            .as_array()
            .is_some_and(|a| a.len() > MAX_SENSOR_BYTES)
    {
        return Err("malformed LXMF FIELD_TELEMETRY (0x02): sensor byte limit exceeded");
    }
    let packed = json_bytes(payload);
    if packed.len() > MAX_SENSOR_BYTES {
        return Err("malformed LXMF FIELD_TELEMETRY (0x02): sensor byte limit exceeded");
    }
    let mut telemetry = parse_payload(payload).ok_or(
        "malformed LXMF FIELD_TELEMETRY (0x02): invalid, truncated or excessive MessagePack",
    )?;
    validate_and_normalize(&mut telemetry)?;
    let telemetry = humanize(telemetry);
    let timestamp_s = timestamp_seconds(&telemetry);
    Ok(CheckedTelemetry {
        packed_telemeter: (!packed.is_empty()).then_some(packed),
        telemetry,
        timestamp_s,
    })
}

/// Interprets a payload as a sensor map: JSON objects as-is, otherwise its
/// bytes as exactly one checked `MessagePack` value.
#[must_use]
pub fn parse_payload(value: &JsonValue) -> Option<JsonValue> {
    if value.as_object().is_some() {
        return Some(value.clone());
    }
    let bytes = json_bytes(value);
    if bytes.is_empty() {
        return None;
    }
    msgpack::to_json(&bytes)
}

fn timestamp(value: &JsonValue) -> Result<f64, &'static str> {
    value.as_f64().filter(|v| v.is_finite() && *v >= 0.0 && *v < MAX_TIMESTAMP)
        .ok_or("malformed LXMF FIELD_TELEMETRY (0x02): time must be finite epoch seconds before year 10000")
}

fn coordinates(location: &JsonValue) -> Result<(), &'static str> {
    for (key, limit) in [("latitude", 90.0), ("longitude", 180.0)] {
        if !location
            .get(key)
            .and_then(JsonValue::as_f64)
            .is_some_and(|v| v.is_finite() && v.abs() <= limit)
        {
            return Err(
                "malformed LXMF FIELD_TELEMETRY (0x02): location coordinates have invalid type or range",
            );
        }
    }
    for key in ["altitude", "speed", "bearing", "accuracy"] {
        if location
            .get(key)
            .is_some_and(|v| !v.is_null() && !v.as_f64().is_some_and(f64::is_finite))
        {
            return Err(
                "malformed LXMF FIELD_TELEMETRY (0x02): location readings must be finite numbers",
            );
        }
    }
    if let Some(t) = location.get("last_update_timestamp") {
        timestamp(t)?;
    }
    Ok(())
}

/// Validates a parsed payload and normalizes the daemon's flat location
/// projection (`lat`, `lon`, ...) to the nested `location` map.
///
/// # Errors
/// A privacy-safe diagnostic for malformed or unsupported payloads.
pub fn validate_and_normalize(telemetry: &mut JsonValue) -> Result<(), &'static str> {
    let object = telemetry.as_object_mut().ok_or(
        "unsupported LXMF FIELD_TELEMETRY (0x02): expected a sensor map or known location projection",
    )?;
    if object.contains_key("schema_version") || object.contains_key("version") {
        return Err(
            "unsupported LXMF FIELD_TELEMETRY (0x02): explicit schema envelope; no schema version negotiated",
        );
    }
    // Pinned reticulumd rmpv_to_json projects packed location into these names.
    // Bootstrap lacks original sensor bytes; normalization does not invent them.
    if object.contains_key("lat") || object.contains_key("lon") {
        let mut location = serde_json::Map::new();
        for (from, to) in [
            ("lat", "latitude"),
            ("lon", "longitude"),
            ("alt", "altitude"),
            ("speed", "speed"),
            ("bearing", "bearing"),
            ("accuracy", "accuracy"),
            ("updated", "last_update_timestamp"),
        ] {
            if let Some(v) = object.get(from) {
                location.insert(to.into(), v.clone());
            }
        }
        let location = JsonValue::Object(location);
        coordinates(&location)?;
        let time = object.get("updated").map(timestamp).transpose()?;
        *telemetry = serde_json::json!({"location": location});
        if let Some(t) = time {
            telemetry["time"] = serde_json::json!({"timestamp":t});
        }
        return Ok(());
    }
    if object.contains_key("location") || object.contains_key("time") {
        if let Some(location) = object.get("location").filter(|v| !v.is_null()) {
            coordinates(location)?;
        }
        if let Some(time) = object.get("time") {
            timestamp(time.get("timestamp").unwrap_or(&JsonValue::Null))?;
        }
        return Ok(());
    }
    if object.keys().any(|key| key.parse::<u8>().is_err()) {
        return Err(
            "unsupported LXMF FIELD_TELEMETRY (0x02): unknown payload shape; no schema version negotiated",
        );
    }
    if let Some(time) = object.get("1") {
        timestamp(time)?;
    }
    if let Some(sensor) = object.get("2").filter(|v| !v.is_null()) {
        let location = decode_location_sensor(sensor).ok_or(
            "malformed LXMF FIELD_TELEMETRY (0x02): location requires seven correctly typed packed readings",
        )?;
        coordinates(&location)?;
    }
    Ok(())
}

/// Names known sensors and keeps unconverted ones under their numeric IDs.
/// Payloads already in named form are returned unchanged.
#[must_use]
pub fn humanize(payload: JsonValue) -> JsonValue {
    let Some(object) = payload.as_object() else {
        return payload;
    };
    if object.contains_key("location") || object.contains_key("time") {
        return payload;
    }
    let mut humanized = serde_json::Map::new();
    if let Some(timestamp) = object.get("1").and_then(json_number_to_f64) {
        humanized.insert(
            "time".to_string(),
            serde_json::json!({
                "timestamp": json_number_from_f64(timestamp),
                "iso": unix_timestamp_iso(timestamp),
            }),
        );
    }
    if let Some(location) = object.get("2").and_then(decode_location_sensor) {
        humanized.insert("location".to_string(), location);
    }
    for (sid, name, field) in [
        ("3", "pressure", "mbar"),
        ("7", "temperature", "c"),
        ("8", "humidity", "percent_relative"),
        ("10", "ambient_light", "lux"),
        ("14", "proximity", "triggered"),
    ] {
        if let Some(sensor) = object
            .get(sid)
            .and_then(|value| decode_lxmf_scalar_sensor(value, field))
        {
            humanized.insert(name.to_string(), sensor);
        }
    }
    for (sid, name, fields) in [
        ("5", "physical_link", ["rssi", "snr", "q"]),
        ("6", "acceleration", ["x", "y", "z"]),
        ("9", "magnetic_field", ["x", "y", "z"]),
        ("11", "gravity", ["x", "y", "z"]),
        ("12", "angular_velocity", ["x", "y", "z"]),
    ] {
        if let Some(sensor) = object
            .get(sid)
            .and_then(|value| decode_lxmf_triplet_sensor(value, fields))
        {
            humanized.insert(name.to_string(), sensor);
        }
    }
    for (sid, name) in [
        ("24", "lxmf_propagation"),
        ("25", "rns_transport"),
        ("26", "connection_map"),
    ] {
        if let Some(sensor) = object.get(sid).filter(|value| value.as_object().is_some()) {
            humanized.insert(name.to_string(), sensor.clone());
        }
    }
    if let Some(received) = object.get("16").and_then(decode_lxmf_received_sensor) {
        humanized.insert("received".to_string(), received);
    }
    for (sid, name) in [
        ("17", "power_consumption"),
        ("18", "power_production"),
        ("19", "processor"),
        ("20", "ram"),
        ("21", "nvm"),
        ("22", "tank"),
        ("23", "fuel"),
        ("255", "custom"),
    ] {
        if let Some(sensor) = object.get(sid).and_then(decode_lxmf_collection_sensor) {
            humanized.insert(name.to_string(), sensor);
        }
    }
    if let Some(battery) = object.get("4").and_then(decode_lxmf_battery_sensor) {
        humanized.insert("battery".to_string(), battery);
    }
    if let Some(information) = object.get("15").and_then(decode_lxmf_information_sensor) {
        humanized.insert("information".to_string(), information);
    }
    preserve_unconverted_sensors(object, &mut humanized);
    if humanized.is_empty() {
        payload
    } else {
        JsonValue::Object(humanized)
    }
}

/// Sensor time (`time.timestamp`) in whole epoch seconds.
#[must_use]
pub fn timestamp_seconds(telemetry: &JsonValue) -> Option<i64> {
    telemetry
        .get("time")
        .and_then(|time| time.get("timestamp"))
        .and_then(json_number_to_i64)
}

/// Decodes packed location sensor 2 into named readings.
#[must_use]
pub fn decode_location_sensor(value: &JsonValue) -> Option<JsonValue> {
    let items = value.as_array()?;
    if items.len() < 7 {
        return None;
    }
    let latitude = f64::from(read_i32_be(&json_bytes(&items[0]))?) / 1_000_000.0;
    let longitude = f64::from(read_i32_be(&json_bytes(&items[1]))?) / 1_000_000.0;
    let altitude = f64::from(read_i32_be(&json_bytes(&items[2]))?) / 100.0;
    let speed = f64::from(read_u32_be(&json_bytes(&items[3]))?) / 100.0;
    let bearing = f64::from(read_i32_be(&json_bytes(&items[4]))?) / 100.0;
    let accuracy = f64::from(read_u16_be(&json_bytes(&items[5]))?) / 100.0;
    let last_update = json_number_to_f64(&items[6])?;
    Some(serde_json::json!({
        "latitude": latitude,
        "longitude": longitude,
        "altitude": altitude,
        "speed": speed,
        "bearing": bearing,
        "accuracy": accuracy,
        "last_update_timestamp": last_update,
        "last_update_iso": unix_timestamp_iso(last_update),
    }))
}

fn decode_lxmf_scalar_sensor(value: &JsonValue, field: &str) -> Option<JsonValue> {
    if value.is_null() {
        return None;
    }
    let mut object = serde_json::Map::new();
    object.insert(field.to_string(), value.clone());
    Some(JsonValue::Object(object))
}

fn decode_lxmf_triplet_sensor(value: &JsonValue, fields: [&str; 3]) -> Option<JsonValue> {
    let items = value.as_array()?;
    let mut object = serde_json::Map::new();
    object.insert(fields[0].to_string(), items.first()?.clone());
    object.insert(fields[1].to_string(), items.get(1)?.clone());
    object.insert(fields[2].to_string(), items.get(2)?.clone());
    Some(JsonValue::Object(object))
}

fn decode_lxmf_received_sensor(value: &JsonValue) -> Option<JsonValue> {
    let items = value.as_array()?;
    Some(serde_json::json!({
        "by": items.first()?.clone(),
        "via": items.get(1)?.clone(),
        "distance": {
            "geodesic": items.get(2)?.clone(),
            "euclidian": items.get(3)?.clone(),
        },
    }))
}

fn decode_lxmf_collection_sensor(value: &JsonValue) -> Option<JsonValue> {
    let records = value.as_array()?;
    let mut object = serde_json::Map::new();
    for record in records {
        let Some(items) = record.as_array() else {
            continue;
        };
        if items.len() < 2 {
            continue;
        }
        let Some(label) = lxmf_collection_label(&items[0]) else {
            continue;
        };
        object.insert(label, items[1].clone());
    }
    (!object.is_empty()).then_some(JsonValue::Object(object))
}

fn lxmf_collection_label(value: &JsonValue) -> Option<String> {
    if value.is_null() {
        return Some("0".to_string());
    }
    if let Some(label) = value
        .as_str()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        return Some(label.to_string());
    }
    if let Some(label) = json_number_to_i64(value) {
        return Some(label.to_string());
    }
    let bytes = json_bytes(value);
    if bytes.is_empty() {
        return None;
    }
    std::str::from_utf8(&bytes)
        .ok()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string)
}

fn decode_lxmf_battery_sensor(value: &JsonValue) -> Option<JsonValue> {
    let items = value.as_array()?;
    let charge_percent = items.first().map(|value| {
        if value.is_null() {
            JsonValue::Null
        } else {
            json_number_to_f64(value)
                .map_or(JsonValue::Null, |value| JsonValue::from(round_1(value)))
        }
    })?;
    let charging = items.get(1).cloned().unwrap_or(JsonValue::Null);
    let temperature = items.get(2).cloned().unwrap_or(JsonValue::Null);
    Some(serde_json::json!({
        "charge_percent": charge_percent,
        "charging": charging,
        "temperature": temperature,
    }))
}

fn decode_lxmf_information_sensor(value: &JsonValue) -> Option<JsonValue> {
    let contents = value.as_str().map(ToString::to_string)?;
    Some(serde_json::json!({
        "contents": contents,
    }))
}

fn read_i32_be(bytes: &[u8]) -> Option<i32> {
    Some(i32::from_be_bytes(bytes.try_into().ok()?))
}

fn read_u32_be(bytes: &[u8]) -> Option<u32> {
    Some(u32::from_be_bytes(bytes.try_into().ok()?))
}

fn read_u16_be(bytes: &[u8]) -> Option<u16> {
    Some(u16::from_be_bytes(bytes.try_into().ok()?))
}

fn json_number_to_f64(value: &JsonValue) -> Option<f64> {
    value.as_f64()
}

fn json_number_to_i64(value: &JsonValue) -> Option<i64> {
    value
        .as_i64()
        .or_else(|| value.as_u64().and_then(|value| i64::try_from(value).ok()))
        .or_else(|| {
            value.as_f64().and_then(|value| {
                if value.is_finite() && value.fract() == 0.0 {
                    format!("{value:.0}").parse().ok()
                } else {
                    None
                }
            })
        })
}

fn json_number_from_f64(value: f64) -> JsonValue {
    if value.is_finite()
        && value.fract() == 0.0
        && let Ok(integer) = format!("{value:.0}").parse::<i64>()
    {
        return JsonValue::from(integer);
    }
    JsonValue::from(value)
}

fn round_1(value: f64) -> f64 {
    (value * 10.0).round() / 10.0
}

fn unix_timestamp_iso(value: f64) -> String {
    format!("{value}")
}

fn preserve_unconverted_sensors(
    object: &serde_json::Map<String, JsonValue>,
    humanized: &mut serde_json::Map<String, JsonValue>,
) {
    for (sid, value) in object {
        let name = match sid.as_str() {
            "1" => "time",
            "2" => "location",
            "3" => "pressure",
            "4" => "battery",
            "5" => "physical_link",
            "6" => "acceleration",
            "7" => "temperature",
            "8" => "humidity",
            "9" => "magnetic_field",
            "10" => "ambient_light",
            "11" => "gravity",
            "12" => "angular_velocity",
            "14" => "proximity",
            "15" => "information",
            "16" => "received",
            "17" => "power_consumption",
            "18" => "power_production",
            "19" => "processor",
            "20" => "ram",
            "21" => "nvm",
            "22" => "tank",
            "23" => "fuel",
            "24" => "lxmf_propagation",
            "25" => "rns_transport",
            "26" => "connection_map",
            "255" => "custom",
            _ => "",
        };
        if !humanized.contains_key(name) {
            humanized.insert(sid.clone(), value.clone());
        }
    }
}
