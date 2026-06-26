use std::future::Future;
use std::pin::Pin;
use std::task::{Context, Poll, Waker};

use r3akt_identity::NodeIdentity;
use r3akt_node::R3aktNode;
use r3akt_protocol::{
    Command, Destination, NodeId, Payload, ProtocolEnvelope, TelemetryMetric, Topic, TopicMessage,
};
use r3akt_router::TopicRouter;
use r3akt_store::MemoryStore;
use r3akt_transport_rns::MockTransport;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    block_on(run())
}

async fn run() -> Result<(), Box<dyn std::error::Error>> {
    let identity = NodeIdentity::new(NodeId::new("sim-server"), "Sim Server", "lxmf-rs-dev-key");
    let mut transport = MockTransport::new();
    let heartbeat = ProtocolEnvelope::new(
        NodeId::new("sim-agent"),
        Destination::Topic(Topic::new("heartbeat")),
        Topic::new("heartbeat"),
        Payload::Heartbeat(r3akt_protocol::Heartbeat {
            status: r3akt_protocol::HealthStatus::Nominal,
            sequence: 1,
        }),
    )
    .with_dedupe_key("sim-agent:heartbeat:1");
    let topic_message = ProtocolEnvelope::new(
        NodeId::new("sim-agent"),
        Destination::Topic(Topic::new("ops")),
        Topic::new("ops"),
        Payload::TopicMessage(TopicMessage {
            body: "field check complete".to_string(),
            content_type: "text/plain".to_string(),
            correlation_id: Some("sim-topic-1".to_string()),
            attachments: Vec::new(),
        }),
    )
    .with_dedupe_key("sim-agent:ops:sim-topic-1");
    transport.push_inbound(heartbeat)?;
    transport.push_inbound(topic_message)?;

    let store = MemoryStore::new();
    let mut router = TopicRouter::new();
    router.subscribe(NodeId::new("sim-server"), &Topic::new("heartbeat"));
    router.subscribe(NodeId::new("sim-server"), &Topic::new("ops"));
    router.subscribe(NodeId::new("sim-agent"), &Topic::new("commands"));

    let mut node = R3aktNode::new(identity, transport, store, router);
    let first = node.poll_once().await?;
    let second = node.poll_once().await?;
    let command = node
        .command(
            Destination::Node(NodeId::new("sim-agent")),
            Topic::new("commands"),
            Command {
                name: "ping".to_string(),
                args: serde_json::Value::Null,
                correlation_id: Some("sim-command-1".to_string()),
            },
        )
        .await?;
    let telemetry = node
        .telemetry(
            Topic::new("heartbeat"),
            vec![TelemetryMetric::new("battery", 97.0, "%")],
        )
        .await?;

    println!(
        "processed inbound outcomes: {:?}, {:?}",
        first.status, second.status
    );
    println!("sent command: {}", command.id);
    println!("sent telemetry: {}", telemetry.id);
    Ok(())
}

fn block_on<F>(future: F) -> F::Output
where
    F: Future,
{
    let mut context = Context::from_waker(Waker::noop());
    let mut future = Box::pin(future);

    loop {
        match Pin::new(&mut future).poll(&mut context) {
            Poll::Ready(output) => return output,
            Poll::Pending => std::thread::yield_now(),
        }
    }
}
