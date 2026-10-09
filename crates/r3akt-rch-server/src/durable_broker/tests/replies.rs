use super::*;
use rns_rpc::rpc::zmq::{ZmqRpcEnvelope, encode_envelope};
use zeromq::{PushSocket, SocketSend};

pub(super) async fn deliver(request: ZmqRpcEnvelope, payload: Vec<u8>) -> std::io::Result<()> {
    // Match the daemon's one-second response budget, including the handshake.
    // The socket's default 30-second connect timeout otherwise blocks every later request.
    tokio::time::timeout(Duration::from_secs(1), async {
        let mut socket = PushSocket::new();
        socket
            .connect(request.response_endpoint.as_deref().unwrap())
            .await
            .map_err(std::io::Error::other)?;
        tokio::time::sleep(Duration::from_millis(50)).await;
        let reply = ZmqRpcEnvelope::response(request.session_id, request.request_id, payload);
        socket
            .send(encode_envelope(&reply)?.into())
            .await
            .map_err(std::io::Error::other)
    })
    .await
    .map_err(|error| std::io::Error::new(std::io::ErrorKind::TimedOut, error))?
}

#[test]
fn abandoned_reply_does_not_block_the_next_broker_request() {
    let dir = std::env::temp_dir().join(format!("rch-abandoned-reply-{}", Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    let fixture = Fixture::open(&dir.join("daemon.db"));
    let state = fixture.state(&dir.join("rch.db"), &dir.join("identity"));
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();
    let command = runtime.block_on(async {
        let mut command = PushSocket::new();
        command.connect(&fixture.endpoint).await.unwrap();
        tokio::time::sleep(Duration::from_millis(50)).await;
        let request = ZmqRpcEnvelope::request(
            "abandoned-client",
            1,
            endpoint(), // No listener: the originating client has already gone away.
            rns_rpc::e2e_harness::build_rpc_frame(1, "status", None).unwrap(),
            None,
        );
        command
            .send(encode_envelope(&request).unwrap().into())
            .await
            .unwrap();
        command
    });
    let started = std::time::Instant::now();
    runtime.block_on(async {
        tokio::time::timeout(Duration::from_secs(3), async {
            while fixture.reply_failures.load(Ordering::Acquire) == 0 {
                tokio::time::sleep(Duration::from_millis(5)).await;
            }
        })
        .await
        .expect("abandoned reply must not use the 30-second socket timeout");
    });
    let projection = plane(&state).unwrap().broker_announces().unwrap();
    assert!(projection.get("announces").is_some());
    assert!(started.elapsed() < Duration::from_secs(3));
    plane(&state).unwrap().shutdown().unwrap();
    runtime.block_on(command.close());
    drop(state);
    drop(fixture);
    std::fs::remove_dir_all(dir).unwrap();
}
