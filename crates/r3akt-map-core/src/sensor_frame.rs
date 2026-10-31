//! Shared parsing of R3S LXMF fields; authenticated origin authorization stays with the host.
use crate::{
    bytes::json_bytes,
    sensor_stream::OriginSensorSample,
    sensor_wire::{self, SensorEvent},
};
use serde_json::Value;

#[derive(Debug, Default)]
pub struct SensorFrame {
    pub events: Vec<SensorEvent>,
    pub assertions: Vec<OriginAssertion>,
    pub expiries: Vec<crate::sensor_expiry::SensorExpiry>,
    pub samples: Vec<OriginSensorSample>,
    pub diagnostics: Vec<&'static str>,
}

/// # Errors
/// Rejects malformed/oversized outer fields and invalid authenticated source identities.
pub fn decode(fields: &[u8], source: &str) -> Result<SensorFrame, &'static str> {
    crate::marker::object_destination_hash(source).map_err(|_| "invalid authenticated source")?;
    if fields.len() > crate::telemetry::MAX_SENSOR_BYTES {
        return Err("sensor fields limit exceeded");
    }
    let fields = crate::msgpack::to_json(fields).ok_or("invalid sensor fields")?;
    decode_json(&fields, source)
}

/// # Errors
/// Rejects excessive event lists or object streams. Optional geometry errors are diagnostics.
pub const ASSERT_EVENT: &str = "mission.registry.sensor_origin.assert";
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct OriginAssertion {
    pub origin_id: String,
    pub writer_id: String,
    pub origin_kind: String,
    pub label: String,
}
impl OriginAssertion {
    /// # Errors
    /// Rejects noncanonical IDs, unrecognized kinds, and unbounded labels.
    pub fn validate(&self) -> Result<(), &'static str> {
        for id in [&self.origin_id, &self.writer_id] {
            if crate::marker::object_destination_hash(id)
                .map_err(|_| "invalid asserted identity")?
                != *id
            {
                return Err("noncanonical asserted identity");
            }
        }
        if !["device", "mobile", "uav", "vehicle", "camera", "fixed"]
            .contains(&self.origin_kind.as_str())
            || self.origin_kind == "device" && self.origin_id != self.writer_id
            || self.label.len() > 128
            || self.label.chars().any(char::is_control)
        {
            return Err("invalid origin assertion");
        }
        Ok(())
    }
}
/// # Errors
/// Rejects excessive event lists, invalid source fixes and malformed object streams.
pub fn decode_json(fields: &Value, source: &str) -> Result<SensorFrame, &'static str> {
    let mut frame = SensorFrame::default();
    let events = fields
        .get("13")
        .map(|v| v.as_array().map_or_else(|| vec![v], |a| a.iter().collect()))
        .unwrap_or_default();
    if events.len() > 2304 {
        return Err("sensor event limit exceeded");
    }
    for event in events {
        if event["event_type"] == crate::sensor_expiry::EVENT {
            let expiry: crate::sensor_expiry::SensorExpiry =
                serde_json::from_value(event["payload"].clone())
                    .map_err(|_| "invalid sensor expiry")?;
            expiry.validate()?;
            frame.expiries.push(expiry);
            continue;
        }
        if event["event_type"] == ASSERT_EVENT {
            let assertion: OriginAssertion = serde_json::from_value(event["payload"].clone())
                .map_err(|_| "invalid origin assertion")?;
            assertion.validate()?;
            frame.assertions.push(assertion);
            continue;
        }
        if event
            .get("event_type")
            .and_then(Value::as_str)
            .is_some_and(|s| {
                [
                    sensor_wire::ORIGIN_FIX_EVENT,
                    sensor_wire::MANIFEST_EVENT,
                    sensor_wire::SENSOR_REMOVE_EVENT,
                    sensor_wire::ORIGIN_REMOVE_EVENT,
                ]
                .contains(&s)
            })
        {
            let parsed: SensorEvent =
                serde_json::from_value(event.clone()).map_err(|_| "invalid sensor event")?;
            parsed.validate()?;
            frame.events.push(parsed);
        }
    }
    if let Some(value) = fields.get("2") {
        let packed = json_bytes(value);
        match sensor_wire::decode_packed(&packed) {
            Ok(Some(sensors)) => frame.samples.push(OriginSensorSample {
                origin_id: source.into(),
                sample_at_ms: sensors.iter().map(|s| s.sample_at_ms).max().unwrap_or(0),
                packed_telemeter: packed,
                sensors,
                diagnostic: None,
            }),
            Ok(None) => {}
            Err(e) => frame.diagnostics.push(e),
        }
    }
    if let Some(stream) = fields.get("3") {
        frame.samples.extend(crate::sensor_stream::decode(stream)?);
    }
    for sample in &frame.samples {
        if !frame
            .events
            .iter()
            .any(|e| matches!(e,SensorEvent::OriginFix(e) if e.origin_id==sample.origin_id))
            && let Some(event) = standard_fix(sample)?
        {
            frame.events.push(event);
        }

        if let Some(e) = sample.diagnostic {
            frame.diagnostics.push(e);
        }
        if let Some(position) = frame.events.iter().find_map(|e| match e {
            SensorEvent::OriginFix(e) if e.origin_id == sample.origin_id => Some(&e.position),
            _ => None,
        }) {
            sensor_wire::validate_position_against_packed(position, &sample.packed_telemeter)?;
        }
    }
    Ok(frame)
}

fn standard_fix(sample: &OriginSensorSample) -> Result<Option<SensorEvent>, &'static str> {
    let decoded = crate::telemetry::decode_field(&serde_json::json!(sample.packed_telemeter))?;
    if let Some(location) = decoded.telemetry.get("location") {
        let number = |key| {
            location
                .get(key)
                .and_then(Value::as_f64)
                .ok_or("invalid standard origin position")
        };
        let seconds = number("last_update_timestamp")?;
        if !seconds.is_finite() || !(0.0..253_402_300_800.0).contains(&seconds) {
            return Err("invalid standard fix source time");
        }
        let fix_time = format!("{:.0}", seconds * 1000.)
            .parse::<u64>()
            .map_err(|_| "invalid standard fix source time")?;
        return Ok(Some(SensorEvent::OriginFix(sensor_wire::OriginFixEvent {
            origin_id: sample.origin_id.clone(),
            position: crate::sensor::OriginPosition {
                lat: number("latitude")?,
                lon: number("longitude")?,
                alt_m: Some(number("altitude")?),
                altitude_datum: crate::sensor::AltitudeDatum::Unknown,
                fix_at_ms: fix_time,
                speed_mps: Some(number("speed")? / 3.6),
                course_deg: Some(number("bearing")?),
                accuracy_m: Some(number("accuracy")?),
            },
        })));
    }
    Ok(None)
}
