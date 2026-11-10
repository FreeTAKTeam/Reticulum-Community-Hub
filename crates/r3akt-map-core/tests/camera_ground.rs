use r3akt_map_core::{
    Position,
    camera_ground::{Accuracy, GroundModel, GroundPointError, ImageOffset, Limits, ground_point},
    sensor::{AltitudeDatum, OriginPosition, RangeKind, SensorState},
    sensor_geometry::destination,
};

const NOW: u64 = 1_700_000_000_000;

fn image_offset(x: f64, y: f64) -> ImageOffset {
    ImageOffset {
        x,
        y,
        frame_at_ms: NOW,
    }
}

fn origin() -> OriginPosition {
    OriginPosition {
        lat: 0.0,
        lon: 0.0,
        alt_m: Some(100.0),
        altitude_datum: AltitudeDatum::Hae,
        fix_at_ms: NOW,
        speed_mps: Some(10.0),
        course_deg: Some(0.0),
        accuracy_m: Some(0.0),
    }
}

fn sensor() -> SensorState {
    SensorState {
        sensor_id: "camera".into(),
        sample_at_ms: NOW,
        azimuth_deg: Some(0.0),
        elevation_deg: Some(-45.0),
        roll_deg: Some(0.0),
        horizontal_fov_deg: Some(90.0),
        vertical_fov_deg: Some(90.0),
        slant_range_m: None,
        image_north_deg: None,
        range_kind: RangeKind::Unknown,
    }
}

fn ground() -> GroundModel {
    GroundModel::Flat {
        height_m: 0.0,
        datum: AltitudeDatum::Hae,
        height_error_m: 0.0,
    }
}

fn accuracy() -> Accuracy {
    Accuracy {
        altitude_m: 0.0,
        azimuth_deg: 0.0,
        elevation_deg: 0.0,
        roll_deg: Some(0.0),
        pixel_deg: Some(0.0),
        max_speed_mps: 0.0,
    }
}

fn limits() -> Limits {
    Limits {
        now_ms: NOW,
        max_age_ms: 10_000,
        min_depression_deg: 1.0,
        max_slant_range_m: 10_000.0,
    }
}

#[test]
fn nadir_and_forty_five_degrees_use_the_camera_azimuth() {
    let mut camera = sensor();
    camera.elevation_deg = Some(-90.0);
    let nadir = ground_point(&origin(), &camera, None, ground(), accuracy(), limits()).unwrap();
    assert!(nadir.ground_range_m < 1e-10);
    assert!((nadir.slant_range_m - 100.0).abs() < 1e-10);
    assert_eq!(nadir.ground, ground());

    camera.elevation_deg = Some(-45.0);
    camera.azimuth_deg = Some(90.0); // aircraft course remains north
    let east = ground_point(&origin(), &camera, None, ground(), accuracy(), limits()).unwrap();
    assert!((east.ground_range_m - 100.0).abs() < 1e-10);
    assert!((east.slant_range_m - 100.0_f64 * 2.0_f64.sqrt()).abs() < 1e-10);
    assert!(east.position.lat().abs() < 1e-9);
    assert!(east.position.lon() > 0.0);
}

#[test]
fn center_ray_needs_no_image_calibration_and_ignores_display_range() {
    let mut camera = sensor();
    camera.roll_deg = None;
    camera.horizontal_fov_deg = None;
    camera.vertical_fov_deg = None;
    camera.slant_range_m = Some(10.0);
    camera.range_kind = RangeKind::DisplayLimit;
    let mut bounds = accuracy();
    bounds.roll_deg = None;
    bounds.pixel_deg = None;
    let point = ground_point(&origin(), &camera, None, ground(), bounds, limits()).unwrap();
    assert!((point.ground_range_m - 100.0).abs() < 1e-10);
    camera.azimuth_deg = None;
    assert_eq!(
        ground_point(&origin(), &camera, None, ground(), bounds, limits()),
        Err(GroundPointError::MissingPointing)
    );
}

#[test]
fn off_centre_pixels_use_pinhole_geometry_and_camera_roll() {
    let mut camera = sensor();
    camera.elevation_deg = Some(-90.0);
    let right = image_offset(1.0, 0.0);
    let east = ground_point(
        &origin(),
        &camera,
        Some(right),
        ground(),
        accuracy(),
        limits(),
    )
    .unwrap();
    assert!((east.ground_range_m - 100.0).abs() < 1e-10);
    assert!(east.position.lon() > 0.0 && east.position.lat().abs() < 1e-9);

    camera.roll_deg = Some(90.0);
    let south = ground_point(
        &origin(),
        &camera,
        Some(right),
        ground(),
        accuracy(),
        limits(),
    )
    .unwrap();
    assert!(south.position.lat() < 0.0 && south.position.lon().abs() < 1e-9);

    camera.roll_deg = Some(0.0);
    camera.elevation_deg = Some(-45.0);
    let diagonal = ground_point(
        &origin(),
        &camera,
        Some(right),
        ground(),
        accuracy(),
        limits(),
    )
    .unwrap();
    let expected = destination(
        Position::new(0.0, 0.0).unwrap(),
        2.0_f64.sqrt().atan2(1.0).to_degrees(),
        100.0 * 3.0_f64.sqrt(),
    )
    .unwrap();
    assert!(separation_m(diagonal.position, expected) < 1e-6);
    let down = image_offset(0.0, 1.0);
    let nadir = ground_point(
        &origin(),
        &camera,
        Some(down),
        ground(),
        accuracy(),
        limits(),
    )
    .unwrap();
    assert!(nadir.ground_range_m < 1e-10);
}

#[test]
fn flat_ground_requires_known_matching_altitude_and_uncertainty() {
    let mut p = origin();
    p.altitude_datum = AltitudeDatum::Unknown;
    assert_eq!(
        ground_point(&p, &sensor(), None, ground(), accuracy(), limits()),
        Err(GroundPointError::UnknownAltitude)
    );
    p.altitude_datum = AltitudeDatum::Msl;
    assert_eq!(
        ground_point(&p, &sensor(), None, ground(), accuracy(), limits()),
        Err(GroundPointError::DatumMismatch)
    );
    p.alt_m = None;
    p.altitude_datum = AltitudeDatum::Unknown;
    assert_eq!(
        ground_point(&p, &sensor(), None, ground(), accuracy(), limits()),
        Err(GroundPointError::UnknownAltitude)
    );
    p.accuracy_m = None;
    assert_eq!(
        ground_point(&p, &sensor(), None, ground(), accuracy(), limits()),
        Err(GroundPointError::MissingAccuracy)
    );
}

#[test]
fn takeoff_reference_is_explicit_and_does_not_relabel_r3s_altitude() {
    let mut p = origin();
    p.alt_m = None;
    p.altitude_datum = AltitudeDatum::Unknown;
    let ground = GroundModel::TakeoffRelative {
        origin_altitude_m: 100.0,
        height_m: 0.0,
        height_error_m: 0.0,
    };
    let point = ground_point(&p, &sensor(), None, ground, accuracy(), limits()).unwrap();
    assert!((point.ground_range_m - 100.0).abs() < 1e-10);
    assert_eq!(point.ground, ground);
}

#[test]
fn unsafe_rays_missing_calibration_and_unsynchronized_samples_are_refused() {
    let mut camera = sensor();
    camera.elevation_deg = Some(0.0);
    assert_eq!(
        ground_point(&origin(), &camera, None, ground(), accuracy(), limits()),
        Err(GroundPointError::Horizon)
    );
    camera.elevation_deg = Some(-1.5);
    let mut uncertain = accuracy();
    uncertain.elevation_deg = 1.0;
    assert_eq!(
        ground_point(&origin(), &camera, None, ground(), uncertain, limits()),
        Err(GroundPointError::Horizon)
    );
    camera.elevation_deg = Some(-45.0);
    let mut short = limits();
    short.max_slant_range_m = 100.0;
    assert_eq!(
        ground_point(&origin(), &camera, None, ground(), accuracy(), short),
        Err(GroundPointError::RangeExceeded)
    );
    camera.roll_deg = None;
    assert_eq!(
        ground_point(
            &origin(),
            &camera,
            Some(image_offset(0.5, 0.0)),
            ground(),
            accuracy(),
            limits()
        ),
        Err(GroundPointError::MissingCalibration)
    );
    camera.roll_deg = Some(0.0);
    camera.sample_at_ms = NOW - 2_001;
    assert_eq!(
        ground_point(&origin(), &camera, None, ground(), accuracy(), limits()),
        Err(GroundPointError::Unsynchronized)
    );
    camera.sample_at_ms = NOW + 1;
    assert_eq!(
        ground_point(&origin(), &camera, None, ground(), accuracy(), limits()),
        Err(GroundPointError::Stale)
    );
}

#[test]
fn uncertainties_expand_the_radius_and_can_refuse_an_invalid_height() {
    let mut p = origin();
    p.accuracy_m = Some(3.0);
    p.fix_at_ms = NOW - 1_000;
    let mut a = accuracy();
    a.altitude_m = 2.0;
    a.azimuth_deg = 1.0;
    a.elevation_deg = 1.0;
    a.max_speed_mps = 10.0;
    let result = ground_point(&p, &sensor(), None, ground(), a, limits()).unwrap();
    assert!(result.uncertainty_radius_m > 13.0);
    a.altitude_m = 100.0;
    assert_eq!(
        ground_point(&p, &sensor(), None, ground(), a, limits()),
        Err(GroundPointError::BelowGround)
    );
}

#[test]
fn shared_destination_and_ground_point_wrap_the_antimeridian() {
    let start = Position::new(0.0, 179.999).unwrap();
    let end = destination(start, 90.0, 500.0).unwrap();
    assert!(end.lon() < -179.99);
    assert!(destination(start, f64::NAN, 1.0).is_err());
    assert!(destination(start, 0.0, -1.0).is_err());
    let mut p = origin();
    p.lon = 179.999;
    p.alt_m = Some(1_000.0);
    let mut camera = sensor();
    camera.azimuth_deg = Some(90.0);
    let point = ground_point(&p, &camera, None, ground(), accuracy(), limits()).unwrap();
    assert!(point.position.lon() < -179.99);
}

#[test]
fn invalid_or_unbounded_inputs_do_not_produce_a_point() {
    let mut camera = sensor();
    let pixel = Some(image_offset(0.5, 0.1));
    let mut a = accuracy();
    a.pixel_deg = None;
    assert_eq!(
        ground_point(&origin(), &camera, pixel, ground(), a, limits()),
        Err(GroundPointError::MissingCalibration)
    );
    a.pixel_deg = Some(0.0);
    camera.horizontal_fov_deg = Some(180.0);
    assert_eq!(
        ground_point(&origin(), &camera, pixel, ground(), a, limits()),
        Err(GroundPointError::MissingCalibration)
    );
    camera.horizontal_fov_deg = Some(90.0);
    assert_eq!(
        ground_point(
            &origin(),
            &camera,
            Some(image_offset(f64::NAN, 0.0)),
            ground(),
            a,
            limits(),
        ),
        Err(GroundPointError::InvalidInput)
    );
    a.azimuth_deg = -1.0;
    assert_eq!(
        ground_point(&origin(), &camera, None, ground(), a, limits()),
        Err(GroundPointError::InvalidInput)
    );
    let mut p = origin();
    p.lat = 89.999_99;
    p.accuracy_m = Some(3.0);
    assert_eq!(
        ground_point(&p, &camera, None, ground(), accuracy(), limits()),
        Err(GroundPointError::PolarUncertainty)
    );
    p = origin();
    p.altitude_datum = AltitudeDatum::Agl;
    let raised_agl = GroundModel::Flat {
        height_m: 10.0,
        datum: AltitudeDatum::Agl,
        height_error_m: 0.0,
    };
    assert_eq!(
        ground_point(&p, &camera, None, raised_agl, accuracy(), limits()),
        Err(GroundPointError::InvalidInput)
    );
}

#[test]
fn image_frame_time_is_checked_and_motion_during_skew_expands_uncertainty() {
    let mut pixel = image_offset(0.1, 0.0);
    pixel.frame_at_ms = NOW - 2_001;
    assert_eq!(
        ground_point(
            &origin(),
            &sensor(),
            Some(pixel),
            ground(),
            accuracy(),
            limits()
        ),
        Err(GroundPointError::Unsynchronized)
    );
    pixel.frame_at_ms = NOW + 1;
    assert_eq!(
        ground_point(
            &origin(),
            &sensor(),
            Some(pixel),
            ground(),
            accuracy(),
            limits()
        ),
        Err(GroundPointError::Stale)
    );
    pixel.frame_at_ms = NOW - 1_000;
    assert_eq!(
        ground_point(
            &origin(),
            &sensor(),
            Some(pixel),
            ground(),
            accuracy(),
            limits()
        ),
        Err(GroundPointError::InvalidInput)
    );
    let mut bounds = accuracy();
    bounds.max_speed_mps = 10.0;
    let point = ground_point(
        &origin(),
        &sensor(),
        Some(pixel),
        ground(),
        bounds,
        limits(),
    )
    .unwrap();
    assert!(point.uncertainty_radius_m > 10.0);
}

fn separation_m(a: Position, b: Position) -> f64 {
    let lat1 = a.lat().to_radians();
    let lat2 = b.lat().to_radians();
    let dlat = lat2 - lat1;
    let dlon = (b.lon() - a.lon()).to_radians();
    let haversine =
        (dlat / 2.0).sin().powi(2) + lat1.cos() * lat2.cos() * (dlon / 2.0).sin().powi(2);
    2.0 * 6_371_008.8 * haversine.clamp(0.0, 1.0).sqrt().asin()
}

#[test]
fn position_uncertainty_covers_moving_the_fix_at_high_latitudes() {
    for latitude in [0.0, 45.0, 85.0, 89.99, 89.999] {
        let mut p = origin();
        p.lat = latitude;
        p.lon = 179.999;
        p.accuracy_m = Some(20.0);
        for azimuth in [0.0, 90.0, 180.0, 270.0] {
            let mut camera = sensor();
            camera.azimuth_deg = Some(azimuth);
            let estimate = ground_point(&p, &camera, None, ground(), accuracy(), limits()).unwrap();
            for bearing in [0.0, 45.0, 90.0, 180.0, 270.0] {
                let shifted =
                    destination(Position::new(p.lat, p.lon).unwrap(), bearing, 20.0).unwrap();
                let mut actual = p.clone();
                actual.lat = shifted.lat();
                actual.lon = shifted.lon();
                actual.accuracy_m = Some(0.0);
                let actual =
                    ground_point(&actual, &camera, None, ground(), accuracy(), limits()).unwrap();
                assert!(
                    separation_m(estimate.position, actual.position)
                        <= estimate.uncertainty_radius_m + 0.02,
                    "latitude {latitude}, camera {azimuth}, shift {bearing}: {estimate:?} versus {actual:?}"
                );
            }
        }
    }
}

#[test]
fn limits_cover_the_uncertainty_envelope_and_off_axis_horizon() {
    let mut a = accuracy();
    a.altitude_m = 10.0;
    a.elevation_deg = 3.0;
    let mut short = limits();
    short.max_slant_range_m = 150.0;
    assert_eq!(
        ground_point(&origin(), &sensor(), None, ground(), a, short),
        Err(GroundPointError::RangeExceeded)
    );
    let mut camera = sensor();
    camera.elevation_deg = Some(-5.0);
    assert_eq!(
        ground_point(
            &origin(),
            &camera,
            Some(image_offset(0.0, -1.0)),
            ground(),
            accuracy(),
            limits(),
        ),
        Err(GroundPointError::Horizon)
    );
}

#[test]
fn reported_radius_covers_combined_altitude_and_off_axis_attitude_errors() {
    let mut camera = sensor();
    camera.azimuth_deg = Some(35.0);
    camera.elevation_deg = Some(-40.0);
    camera.roll_deg = Some(10.0);
    camera.horizontal_fov_deg = Some(50.0);
    camera.vertical_fov_deg = Some(30.0);
    let pixel = Some(image_offset(0.6, -0.4));
    let ground = GroundModel::Flat {
        height_m: 0.0,
        datum: AltitudeDatum::Hae,
        height_error_m: 3.0,
    };
    let mut bounds = accuracy();
    bounds.altitude_m = 4.0;
    bounds.azimuth_deg = 1.0;
    bounds.elevation_deg = 1.0;
    bounds.roll_deg = Some(2.0);
    let estimate = ground_point(&origin(), &camera, pixel, ground, bounds, limits()).unwrap();

    for azimuth_error in [-1.0, 0.0, 1.0] {
        for elevation_error in [-1.0, 0.0, 1.0] {
            for roll_error in [-2.0, 0.0, 2.0] {
                for height_error in [-7.0, 7.0] {
                    let mut actual_origin = origin();
                    actual_origin.alt_m = Some(100.0 + height_error);
                    let mut actual_camera = camera.clone();
                    actual_camera.azimuth_deg = Some(35.0 + azimuth_error);
                    actual_camera.elevation_deg = Some(-40.0 + elevation_error);
                    actual_camera.roll_deg = Some(10.0 + roll_error);
                    let actual = ground_point(
                        &actual_origin,
                        &actual_camera,
                        pixel,
                        self::ground(),
                        accuracy(),
                        limits(),
                    )
                    .unwrap();
                    assert!(
                        separation_m(estimate.position, actual.position)
                            <= estimate.uncertainty_radius_m + 1e-5,
                        "sample outside uncertainty radius: {actual:?} versus {estimate:?}"
                    );
                }
            }
        }
    }
}
