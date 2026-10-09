use super::{
    Destination, JsonValue, NodeId, Payload, ProtocolEnvelope, Topic, TransportError,
    direct_lxmf_fallback_envelope, direct_lxmf_telemetry, optional_field_string,
    optional_field_value, optional_message_string,
};
use crate::field_commands::{DirectLxmfCommandResult, direct_lxmf_commands};

/// Independently decoded application payloads and privacy-safe command diagnostics.
#[derive(Debug, Default)]
pub struct DecodedLxmfMessage {
    pub envelopes: Vec<ProtocolEnvelope>,
    pub command_diagnostics: Vec<String>,
}

pub(super) fn direct_lxmf_message_envelope(
    message: &JsonValue,
    local_source: &str,
) -> Result<Option<ProtocolEnvelope>, TransportError> {
    let decoded = direct_lxmf_message_payloads(message, local_source);
    if decoded.envelopes.is_empty()
        && decoded
            .command_diagnostics
            .iter()
            .any(|d| d.starts_with("malformed"))
    {
        return Err(TransportError::Receive(
            decoded.command_diagnostics.join("; "),
        ));
    }
    Ok(decoded.envelopes.into_iter().next())
}

pub(super) fn direct_lxmf_message_payloads(
    message: &JsonValue,
    local_source: &str,
) -> DecodedLxmfMessage {
    let fields = message.get("fields").and_then(JsonValue::as_object);
    let source = optional_message_string(message, &["source", "source_hash", "source_id"])
        .unwrap_or("unknown");
    let mut decoded = DecodedLxmfMessage::default();
    // Telemetry is processed first, so a same-message collector query sees it.
    if let Some(telemetry) = direct_lxmf_telemetry(fields, message) {
        let topic = Topic::new("telemetry");
        decoded.envelopes.push(ProtocolEnvelope::new(
            NodeId::new(source),
            Destination::Topic(topic.clone()),
            topic,
            Payload::TelemetrySample(telemetry),
        ));
    }
    for (index, result) in direct_lxmf_commands(fields).into_iter().enumerate() {
        match result {
            DirectLxmfCommandResult::Valid(mut command) => {
                if command.name == "telemetry.collect" {
                    if command.args.get("topic_id").is_none() {
                        if let Some(topic) = fields.and_then(|f| {
                            optional_field_value(f, &["TopicID", "topic_id", "topic", "Topic"])
                        }) {
                            let Some(topic) =
                                topic.as_str().map(str::trim).filter(|s| !s.is_empty())
                            else {
                                decoded.command_diagnostics.push(format!("malformed LXMF FIELD_COMMANDS (0x09) entry {index}: topic must be a non-empty string"));
                                continue;
                            };
                            command.args["topic_id"] = JsonValue::String(topic.into());
                        }
                    }
                } else if let Some(team_uid) = fields.and_then(|f| {
                    optional_field_string(f, &["11", "FIELD_GROUP", "group", "Group"])
                }) {
                    if let Some(args) = command.args.as_object_mut() {
                        args.insert("_rem_team_uid".into(), JsonValue::String(team_uid.into()));
                    }
                }
                decoded.envelopes.push(ProtocolEnvelope::new(
                    NodeId::new(source),
                    Destination::Node(NodeId::new(local_source)),
                    Topic::new("rem-directory"),
                    Payload::Command(command),
                ));
            }
            DirectLxmfCommandResult::Malformed(reason) => decoded.command_diagnostics.push(
                format!("malformed LXMF FIELD_COMMANDS (0x09) entry {index}: {reason}"),
            ),
            DirectLxmfCommandResult::Unsupported => decoded.command_diagnostics.push(format!(
                "unsupported LXMF FIELD_COMMANDS (0x09) entry {index}"
            )),
        }
    }
    if decoded.envelopes.is_empty()
        && decoded
            .command_diagnostics
            .iter()
            .all(|d| d.starts_with("unsupported"))
    {
        if let Some(envelope) = direct_lxmf_fallback_envelope(fields, message, source, local_source)
        {
            decoded.envelopes.push(envelope);
        }
    }
    if let Some(id) = message
        .get("id")
        .and_then(JsonValue::as_str)
        .filter(|id| !id.trim().is_empty())
    {
        for (index, envelope) in decoded.envelopes.iter_mut().enumerate() {
            envelope.dedupe_key = Some(if index == 0 {
                id.into()
            } else {
                format!("{id}:payload:{index}")
            });
        }
    }
    decoded
}
