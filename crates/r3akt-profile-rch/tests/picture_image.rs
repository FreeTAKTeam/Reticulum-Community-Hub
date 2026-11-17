use std::collections::BTreeMap;

use r3akt_profile_rch::{
    FIELD_COMMANDS, FIELD_GROUP, FIELD_IMAGE, MissionCommandEnvelope, RchSource, decode_commands,
    encode_commands_for_team, encode_commands_for_team_with_image,
};

fn command() -> MissionCommandEnvelope {
    MissionCommandEnvelope {
        command_id: "cmd-picture".into(),
        source: RchSource::new("drone"),
        timestamp: "2026-11-17T12:00:00Z".into(),
        command_type: "mission.marker.create".into(),
        args: serde_json::json!({"marker_type": "picture", "lat": 44.5, "lon": -1.25}),
        correlation_id: None,
        topics: vec![],
    }
}

const TEAM: &str = "43341e5c822d99857fa6e8641f2ca9c0";

#[test]
fn image_is_written_as_lxmf_field_image_with_binary_bytes() {
    let commands = vec![command()];
    let jpeg = [0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10];
    let bytes =
        encode_commands_for_team_with_image(&commands, Some(TEAM), Some(("jpg", &jpeg))).unwrap();
    let fields: BTreeMap<i64, rmpv::Value> = rmp_serde::from_slice(&bytes).unwrap();

    assert_eq!(fields.len(), 3);
    assert_eq!(fields[&FIELD_GROUP], rmpv::Value::from(TEAM));
    assert_eq!(
        fields[&FIELD_IMAGE],
        rmpv::Value::Array(vec!["jpg".into(), rmpv::Value::Binary(jpeg.to_vec())])
    );
    let plain: BTreeMap<i64, rmpv::Value> =
        rmp_serde::from_slice(&encode_commands_for_team(&commands, Some(TEAM)).unwrap()).unwrap();
    assert_eq!(fields[&FIELD_COMMANDS], plain[&FIELD_COMMANDS]);
    assert_eq!(decode_commands(&bytes).unwrap(), commands);
}

#[test]
fn image_without_team_and_no_image_keep_existing_encodings() {
    let commands = vec![command()];
    let bytes = encode_commands_for_team_with_image(&commands, None, Some(("jpg", &[1]))).unwrap();
    let fields: BTreeMap<i64, rmpv::Value> = rmp_serde::from_slice(&bytes).unwrap();
    assert!(!fields.contains_key(&FIELD_GROUP));
    assert!(fields.contains_key(&FIELD_IMAGE));

    assert_eq!(
        encode_commands_for_team_with_image(&commands, Some(TEAM), None).unwrap(),
        encode_commands_for_team(&commands, Some(TEAM)).unwrap()
    );
    assert!(encode_commands_for_team_with_image(&commands, None, Some(("", &[1]))).is_err());
    assert!(encode_commands_for_team_with_image(&commands, None, Some(("jpg", &[]))).is_err());
}
