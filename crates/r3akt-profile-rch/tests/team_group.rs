use std::collections::BTreeMap;

use r3akt_profile_rch::{
    CommandResultEnvelope, CommandResultStatus, FIELD_COMMANDS, FIELD_GROUP, FIELD_RESULTS,
    MissionCommandEnvelope, RchSource, decode_commands, decode_results, encode_commands,
    encode_commands_for_team,
};

fn command() -> MissionCommandEnvelope {
    MissionCommandEnvelope {
        command_id: "cmd-team".into(),
        source: RchSource::new("peer"),
        timestamp: "2026-11-10T12:00:00Z".into(),
        command_type: "mission.marker.create".into(),
        args: serde_json::json!({"name": "Ridge", "lat": 44.5, "lon": -1.25}),
        correlation_id: None,
        topics: vec![],
    }
}

#[test]
fn team_scoped_commands_round_trip_with_numeric_group_field() {
    let commands = vec![command(), command()];
    let team = "43341e5c822d99857fa6e8641f2ca9c0";
    let bytes = encode_commands_for_team(&commands, Some(team)).expect("encode");
    let fields: BTreeMap<i64, rmpv::Value> = rmp_serde::from_slice(&bytes).expect("fields");
    let legacy: BTreeMap<i64, rmpv::Value> =
        rmp_serde::from_slice(&encode_commands(&commands).expect("legacy encode")).expect("fields");

    assert_eq!(fields.len(), 2);
    assert_eq!(fields[&FIELD_GROUP], rmpv::Value::from(team));
    assert_eq!(fields[&FIELD_COMMANDS], legacy[&FIELD_COMMANDS]);
    assert_eq!(decode_commands(&bytes).expect("decode"), commands);
}

#[test]
fn no_team_keeps_existing_encoding_and_blank_team_is_rejected() {
    let commands = vec![command()];
    let bytes = encode_commands_for_team(&commands, None).expect("encode");
    let fields: BTreeMap<i64, rmpv::Value> = rmp_serde::from_slice(&bytes).expect("fields");

    assert_eq!(bytes, encode_commands(&commands).expect("legacy encode"));
    assert!(!fields.contains_key(&FIELD_GROUP));
    for team in ["", " ", "\t\n"] {
        assert!(encode_commands_for_team(&commands, Some(team)).is_err());
    }
}

#[test]
fn team_scoped_result_field_ignores_group_metadata() {
    let result = CommandResultEnvelope {
        command_id: "cmd-team-result".to_string(),
        status: CommandResultStatus::Completed,
        detail: None,
        reason_code: None,
        reason: None,
        required_capabilities: Vec::new(),
        accepted_at: None,
        by_identity: None,
        correlation_id: Some("corr-team-result".to_string()),
        result: serde_json::json!({ "ok": true }),
    };
    let fields = BTreeMap::from([
        (FIELD_RESULTS, serde_json::json!([result.clone()])),
        (
            FIELD_GROUP,
            serde_json::json!("d6b6e188b910d6bdd24d04b7a7ec5444"),
        ),
    ]);
    let bytes = rmp_serde::to_vec_named(&fields).expect("encode");

    assert_eq!(decode_results(&bytes).expect("decode"), vec![result]);
}
