use r3akt_map_core::{
    Position,
    sensor_geometry::{destination, distance_and_bearing},
};

fn point(lat: f64, lon: f64) -> Position {
    Position::new(lat, lon).unwrap()
}

#[test]
fn measures_distance_and_true_bearing_on_the_same_sphere_as_destination() {
    // Independent spherical great-circle references, including an antimeridian crossing.
    for (from, to, distance, bearing) in [
        (
            point(40.0, -73.0),
            point(51.0, 0.0),
            5_578_851.115_852_646,
            51.596_490_214_809_22,
        ),
        (
            point(0.0, 179.9),
            point(0.0, -179.9),
            22_239.016_046_706_58,
            90.0,
        ),
        (
            point(89.999, -45.0),
            point(89.999, 135.0),
            222.390_160_467_065_83,
            0.0,
        ),
    ] {
        let (actual_distance, actual_bearing) = distance_and_bearing(from, to);
        assert!((actual_distance - distance).abs() < 1e-5);
        assert!((actual_bearing.unwrap() - bearing).abs() < 1e-8);
    }

    for bearing in [0.0, 45.0, 90.0, 180.0, 270.0, 359.0] {
        let from = point(45.0, 179.99);
        let to = destination(from, bearing, 12_345.0).unwrap();
        let (distance, actual_bearing) = distance_and_bearing(from, to);
        assert!((distance - 12_345.0).abs() < 1e-6);
        let difference = (actual_bearing.unwrap() - bearing + 180.0).rem_euclid(360.0) - 180.0;
        assert!(difference.abs() < 1e-8);
    }
}

#[test]
fn returns_no_bearing_for_coincident_antipodal_or_polar_origins() {
    for (from, to) in [
        (point(10.0, 20.0), point(10.0, 20.0)),
        (point(0.0, 180.0), point(0.0, -180.0)),
        (point(90.0, 0.0), point(90.0, 90.0)),
    ] {
        assert_eq!(distance_and_bearing(from, to), (0.0, None));
    }

    let half_circumference = std::f64::consts::PI * 6_371_008.8;
    for (from, to) in [
        (point(12.0, 34.0), point(-12.0, -146.0)),
        (point(90.0, 0.0), point(-90.0, 90.0)),
    ] {
        assert_eq!(distance_and_bearing(from, to), (half_circumference, None));
    }

    let (distance, bearing) = distance_and_bearing(point(90.0, 0.0), point(89.0, 0.0));
    assert!(distance > 111_000.0 && distance < 112_000.0);
    assert_eq!(bearing, None);
}

#[test]
fn near_antipodes_keep_a_finite_distance_and_bearing() {
    let (distance, bearing) =
        distance_and_bearing(point(12.0, 34.0), point(-12.000_000_1, -145.999_999_9));
    assert!((distance - 20_015_114.426_481_433).abs() < 1e-5);
    assert!((bearing.unwrap() - 224.367_084_966_954_5).abs() < 1e-4);
}
