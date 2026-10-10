//! Checked application telemetry at the daemon JSON and durable wire boundaries.
use super::{
    JsonValue, TelemetrySample, attachment_data_bytes, decode_lxmf_location_sensor,
    humanize_lxmf_telemetry_payload, lxmf_telemetry_timestamp, optional_field_value,
    optional_message_i64, parse_lxmf_telemetry_payload,
};
use crate::{DecodedLxmfMessage, TransportError, reticulumd_message_to_payloads};
use lxmf::inbound_decode::{InboundPayloadMode, decode_inbound_message};

// Match durable journal frame and collector sensor bounds. These are decode
// ceilings, not a new history/cache retention policy.
const MAX_FRAME_BYTES: usize = 12 * 1024 * 1024;
const MAX_SENSOR_BYTES: usize = 1024 * 1024;
const MAX_TIMESTAMP: f64 = 253_402_300_800.0;

pub(super) fn direct_lxmf_telemetry(
    fields: Option<&serde_json::Map<String, JsonValue>>,
    message: &JsonValue,
) -> Result<Option<TelemetrySample>, &'static str> {
    let Some(payload) = fields
        .and_then(|f| optional_field_value(f, &["telemetry", "FIELD_TELEMETRY", "2", "0x02"]))
    else {
        return Ok(None);
    };
    if payload
        .as_str()
        .is_some_and(|s| s.len() > MAX_SENSOR_BYTES * 2)
        || payload
            .as_array()
            .is_some_and(|a| a.len() > MAX_SENSOR_BYTES)
    {
        return Err("malformed LXMF FIELD_TELEMETRY (0x02): sensor byte limit exceeded");
    }
    let packed = attachment_data_bytes(payload);
    if packed.len() > MAX_SENSOR_BYTES {
        return Err("malformed LXMF FIELD_TELEMETRY (0x02): sensor byte limit exceeded");
    }
    let mut telemetry = parse_lxmf_telemetry_payload(payload).ok_or(
        "malformed LXMF FIELD_TELEMETRY (0x02): invalid, truncated or excessive MessagePack",
    )?;
    validate_and_normalize(&mut telemetry)?;
    let telemetry = humanize_lxmf_telemetry_payload(telemetry);
    let timestamp_s = lxmf_telemetry_timestamp(&telemetry)
        .or_else(|| optional_message_i64(message, &["timestamp", "timestamp_s", "time"]));
    Ok(Some(TelemetrySample {
        packed_telemeter: (!packed.is_empty()).then_some(packed),
        telemetry,
        timestamp_s,
    }))
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
fn validate_and_normalize(telemetry: &mut JsonValue) -> Result<(), &'static str> {
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
        let location = decode_lxmf_location_sensor(sensor).ok_or(
            "malformed LXMF FIELD_TELEMETRY (0x02): location requires seven correctly typed packed readings",
        )?;
        coordinates(&location)?;
    }
    Ok(())
}

fn hex_bytes(text: &str, limit: usize) -> Result<Vec<u8>, &'static str> {
    let text = text.strip_prefix("0x").unwrap_or(text);
    if text.len() > limit * 2 || text.len() % 2 != 0 {
        return Err("malformed LXMF FIELD_TELEMETRY (0x02): invalid or excessive raw frame length");
    }
    text.as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let digit = |b: u8| match b {
                b'0'..=b'9' => Some(b - b'0'),
                b'a'..=b'f' => Some(b - b'a' + 10),
                b'A'..=b'F' => Some(b - b'A' + 10),
                _ => None,
            };
            Ok(digit(pair[0])
                .ok_or("malformed LXMF FIELD_TELEMETRY (0x02): invalid raw frame hex")?
                * 16
                + digit(pair[1])
                    .ok_or("malformed LXMF FIELD_TELEMETRY (0x02): invalid raw frame hex")?)
        })
        .collect()
}
fn recover_sensor(message: &JsonValue, raw: &JsonValue) -> Result<Option<Vec<u8>>, &'static str> {
    let raw = raw
        .as_str()
        .ok_or("malformed LXMF FIELD_TELEMETRY (0x02): raw frame must be hex text")?;
    let bytes = hex_bytes(raw, MAX_FRAME_BYTES)?;
    let source = message
        .get("source")
        .and_then(JsonValue::as_str)
        .ok_or("malformed LXMF FIELD_TELEMETRY (0x02): missing verified metadata")?;
    let destination = message
        .get("destination")
        .and_then(JsonValue::as_str)
        .ok_or("malformed LXMF FIELD_TELEMETRY (0x02): missing verified metadata")?;
    let id = message
        .get("id")
        .and_then(JsonValue::as_str)
        .ok_or("malformed LXMF FIELD_TELEMETRY (0x02): missing verified metadata")?;
    let source = hex_bytes(source, 16)?;
    let destination: [u8; 16] = hex_bytes(destination, 16)?
        .try_into()
        .map_err(|_| "malformed LXMF FIELD_TELEMETRY (0x02): invalid verified destination")?;
    for mode in [
        InboundPayloadMode::FullWire,
        InboundPayloadMode::DestinationStripped,
    ] {
        let header = match mode {
            InboundPayloadMode::FullWire => 96,
            InboundPayloadMode::DestinationStripped => 80,
        };
        let Some(payload) = bytes.get(header..) else {
            continue;
        };
        if !super::bounded_lxmf_wire_payload(payload) {
            continue;
        }
        let Ok(decoded) = decode_inbound_message(destination, &bytes, mode) else {
            continue;
        };
        if decoded.source.as_slice() != source
            || decoded.destination != destination
            || !decoded.id.eq_ignore_ascii_case(id)
        {
            continue;
        }
        if let Some(fields) = decoded.fields.as_ref().and_then(|f| f.as_map()) {
            for (key, value) in fields {
                if key.as_u64() == Some(2) || key.as_i64() == Some(2) {
                    // The pinned wire decoder accepts binary and legacy byte strings.
                    let sensor = value.as_slice().ok_or(
                        "malformed LXMF FIELD_TELEMETRY (0x02): raw sensor must be packed bytes",
                    )?;
                    if sensor.len() > MAX_SENSOR_BYTES {
                        return Err(
                            "malformed LXMF FIELD_TELEMETRY (0x02): sensor byte limit exceeded",
                        );
                    }
                    return Ok(Some(sensor.to_vec()));
                }
            }
        }
        return Ok(None);
    }
    Err(
        "malformed LXMF FIELD_TELEMETRY (0x02): raw frame decode or verified source/destination/message-id binding failed",
    )
}

/// Decode a durable broker event payload, retaining original sensor bytes only
/// after binding the raw frame to the daemon's verified message metadata.
pub fn reticulumd_event_payload_to_payloads(
    payload: &JsonValue,
    local_source: &str,
) -> Result<DecodedLxmfMessage, TransportError> {
    let message = payload.get("message").unwrap_or(payload);
    // Keep verified direction/destination and embedded-envelope checks authoritative.
    let mut decoded = reticulumd_message_to_payloads(message, local_source)?;
    if message.get("direction").and_then(JsonValue::as_str) != Some("in")
        || !message
            .get("destination")
            .and_then(JsonValue::as_str)
            .is_some_and(|d| {
                d.trim()
                    .trim_start_matches("0x")
                    .eq_ignore_ascii_case(local_source.trim().trim_start_matches("0x"))
            })
        || message
            .get("fields")
            .and_then(|f| {
                optional_field_value(
                    f.as_object()?,
                    &["2", "FIELD_TELEMETRY", "telemetry", "0x02"],
                )
            })
            .is_none()
    {
        return Ok(decoded);
    }
    let Some(raw) = payload.get("lxmf_bytes_hex") else {
        return Ok(decoded);
    };
    let mut corrected = message.clone();
    let fields = corrected
        .get_mut("fields")
        .and_then(JsonValue::as_object_mut);
    if let Some(fields) = fields {
        for key in ["2", "FIELD_TELEMETRY", "telemetry", "0x02"] {
            fields.remove(key);
        }
        match recover_sensor(message, raw) {
            Ok(Some(sensor)) => {
                fields.insert("2".into(), serde_json::json!(sensor));
            }
            Ok(None) => {
                decoded = reticulumd_message_to_payloads(&corrected, local_source)?;
                decoded.telemetry_diagnostics.push("malformed LXMF FIELD_TELEMETRY (0x02): projected sensor absent from verified raw frame".into());
                return Ok(decoded);
            }
            Err(reason) => {
                decoded = reticulumd_message_to_payloads(&corrected, local_source)?;
                decoded.telemetry_diagnostics.push(reason.into());
                return Ok(decoded);
            }
        }
    }
    reticulumd_message_to_payloads(&corrected, local_source)
}

pub(super) fn preserve_unconverted_sensors(
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
