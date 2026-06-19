#![allow(clippy::missing_errors_doc)]

use std::collections::{HashMap, HashSet};

use r3akt_protocol::{Destination, NodeId, ProtocolEnvelope, Topic};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum RouterError {
    #[error("no route for envelope topic")]
    NoRoute,
}

pub trait Fanout {
    fn fanout(&self, envelope: &ProtocolEnvelope) -> Result<Vec<NodeId>, RouterError>;
}

pub trait Router: Fanout {
    fn dispatch(&mut self, envelope: &ProtocolEnvelope) -> Result<Vec<NodeId>, RouterError>;
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RoutedEnvelope {
    pub topic: Topic,
    pub envelope_id: r3akt_protocol::EnvelopeId,
    pub recipients: Vec<NodeId>,
}

#[derive(Debug, Clone, Default)]
pub struct TopicRouter {
    subscriptions: HashMap<Topic, HashSet<NodeId>>,
    routed: Vec<RoutedEnvelope>,
}

impl TopicRouter {
    #[must_use]
    pub fn new() -> Self {
        Self::default()
    }

    pub fn subscribe(&mut self, node_id: NodeId, topic: &Topic) {
        self.subscriptions
            .entry(canonical_topic(topic))
            .or_default()
            .insert(node_id);
    }

    pub fn unsubscribe(&mut self, node_id: &NodeId, topic: &Topic) {
        if let Some(nodes) = self.subscriptions.get_mut(&canonical_topic(topic)) {
            nodes.remove(node_id);
        }
    }

    #[must_use]
    pub fn routed(&self) -> &[RoutedEnvelope] {
        &self.routed
    }
}

impl Fanout for TopicRouter {
    fn fanout(&self, envelope: &ProtocolEnvelope) -> Result<Vec<NodeId>, RouterError> {
        match &envelope.destination {
            Destination::Node(node_id) => Ok(vec![node_id.clone()]),
            Destination::Broadcast | Destination::Topic(_) => {
                let nodes = self
                    .subscriptions
                    .get(&canonical_topic(&envelope.topic))
                    .ok_or(RouterError::NoRoute)?;
                Ok(nodes.iter().cloned().collect())
            }
        }
    }
}

#[must_use]
pub fn normalize_topic_id(value: &str) -> String {
    let mut normalized = value.trim().replace('\\', "/").to_ascii_lowercase();
    while normalized.contains("//") {
        normalized = normalized.replace("//", "/");
    }
    normalized.trim_matches('/').to_string()
}

fn canonical_topic(topic: &Topic) -> Topic {
    Topic::new(normalize_topic_id(topic.as_str()))
}

impl Router for TopicRouter {
    fn dispatch(&mut self, envelope: &ProtocolEnvelope) -> Result<Vec<NodeId>, RouterError> {
        let recipients = self.fanout(envelope)?;
        self.routed.push(RoutedEnvelope {
            topic: envelope.topic.clone(),
            envelope_id: envelope.id,
            recipients: recipients.clone(),
        });
        Ok(recipients)
    }
}

#[cfg(test)]
mod tests {
    use r3akt_protocol::{Command, Payload};

    use super::*;

    #[test]
    fn topic_subscribers_receive_matching_envelope() {
        let mut router = TopicRouter::new();
        let topic = Topic::new("telemetry");
        let node = NodeId::new("bravo");
        router.subscribe(node.clone(), &topic);

        let envelope = ProtocolEnvelope::new(
            NodeId::new("alpha"),
            Destination::Topic(topic),
            Topic::new("telemetry"),
            Payload::Command(Command {
                name: "ping".to_string(),
                args: serde_json::Value::Null,
                correlation_id: None,
            }),
        );

        assert_eq!(router.dispatch(&envelope).expect("route"), vec![node]);
        assert_eq!(router.routed().len(), 1);
    }

    #[test]
    fn topic_ids_are_canonicalized_like_rch_routes() {
        let mut router = TopicRouter::new();
        let node = NodeId::new("bravo");
        router.subscribe(node.clone(), &Topic::new(" /Ops//Team "));

        let envelope = ProtocolEnvelope::new(
            NodeId::new("alpha"),
            Destination::Topic(Topic::new("ops/team")),
            Topic::new("\\OPS\\TEAM\\"),
            Payload::Command(Command {
                name: "ping".to_string(),
                args: serde_json::Value::Null,
                correlation_id: None,
            }),
        );

        assert_eq!(router.dispatch(&envelope).expect("route"), vec![node]);
        assert_eq!(normalize_topic_id(" /Ops//Team "), "ops/team");
    }
}
