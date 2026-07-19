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

use std::fmt;

use chrono::{DateTime, Duration, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use thiserror::Error;
use uuid::Uuid;

pub const SCHEMA_VERSION: u16 = 1;

#[derive(Debug, Error)]
pub enum ProtocolError {
    #[error("protocol encode failed: {0}")]
    Encode(String),
    #[error("protocol decode failed: {0}")]
    Decode(String),
    #[error("missing required field: {0}")]
    MissingField(&'static str),
    #[error("ttl must be greater than zero")]
    InvalidTtl,
    #[error("envelope has expired")]
    Expired,
    #[error("unsupported schema version: {0}")]
    UnsupportedSchema(u16),
}

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct NodeId(String);

impl NodeId {
    #[must_use]
    pub fn new(value: impl Into<String>) -> Self {
        Self(value.into())
    }

    #[must_use]
    pub fn as_str(&self) -> &str {
        &self.0
    }

    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.0.trim().is_empty()
    }
}

impl fmt::Display for NodeId {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.0)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Topic(String);

impl Topic {
    #[must_use]
    pub fn new(value: impl Into<String>) -> Self {
        Self(value.into())
    }

    #[must_use]
    pub fn as_str(&self) -> &str {
        &self.0
    }

    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.0.trim().is_empty()
    }
}

impl fmt::Display for Topic {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.0)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct EnvelopeId(Uuid);

impl EnvelopeId {
    #[must_use]
    pub fn new() -> Self {
        Self(Uuid::now_v7())
    }

    #[must_use]
    pub fn from_uuid(value: Uuid) -> Self {
        Self(value)
    }

    #[must_use]
    pub fn as_uuid(self) -> Uuid {
        self.0
    }
}

impl Default for EnvelopeId {
    fn default() -> Self {
        Self::new()
    }
}

impl fmt::Display for EnvelopeId {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}", self.0)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum Destination {
    Node(NodeId),
    Topic(Topic),
    Broadcast,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Envelope<T> {
    pub schema_version: u16,
    pub id: EnvelopeId,
    pub dedupe_key: Option<String>,
    pub source: NodeId,
    pub destination: Destination,
    pub topic: Topic,
    pub timestamp: DateTime<Utc>,
    pub ttl_seconds: u32,
    pub payload: T,
}

impl<T> Envelope<T> {
    #[must_use]
    pub fn new(source: NodeId, destination: Destination, topic: Topic, payload: T) -> Self {
        Self {
            schema_version: SCHEMA_VERSION,
            id: EnvelopeId::new(),
            dedupe_key: None,
            source,
            destination,
            topic,
            timestamp: Utc::now(),
            ttl_seconds: 300,
            payload,
        }
    }

    #[must_use]
    pub fn with_ttl(mut self, ttl_seconds: u32) -> Self {
        self.ttl_seconds = ttl_seconds;
        self
    }

    #[must_use]
    pub fn with_dedupe_key(mut self, dedupe_key: impl Into<String>) -> Self {
        self.dedupe_key = Some(dedupe_key.into());
        self
    }

    #[must_use]
    pub fn stable_dedupe_key(&self) -> String {
        self.dedupe_key
            .clone()
            .filter(|value| !value.trim().is_empty())
            .unwrap_or_else(|| self.id.to_string())
    }

    #[must_use]
    pub fn map_payload<U>(self, payload: U) -> Envelope<U> {
        Envelope {
            schema_version: self.schema_version,
            id: self.id,
            dedupe_key: self.dedupe_key,
            source: self.source,
            destination: self.destination,
            topic: self.topic,
            timestamp: self.timestamp,
            ttl_seconds: self.ttl_seconds,
            payload,
        }
    }

    pub fn validate_basic(&self, now: DateTime<Utc>) -> Result<(), ProtocolError> {
        if self.schema_version != SCHEMA_VERSION {
            return Err(ProtocolError::UnsupportedSchema(self.schema_version));
        }
        if self.source.is_empty() {
            return Err(ProtocolError::MissingField("source"));
        }
        if self.topic.is_empty() {
            return Err(ProtocolError::MissingField("topic"));
        }
        if self.ttl_seconds == 0 {
            return Err(ProtocolError::InvalidTtl);
        }
        let expires_at = self.timestamp + Duration::seconds(i64::from(self.ttl_seconds));
        if expires_at < now {
            return Err(ProtocolError::Expired);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum Payload {
    NodeHello(NodeHello),
    Heartbeat(Heartbeat),
    HealthTelemetry(HealthTelemetry),
    TelemetrySample(TelemetrySample),
    TopicMessage(TopicMessage),
    Command(Command),
    AckAccepted(Ack),
    AckRejected(Ack),
    AckCompleted(Ack),
}

pub type ProtocolEnvelope = Envelope<Payload>;

impl ProtocolEnvelope {
    pub fn encode_msgpack(&self) -> Result<Vec<u8>, ProtocolError> {
        rmp_serde::to_vec_named(self).map_err(|error| ProtocolError::Encode(error.to_string()))
    }

    pub fn decode_msgpack(bytes: &[u8]) -> Result<Self, ProtocolError> {
        rmp_serde::from_slice(bytes).map_err(|error| ProtocolError::Decode(error.to_string()))
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NodeHello {
    pub display_name: String,
    pub capabilities: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Heartbeat {
    pub status: HealthStatus,
    pub sequence: u64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct HealthTelemetry {
    pub status: HealthStatus,
    pub metrics: Vec<TelemetryMetric>,
    pub observed_at: DateTime<Utc>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TelemetrySample {
    pub telemetry: Value,
    pub timestamp_s: Option<i64>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TopicMessage {
    pub body: String,
    pub content_type: String,
    pub correlation_id: Option<String>,
    #[serde(default)]
    pub attachments: Vec<TopicAttachment>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TopicAttachment {
    pub name: String,
    pub data: Vec<u8>,
    #[serde(default)]
    pub media_type: Option<String>,
    #[serde(default = "default_topic_attachment_category")]
    pub category: String,
}

fn default_topic_attachment_category() -> String {
    "file".to_string()
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Command {
    pub name: String,
    pub args: serde_json::Value,
    pub correlation_id: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Ack {
    pub envelope_id: EnvelopeId,
    pub detail: Option<String>,
    pub correlation_id: Option<String>,
}

impl Ack {
    #[must_use]
    pub fn for_envelope(envelope: &ProtocolEnvelope, detail: Option<String>) -> Self {
        Self {
            envelope_id: envelope.id,
            detail,
            correlation_id: envelope.correlation_id(),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum HealthStatus {
    Nominal,
    Degraded,
    Offline,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TelemetryMetric {
    pub name: String,
    pub value: f64,
    pub unit: String,
}

impl TelemetryMetric {
    #[must_use]
    pub fn new(name: impl Into<String>, value: f64, unit: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            value,
            unit: unit.into(),
        }
    }
}

impl ProtocolEnvelope {
    #[must_use]
    pub fn correlation_id(&self) -> Option<String> {
        match &self.payload {
            Payload::TopicMessage(payload) => payload.correlation_id.clone(),
            Payload::Command(payload) => payload.correlation_id.clone(),
            Payload::AckAccepted(payload)
            | Payload::AckRejected(payload)
            | Payload::AckCompleted(payload) => payload.correlation_id.clone(),
            Payload::NodeHello(_)
            | Payload::Heartbeat(_)
            | Payload::HealthTelemetry(_)
            | Payload::TelemetrySample(_) => None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn msgpack_round_trip_preserves_envelope() {
        let envelope = ProtocolEnvelope::new(
            NodeId::new("alpha"),
            Destination::Topic(Topic::new("health")),
            Topic::new("health"),
            Payload::Heartbeat(Heartbeat {
                status: HealthStatus::Nominal,
                sequence: 7,
            }),
        )
        .with_dedupe_key("alpha:heartbeat:7");

        let encoded = envelope.encode_msgpack().expect("encode");
        let decoded = ProtocolEnvelope::decode_msgpack(&encoded).expect("decode");

        assert_eq!(decoded, envelope);
        assert_eq!(decoded.stable_dedupe_key(), "alpha:heartbeat:7");
    }

    #[test]
    fn validation_rejects_expired_envelope() {
        let mut envelope = ProtocolEnvelope::new(
            NodeId::new("alpha"),
            Destination::Broadcast,
            Topic::new("health"),
            Payload::Heartbeat(Heartbeat {
                status: HealthStatus::Nominal,
                sequence: 1,
            }),
        )
        .with_ttl(1);
        envelope.timestamp = Utc::now() - Duration::seconds(5);

        assert!(matches!(
            envelope.validate_basic(Utc::now()),
            Err(ProtocolError::Expired)
        ));
    }
}
