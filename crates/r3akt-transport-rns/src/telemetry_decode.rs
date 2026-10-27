//! Checked application telemetry at the daemon JSON and durable wire boundaries.
use super::{JsonValue, TelemetrySample, optional_field_value, optional_message_i64};
use crate::{DecodedLxmfMessage, TransportError, reticulumd_message_to_payloads};
use lxmf::inbound_decode::{InboundPayloadMode, decode_inbound_message};
use r3akt_map_core::telemetry::{self, MAX_SENSOR_BYTES};

// Match the durable journal frame bound. This is a decode ceiling, not a
// history/cache retention policy; the sensor bound is shared.
const MAX_FRAME_BYTES: usize = 12 * 1024 * 1024;

pub(super) fn direct_lxmf_telemetry(
    fields: Option<&serde_json::Map<String, JsonValue>>,
    message: &JsonValue,
) -> Result<Option<TelemetrySample>, &'static str> {
    let Some(payload) = fields
        .and_then(|f| optional_field_value(f, &["telemetry", "FIELD_TELEMETRY", "2", "0x02"]))
    else {
        return Ok(None);
    };
    let checked = telemetry::decode_field(payload)?;
    Ok(Some(TelemetrySample {
        packed_telemeter: checked.packed_telemeter,
        telemetry: checked.telemetry,
        timestamp_s: checked
            .timestamp_s
            .or_else(|| optional_message_i64(message, &["timestamp", "timestamp_s", "time"])),
    }))
}

fn hex_bytes(text: &str, limit: usize) -> Result<Vec<u8>, &'static str> {
    let text = text.strip_prefix("0x").unwrap_or(text);
    if text.len() > limit * 2 || !text.len().is_multiple_of(2) {
        return Err("malformed LXMF FIELD_TELEMETRY (0x02): invalid or excessive raw frame length");
    }
    text.as_bytes()
        .as_chunks::<2>()
        .0
        .iter()
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
