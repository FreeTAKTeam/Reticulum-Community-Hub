use rns_rpc::rpc::{RpcDaemon, RpcEvent};

use super::*;

#[test]
fn zmq_event_consumer_keeps_receiving_after_retained_window_fills() {
    const BATCH_SIZE: usize = 64;
    const BATCHES: usize = 20;
    let (command_endpoint, response_endpoint) = unused_zmq_endpoint_pair_v4();
    let server_endpoint = command_endpoint.clone();
    let server = thread::spawn(move || {
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("test runtime");
        runtime.block_on(async move {
            let daemon = RpcDaemon::test_instance();
            let mut commands = PullSocket::new();
            commands.bind(&server_endpoint).await.expect("bind commands");
            let mut batch_index = 0;
            for _ in 0..=BATCHES {
                let envelope = tokio::time::timeout(
                    Duration::from_secs(5),
                    recv_zmq_request_envelope(&mut commands),
                )
                .await
                .expect("request deadline")
                .expect("request envelope");
                let request: ReticulumdRpcRequest =
                    decode_frame(&envelope.payload).expect("decode request");
                if request.method == "sdk_poll_events_v2" {
                    for index in 0..BATCH_SIZE {
                        daemon.emit_event(RpcEvent {
                            event_type: "inbound".to_string(),
                            payload: serde_json::json!({"marker": batch_index * BATCH_SIZE + index}),
                        });
                    }
                    batch_index += 1;
                }
                let payload = daemon
                    .handle_framed_request_for_session(&envelope.session_id, &envelope.payload)
                    .expect("daemon response");
                let mut response = PushSocket::new();
                response
                    .connect(envelope.response_endpoint.as_deref().expect("response endpoint"))
                    .await
                    .expect("connect response");
                tokio::time::sleep(Duration::from_millis(50)).await;
                response
                    .send(ZmqMessage::from(
                        zmq::encode_envelope(&ZmqRpcEnvelope::response(
                            envelope.session_id,
                            envelope.request_id,
                            payload,
                        ))
                        .expect("encode response"),
                    ))
                    .await
                    .expect("send response");
            }
            assert_eq!(batch_index, BATCHES);
        });
    });
    let data_plane =
        ZmqDataPlane::new_with_timeout(command_endpoint, response_endpoint, Duration::from_secs(3))
            .expect("data plane");
    let mut cursor = None;
    let mut markers = Vec::new();
    for _ in 0..BATCHES {
        let batch = data_plane
            .poll_events(cursor.clone(), BATCH_SIZE)
            .expect("poll events");
        markers.extend(
            batch
                .events
                .iter()
                .map(|event| event.payload["marker"].clone()),
        );
        assert_ne!(batch.next_cursor, cursor, "cursor must keep advancing");
        cursor = batch.next_cursor;
    }
    data_plane.shutdown().expect("shutdown data plane");
    server.join().expect("server joined");
    let expected = (0..BATCH_SIZE * BATCHES)
        .map(|index| serde_json::json!(index))
        .collect::<Vec<_>>();
    assert_eq!(
        markers, expected,
        "every event must reach the continuous consumer"
    );
}
