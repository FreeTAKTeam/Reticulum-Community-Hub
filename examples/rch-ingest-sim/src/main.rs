use std::future::Future;
use std::pin::Pin;
use std::sync::Arc;
use std::task::{Context, Poll, Wake, Waker};

use r3akt_identity::NodeIdentity;
use r3akt_node::R3aktNode;
use r3akt_profile_rch::{
    MissionCommandEnvelope, RchSource, ack_to_result, decode_commands, encode_commands,
    encode_results,
};
use r3akt_protocol::{NodeId, Payload, Topic};
use r3akt_rch_core::RchCore;
use r3akt_router::TopicRouter;
use r3akt_store::MemoryStore;
use r3akt_transport_rns::MockTransport;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    block_on(run())
}

async fn run() -> Result<(), Box<dyn std::error::Error>> {
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

    let decoded = decode_commands(&inbound_fields)?;
    let envelope = decoded[0].to_protocol_envelope(Topic::new("mission-alpha"));
    let mut rch_core = RchCore::new();
    let core_outcome = rch_core.handle_command(&decoded[0]);
    let mission_sync_responses = rch_core.handle_mission_sync_command(&decoded[0]);

    let mut transport = MockTransport::new();
    transport.push_inbound(envelope)?;
    let identity = NodeIdentity::new(NodeId::new("rch-rust-runtime"), "RCH Rust Runtime", "dev");
    let store = MemoryStore::new();
    let mut router = TopicRouter::new();
    router.subscribe(
        NodeId::new("rch-rust-runtime"),
        &Topic::new("mission-alpha"),
    );

    let mut node = R3aktNode::new(identity, transport, store, router);
    let outcome = node.poll_once().await?;
    let (_, transport, _, _) = node.into_parts();
    let outbound = transport.outbound()?;
    let accepted_ack = outbound
        .iter()
        .find(|candidate| matches!(candidate.payload, Payload::AckAccepted(_)))
        .ok_or("runtime did not emit AckAccepted")?;
    let result = ack_to_result(accepted_ack)?;
    let result_fields = encode_results(&[result])?;

    println!("decoded RCH commands: {}", decoded.len());
    println!("runtime outcome: {:?}", outcome.status);
    println!("RCH core outcome: {:?}", core_outcome.result.status);
    println!(
        "RCH mission-sync responses: {}",
        mission_sync_responses.len()
    );
    println!("RCH topics after command: {}", rch_core.topics().len());
    println!("encoded FIELD_RESULTS bytes: {}", result_fields.len());
    Ok(())
}

fn block_on<F>(future: F) -> F::Output
where
    F: Future,
{
    struct NoopWake;

    impl Wake for NoopWake {
        fn wake(self: Arc<Self>) {}
    }

    let waker = Waker::from(Arc::new(NoopWake));
    let mut context = Context::from_waker(&waker);
    let mut future = Box::pin(future);

    loop {
        match Pin::new(&mut future).poll(&mut context) {
            Poll::Ready(output) => return output,
            Poll::Pending => std::thread::yield_now(),
        }
    }
}
