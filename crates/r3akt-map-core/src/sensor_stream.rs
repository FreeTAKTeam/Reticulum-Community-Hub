//! Checked field-3 object tuples, independent of the authenticated relay address.
use crate::{bytes::json_bytes, sensor::SensorState, sensor_wire, telemetry};
use serde_json::Value;
use std::fmt::Write as _;

#[derive(Debug, Clone, PartialEq)]
pub struct OriginSensorSample {
    pub origin_id: String,
    pub sample_at_ms: u64,
    pub packed_telemeter: Vec<u8>,
    pub sensors: Vec<SensorState>,
    pub diagnostic: Option<&'static str>,
}

/// Reads only sensor-bearing object tuples; ordinary marker streams stay on their existing path.
/// # Errors
/// Rejects invalid identities, timestamps, appearance or oversized tuples.
pub fn decode(value: &Value) -> Result<Vec<OriginSensorSample>, &'static str> {
    let items = value
        .as_array()
        .filter(|a| a.len() <= 1024)
        .ok_or("invalid object sensor stream")?;
    let mut result = Vec::new();
    let mut ids = std::collections::HashSet::new();
    for item in items {
        let tuple = item
            .as_array()
            .filter(|a| a.len() == 4)
            .ok_or("object stream requires four fields")?;
        let hash = json_bytes(&tuple[0]);
        if hash.len() != 16 {
            return Err("invalid object identity");
        }
        let mut origin_id = String::with_capacity(32);
        for byte in &hash {
            write!(&mut origin_id, "{byte:02x}").map_err(|_| "invalid object identity")?;
        }
        if !ids.insert(origin_id.clone()) {
            return Err("duplicate object identity");
        }
        let sample_at_ms = tuple[1]
            .as_u64()
            .and_then(|v| v.checked_mul(1000))
            .ok_or("invalid object source time")?;
        crate::sensor::valid_time(sample_at_ms)?;
        if !tuple[3].is_null() {
            let appearance = tuple[3]
                .as_array()
                .filter(|a| a.len() == 3)
                .ok_or("invalid object appearance")?;
            if appearance[0]
                .as_str()
                .is_none_or(|s| s.is_empty() || s.len() > 64)
                || json_bytes(&appearance[1]).len() != 3
                || json_bytes(&appearance[2]).len() != 3
            {
                return Err("invalid object appearance");
            }
        }
        let packed = json_bytes(&tuple[2]);
        telemetry::decode_field(&serde_json::json!(packed))?;
        match sensor_wire::decode_packed(&packed) {
            Ok(None) => {}
            Ok(Some(sensors)) => {
                if sensors.iter().any(|s| {
                    s.sample_at_ms / 1000 != sample_at_ms / 1000
                        && s.sample_at_ms > sample_at_ms.saturating_add(999)
                }) {
                    return Err("object sample time precedes its sensors");
                }
                result.push(OriginSensorSample {
                    origin_id,
                    sample_at_ms,
                    packed_telemeter: packed,
                    sensors,
                    diagnostic: None,
                });
            }
            Err(diagnostic) => result.push(OriginSensorSample {
                origin_id,
                sample_at_ms,
                packed_telemeter: packed,
                sensors: Vec::new(),
                diagnostic: Some(diagnostic),
            }),
        }
    }
    if result.len() > 16 {
        return Err("object sensor stream limit exceeded");
    }
    Ok(result)
}
