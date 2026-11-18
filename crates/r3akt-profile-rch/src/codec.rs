//! LXMF field codecs for RCH mission commands, results and events, plus
//! conversion from R3AKT protocol envelopes.
use std::collections::BTreeMap;

use r3akt_protocol::{Ack, Payload, ProtocolEnvelope};
use serde::{Deserialize, de::DeserializeOwned};

use crate::{
    CommandResultEnvelope, CommandResultStatus, EventEnvelope, FIELD_COMMANDS, FIELD_EVENT,
    FIELD_RESULTS, MissionCommandEnvelope, RchProfileError, RchSource,
};

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

pub fn decode_commands(bytes: &[u8]) -> Result<Vec<MissionCommandEnvelope>, RchProfileError> {
    decode_field(bytes, FIELD_COMMANDS)
}

pub fn encode_results(results: &[CommandResultEnvelope]) -> Result<Vec<u8>, RchProfileError> {
    let fields = BTreeMap::from([(FIELD_RESULTS, results)]);
    rmp_serde::to_vec_named(&fields).map_err(|error| RchProfileError::Encode(error.to_string()))
}

pub fn decode_results(bytes: &[u8]) -> Result<Vec<CommandResultEnvelope>, RchProfileError> {
    Ok(decode_field::<OneOrMany<CommandResultEnvelope>>(bytes, FIELD_RESULTS)?.into_vec())
}

pub fn encode_events(events: &[EventEnvelope]) -> Result<Vec<u8>, RchProfileError> {
    let fields = BTreeMap::from([(FIELD_EVENT, events)]);
    rmp_serde::to_vec_named(&fields).map_err(|error| RchProfileError::Encode(error.to_string()))
}

pub fn decode_events(bytes: &[u8]) -> Result<Vec<EventEnvelope>, RchProfileError> {
    Ok(decode_field::<OneOrMany<EventEnvelope>>(bytes, FIELD_EVENT)?.into_vec())
}

fn decode_field<T: DeserializeOwned>(bytes: &[u8], field: i64) -> Result<T, RchProfileError> {
    // rmpv first: other fields may hold binary data (FIELD_IMAGE) that JSON cannot.
    let mut fields: BTreeMap<i64, rmpv::Value> =
        rmp_serde::from_slice(bytes).map_err(|error| RchProfileError::Decode(error.to_string()))?;
    let value = fields
        .remove(&field)
        .ok_or(RchProfileError::MissingField(field))?;
    let value =
        serde_json::to_value(value).map_err(|error| RchProfileError::Decode(error.to_string()))?;
    serde_json::from_value(value).map_err(|error| RchProfileError::Decode(error.to_string()))
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
