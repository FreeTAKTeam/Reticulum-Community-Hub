#![cfg_attr(
    not(test),
    deny(
        clippy::expect_used,
        clippy::let_underscore_must_use,
        clippy::panic,
        clippy::unwrap_used
    )
)]

use r3akt_identity::{EnrollmentRequest, IdentityDirectory, NodeIdentity};
use r3akt_profile_rch::{
    MissionCommandEnvelope, RchSource, decode_commands, encode_commands, encode_results,
};
use r3akt_protocol::NodeId;
use r3akt_rch_core::RchCore;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let identity = NodeIdentity::new(
        NodeId::new("rch-rust-runtime"),
        "RCH Rust Runtime",
        "example-public-key",
    );
    let mut directory = IdentityDirectory::new();
    directory.submit_enrollment(EnrollmentRequest::new(identity))?;

    let inbound_fields = encode_commands(&[MissionCommandEnvelope {
        command_id: "cmd-rch-1".to_string(),
        source: RchSource {
            rns_identity: "agent-rns-identity".to_string(),
            display_name: Some("Field Agent".to_string()),
        },
        timestamp: "2026-03-06T12:00:00Z".to_string(),
        command_type: "topic.create".to_string(),
        args: serde_json::json!({
            "topic_path": "mission-alpha",
            "topic_name": "Mission Alpha",
            "visibility": "public"
        }),
        correlation_id: Some("corr-rch-1".to_string()),
        topics: vec!["mission-alpha".to_string()],
    }])?;

    let command = decode_commands(&inbound_fields)?
        .into_iter()
        .next()
        .ok_or("encoded command batch was empty")?;
    let mut core = RchCore::new();
    let outcome = core.handle_command(&command);
    let responses = core.handle_mission_sync_command(&command);
    let encoded_results = encode_results(&[outcome.result])?;

    println!(
        "identity enrollment pending: {}",
        directory
            .enrollment(&NodeId::new("rch-rust-runtime"))
            .is_some()
    );
    println!("decoded command: {}", command.command_type);
    println!("topics after command: {}", core.topics().len());
    println!("mission-sync responses: {}", responses.len());
    println!("encoded FIELD_RESULTS bytes: {}", encoded_results.len());
    Ok(())
}
