#![allow(clippy::missing_errors_doc)]

use std::collections::BTreeMap;

use r3akt_protocol::{Ack, Command, Destination, NodeId, Payload, ProtocolEnvelope, Topic};
use serde::{Deserialize, Serialize};
use thiserror::Error;

pub const FIELD_COMMANDS: i64 = 0x09;
pub const FIELD_RESULTS: i64 = 0x0A;
pub const FIELD_EVENT: i64 = 0x0D;

#[derive(Debug, Error)]
pub enum RchProfileError {
    #[error("RCH profile encode failed: {0}")]
    Encode(String),
    #[error("RCH profile decode failed: {0}")]
    Decode(String),
    #[error("missing LXMF field {0:#04x}")]
    MissingField(i64),
    #[error("payload is not an ACK envelope")]
    NotAck,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RchSource {
    pub rns_identity: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub display_name: Option<String>,
}

impl RchSource {
    #[must_use]
    pub fn new(rns_identity: impl Into<String>) -> Self {
        Self {
            rns_identity: rns_identity.into(),
            display_name: None,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MissionCommandEnvelope {
    pub command_id: String,
    pub source: RchSource,
    pub timestamp: String,
    pub command_type: String,
    pub args: serde_json::Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub correlation_id: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub topics: Vec<String>,
}

impl MissionCommandEnvelope {
    #[must_use]
    pub fn to_protocol_envelope(&self, topic: Topic) -> ProtocolEnvelope {
        ProtocolEnvelope::new(
            NodeId::new(self.source.rns_identity.clone()),
            Destination::Topic(topic.clone()),
            topic,
            Payload::Command(Command {
                name: self.command_type.clone(),
                args: self.args.clone(),
                correlation_id: self.correlation_id.clone(),
            }),
        )
        .with_dedupe_key(self.stable_dedupe_key())
    }

    #[must_use]
    pub fn stable_dedupe_key(&self) -> String {
        if let Some(correlation_id) = self
            .correlation_id
            .as_ref()
            .filter(|value| !value.trim().is_empty())
        {
            return format!("rch:{}:{correlation_id}", self.command_id);
        }
        format!("rch:{}", self.command_id)
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CommandResultEnvelope {
    pub command_id: String,
    pub status: CommandResultStatus,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub detail: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason_code: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub required_capabilities: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub accepted_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub by_identity: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub correlation_id: Option<String>,
    #[serde(default, skip_serializing_if = "serde_json::Value::is_null")]
    pub result: serde_json::Value,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CommandResultStatus {
    Accepted,
    Rejected,
    #[serde(rename = "result")]
    Completed,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct EventEnvelope {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub event_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source: Option<RchSource>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub timestamp: Option<String>,
    pub event_type: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub command_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub correlation_id: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub topics: Vec<String>,
    #[serde(default, skip_serializing_if = "serde_json::Value::is_null")]
    pub payload: serde_json::Value,
}

#[derive(Debug, Deserialize)]
#[serde(untagged)]
enum OneOrMany<T> {
    One(T),
    Many(Vec<T>),
}

impl<T> OneOrMany<T> {
    fn into_vec(self) -> Vec<T> {
        match self {
            Self::One(value) => vec![value],
            Self::Many(values) => values,
        }
    }
}

pub fn encode_commands(commands: &[MissionCommandEnvelope]) -> Result<Vec<u8>, RchProfileError> {
    let fields = BTreeMap::from([(FIELD_COMMANDS, commands)]);
    rmp_serde::to_vec_named(&fields).map_err(|error| RchProfileError::Encode(error.to_string()))
}

pub fn decode_commands(bytes: &[u8]) -> Result<Vec<MissionCommandEnvelope>, RchProfileError> {
    let mut fields: BTreeMap<i64, Vec<MissionCommandEnvelope>> =
        rmp_serde::from_slice(bytes).map_err(|error| RchProfileError::Decode(error.to_string()))?;
    fields
        .remove(&FIELD_COMMANDS)
        .ok_or(RchProfileError::MissingField(FIELD_COMMANDS))
}

pub fn encode_results(results: &[CommandResultEnvelope]) -> Result<Vec<u8>, RchProfileError> {
    let fields = BTreeMap::from([(FIELD_RESULTS, results)]);
    rmp_serde::to_vec_named(&fields).map_err(|error| RchProfileError::Encode(error.to_string()))
}

pub fn decode_results(bytes: &[u8]) -> Result<Vec<CommandResultEnvelope>, RchProfileError> {
    let mut fields: BTreeMap<i64, OneOrMany<CommandResultEnvelope>> =
        rmp_serde::from_slice(bytes).map_err(|error| RchProfileError::Decode(error.to_string()))?;
    Ok(fields
        .remove(&FIELD_RESULTS)
        .ok_or(RchProfileError::MissingField(FIELD_RESULTS))?
        .into_vec())
}

pub fn encode_events(events: &[EventEnvelope]) -> Result<Vec<u8>, RchProfileError> {
    let fields = BTreeMap::from([(FIELD_EVENT, events)]);
    rmp_serde::to_vec_named(&fields).map_err(|error| RchProfileError::Encode(error.to_string()))
}

pub fn decode_events(bytes: &[u8]) -> Result<Vec<EventEnvelope>, RchProfileError> {
    let mut fields: BTreeMap<i64, OneOrMany<EventEnvelope>> =
        rmp_serde::from_slice(bytes).map_err(|error| RchProfileError::Decode(error.to_string()))?;
    Ok(fields
        .remove(&FIELD_EVENT)
        .ok_or(RchProfileError::MissingField(FIELD_EVENT))?
        .into_vec())
}

pub fn ack_to_result(
    envelope: &ProtocolEnvelope,
) -> Result<CommandResultEnvelope, RchProfileError> {
    let (ack, status) = match &envelope.payload {
        Payload::AckAccepted(ack) => (ack, CommandResultStatus::Accepted),
        Payload::AckRejected(ack) => (ack, CommandResultStatus::Rejected),
        Payload::AckCompleted(ack) => (ack, CommandResultStatus::Completed),
        _ => return Err(RchProfileError::NotAck),
    };
    Ok(result_from_ack(ack, status))
}

pub fn command_from_protocol(
    envelope: &ProtocolEnvelope,
    timestamp: impl Into<String>,
) -> Result<MissionCommandEnvelope, RchProfileError> {
    let Payload::Command(command) = &envelope.payload else {
        return Err(RchProfileError::Decode(
            "payload is not a command envelope".to_string(),
        ));
    };
    Ok(MissionCommandEnvelope {
        command_id: envelope.id.to_string(),
        source: RchSource::new(envelope.source.as_str()),
        timestamp: timestamp.into(),
        command_type: command.name.clone(),
        args: command.args.clone(),
        correlation_id: command.correlation_id.clone(),
        topics: vec![envelope.topic.as_str().to_string()],
    })
}

fn result_from_ack(ack: &Ack, status: CommandResultStatus) -> CommandResultEnvelope {
    CommandResultEnvelope {
        command_id: ack.envelope_id.to_string(),
        status,
        detail: ack.detail.clone(),
        reason_code: None,
        reason: ack.detail.clone(),
        required_capabilities: Vec::new(),
        accepted_at: None,
        by_identity: None,
        correlation_id: ack.correlation_id.clone(),
        result: serde_json::Value::Null,
    }
}

#[cfg(test)]
mod tests {
    use r3akt_protocol::{Ack, Destination, EnvelopeId, NodeId, Payload, Topic};
    use rmpv::Value as MsgPackValue;
    use uuid::Uuid;

    use super::*;

    fn command() -> MissionCommandEnvelope {
        MissionCommandEnvelope {
            command_id: "cmd-123".to_string(),
            source: RchSource {
                rns_identity: "abcdef0123456789".to_string(),
                display_name: Some("Pixel".to_string()),
            },
            timestamp: "2026-03-06T12:00:00Z".to_string(),
            command_type: "mission.registry.log_entry.upsert".to_string(),
            args: serde_json::json!({
                "entry_uid": "evt-123",
                "mission_uid": "mission-1",
                "content": "Operator note"
            }),
            correlation_id: Some("corr-123".to_string()),
            topics: vec!["mission-1".to_string(), "audit".to_string()],
        }
    }

    #[test]
    fn command_field_round_trip_uses_rch_field_id() {
        let bytes = encode_commands(&[command()]).expect("encode");
        let fields: BTreeMap<i64, MsgPackValue> = rmp_serde::from_slice(&bytes).expect("fields");

        assert!(fields.contains_key(&FIELD_COMMANDS));
        assert_eq!(decode_commands(&bytes).expect("decode"), vec![command()]);
    }

    #[test]
    fn ack_result_round_trip_uses_results_field() {
        let command_id = EnvelopeId::from_uuid(
            Uuid::parse_str("018f053d-7dec-7000-8000-000000000001").expect("uuid"),
        );
        let envelope = ProtocolEnvelope::new(
            NodeId::new("server"),
            Destination::Node(NodeId::new("agent")),
            Topic::new("acks"),
            Payload::AckAccepted(Ack {
                envelope_id: command_id,
                detail: None,
                correlation_id: Some("corr-123".to_string()),
            }),
        );

        let result = ack_to_result(&envelope).expect("ack result");
        let bytes = encode_results(std::slice::from_ref(&result)).expect("encode");

        assert_eq!(decode_results(&bytes).expect("decode"), vec![result]);
    }

    #[test]
    fn command_profile_converts_to_protocol_envelope_with_dedupe() {
        let command = command();

        let envelope = command.to_protocol_envelope(Topic::new("mission-1"));

        assert_eq!(envelope.source, NodeId::new("abcdef0123456789"));
        assert_eq!(envelope.topic, Topic::new("mission-1"));
        assert_eq!(envelope.stable_dedupe_key(), "rch:cmd-123:corr-123");
        assert!(matches!(envelope.payload, Payload::Command(_)));
    }

    #[test]
    fn protocol_command_converts_to_rch_field_command() {
        let envelope = command().to_protocol_envelope(Topic::new("mission-1"));

        let command = command_from_protocol(&envelope, "2026-03-06T12:00:00Z").expect("command");

        assert_eq!(command.command_type, "mission.registry.log_entry.upsert");
        assert_eq!(command.topics, vec!["mission-1".to_string()]);
        assert_eq!(command.correlation_id.as_deref(), Some("corr-123"));
    }

    #[test]
    fn python_rch_field_command_fixture_decodes() {
        let bytes = decode_hex(
            "81099187aa636f6d6d616e645f6964ac636d642d676f6c64656e2d31a6736f7572636582ac726e735f6964656e74697479a6414243444546ac646973706c61795f6e616d65ab4669656c64204167656e74a974696d657374616d70b4323032362d30352d30335431323a30303a30305aac636f6d6d616e645f74797065ac746f7069632e637265617465a46172677383aa746f7069635f70617468ad6d697373696f6e2d616c706861aa746f7069635f6e616d65ad4d697373696f6e20416c706861aa7669736962696c697479a67075626c6963ae636f7272656c6174696f6e5f6964ad636f72722d676f6c64656e2d31a6746f7069637391ad6d697373696f6e2d616c706861",
        );

        let decoded = decode_commands(&bytes).expect("decode python fixture");

        assert_eq!(decoded.len(), 1);
        assert_eq!(decoded[0].command_id, "cmd-golden-1");
        assert_eq!(decoded[0].source.rns_identity, "ABCDEF");
        assert_eq!(
            decoded[0].source.display_name.as_deref(),
            Some("Field Agent")
        );
        assert_eq!(decoded[0].timestamp, "2026-05-03T12:00:00Z");
        assert_eq!(decoded[0].command_type, "topic.create");
        assert_eq!(decoded[0].args["topic_path"], "mission-alpha");
        assert_eq!(decoded[0].args["topic_name"], "Mission Alpha");
        assert_eq!(decoded[0].args["visibility"], "public");
        assert_eq!(decoded[0].correlation_id.as_deref(), Some("corr-golden-1"));
        assert_eq!(decoded[0].topics, vec!["mission-alpha".to_string()]);
    }

    #[test]
    fn python_rch_product_command_fixtures_decode_optional_shapes() {
        let eam_bytes = decode_hex(
            "81099185aa636f6d6d616e645f6964af636d642d65616d2d66697874757265a6736f7572636581ac726e735f6964656e74697479a75243484e4f4445a974696d657374616d70b4323032362d30352d30335431323a31303a30305aac636f6d6d616e645f74797065bb6d697373696f6e2e72656769737472792e65616d2e757073657274a46172677384a863616c6c7369676ea85245534355452d31a47465616da3526564ae6f766572616c6c5f737461747573a5475245454ea56e6f746573a55265616479",
        );
        let checklist_bytes = decode_hex(
            "81099187aa636f6d6d616e645f6964b5636d642d636865636b6c6973742d66697874757265ae636f7272656c6174696f6e5f6964b5636d642d636865636b6c6973742d66697874757265ac636f6d6d616e645f74797065b7636865636b6c6973742e6372656174652e6f6e6c696e65a6736f7572636582ac726e735f6964656e74697479a75243484e4f4445ac646973706c61795f6e616d65a752434820487562a974696d657374616d70b4323032362d30352d30335431323a31353a30305aa6746f7069637392a96d697373696f6e2d31ab636865636b6c6973742d31a46172677387ad636865636b6c6973745f756964ab636865636b6c6973742d31ab6d697373696f6e5f756964a96d697373696f6e2d31ac74656d706c6174655f756964b87263683a636865636b6c6973742d313a74656d706c617465a46e616d65b24d65646963616c2045766163756174696f6eba7061727469636970616e745f726e735f6964656e74697469657392a6706565722d61a6706565722d62ab746f74616c5f7461736b7302d923637265617465645f62795f7465616d5f6d656d6265725f726e735f6964656e74697479a6706565722d61",
        );

        let eam = decode_commands(&eam_bytes).expect("decode python EAM fixture");
        let checklist = decode_commands(&checklist_bytes).expect("decode python checklist fixture");

        assert_eq!(eam.len(), 1);
        assert_eq!(eam[0].command_id, "cmd-eam-fixture");
        assert_eq!(eam[0].source.rns_identity, "RCHNODE");
        assert_eq!(eam[0].source.display_name, None);
        assert_eq!(eam[0].command_type, "mission.registry.eam.upsert");
        assert_eq!(eam[0].args["callsign"], "RESCUE-1");
        assert_eq!(eam[0].args["overall_status"], "GREEN");
        assert_eq!(eam[0].correlation_id, None);
        assert!(eam[0].topics.is_empty());

        assert_eq!(checklist.len(), 1);
        assert_eq!(checklist[0].command_id, "cmd-checklist-fixture");
        assert_eq!(checklist[0].source.rns_identity, "RCHNODE");
        assert_eq!(checklist[0].source.display_name.as_deref(), Some("RCH Hub"));
        assert_eq!(checklist[0].command_type, "checklist.create.online");
        assert_eq!(
            checklist[0].topics,
            vec!["mission-1".to_string(), "checklist-1".to_string()]
        );
        assert_eq!(checklist[0].args["checklist_uid"], "checklist-1");
        assert_eq!(checklist[0].args["participant_rns_identities"][0], "peer-a");
        assert_eq!(checklist[0].args["total_tasks"], 2);
    }

    #[test]
    fn python_rch_field_results_fixture_decodes_variants() {
        let bytes = decode_hex(
            "810a9385aa636f6d6d616e645f6964b4636d642d61636365707465642d66697874757265a6737461747573a86163636570746564ab61636365707465645f6174b9323032362d30352d30335431323a30303a30312b30303a3030ae636f7272656c6174696f6e5f6964ac636f72722d66697874757265ab62795f6964656e74697479ac6875622d6964656e7469747984aa636f6d6d616e645f6964b2636d642d726573756c742d66697874757265a6737461747573a6726573756c74a6726573756c7482a66a6f696e6564c3a86964656e74697479a6706565722d61ae636f7272656c6174696f6e5f6964ac636f72722d6669787475726586aa636f6d6d616e645f6964b4636d642d72656a65637465642d66697874757265a6737461747573a872656a6563746564ab726561736f6e5f636f6465ac756e617574686f72697a6564a6726561736f6ed9224964656e74697479206c61636b73207265717569726564206361706162696c697479ae636f7272656c6174696f6e5f6964ac636f72722d66697874757265b572657175697265645f6361706162696c697469657391ac6d697373696f6e2e6a6f696e",
        );

        let decoded = decode_results(&bytes).expect("decode python results fixture");

        assert_eq!(decoded.len(), 3);
        assert_eq!(decoded[0].command_id, "cmd-accepted-fixture");
        assert_eq!(decoded[0].status, CommandResultStatus::Accepted);
        assert_eq!(
            decoded[0].accepted_at.as_deref(),
            Some("2026-05-03T12:00:01+00:00")
        );
        assert_eq!(decoded[0].by_identity.as_deref(), Some("hub-identity"));
        assert_eq!(decoded[1].command_id, "cmd-result-fixture");
        assert_eq!(decoded[1].status, CommandResultStatus::Completed);
        assert_eq!(decoded[1].result["joined"], true);
        assert_eq!(decoded[1].result["identity"], "peer-a");
        assert_eq!(decoded[2].command_id, "cmd-rejected-fixture");
        assert_eq!(decoded[2].status, CommandResultStatus::Rejected);
        assert_eq!(decoded[2].reason_code.as_deref(), Some("unauthorized"));
        assert_eq!(
            decoded[2].required_capabilities,
            vec!["mission.join".to_string()]
        );
    }

    #[test]
    fn python_mission_sync_single_result_fixtures_decode() {
        let accepted_bytes = decode_hex(
            "810a85aa636f6d6d616e645f6964b3636d642d73696e676c652d6163636570746564a6737461747573a86163636570746564ab61636365707465645f6174b4323032362d30352d30335431323a32303a30305aae636f7272656c6174696f6e5f6964ab636f72722d73696e676c65ab62795f6964656e74697479ac6875622d6964656e74697479",
        );
        let rejected_bytes = decode_hex(
            "810a86aa636f6d6d616e645f6964b3636d642d73696e676c652d72656a6563746564a6737461747573a872656a6563746564ab726561736f6e5f636f6465af756e6b6e6f776e5f636f6d6d616e64a6726561736f6ed929556e737570706f72746564206d697373696f6e20636f6d6d616e6420276261642e636f6d6d616e6427ae636f7272656c6174696f6e5f6964ab636f72722d73696e676c65b572657175697265645f6361706162696c697469657390",
        );
        let result_bytes = decode_hex(
            "810a84aa636f6d6d616e645f6964b1636d642d73696e676c652d726573756c74a6737461747573a6726573756c74a6726573756c7482a66a6f696e6564c3a86964656e74697479a6706565722d61ae636f7272656c6174696f6e5f6964ab636f72722d73696e676c65",
        );

        let accepted = decode_results(&accepted_bytes).expect("accepted result");
        let rejected = decode_results(&rejected_bytes).expect("rejected result");
        let result = decode_results(&result_bytes).expect("completed result");

        assert_eq!(accepted.len(), 1);
        assert_eq!(accepted[0].command_id, "cmd-single-accepted");
        assert_eq!(accepted[0].status, CommandResultStatus::Accepted);
        assert_eq!(
            accepted[0].accepted_at.as_deref(),
            Some("2026-05-03T12:20:00Z")
        );
        assert_eq!(accepted[0].by_identity.as_deref(), Some("hub-identity"));
        assert_eq!(rejected.len(), 1);
        assert_eq!(rejected[0].command_id, "cmd-single-rejected");
        assert_eq!(rejected[0].status, CommandResultStatus::Rejected);
        assert_eq!(rejected[0].reason_code.as_deref(), Some("unknown_command"));
        assert!(rejected[0].required_capabilities.is_empty());
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].command_id, "cmd-single-result");
        assert_eq!(result[0].status, CommandResultStatus::Completed);
        assert_eq!(result[0].result["joined"], true);
        assert_eq!(result[0].result["identity"], "peer-a");
    }

    #[test]
    fn python_rch_field_event_fixture_decodes() {
        let bytes = decode_hex(
            "810d9184aa6576656e745f74797065ae6d697373696f6e2e6a6f696e6564aa636f6d6d616e645f6964b1636d642d6576656e742d66697874757265ae636f7272656c6174696f6e5f6964ac636f72722d66697874757265a77061796c6f616482a86964656e74697479a6706565722d61a66a6f696e6564c3",
        );

        let decoded = decode_events(&bytes).expect("decode python event fixture");

        assert_eq!(decoded.len(), 1);
        assert_eq!(decoded[0].event_type, "mission.joined");
        assert_eq!(decoded[0].command_id.as_deref(), Some("cmd-event-fixture"));
        assert_eq!(decoded[0].correlation_id.as_deref(), Some("corr-fixture"));
        assert_eq!(decoded[0].payload["identity"], "peer-a");
        assert_eq!(decoded[0].payload["joined"], true);
    }

    #[test]
    fn python_mission_sync_single_event_fixture_decodes() {
        let bytes = decode_hex(
            "810d86a86576656e745f6964b26576742d73696e676c652d66697874757265a6736f7572636581ac726e735f6964656e74697479a6706565722d61a974696d657374616d70b9323032362d30352d30335431323a32353a30302b30303a3030aa6576656e745f74797065ae6d697373696f6e2e6a6f696e6564a6746f7069637391a96d697373696f6e2d31a77061796c6f616482a86964656e74697479a6706565722d61a66a6f696e6564c3",
        );

        let decoded = decode_events(&bytes).expect("decode python mission event fixture");

        assert_eq!(decoded.len(), 1);
        assert_eq!(decoded[0].event_id.as_deref(), Some("evt-single-fixture"));
        assert_eq!(
            decoded[0]
                .source
                .as_ref()
                .map(|source| source.rns_identity.as_str()),
            Some("peer-a")
        );
        assert_eq!(
            decoded[0].timestamp.as_deref(),
            Some("2026-05-03T12:25:00+00:00")
        );
        assert_eq!(decoded[0].event_type, "mission.joined");
        assert_eq!(decoded[0].topics, vec!["mission-1".to_string()]);
        assert_eq!(decoded[0].command_id, None);
        assert_eq!(decoded[0].payload["identity"], "peer-a");
        assert_eq!(decoded[0].payload["joined"], true);
    }

    #[test]
    fn completed_ack_serializes_as_rch_result_status() {
        let result = CommandResultEnvelope {
            command_id: "cmd-1".to_string(),
            status: CommandResultStatus::Completed,
            detail: None,
            reason_code: None,
            reason: None,
            required_capabilities: Vec::new(),
            accepted_at: None,
            by_identity: None,
            correlation_id: Some("corr-1".to_string()),
            result: serde_json::json!({ "ok": true }),
        };
        let bytes = encode_results(std::slice::from_ref(&result)).expect("encode");

        let raw: BTreeMap<i64, Vec<serde_json::Value>> =
            rmp_serde::from_slice(&bytes).expect("raw");

        assert_eq!(raw[&FIELD_RESULTS][0]["status"], "result");
        assert_eq!(decode_results(&bytes).expect("decode"), vec![result]);
    }

    #[test]
    fn rejected_result_round_trip_uses_python_status_shape() {
        let result = CommandResultEnvelope {
            command_id: "cmd-rejected".to_string(),
            status: CommandResultStatus::Rejected,
            detail: None,
            reason_code: Some("unauthorized".to_string()),
            reason: Some("Identity lacks required capability".to_string()),
            required_capabilities: vec!["mission.join".to_string()],
            accepted_at: None,
            by_identity: None,
            correlation_id: Some("corr-rejected".to_string()),
            result: serde_json::Value::Null,
        };
        let bytes = encode_results(std::slice::from_ref(&result)).expect("encode");

        let raw: BTreeMap<i64, Vec<serde_json::Value>> =
            rmp_serde::from_slice(&bytes).expect("raw");

        assert_eq!(raw[&FIELD_RESULTS][0]["status"], "rejected");
        assert_eq!(raw[&FIELD_RESULTS][0]["reason_code"], "unauthorized");
        assert_eq!(
            raw[&FIELD_RESULTS][0]["required_capabilities"][0],
            "mission.join"
        );
        assert_eq!(decode_results(&bytes).expect("decode"), vec![result]);
    }

    #[test]
    fn event_round_trip_uses_rch_field_event_id() {
        let event = EventEnvelope {
            event_id: None,
            source: None,
            timestamp: None,
            event_type: "mission.joined".to_string(),
            command_id: Some("cmd-event".to_string()),
            correlation_id: Some("corr-event".to_string()),
            topics: Vec::new(),
            payload: serde_json::json!({
                "identity": "abcdef",
                "joined": true
            }),
        };
        let bytes = encode_events(std::slice::from_ref(&event)).expect("encode");

        let raw: BTreeMap<i64, Vec<serde_json::Value>> =
            rmp_serde::from_slice(&bytes).expect("raw");

        assert!(raw.contains_key(&FIELD_EVENT));
        assert_eq!(raw[&FIELD_EVENT][0]["event_type"], "mission.joined");
        assert_eq!(raw[&FIELD_EVENT][0]["payload"]["joined"], true);
        assert_eq!(decode_events(&bytes).expect("decode"), vec![event]);
    }

    fn decode_hex(input: &str) -> Vec<u8> {
        assert_eq!(input.len() % 2, 0);
        (0..input.len())
            .step_by(2)
            .map(|index| u8::from_str_radix(&input[index..index + 2], 16).expect("hex byte"))
            .collect()
    }
}
