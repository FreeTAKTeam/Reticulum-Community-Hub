use std::collections::BTreeMap;

use r3akt_profile_rch::{MissionCommandEnvelope, RchSource, encode_commands_for_team};
use r3akt_protocol::Payload;
use serde_json::{Value, json};

#[test]
fn encoded_team_commands_reach_the_transport_with_team_scope() {
    let team = "43341e5c822d99857fa6e8641f2ca9c0";
    let commands = [MissionCommandEnvelope {
        command_id: "marker-command".into(),
        source: RchSource::new("peer"),
        timestamp: "2026-11-10T12:00:00Z".into(),
        command_type: "mission.marker.create".into(),
        args: json!({"name": "Ridge", "lat": 44.5, "lon": -1.25}),
        correlation_id: None,
        topics: vec![],
    }];
    let bytes = encode_commands_for_team(&commands, Some(team)).expect("encode");
    let fields: BTreeMap<i64, Value> = rmp_serde::from_slice(&bytes).expect("fields");
    let fields: serde_json::Map<String, Value> = fields
        .into_iter()
        .map(|(key, value)| (key.to_string(), value))
        .collect();
    let decoded = r3akt_transport_rns::reticulumd_message_to_payloads(
        &json!({
            "id": "message", "source": "peer", "destination": "hub",
            "direction": "in", "fields": fields,
        }),
        "hub",
    )
    .expect("decode");

    assert!(decoded.command_diagnostics.is_empty());
    assert_eq!(decoded.envelopes.len(), 1);
    let Payload::Command(command) = &decoded.envelopes[0].payload else {
        panic!("expected a command");
    };
    assert_eq!(command.name, "mission.marker.create");
    assert_eq!(command.args["name"], "Ridge");
    assert_eq!(command.args["_rem_team_uid"], team);
}
