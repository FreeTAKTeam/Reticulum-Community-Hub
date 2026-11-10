//! Flat-ground camera-ray estimates. Inputs and error bounds must come from
//! calibrated, synchronized sources; this module does not inspect terrain.

use thiserror::Error;

use crate::{
    Position,
    sensor::{AltitudeDatum, OriginPosition, POSITION_SKEW_MS, SensorState, valid_time},
    sensor_geometry,
};

/// A horizontal plane and a bound on its height error over the target area.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum GroundModel {
    /// Ground height and origin altitude use the same R3S datum.
    Flat {
        height_m: f64,
        datum: AltitudeDatum,
        height_error_m: f64,
    },
    /// Both heights are relative to the same take-off point; this does not
    /// change or relabel the origin's R3S altitude datum.
    TakeoffRelative {
        origin_altitude_m: f64,
        height_m: f64,
        height_error_m: f64,
    },
}

/// Image offset in half-image widths/heights: right and down are positive.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ImageOffset {
    pub x: f64,
    pub y: f64,
    /// Source capture time of the selected image frame, in UTC milliseconds.
    pub frame_at_ms: u64,
}

/// Absolute error bounds, not standard deviations or confidence levels.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Accuracy {
    pub altitude_m: f64,
    pub azimuth_deg: f64,
    pub elevation_deg: f64,
    /// Required for an image offset; rotation about the camera's optical axis.
    pub roll_deg: Option<f64>,
    /// Required for an image offset; bounds pixel, lens and frame/pose timing error.
    pub pixel_deg: Option<f64>,
    /// Maximum 3D platform speed between the position fix and selected ray time.
    pub max_speed_mps: f64,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Limits {
    pub now_ms: u64,
    pub max_age_ms: u64,
    pub min_depression_deg: f64,
    pub max_slant_range_m: f64,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct GroundPoint {
    pub position: Position,
    pub ground_range_m: f64,
    pub slant_range_m: f64,
    /// Conditional horizontal bound under the supplied flat-ground/error model.
    pub uncertainty_radius_m: f64,
    pub ground: GroundModel,
}

#[derive(Debug, Error, Clone, Copy, PartialEq, Eq)]
pub enum GroundPointError {
    #[error("invalid origin position: {0}")]
    InvalidOrigin(&'static str),
    #[error("invalid sensor state: {0}")]
    InvalidSensor(&'static str),
    #[error("origin altitude or datum is unknown")]
    UnknownAltitude,
    #[error("origin and ground altitude datums differ")]
    DatumMismatch,
    #[error("origin horizontal accuracy is required")]
    MissingAccuracy,
    #[error("absolute camera azimuth and elevation are required")]
    MissingPointing,
    #[error("image offset requires camera roll, field of view and calibration bounds")]
    MissingCalibration,
    #[error("invalid ground, accuracy, image offset or limits")]
    InvalidInput,
    #[error("position, camera pose or image is stale or in the future")]
    Stale,
    #[error("position, camera pose and image are not synchronized")]
    Unsynchronized,
    #[error("position uncertainty reaches a pole where true north is undefined")]
    PolarUncertainty,
    #[error("the altitude uncertainty reaches or crosses the ground")]
    BelowGround,
    #[error("the camera ray or its uncertainty reaches the horizon limit")]
    Horizon,
    #[error("the camera ray or its uncertainty exceeds the range limit")]
    RangeExceeded,
}

fn nonnegative(value: f64) -> bool {
    value.is_finite() && value >= 0.0
}

fn validate_inputs(
    origin: &OriginPosition,
    sensor: &SensorState,
    pixel: Option<ImageOffset>,
    accuracy: Accuracy,
    limits: Limits,
) -> Result<(f64, f64), GroundPointError> {
    origin.validate().map_err(GroundPointError::InvalidOrigin)?;
    sensor.validate().map_err(GroundPointError::InvalidSensor)?;
    let position_error = origin.accuracy_m.ok_or(GroundPointError::MissingAccuracy)?;
    if valid_time(limits.now_ms).is_err()
        || !limits.min_depression_deg.is_finite()
        || !(0.0..=90.0).contains(&limits.min_depression_deg)
        || limits.min_depression_deg == 0.0
        || !limits.max_slant_range_m.is_finite()
        || limits.max_slant_range_m <= 0.0
        || ![
            accuracy.altitude_m,
            accuracy.azimuth_deg,
            accuracy.elevation_deg,
            accuracy.max_speed_mps,
        ]
        .into_iter()
        .all(nonnegative)
        || accuracy.roll_deg.is_some_and(|value| !nonnegative(value))
        || accuracy.pixel_deg.is_some_and(|value| !nonnegative(value))
    {
        return Err(GroundPointError::InvalidInput);
    }
    let image_time = pixel.map_or(sensor.sample_at_ms, |pixel| pixel.frame_at_ms);
    if valid_time(image_time).is_err() {
        return Err(GroundPointError::InvalidInput);
    }
    if [origin.fix_at_ms, sensor.sample_at_ms, image_time]
        .into_iter()
        .any(|time| time > limits.now_ms || limits.now_ms - time > limits.max_age_ms)
    {
        return Err(GroundPointError::Stale);
    }
    let skew_ms = origin.fix_at_ms.abs_diff(image_time);
    if skew_ms > POSITION_SKEW_MS
        || origin.fix_at_ms.abs_diff(sensor.sample_at_ms) > POSITION_SKEW_MS
        || sensor.sample_at_ms.abs_diff(image_time) > POSITION_SKEW_MS
    {
        return Err(GroundPointError::Unsynchronized);
    }
    if skew_ms > 0
        && origin
            .speed_mps
            .is_some_and(|speed| speed > accuracy.max_speed_mps)
    {
        return Err(GroundPointError::InvalidInput);
    }
    let motion_error =
        accuracy.max_speed_mps * std::time::Duration::from_millis(skew_ms).as_secs_f64();
    if !motion_error.is_finite() {
        return Err(GroundPointError::InvalidInput);
    }
    Ok((position_error, motion_error))
}

fn height_above_ground(
    origin: &OriginPosition,
    ground: GroundModel,
    accuracy: Accuracy,
    motion_error: f64,
) -> Result<(f64, f64), GroundPointError> {
    let (origin_height, ground_height, ground_error) = match ground {
        GroundModel::Flat {
            height_m,
            datum,
            height_error_m,
        } => {
            let altitude = origin.alt_m.ok_or(GroundPointError::UnknownAltitude)?;
            if datum == AltitudeDatum::Unknown || origin.altitude_datum == AltitudeDatum::Unknown {
                return Err(GroundPointError::UnknownAltitude);
            }
            if datum != origin.altitude_datum {
                return Err(GroundPointError::DatumMismatch);
            }
            if datum == AltitudeDatum::Agl && height_m != 0.0 {
                return Err(GroundPointError::InvalidInput);
            }
            (altitude, height_m, height_error_m)
        }
        GroundModel::TakeoffRelative {
            origin_altitude_m,
            height_m,
            height_error_m,
        } => (origin_altitude_m, height_m, height_error_m),
    };
    if !origin_height.is_finite() || !ground_height.is_finite() || !nonnegative(ground_error) {
        return Err(GroundPointError::InvalidInput);
    }
    let height = origin_height - ground_height;
    let height_error = accuracy.altitude_m + ground_error + motion_error;
    if !height.is_finite() || !height_error.is_finite() {
        return Err(GroundPointError::InvalidInput);
    }
    if height <= height_error {
        return Err(GroundPointError::BelowGround);
    }
    Ok((height, height_error))
}

fn camera_ray(
    sensor: &SensorState,
    pixel: Option<ImageOffset>,
    accuracy: Accuracy,
) -> Result<([f64; 3], f64), GroundPointError> {
    let azimuth = sensor
        .azimuth_deg
        .ok_or(GroundPointError::MissingPointing)?
        .to_radians();
    let depression = -sensor
        .elevation_deg
        .ok_or(GroundPointError::MissingPointing)?
        .to_radians();
    let (sin_az, cos_az) = azimuth.sin_cos();
    let (sin_dep, cos_dep) = depression.sin_cos();
    let mut angular_error = accuracy.azimuth_deg + accuracy.elevation_deg;
    let (right, down) = if let Some(pixel) = pixel {
        if !pixel.x.is_finite()
            || !pixel.y.is_finite()
            || pixel.x.abs() > 1.0
            || pixel.y.abs() > 1.0
        {
            return Err(GroundPointError::InvalidInput);
        }
        let roll = sensor
            .roll_deg
            .ok_or(GroundPointError::MissingCalibration)?
            .to_radians();
        let horizontal = sensor
            .horizontal_fov_deg
            .ok_or(GroundPointError::MissingCalibration)?;
        let vertical = sensor
            .vertical_fov_deg
            .ok_or(GroundPointError::MissingCalibration)?;
        if !(0.0..180.0).contains(&horizontal)
            || horizontal == 0.0
            || !(0.0..180.0).contains(&vertical)
            || vertical == 0.0
        {
            return Err(GroundPointError::MissingCalibration);
        }
        angular_error += accuracy
            .roll_deg
            .ok_or(GroundPointError::MissingCalibration)?
            + accuracy
                .pixel_deg
                .ok_or(GroundPointError::MissingCalibration)?;
        let x = pixel.x * (horizontal.to_radians() / 2.0).tan();
        let y = pixel.y * (vertical.to_radians() / 2.0).tan();
        let (sin_roll, cos_roll) = roll.sin_cos();
        (x * cos_roll - y * sin_roll, x * sin_roll + y * cos_roll)
    } else {
        (0.0, 0.0)
    };
    let north = cos_dep * cos_az - right * sin_az - down * sin_dep * cos_az;
    let east = cos_dep * sin_az + right * cos_az - down * sin_dep * sin_az;
    let up = -sin_dep - down * cos_dep;
    if !angular_error.is_finite() {
        return Err(GroundPointError::InvalidInput);
    }
    Ok(([north, east, up], angular_error.to_radians()))
}

/// Projects the camera ray onto the supplied flat ground.
///
/// `azimuth_deg` is absolute clockwise from true north; sensor elevation is
/// positive above the horizon. For image offsets, positive roll turns image
/// right toward image down. FOV describes a centered, undistorted pinhole
/// image; `pixel_deg` must bound calibration, distortion, selection and any
/// camera motion between the frame and pose timestamps.
///
/// The uncertainty radius is conditional on every supplied accuracy being an
/// absolute bound and on the ground plane being valid across the target area.
/// It is not CEP or a statistical confidence level. Real terrain, Earth
/// curvature, unbounded calibration errors and unmodeled motion are excluded.
/// Sensor display-limit ranges are not used as measured target distances.
///
/// # Errors
/// Rejects missing or invalid inputs, stale or unsynchronized samples, a ray
/// whose uncertainty reaches the horizon, or a range outside the supplied limit.
pub fn ground_point(
    origin: &OriginPosition,
    sensor: &SensorState,
    pixel: Option<ImageOffset>,
    ground: GroundModel,
    accuracy: Accuracy,
    limits: Limits,
) -> Result<GroundPoint, GroundPointError> {
    let (position_error, motion_error) = validate_inputs(origin, sensor, pixel, accuracy, limits)?;
    let (height, height_error) = height_above_ground(origin, ground, accuracy, motion_error)?;
    let ([north, east, up], ray_error) = camera_ray(sensor, pixel, accuracy)?;

    // True north can rotate substantially across an uncertain fix near a pole.
    let latitude = origin.lat.to_radians();
    let position_arc = (position_error + motion_error) / sensor_geometry::EARTH_RADIUS_M;
    if !position_arc.is_finite() || position_arc >= std::f64::consts::FRAC_PI_2 - latitude.abs() {
        return Err(GroundPointError::PolarUncertainty);
    }
    let frame_error = position_arc
        + (position_arc.sin() / latitude.cos())
            .clamp(-1.0, 1.0)
            .asin();
    let angular_error = ray_error + frame_error;
    let ray_depression = (-up).atan2(north.hypot(east));
    let min_depression = ray_depression - angular_error;
    if !min_depression.is_finite()
        || min_depression <= 0.0
        || min_depression < limits.min_depression_deg.to_radians()
    {
        return Err(GroundPointError::Horizon);
    }

    let min_sin = min_depression.sin();
    let worst_slant = (height + height_error) / min_sin;
    if !worst_slant.is_finite() || worst_slant > limits.max_slant_range_m {
        return Err(GroundPointError::RangeExceeded);
    }
    let ground_range = height * north.hypot(east) / -up;
    let slant_range = height / ray_depression.sin();
    // The perturbed ray lies within this cone; its plane-intersection error
    // is bounded by the cone angle and the least possible depression.
    let radius = position_error
        + motion_error
        + height_error / min_depression.tan()
        + height * angular_error.sin() / (min_sin * ray_depression.sin());
    if !ground_range.is_finite() || !slant_range.is_finite() || !radius.is_finite() || radius < 0.0
    {
        return Err(GroundPointError::InvalidInput);
    }
    let origin = Position::new(origin.lat, origin.lon)
        .map_err(|_| GroundPointError::InvalidOrigin("invalid coordinates"))?;
    let bearing = east.atan2(north).to_degrees();
    let position = sensor_geometry::destination(origin, bearing, ground_range)
        .map_err(|_| GroundPointError::RangeExceeded)?;
    Ok(GroundPoint {
        position,
        ground_range_m: ground_range,
        slant_range_m: slant_range,
        uncertainty_radius_m: radius,
        ground,
    })
}
