use r3akt_tak_connector::{TakInboundCotEvent, TakInboundCotResult, parse_inbound_cot_payload};
fn parse_inbound_cot_event(raw: &str) -> Option<TakInboundCotEvent> {
    match parse_inbound_cot_payload(raw, true) {
        TakInboundCotResult::Parsed(event) => Some(*event),
        TakInboundCotResult::Raw(_) => None,
    }
}
#[test]
fn uploaded_geometry_semantics_keep_video_separate_and_altitude_unknown() {
    let raw = r#"<event uid="sample-drone" type="a-f-A-M-H-Q" time="2026-10-31T00:00:00Z" stale="2026-10-31T00:00:30Z"><point lat="38.889" lon="-77.01399" hae="9999999"/><detail><sensor version="0.6" azimuth="0" fov="20" vfov="60" elevation="0" range="500" north="227"/><__video url="rtmp://camera.local/live"/></detail></event>"#;
    let parsed = parse_inbound_cot_event(raw).unwrap().sensor.unwrap();
    assert_eq!(parsed.position.alt_m, None);
    assert_eq!(parsed.sensor.azimuth_deg, Some(0.));
    assert_eq!(parsed.sensor.horizontal_fov_deg, Some(20.));
    assert_eq!(parsed.sensor.vertical_fov_deg, Some(60.));
    assert_eq!(parsed.sensor.slant_range_m, Some(500.));
    assert_eq!(parsed.sensor.image_north_deg, Some(227.));
    assert!(parsed.manifest.is_none());
    assert_eq!(parsed.unapproved_video.unwrap().protocol, "rtmp");
    let hostile = raw.replace(
        "rtmp://camera.local/live",
        "rtmp://user:password@camera.local/live",
    );
    let parsed = parse_inbound_cot_event(&hostile).unwrap().sensor.unwrap();
    assert!(parsed.unapproved_video.is_none());
    assert!(parsed.video_diagnostic.is_some());
    assert_eq!(parsed.sensor.azimuth_deg, Some(0.));
}
