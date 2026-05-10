use std::future::Future;
use std::pin::Pin;
use std::sync::Arc;
use std::task::{Context, Poll, Wake, Waker};

use r3akt_identity::NodeIdentity;
use r3akt_node::{ProcessStatus, R3aktNode};
use r3akt_profile_rch::{
    CommandResultStatus, MissionCommandEnvelope, RchSource, ack_to_result, decode_commands,
    encode_commands,
};
use r3akt_protocol::{NodeId, Payload, Topic};
use r3akt_rch_core::RchCore;
use r3akt_router::TopicRouter;
use r3akt_store::MemoryStore;
use r3akt_transport_rns::MockTransport;

#[test]
fn rch_field_command_runs_through_runtime_and_returns_result_ack() {
    let fields = encode_commands(&[MissionCommandEnvelope {
        command_id: "cmd-it-1".to_string(),
        source: RchSource::new("agent-rns"),
        timestamp: "2026-03-06T12:00:00Z".to_string(),
        command_type: "topic.create".to_string(),
        args: serde_json::json!({ "topic_path": "mission-a", "topic_name": "Mission A" }),
        correlation_id: Some("corr-it-1".to_string()),
        topics: vec!["mission-a".to_string()],
    }])
    .expect("encode commands");
    let command = decode_commands(&fields).expect("decode").remove(0);
    let envelope = command.to_protocol_envelope(Topic::new("mission-a"));

    let mut transport = MockTransport::new();
    transport.push_inbound(envelope).expect("inbound");
    let store = MemoryStore::new();
    let mut router = TopicRouter::new();
    router.subscribe(NodeId::new("runtime"), &Topic::new("mission-a"));
    let identity = NodeIdentity::new(NodeId::new("runtime"), "Runtime", "test");
    let mut node = R3aktNode::new(identity, transport, store, router);

    let outcome = block_on(node.poll_once()).expect("poll");
    let (_, transport, store, router) = node.into_parts();
    let outbound = transport.outbound().expect("outbound");
    let accepted = outbound
        .iter()
        .find(|candidate| matches!(candidate.payload, Payload::AckAccepted(_)))
        .expect("accepted ack");
    let result = ack_to_result(accepted).expect("result");
    let mut rch_core = RchCore::new();
    let core_outcome = rch_core.handle_command(&command);

    assert_eq!(outcome.status, ProcessStatus::Accepted);
    assert_eq!(store.inbox_len(), 1);
    assert_eq!(router.routed().len(), 1);
    assert_eq!(result.status, CommandResultStatus::Accepted);
    assert_eq!(result.correlation_id.as_deref(), Some("corr-it-1"));
    assert_eq!(core_outcome.result.status, CommandResultStatus::Accepted);
    assert_eq!(rch_core.topics().len(), 1);
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
