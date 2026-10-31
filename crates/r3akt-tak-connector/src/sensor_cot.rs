//! Stock ATAK single-sensor `CoT` adapter. R3S remains native; `CoT` is a boundary format.
use super::{
    BytesStart, DateTime, EVENT_TYPE_LOCATION, Reader, TakConnector, TakConnectorError, Utc,
    XmlEvent, escape_attr, format_cot_millis, format_float, xml_attr,
};
use r3akt_map_core::sensor::{
    AltitudeDatum, OriginPosition, RangeKind, SensorManifest, SensorState,
};
use serde::{Deserialize, Serialize};
use std::fmt::Write as _;
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CotSensorObservation {
    pub sensor: SensorState,
    pub position: OriginPosition,
    pub manifest: Option<SensorManifest>,
    #[serde(default)]
    pub unapproved_video: Option<r3akt_map_core::sensor::VideoDescriptor>,
    #[serde(default)]
    pub video_diagnostic: Option<String>,
    pub stale_at_ms: u64,
}
fn time(value: &str) -> Result<u64, String> {
    DateTime::parse_from_rfc3339(value)
        .map_err(|_| "invalid sensor CoT source time".to_string())?
        .timestamp_millis()
        .try_into()
        .map_err(|_| "invalid sensor CoT source time".into())
}
fn number(
    reader: &Reader<&[u8]>,
    element: &BytesStart<'_>,
    key: &[u8],
) -> Result<Option<f64>, String> {
    xml_attr(reader, element, key)
        .map_err(|()| "invalid CoT sensor attribute".to_string())?
        .map(|s| {
            s.parse::<f64>()
                .map_err(|_| "invalid CoT sensor number".to_string())
        })
        .transpose()
}
fn parent_position(
    reader: &Reader<&[u8]>,
    element: &BytesStart<'_>,
    event_time: &str,
) -> Result<OriginPosition, String> {
    let altitude = number(reader, element, b"hae")?.filter(|n| *n < 9_999_999.);
    let position = OriginPosition {
        lat: number(reader, element, b"lat")?.ok_or("sensor latitude is required")?,
        lon: number(reader, element, b"lon")?.ok_or("sensor longitude is required")?,
        alt_m: altitude,
        altitude_datum: if altitude.is_some() {
            AltitudeDatum::Hae
        } else {
            AltitudeDatum::Unknown
        },
        fix_at_ms: time(event_time)?,
        speed_mps: None,
        course_deg: None,
        accuracy_m: number(reader, element, b"ce")?.filter(|n| *n < 9_999_999.),
    };
    position.validate().map_err(str::to_string)?;
    Ok(position)
}
pub(super) fn parse(
    raw: &str,
    event_time: &str,
    stale: &str,
) -> Result<Option<CotSensorObservation>, String> {
    let mut reader = Reader::from_str(raw);
    let mut depth = 0usize;
    let mut detail = false;
    let mut sensor = None;
    let mut position: Result<Option<OriginPosition>, String> = Ok(None);
    let mut track = (None, None);
    loop {
        match reader.read_event() {
            Ok(XmlEvent::Start(element)) => {
                depth += 1;
                if depth == 2 {
                    detail = element.name().as_ref() == b"detail";
                }
                if depth == 2 && element.name().as_ref() == b"point" {
                    position = parent_position(&reader, &element, event_time).map(Some);
                }
                if depth == 3 && detail && element.name().as_ref() == b"sensor" {
                    if sensor.is_some() {
                        return Err("multiple CoT sensors require explicit selection".into());
                    }
                    sensor = Some(read(&reader, &element, event_time, stale)?);
                }
                if depth == 3 && detail && element.name().as_ref() == b"track" {
                    track = (
                        number(&reader, &element, b"speed")?,
                        number(&reader, &element, b"course")?,
                    );
                }
            }
            Ok(XmlEvent::Empty(element)) => {
                if depth == 1 && element.name().as_ref() == b"point" {
                    position = parent_position(&reader, &element, event_time).map(Some);
                }
                if depth == 2 && detail && element.name().as_ref() == b"sensor" {
                    if sensor.is_some() {
                        return Err("multiple CoT sensors require explicit selection".into());
                    }
                    sensor = Some(read(&reader, &element, event_time, stale)?);
                }
                if depth == 2 && detail && element.name().as_ref() == b"track" {
                    track = (
                        number(&reader, &element, b"speed")?,
                        number(&reader, &element, b"course")?,
                    );
                }
            }
            Ok(XmlEvent::End(_)) => {
                if depth == 2 {
                    detail = false;
                }
                depth = depth.saturating_sub(1);
            }
            Ok(XmlEvent::Eof) => break,
            Err(_) => return Err("invalid CoT sensor XML".into()),
            _ => {}
        }
    }
    let Some((sensor, manifest, stale_at_ms)) = sensor else {
        return Ok(None);
    };
    let mut position = position?.ok_or("sensor origin point missing")?;
    position.speed_mps = track.0;
    position.course_deg = track.1;
    position.validate().map_err(str::to_string)?;
    let (unapproved_video, video_diagnostic) = super::sensor_video::parse(raw);
    Ok(Some(CotSensorObservation {
        sensor,
        position,
        manifest,
        unapproved_video,
        video_diagnostic,
        stale_at_ms,
    }))
}
fn read(
    reader: &Reader<&[u8]>,
    element: &BytesStart<'_>,
    event_time: &str,
    stale: &str,
) -> Result<(SensorState, Option<SensorManifest>, u64), String> {
    if xml_attr(reader, element, b"version")
        .map_err(|()| "invalid sensor version")?
        .is_some_and(|v| v != "0.6")
    {
        return Err("unsupported CoT sensor version".into());
    }
    let range = number(reader, element, b"range")?;
    let sensor = SensorState {
        sensor_id: "cot-main".into(),
        sample_at_ms: time(event_time)?,
        azimuth_deg: number(reader, element, b"azimuth")?,
        elevation_deg: number(reader, element, b"elevation")?,
        roll_deg: number(reader, element, b"roll")?,
        horizontal_fov_deg: number(reader, element, b"fov")?,
        vertical_fov_deg: number(reader, element, b"vfov")?,
        slant_range_m: range,
        image_north_deg: number(reader, element, b"north")?,
        range_kind: if range.is_some() {
            RangeKind::MeasuredTarget
        } else {
            RangeKind::Unknown
        },
    };
    sensor.validate().map_err(str::to_string)?;
    let sensor_type = xml_attr(reader, element, b"type").map_err(|()| "invalid sensor type")?;
    let model = xml_attr(reader, element, b"model").map_err(|()| "invalid sensor model")?;
    let manifest = if sensor_type.is_some() || model.is_some() {
        let manifest = SensorManifest {
            sensor_id: sensor.sensor_id.clone(),
            label: None,
            sensor_type,
            model,
            mount_id: None,
            intrinsics: None,
            video: None,
        };
        manifest.validate().map_err(str::to_string)?;
        Some(manifest)
    } else {
        None
    };
    let stale_at_ms = time(stale)?;
    r3akt_map_core::sensor_expiry::SensorExpiry {
        origin_id: "ab".repeat(16),
        sensor_id: sensor.sensor_id.clone(),
        sample_at_ms: sensor.sample_at_ms,
        expires_at_ms: stale_at_ms,
    }
    .validate()
    .map_err(str::to_string)?;
    Ok((sensor, manifest, stale_at_ms))
}
#[derive(Debug, Clone)]
pub struct SensorCotSnapshot {
    pub origin_id: String,
    pub label: String,
    pub origin_kind: String,
    pub manifest: Option<SensorManifest>,
    pub position: OriginPosition,
    pub sensor: SensorState,
    pub stale_at_ms: u64,
}
impl TakConnector {
    /// # Errors
    /// Rejects invalid sensor/position/source expiry; preserves nullable altitude as `CoT` unknown.
    pub fn build_sensor_xml(
        &self,
        snapshot: &SensorCotSnapshot,
    ) -> Result<String, TakConnectorError> {
        let invalid = |e: &str| TakConnectorError::Send(e.into());
        snapshot.position.validate().map_err(invalid)?;
        snapshot.sensor.validate().map_err(invalid)?;
        r3akt_map_core::marker::object_destination_hash(&snapshot.origin_id)
            .map_err(|e| TakConnectorError::Send(e.to_string()))?;
        r3akt_map_core::sensor_expiry::SensorExpiry {
            origin_id: snapshot.origin_id.clone(),
            sensor_id: snapshot.sensor.sensor_id.clone(),
            sample_at_ms: snapshot.sensor.sample_at_ms,
            expires_at_ms: snapshot.stale_at_ms,
        }
        .validate()
        .map_err(invalid)?;
        let date = |t: u64| {
            i64::try_from(t)
                .ok()
                .and_then(DateTime::<Utc>::from_timestamp_millis)
                .ok_or_else(|| invalid("unrepresentable CoT source time"))
        };
        let sample = date(snapshot.sensor.sample_at_ms)?;
        let stale = date(snapshot.stale_at_ms)?;
        let mut attributes = String::new();
        for (key, value) in [
            ("north", snapshot.sensor.image_north_deg),
            ("azimuth", snapshot.sensor.azimuth_deg),
            ("fov", snapshot.sensor.horizontal_fov_deg),
            ("vfov", snapshot.sensor.vertical_fov_deg),
            ("roll", snapshot.sensor.roll_deg),
            ("elevation", snapshot.sensor.elevation_deg),
            (
                "range",
                if snapshot.sensor.range_kind == RangeKind::MeasuredTarget {
                    snapshot.sensor.slant_range_m
                } else {
                    None
                },
            ),
        ] {
            if let Some(value) = value {
                write!(attributes, " {key}=\"{}\"", format_float(value))
                    .map_err(|e| invalid(&e.to_string()))?;
            }
        }
        if let Some(manifest) = &snapshot.manifest {
            manifest.validate().map_err(invalid)?;
            for (key, value) in [
                ("type", manifest.sensor_type.as_deref()),
                ("model", manifest.model.as_deref()),
            ] {
                if let Some(value) = value {
                    write!(attributes, " {key}=\"{}\"", escape_attr(value))
                        .map_err(|e| invalid(&e.to_string()))?;
                }
            }
        }
        let event_type = if snapshot.origin_kind == "uav" {
            "a-f-A"
        } else {
            EVENT_TYPE_LOCATION
        };
        // CoT uses 9999999 for unknown point attributes; no zero altitude is invented.
        let altitude = if snapshot.position.altitude_datum == AltitudeDatum::Hae {
            snapshot.position.alt_m.unwrap_or(9_999_999.)
        } else {
            9_999_999.
        };
        Ok(format!(
            "<event version=\"2.0\" uid=\"{}\" type=\"{event_type}\" how=\"m-g\" time=\"{}\" start=\"{}\" stale=\"{}\"><point lat=\"{}\" lon=\"{}\" hae=\"{}\" ce=\"{}\" le=\"9999999\"/><detail><contact callsign=\"{}\"/><sensor version=\"0.6\"{attributes}/></detail></event>",
            escape_attr(&snapshot.origin_id),
            format_cot_millis(sample),
            format_cot_millis(sample),
            format_cot_millis(stale),
            format_float(snapshot.position.lat),
            format_float(snapshot.position.lon),
            format_float(altitude),
            format_float(snapshot.position.accuracy_m.unwrap_or(9_999_999.)),
            escape_attr(&snapshot.label)
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::{
        AltitudeDatum, OriginPosition, RangeKind, SensorCotSnapshot, SensorState, TakConnector,
    };
    use crate::{TakConnectionConfig, parse_inbound_cot_event};
    #[test]
    fn sensor_cot_roundtrip_preserves_source_time_angles_and_unknown_altitude() {
        let now = 1_700_000_000_123;
        let sensor = SensorState {
            sensor_id: "cot-main".into(),
            sample_at_ms: now,
            azimuth_deg: Some(0.),
            elevation_deg: Some(-30.),
            roll_deg: Some(12.),
            horizontal_fov_deg: Some(20.),
            vertical_fov_deg: Some(10.),
            slant_range_m: Some(2000.),
            image_north_deg: Some(180.),
            range_kind: RangeKind::MeasuredTarget,
        };
        let position = OriginPosition {
            lat: 45.,
            lon: -63.,
            alt_m: None,
            altitude_datum: AltitudeDatum::Unknown,
            fix_at_ms: now,
            speed_mps: None,
            course_deg: None,
            accuracy_m: None,
        };
        let snapshot = SensorCotSnapshot {
            origin_id: "ab".repeat(16),
            label: "Camera <A>".into(),
            origin_kind: "uav".into(),
            manifest: None,
            position,
            sensor: sensor.clone(),
            stale_at_ms: now + 30_000,
        };
        let connector = TakConnector::new(TakConnectionConfig::default());
        let xml = connector.build_sensor_xml(&snapshot).unwrap();
        assert_eq!(parse_inbound_cot_event(&xml).unwrap().point.hae, 9_999_999.);
        assert_eq!(
            parse_inbound_cot_event(&xml)
                .unwrap()
                .sensor
                .unwrap()
                .sensor
                .image_north_deg,
            Some(180.)
        );
        let parsed = parse_inbound_cot_event(&xml).unwrap();
        assert_eq!(parsed.uid, snapshot.origin_id);
        let observation = parsed.sensor.unwrap();
        assert_eq!(observation.sensor, sensor);
        assert_eq!(observation.stale_at_ms, now + 30_000);
    }
    #[test]
    fn malformed_optional_sensor_preserves_valid_parent() {
        let xml = r#"<event uid="camera" time="2026-01-01T00:00:00Z" stale="2026-01-01T00:00:30Z"><point lat="45" lon="-63" hae="9999999"/><detail><sensor version="0.6" azimuth="NaN" fov="20"/></detail></event>"#;
        let parsed = parse_inbound_cot_event(xml).unwrap();
        assert_eq!(parsed.point.lat, 45.);
        assert!(parsed.sensor.is_none());
        assert!(parsed.sensor_diagnostic.is_some());
        for attribute in ["lat=\"45\"", "lon=\"-63\""] {
            let missing = xml.replace(attribute, "").replace("NaN", "0");
            assert!(parse_inbound_cot_event(&missing).unwrap().sensor.is_none());
        }
        let no_point = xml
            .replace("<point lat=\"45\" lon=\"-63\" hae=\"9999999\"/>", "")
            .replace("NaN", "0");
        let parsed = parse_inbound_cot_event(&no_point).unwrap();
        assert!(parsed.sensor.is_none());
        assert!(parsed.sensor_diagnostic.is_some());
    }
    #[test]
    fn cot_metadata_and_nullable_point_are_checked_without_false_range_claims() {
        let xml = r#"<event uid="camera" time="2026-01-01T00:00:00Z" stale="2026-01-01T00:00:30Z"><point lat="45" lon="-63"/><detail><sensor version="0.6" azimuth="0" fov="20" range="2000" type="EO" model="Camera &amp; lens"/></detail></event>"#;
        let observation = parse_inbound_cot_event(xml).unwrap().sensor.unwrap();
        assert_eq!(observation.position.alt_m, None);
        assert_eq!(observation.position.altitude_datum, AltitudeDatum::Unknown);
        assert_eq!(observation.sensor.range_kind, RangeKind::MeasuredTarget);
        assert_eq!(
            observation.manifest.as_ref().unwrap().model.as_deref(),
            Some("Camera & lens")
        );
        let mut snapshot = SensorCotSnapshot {
            origin_id: "ab".repeat(16),
            label: "Camera".into(),
            origin_kind: "uav".into(),
            position: observation.position,
            sensor: observation.sensor,
            manifest: observation.manifest,
            stale_at_ms: observation.stale_at_ms,
        };
        let connector = TakConnector::new(TakConnectionConfig::default());
        let output = connector.build_sensor_xml(&snapshot).unwrap();
        assert!(output.contains("type=\"a-f-A\""));
        assert_eq!(
            parse_inbound_cot_event(&output)
                .unwrap()
                .sensor
                .unwrap()
                .manifest,
            snapshot.manifest
        );
        snapshot.sensor.range_kind = RangeKind::DisplayLimit;
        assert!(
            !connector
                .build_sensor_xml(&snapshot)
                .unwrap()
                .contains(" range=")
        );
    }
}
