//! Canonical, optional R3S/1 sensor components. SID 128 remains provisional.

use serde::{Deserialize, Serialize};

pub const MAX_SENSORS: usize = 4;
pub const MAX_EXTENSION_BYTES: usize = 512;
pub const MAX_TIME_MS: u64 = 253_402_300_800_000;
pub const FUTURE_SKEW_MS: u64 = 30_000;
pub const POSITION_SKEW_MS: u64 = 2_000;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "kebab-case")]
pub enum RangeKind {
    #[default]
    Unknown,
    MeasuredTarget,
    DisplayLimit,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "lowercase")]
pub enum AltitudeDatum {
    Hae,
    Msl,
    Agl,
    #[default]
    Unknown,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct SensorState {
    pub sensor_id: String,
    pub sample_at_ms: u64,
    pub azimuth_deg: Option<f64>,
    pub elevation_deg: Option<f64>,
    pub roll_deg: Option<f64>,
    pub horizontal_fov_deg: Option<f64>,
    pub vertical_fov_deg: Option<f64>,
    pub slant_range_m: Option<f64>,
    pub image_north_deg: Option<f64>,
    #[serde(default)]
    pub range_kind: RangeKind,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct OriginPosition {
    pub lat: f64,
    pub lon: f64,
    pub alt_m: Option<f64>,
    #[serde(default)]
    pub altitude_datum: AltitudeDatum,
    pub fix_at_ms: u64,
    pub speed_mps: Option<f64>,
    pub course_deg: Option<f64>,
    pub accuracy_m: Option<f64>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct VideoDescriptor {
    pub protocol: String,
    pub endpoint_ref: String,
    pub sensor_id: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct CameraIntrinsics {
    pub focal_x_px: f64,
    pub focal_y_px: f64,
    pub center_x_px: f64,
    pub center_y_px: f64,
    pub width_px: u32,
    pub height_px: u32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct SensorManifest {
    pub sensor_id: String,
    pub label: Option<String>,
    pub sensor_type: Option<String>,
    pub model: Option<String>,
    pub mount_id: Option<String>,
    pub intrinsics: Option<CameraIntrinsics>,
    pub video: Option<VideoDescriptor>,
}

/// # Errors
/// Rejects zero and timestamps outside the supported UTC range.
pub fn valid_time(value: u64) -> Result<(), &'static str> {
    if value == 0 || value >= MAX_TIME_MS {
        return Err("invalid sensor source time");
    }
    Ok(())
}

/// # Errors
/// Rejects invalid timestamps and excessive future clock skew.
pub fn source_time(value: u64, now_ms: u64) -> Result<(), &'static str> {
    valid_time(value)?;
    if value > now_ms.saturating_add(FUTURE_SKEW_MS) {
        return Err("sensor source clock is in the future");
    }
    Ok(())
}

/// # Errors
/// Rejects empty, oversized or non-printable sensor identifiers.
pub fn sensor_id(value: &str) -> Result<(), &'static str> {
    if value.is_empty() || value.len() > 32 || !value.bytes().all(|b| (32..=126).contains(&b)) {
        return Err("sensor ID must be 1–32 printable ASCII bytes");
    }
    Ok(())
}

fn angle(value: Option<f64>, min: f64, max: f64, upper_closed: bool) -> bool {
    value.is_none_or(|v| {
        v.is_finite() && v >= min && (if upper_closed { v <= max } else { v < max })
    })
}

impl SensorState {
    /// # Errors
    /// Rejects readings outside the canonical sensor or metadata bounds.
    pub fn validate(&self) -> Result<(), &'static str> {
        sensor_id(&self.sensor_id)?;
        valid_time(self.sample_at_ms)?;
        if !angle(self.azimuth_deg, 0.0, 360.0, false)
            || !angle(self.elevation_deg, -90.0, 90.0, true)
            || !angle(self.roll_deg, -180.0, 180.0, true)
            || self.roll_deg == Some(-180.0)
            || !angle(self.horizontal_fov_deg, 0.0, 360.0, false)
            || !angle(self.vertical_fov_deg, 0.0, 360.0, false)
            || !angle(self.image_north_deg, 0.0, 360.0, false)
        {
            return Err("sensor angle outside its range");
        }
        if self
            .slant_range_m
            .is_some_and(|v| !v.is_finite() || !(0.0..=42_949_672.95).contains(&v))
            || (self.range_kind == RangeKind::Unknown) != self.slant_range_m.is_none()
        {
            return Err("invalid sensor range or range kind");
        }
        Ok(())
    }
}

impl OriginPosition {
    /// # Errors
    /// Rejects readings outside the canonical sensor or metadata bounds.
    pub fn validate(&self) -> Result<(), &'static str> {
        crate::Position::new(self.lat, self.lon).map_err(|_| "invalid origin coordinates")?;
        valid_time(self.fix_at_ms)?;
        if [self.alt_m, self.speed_mps, self.course_deg, self.accuracy_m]
            .into_iter()
            .flatten()
            .any(|v| !v.is_finite())
            || self.speed_mps.is_some_and(|v| v < 0.0)
            || self.accuracy_m.is_some_and(|v| v < 0.0)
            || !angle(self.course_deg, 0.0, 360.0, false)
            || self.alt_m.is_none() && self.altitude_datum != AltitudeDatum::Unknown
        {
            return Err("invalid origin fix");
        }
        Ok(())
    }
}

impl SensorManifest {
    /// # Errors
    /// Rejects readings outside the canonical sensor or metadata bounds.
    pub fn validate(&self) -> Result<(), &'static str> {
        sensor_id(&self.sensor_id)?;
        for text in [&self.label, &self.sensor_type, &self.model, &self.mount_id]
            .into_iter()
            .flatten()
        {
            if text.len() > 64 || text.chars().any(char::is_control) {
                return Err("sensor metadata exceeds its text limit");
            }
        }
        if let Some(intrinsics) = &self.intrinsics
            && ([
                intrinsics.focal_x_px,
                intrinsics.focal_y_px,
                intrinsics.center_x_px,
                intrinsics.center_y_px,
            ]
            .into_iter()
            .any(|v| !v.is_finite() || v < 0.0)
                || intrinsics.focal_x_px == 0.0
                || intrinsics.focal_y_px == 0.0
                || !(1..=16_384).contains(&intrinsics.width_px)
                || !(1..=16_384).contains(&intrinsics.height_px))
        {
            return Err("invalid camera intrinsics");
        }
        if let Some(video) = &self.video {
            // Endpoint references are deliberately restricted; approval still belongs to the host.
            let prefix = format!("{}://", video.protocol);
            let authority = video
                .endpoint_ref
                .strip_prefix(&prefix)
                .and_then(|rest| rest.split('/').next());
            if video.sensor_id != self.sensor_id
                || !matches!(video.protocol.as_str(), "rtsp" | "rtmp" | "http" | "https")
                || authority.is_none_or(str::is_empty)
                || video.endpoint_ref.len() > 512
                || video
                    .endpoint_ref
                    .bytes()
                    .any(|c| c <= 32 || c >= 127 || b"@?#%\\".contains(&c))
            {
                return Err("video requires a non-secret endpoint reference");
            }
        }
        Ok(())
    }
}
