use r3akt_map_core::marker_picture::{
    self, MarkerPicture, PictureCrop, decode_relay, image_field, sha256_hex,
};
use r3akt_map_core::{MarkerDraft, MarkerRecord, Position, replica, symbols};
use serde_json::json;

const THUMB: &[u8] = &[0xff, 0xd8, 0xff, 0xe0, 1, 2, 3];
const MESSAGE_ID: &str = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff";

fn picture_json() -> serde_json::Value {
    json!({
        "thumbnail": {"media_type": "image/jpeg", "width": 160, "height": 120,
                      "sha256": sha256_hex(THUMB).to_ascii_uppercase()},
        "captured_at": "2026-11-17T12:00:00Z",
        "camera": {"lat": 44.5, "lon": -1.25, "altitude_reference": "takeoff", "gimbal_pitch_deg": -45.0},
        "crop": "centre"
    })
}

fn marker() -> MarkerRecord {
    let mut picture = MarkerPicture::parse(&picture_json()).unwrap();
    picture.message_id = Some(MESSAGE_ID.into());
    let mut marker = MarkerRecord::create_with_id(
        MarkerDraft {
            marker_type: "picture".into(),
            symbol: "picture".into(),
            name: "Picture".into(),
            category: "picture".into(),
            position: Position::new(44.5, -1.25).unwrap(),
            notes: None,
            origin_rch: "rch".into(),
        },
        "0123456789abcdef0123456789abcdef".into(),
        "local".into(),
        1_763_380_800_000,
    );
    marker.picture = Some(picture);
    marker
}

#[test]
fn picture_is_a_catalog_entry() {
    assert!(symbols::is_supported(marker_picture::MARKER_TYPE));
    assert_eq!(symbols::normalize("Photo").as_deref(), Some("picture"));
}

#[test]
fn picture_metadata_is_validated_and_omits_unknown_camera_values() {
    let picture = MarkerPicture::parse(&picture_json()).unwrap();
    assert_eq!(picture.thumbnail.sha256, sha256_hex(THUMB));
    assert_eq!(picture.crop, Some(PictureCrop::Centre));
    let camera = serde_json::to_value(picture.camera.unwrap()).unwrap();
    assert_eq!(camera.get("heading_deg"), None);
    assert_eq!(camera["altitude_reference"], "takeoff");

    for bad in [
        json!({"thumbnail": {"media_type": "image/jpeg", "width": 160, "height": 120, "sha256": "x"}}),
        json!({"thumbnail": {"media_type": "image/jpeg", "width": 0, "height": 120, "sha256": sha256_hex(THUMB)}}),
        json!({"thumbnail": {"media_type": "image/jpeg", "width": 1, "height": 1, "sha256": sha256_hex(THUMB)}, "crop": "left"}),
        json!("picture"),
    ] {
        assert!(MarkerPicture::parse(&bad).is_err(), "{bad}");
    }
}

#[test]
fn api_value_carries_picture_and_replicates() {
    let marker = marker();
    let value = marker.api_value();
    assert_eq!(value["picture"]["message_id"], MESSAGE_ID);
    assert_eq!(value["picture"]["crop"], "centre");
    let replica = replica::from_api_value(&value, "local".into()).unwrap();
    assert_eq!(replica, marker);

    let mut plain = value.clone();
    plain.as_object_mut().unwrap().remove("picture");
    assert_eq!(
        replica::from_api_value(&plain, "l".into()).unwrap().picture,
        None
    );
    plain["picture"] = json!({"thumbnail": 1});
    assert!(replica::from_api_value(&plain, "l".into()).is_err());
}

#[test]
fn stored_layout_without_picture_still_decodes() {
    let mut marker = marker();
    marker.picture = None;
    let bytes = rmp_serde::to_vec_named(&marker).unwrap();
    let decoded: MarkerRecord = rmp_serde::from_slice(&bytes).unwrap();
    assert_eq!(decoded, marker);
    let with_picture = self::marker();
    let decoded: MarkerRecord =
        rmp_serde::from_slice(&rmp_serde::to_vec_named(&with_picture).unwrap()).unwrap();
    assert_eq!(decoded, with_picture);
}

#[test]
fn relay_decodes_marker_and_verified_thumbnail() {
    let event = json!({"event_type": "mission.marker.created", "payload": marker().api_value()});
    let bytes: Vec<u8> = THUMB.to_vec();
    let fields = json!({"10": [], "13": event, "6": ["jpg", bytes]});
    let received = decode_relay(&fields, "local".into()).unwrap().unwrap();
    assert_eq!(received.marker, marker());
    assert_eq!(received.thumbnail.as_deref(), Some(THUMB));

    // A thumbnail that does not match its digest is dropped: draw the fallback.
    let fields = json!({"13": [event], "6": ["jpg", [1, 2, 3]]});
    let received = decode_relay(&fields, "local".into()).unwrap().unwrap();
    assert_eq!(received.thumbnail, None);

    let other =
        json!({"13": {"event_type": "mission.marker.created", "payload": {"type": "fire"}}});
    assert_eq!(decode_relay(&other, "l".into()).unwrap(), None);
    assert_eq!(
        image_field(&json!(["jpg", "base64:/9j/"])).unwrap().1,
        vec![0xff, 0xd8, 0xff]
    );
    assert_eq!(image_field(&json!(["jpg"])), None);
}
