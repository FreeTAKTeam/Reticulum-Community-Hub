use super::{
    Destination, JsonValue, NodeId, Payload, ProtocolEnvelope, Topic, TransportError,
    direct_lxmf_fallback_envelope, optional_field_string, optional_field_value,
    optional_message_string,
};
use crate::field_commands::{DirectLxmfCommandResult, direct_lxmf_commands};
use crate::telemetry_decode::direct_lxmf_telemetry;

/// Independently decoded application payloads and privacy-safe command diagnostics.
#[derive(Debug, Default)]
pub struct DecodedLxmfMessage {
    pub envelopes: Vec<ProtocolEnvelope>,
    pub command_diagnostics: Vec<String>,
    pub telemetry_diagnostics: Vec<String>,
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
            .chain(&decoded.telemetry_diagnostics)
            .any(|d| d.starts_with("malformed"))
    {
        return Err(TransportError::Receive(
            decoded
                .command_diagnostics
                .iter()
                .chain(&decoded.telemetry_diagnostics)
                .cloned()
                .collect::<Vec<_>>()
                .join("; "),
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
    if let Some(fields) = fields {
        decode_origin_sensors(
            JsonValue::Object(fields.clone()),
            source,
            local_source,
            &mut decoded,
        );
    }
    // Telemetry is processed first, so a same-message collector query sees it.
    match direct_lxmf_telemetry(fields, message) {
        Ok(Some(telemetry)) => {
            let topic = Topic::new("telemetry");
            decoded.envelopes.push(ProtocolEnvelope::new(
                NodeId::new(source),
                Destination::Topic(topic.clone()),
                topic,
                Payload::TelemetrySample(telemetry),
            ));
        }
        Ok(None) => {}
        Err(reason) => decoded.telemetry_diagnostics.push(reason.into()),
    }
    for (index, result) in direct_lxmf_commands(fields).into_iter().enumerate() {
        match result {
            DirectLxmfCommandResult::Valid(mut command) => {
                if command.name == "telemetry.collect" {
                    if command.args.get("topic_id").is_none()
                        && let Some(topic) = fields.and_then(|f| {
                            optional_field_value(f, &["TopicID", "topic_id", "topic", "Topic"])
                        })
                    {
                        let Some(topic) = topic.as_str().map(str::trim).filter(|s| !s.is_empty())
                        else {
                            decoded.command_diagnostics.push(format!("malformed LXMF FIELD_COMMANDS (0x09) entry {index}: topic must be a non-empty string"));
                            continue;
                        };
                        command.args["topic_id"] = JsonValue::String(topic.into());
                    }
                } else if let Some(team_uid) = fields.and_then(|f| {
                    optional_field_string(f, &["11", "FIELD_GROUP", "group", "Group"])
                }) && let Some(args) = command.args.as_object_mut()
                {
                    args.insert("_rem_team_uid".into(), JsonValue::String(team_uid.into()));
                }
                picture_args(&mut command, fields, message);
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
        && let Some(envelope) = direct_lxmf_fallback_envelope(fields, message, source, local_source)
    {
        decoded.envelopes.push(envelope);
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

/// Picture markers (r3akt-uas #19): the hub needs the message's `FIELD_IMAGE`
/// and its LXMF message ID (the picture ID), so both join the command args.
fn picture_args(
    command: &mut r3akt_protocol::Command,
    fields: Option<&serde_json::Map<String, JsonValue>>,
    message: &JsonValue,
) {
    use r3akt_map_core::marker_picture as picture;
    if command.name != "mission.marker.create" && command.name != picture::UPLOAD_COMMAND {
        return;
    }
    let Some(args) = command.args.as_object_mut() else {
        return;
    };
    // Only the transport may set these, never the sender's own args.
    args.remove("_lxmf_image");
    args.remove("_lxmf_message_id");
    if let Some((format, data)) = fields
        .and_then(|f| optional_field_value(f, &[picture::FIELD_IMAGE_KEY]))
        .and_then(picture::image_field)
    {
        use base64::Engine as _;
        let data = base64::engine::general_purpose::STANDARD.encode(data);
        args.insert(
            "_lxmf_image".into(),
            serde_json::json!([format, format!("base64:{data}")]),
        );
    }
    if let Some(id) = message.get("id").and_then(JsonValue::as_str) {
        args.insert("_lxmf_message_id".into(), JsonValue::String(id.into()));
    }
}

fn decode_origin_sensors(
    value: JsonValue,
    source: &str,
    local_source: &str,
    decoded: &mut DecodedLxmfMessage,
) {
    match r3akt_map_core::sensor_frame::decode_json(&value, source) {
        Ok(frame)
            if !frame.events.is_empty()
                || !frame.samples.is_empty()
                || !frame.expiries.is_empty() =>
        {
            decoded.envelopes.push(ProtocolEnvelope::new(
                NodeId::new(source),
                Destination::Node(NodeId::new(local_source)),
                Topic::new("origin-sensors"),
                Payload::OriginSensorTelemetry { fields: value },
            ));
        }
        Ok(_) => {}
        Err(reason) => decoded
            .telemetry_diagnostics
            .push(format!("malformed R3S fields: {reason}")),
    }
}
