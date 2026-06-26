#![allow(clippy::items_after_test_module, clippy::missing_errors_doc)]

use r3akt_identity::NodeIdentity;
use r3akt_protocol::{
    Ack, Command, Destination, HealthStatus, HealthTelemetry, Heartbeat, Payload, ProtocolEnvelope,
    TelemetryMetric, Topic, TopicMessage,
};
use r3akt_router::{Router, RouterError};
use r3akt_store::{AuditAction, AuditRecord, DurableStore, StoreError};
use r3akt_transport_rns::{MessageBus, TransportError};
use thiserror::Error;
use time::OffsetDateTime;

#[derive(Debug, Error)]
pub enum NodeError {
    #[error(transparent)]
    Store(#[from] StoreError),
    #[error(transparent)]
    Transport(#[from] TransportError),
    #[error(transparent)]
    Router(#[from] RouterError),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProcessStatus {
    NoMessage,
    Accepted,
    Rejected,
    Duplicate,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProcessOutcome {
    pub status: ProcessStatus,
    pub emitted_acks: usize,
    pub routed_recipients: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BatchOutcome {
    pub processed: Vec<ProcessOutcome>,
    pub reached_limit: bool,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct NodeMetrics {
    pub polled_empty: u64,
    pub accepted: u64,
    pub rejected: u64,
    pub duplicates: u64,
    pub routed: u64,
    pub emitted_acks: u64,
}

#[derive(Debug)]
pub struct R3aktNode<T, S, R> {
    identity: NodeIdentity,
    transport: T,
    store: S,
    router: R,
    metrics: NodeMetrics,
}

impl<T, S, R> R3aktNode<T, S, R>
where
    T: MessageBus,
    S: DurableStore,
    R: Router,
{
    #[must_use]
    pub fn new(identity: NodeIdentity, transport: T, store: S, router: R) -> Self {
        Self {
            identity,
            transport,
            store,
            router,
            metrics: NodeMetrics::default(),
        }
    }

    #[must_use]
    pub fn identity(&self) -> &NodeIdentity {
        &self.identity
    }

    #[must_use]
    pub fn parts(&self) -> (&T, &S, &R) {
        (&self.transport, &self.store, &self.router)
    }

    #[must_use]
    pub fn metrics(&self) -> NodeMetrics {
        self.metrics
    }

    pub fn into_parts(self) -> (NodeIdentity, T, S, R) {
        (self.identity, self.transport, self.store, self.router)
    }

    pub async fn publish(&mut self, envelope: ProtocolEnvelope) -> Result<(), NodeError> {
        self.router.dispatch(&envelope)?;
        self.store.put_outbox(envelope.clone()).await?;
        self.store
            .audit(AuditRecord::new(&envelope, AuditAction::Sent))
            .await?;
        self.transport.publish(envelope).await?;
        Ok(())
    }

    pub async fn poll_once(&mut self) -> Result<ProcessOutcome, NodeError> {
        let Some(envelope) = self.transport.poll().await? else {
            self.metrics.polled_empty = self.metrics.polled_empty.saturating_add(1);
            return Ok(ProcessOutcome {
                status: ProcessStatus::NoMessage,
                emitted_acks: 0,
                routed_recipients: 0,
            });
        };
        self.handle_inbound(envelope).await
    }

    pub async fn poll_batch(&mut self, max_messages: usize) -> Result<BatchOutcome, NodeError> {
        let mut processed = Vec::new();
        for _ in 0..max_messages {
            let outcome = self.poll_once().await?;
            if outcome.status == ProcessStatus::NoMessage {
                return Ok(BatchOutcome {
                    processed,
                    reached_limit: false,
                });
            }
            processed.push(outcome);
        }
        Ok(BatchOutcome {
            processed,
            reached_limit: true,
        })
    }

    pub async fn handle_inbound(
        &mut self,
        envelope: ProtocolEnvelope,
    ) -> Result<ProcessOutcome, NodeError> {
        if let Err(error) = envelope.validate_basic(OffsetDateTime::now_utc()) {
            self.store
                .audit(
                    AuditRecord::new(&envelope, AuditAction::Rejected)
                        .with_detail(error.to_string()),
                )
                .await?;
            self.emit_ack(envelope, AckKind::Rejected(error.to_string()))
                .await?;
            self.metrics.rejected = self.metrics.rejected.saturating_add(1);
            self.metrics.emitted_acks = self.metrics.emitted_acks.saturating_add(1);
            return Ok(ProcessOutcome {
                status: ProcessStatus::Rejected,
                emitted_acks: 1,
                routed_recipients: 0,
            });
        }

        self.store
            .audit(AuditRecord::new(&envelope, AuditAction::Received))
            .await?;
        let write = self.store.put_inbox(envelope.clone()).await?;
        if write.duplicate {
            self.store
                .audit(AuditRecord::new(&envelope, AuditAction::DroppedDuplicate))
                .await?;
            self.metrics.duplicates = self.metrics.duplicates.saturating_add(1);
            return Ok(ProcessOutcome {
                status: ProcessStatus::Duplicate,
                emitted_acks: 0,
                routed_recipients: 0,
            });
        }
        self.store
            .audit(AuditRecord::new(&envelope, AuditAction::PersistedInbound))
            .await?;

        self.emit_ack(envelope.clone(), AckKind::Accepted).await?;
        let recipients = self.router.dispatch(&envelope)?;
        self.store
            .audit(AuditRecord::new(&envelope, AuditAction::Routed))
            .await?;

        let mut emitted_acks = 1;
        if should_complete(&envelope) {
            self.emit_ack(envelope, AckKind::Completed).await?;
            emitted_acks += 1;
        }
        self.metrics.accepted = self.metrics.accepted.saturating_add(1);
        self.metrics.routed = self.metrics.routed.saturating_add(1);
        self.metrics.emitted_acks = self
            .metrics
            .emitted_acks
            .saturating_add(u64::try_from(emitted_acks).unwrap_or(u64::MAX));

        Ok(ProcessOutcome {
            status: ProcessStatus::Accepted,
            emitted_acks,
            routed_recipients: recipients.len(),
        })
    }

    pub async fn heartbeat(
        &mut self,
        topic: Topic,
        sequence: u64,
    ) -> Result<ProtocolEnvelope, NodeError> {
        let envelope = ProtocolEnvelope::new(
            self.identity.id.clone(),
            Destination::Topic(topic.clone()),
            topic,
            Payload::Heartbeat(Heartbeat {
                status: HealthStatus::Nominal,
                sequence,
            }),
        );
        self.publish(envelope.clone()).await?;
        Ok(envelope)
    }

    pub async fn hello(&mut self, topic: Topic) -> Result<ProtocolEnvelope, NodeError> {
        let envelope = ProtocolEnvelope::new(
            self.identity.id.clone(),
            Destination::Topic(topic.clone()),
            topic,
            Payload::NodeHello(r3akt_protocol::NodeHello {
                display_name: self.identity.display_name.clone(),
                capabilities: vec!["r3akt-runtime".to_string()],
            }),
        );
        self.publish(envelope.clone()).await?;
        Ok(envelope)
    }

    pub async fn telemetry(
        &mut self,
        topic: Topic,
        metrics: Vec<TelemetryMetric>,
    ) -> Result<ProtocolEnvelope, NodeError> {
        let envelope = ProtocolEnvelope::new(
            self.identity.id.clone(),
            Destination::Topic(topic.clone()),
            topic,
            Payload::HealthTelemetry(HealthTelemetry {
                status: HealthStatus::Nominal,
                metrics,
                observed_at: OffsetDateTime::now_utc(),
            }),
        );
        self.publish(envelope.clone()).await?;
        Ok(envelope)
    }

    pub async fn topic_message(
        &mut self,
        topic: Topic,
        body: impl Into<String>,
    ) -> Result<ProtocolEnvelope, NodeError> {
        let envelope = ProtocolEnvelope::new(
            self.identity.id.clone(),
            Destination::Topic(topic.clone()),
            topic,
            Payload::TopicMessage(TopicMessage {
                body: body.into(),
                content_type: "text/plain".to_string(),
                correlation_id: None,
                attachments: Vec::new(),
            }),
        );
        self.publish(envelope.clone()).await?;
        Ok(envelope)
    }

    pub async fn command(
        &mut self,
        destination: Destination,
        topic: Topic,
        command: Command,
    ) -> Result<ProtocolEnvelope, NodeError> {
        let envelope = ProtocolEnvelope::new(
            self.identity.id.clone(),
            destination,
            topic,
            Payload::Command(command),
        );
        self.publish(envelope.clone()).await?;
        Ok(envelope)
    }

    async fn emit_ack(
        &mut self,
        envelope: ProtocolEnvelope,
        kind: AckKind,
    ) -> Result<(), NodeError> {
        let ack = Ack::for_envelope(
            &envelope,
            match &kind {
                AckKind::Accepted | AckKind::Completed => None,
                AckKind::Rejected(reason) => Some(reason.clone()),
            },
        );
        let payload = match kind {
            AckKind::Accepted => Payload::AckAccepted(ack),
            AckKind::Rejected(_) => Payload::AckRejected(ack),
            AckKind::Completed => Payload::AckCompleted(ack),
        };
        let ack_envelope = ProtocolEnvelope::new(
            self.identity.id.clone(),
            Destination::Node(envelope.source.clone()),
            Topic::new("acks"),
            payload,
        )
        .with_ttl(300);
        self.store.put_outbox(ack_envelope.clone()).await?;
        self.store
            .audit(AuditRecord::new(&ack_envelope, AuditAction::AckEmitted))
            .await?;
        self.transport.publish(ack_envelope).await?;
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum AckKind {
    Accepted,
    Rejected(String),
    Completed,
}

fn should_complete(envelope: &ProtocolEnvelope) -> bool {
    matches!(
        envelope.payload,
        Payload::Command(_) | Payload::TopicMessage(_)
    )
}

#[cfg(test)]
mod tests {
    use r3akt_protocol::{NodeId, TopicMessage};
    use r3akt_router::TopicRouter;
    use r3akt_store::MemoryStore;
    use r3akt_transport_rns::MockTransport;

    use super::*;

    fn node_with_inbound(
        envelope: ProtocolEnvelope,
    ) -> R3aktNode<MockTransport, MemoryStore, TopicRouter> {
        let identity = NodeIdentity::new(NodeId::new("server"), "Server", "test-key");
        let mut transport = MockTransport::new();
        transport.push_inbound(envelope).expect("queue inbound");
        let store = MemoryStore::new();
        let mut router = TopicRouter::new();
        router.subscribe(NodeId::new("server"), &Topic::new("ops"));
        R3aktNode::new(identity, transport, store, router)
    }

    fn inbound_topic_message() -> ProtocolEnvelope {
        ProtocolEnvelope::new(
            NodeId::new("agent"),
            Destination::Topic(Topic::new("ops")),
            Topic::new("ops"),
            Payload::TopicMessage(TopicMessage {
                body: "hello".to_string(),
                content_type: "text/plain".to_string(),
                correlation_id: Some("corr-1".to_string()),
                attachments: Vec::new(),
            }),
        )
        .with_dedupe_key("agent:ops:corr-1")
    }

    #[test]
    fn inbound_message_is_persisted_before_processing_and_acknowledged() {
        let envelope = inbound_topic_message();
        let mut node = node_with_inbound(envelope);

        let outcome = crate::test_block_on(node.poll_once()).expect("poll");

        assert_eq!(outcome.status, ProcessStatus::Accepted);
        assert_eq!(outcome.emitted_acks, 2);
        assert_eq!(node.metrics().accepted, 1);
        assert_eq!(node.metrics().emitted_acks, 2);
        let (_, transport, store, router) = node.into_parts();
        let outbound = transport.outbound().expect("outbound");
        assert_eq!(store.inbox_len(), 1);
        assert_eq!(router.routed().len(), 1);
        assert!(
            store
                .audit_records()
                .iter()
                .position(|record| record.action == AuditAction::PersistedInbound)
                .expect("persist audit")
                < store
                    .audit_records()
                    .iter()
                    .position(|record| record.action == AuditAction::Routed)
                    .expect("route audit")
        );
        assert!(matches!(outbound[0].payload, Payload::AckAccepted(_)));
        assert!(matches!(outbound[1].payload, Payload::AckCompleted(_)));
    }

    #[test]
    fn duplicate_message_is_ignored() {
        let envelope = inbound_topic_message();
        let mut node = node_with_inbound(envelope.clone());

        crate::test_block_on(node.handle_inbound(envelope.clone())).expect("first");
        let outcome = crate::test_block_on(node.handle_inbound(envelope)).expect("duplicate");
        let (_, transport, store, router) = node.into_parts();

        assert_eq!(outcome.status, ProcessStatus::Duplicate);
        assert_eq!(store.inbox_len(), 1);
        assert_eq!(router.routed().len(), 1);
        assert_eq!(transport.outbound().expect("outbound").len(), 2);
    }

    #[test]
    fn rejected_ack_is_emitted_for_invalid_envelope() {
        let mut envelope = inbound_topic_message();
        envelope.ttl_seconds = 0;
        let mut node = node_with_inbound(envelope);

        let outcome = crate::test_block_on(node.poll_once()).expect("poll");
        let (_, transport, store, router) = node.into_parts();

        assert_eq!(outcome.status, ProcessStatus::Rejected);
        assert_eq!(store.inbox_len(), 0);
        assert!(router.routed().is_empty());
        assert!(matches!(
            transport.outbound().expect("outbound")[0].payload,
            Payload::AckRejected(_)
        ));
    }

    #[test]
    fn poll_batch_processes_up_to_explicit_limit() {
        let first = inbound_topic_message().with_dedupe_key("agent:ops:first");
        let second = inbound_topic_message().with_dedupe_key("agent:ops:second");
        let identity = NodeIdentity::new(NodeId::new("server"), "Server", "test-key");
        let mut transport = MockTransport::new();
        transport.push_inbound(first).expect("first");
        transport.push_inbound(second).expect("second");
        let store = MemoryStore::new();
        let mut router = TopicRouter::new();
        router.subscribe(NodeId::new("server"), &Topic::new("ops"));
        let mut node = R3aktNode::new(identity, transport, store, router);

        let batch = crate::test_block_on(node.poll_batch(1)).expect("batch");

        assert_eq!(batch.processed.len(), 1);
        assert!(batch.reached_limit);
        assert_eq!(node.metrics().accepted, 1);
    }
}

#[cfg(test)]
pub fn test_block_on<F>(future: F) -> F::Output
where
    F: std::future::Future,
{
    use std::pin::Pin;
    use std::task::{Context, Poll, Waker};

    let mut context = Context::from_waker(Waker::noop());
    let mut future = Box::pin(future);

    loop {
        match Pin::new(&mut future).poll(&mut context) {
            Poll::Ready(output) => return output,
            Poll::Pending => std::thread::yield_now(),
        }
    }
}
