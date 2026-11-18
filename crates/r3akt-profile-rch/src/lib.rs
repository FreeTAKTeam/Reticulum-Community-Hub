#![allow(clippy::missing_errors_doc)]
#![cfg_attr(
    not(test),
    deny(
        clippy::expect_used,
        clippy::let_underscore_must_use,
        clippy::panic,
        clippy::unwrap_used
    )
)]

use r3akt_protocol::{Command, Destination, NodeId, Payload, ProtocolEnvelope, Topic};
use serde::{Deserialize, Serialize};
use thiserror::Error;

mod codec;
mod commands;
mod fields;
mod mecp;
pub mod teams;
#[cfg(test)]
mod tests;
pub use codec::{
    ack_to_result, command_from_protocol, decode_commands, decode_events, decode_results,
    encode_events, encode_results,
};
pub use commands::{
    encode_commands, encode_commands_for_team, encode_commands_for_team_with_image,
};
pub use fields::{FIELD_COMMANDS, FIELD_EVENT, FIELD_GROUP, FIELD_IMAGE, FIELD_RESULTS};
pub use mecp::{
    DecodedMecpCode, DecodedMecpMessage, MecpCoordinates, MecpDecodedExtras, decode_mecp_message,
    is_mecp_category_code, mecp_category_label, mecp_event_label, mecp_severity_label,
    mecp_severity_status,
};

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
