use super::*;
use r3akt_tak_connector::TakConnectionConfig;
use r3akt_tak_connector::{CotPayload, TakConnectorError};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::{thread, time::Duration as StdDuration};

#[derive(Clone)]
struct RetrySender {
    fail: Arc<AtomicBool>,
    sent: Arc<Mutex<Vec<String>>>,
}
impl TakCotSender for RetrySender {
    fn send(&self, payload: &CotPayload) -> Result<(), TakConnectorError> {
        if self.fail.load(Ordering::SeqCst) {
            return Err(TakConnectorError::Send("fixture offline".to_string()));
        }
        self.sent.lock().expect("sent").push(payload.xml.clone());
        Ok(())
    }
}
fn rch_fixture() -> (RchNorthboundClient, thread::JoinHandle<()>) {
    let (url, server) = crate::tests::spawn_rch_server(4, |request| {
        if request.starts_with("GET /Telemetry") {
            json!({"entries":[{"peer_destination":"peer-fixture","timestamp":1_714_000_001,"telemetry":{"location":{"latitude":45,"longitude":-63}}}]}).to_string()
        } else {
            assert!(request.starts_with("GET /Chat/Messages"));
            json!([{"Direction":"outbound","Content":"queued fixture","MessageID":"chat-fixture","CreatedAt":"2026-05-11T00:00:00Z"}]).to_string()
        }
    });
    (
        RchNorthboundClient::new(&url, None).expect("client"),
        server,
    )
}

#[test]
fn admitted_outbound_work_survives_temporary_sender_failure_without_duplication() {
    let (client, server) = rch_fixture();
    let sender = RetrySender {
        fail: Arc::new(AtomicBool::new(true)),
        sent: Arc::new(Mutex::new(Vec::new())),
    };
    let mut service = TakService::new(TakConnectionConfig::default(), 4, sender.clone());
    service.start();
    let mut state = BridgeState::default();
    assert!(bridge_rch_to_tak(&client, &mut service, &mut state).is_err());
    assert_eq!(service.status().queue.pending, 2);
    assert_eq!(service.status().total_sent, 0);
    sender.fail.store(false, Ordering::SeqCst);
    bridge_rch_to_tak(&client, &mut service, &mut state).expect("recovered cycle");
    assert_eq!(service.status().queue.pending, 0);
    assert_eq!(service.status().total_sent, 2);
    let sent = sender.sent.lock().expect("sent");
    assert_eq!(sent.len(), 2);
    assert!(sent[1].contains("queued fixture"));
    server.join().expect("server");
}

#[test]
fn queue_backpressure_does_not_mark_unadmitted_chat_as_delivered() {
    let (client, server) = rch_fixture();
    let sender = RetrySender {
        fail: Arc::new(AtomicBool::new(false)),
        sent: Arc::new(Mutex::new(Vec::new())),
    };
    let mut service = TakService::new(TakConnectionConfig::default(), 1, sender.clone());
    service.start();
    let mut state = BridgeState::default();
    assert!(bridge_rch_to_tak(&client, &mut service, &mut state).is_err());
    assert!(!state.chat.contains("chat-fixture"));
    assert_eq!(service.status().queue.pending, 1);
    bridge_rch_to_tak(&client, &mut service, &mut state).expect("recovered admission");
    assert_eq!(service.status().total_sent, 2);
    assert!(state.chat.contains("chat-fixture"));
    assert_eq!(sender.sent.lock().expect("sent").len(), 2);
    server.join().expect("server");
}

#[test]
fn inbound_post_failure_retains_the_event_and_retries_before_receiving_more() {
    use std::io::Write;
    struct Receiver(usize);
    impl TakCotReceiver for Receiver {
        fn receive(&mut self) -> Result<Option<Vec<u8>>, TakConnectorError> {
            self.0 += 1;
            Ok((self.0 == 1).then(|| br#"<event version="2.0" uid="fixture-peer" type="a-f-G-U-C" how="m-g" time="2026-05-11T00:00:00Z" start="2026-05-11T00:00:00Z" stale="2026-05-11T00:10:00Z"><point lat="45" lon="-63" hae="12" ce="5" le="5" /></event>"#.to_vec()))
        }
    }
    let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("listener");
    let client = RchNorthboundClient::new(
        &format!("http://{}", listener.local_addr().expect("address")),
        None,
    )
    .expect("client");
    let server = thread::spawn(move || {
        let mut bodies = Vec::new();
        for status in ["503 Unavailable", "201 Created"] {
            let (mut stream, _) = listener.accept().expect("accept");
            let request = crate::tests::read_http_request(&mut stream);
            assert!(request.starts_with("POST /api/markers"));
            assert!(
                request
                    .to_ascii_lowercase()
                    .contains("idempotency-key: rch-tak-cot:")
            );
            bodies.push(request.split_once("\r\n\r\n").expect("body").1.to_string());
            write!(
                stream,
                "HTTP/1.1 {status}\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{{}}"
            )
            .expect("response");
        }
        assert_eq!(bodies[0], bodies[1]);
    });
    let mut receiver = TakInboundService::new(Receiver(0), true);
    receiver.start();
    let mut state = BridgeState::default();
    assert!(bridge_tak_to_rch(&client, &mut receiver, &mut state).is_err());
    assert_eq!(state.pending_cot.len(), 1);
    assert_eq!(state.cot.keys.len(), 0);
    bridge_tak_to_rch(&client, &mut receiver, &mut state).expect("recovered POST");
    assert!(state.pending_cot.is_empty());
    assert_eq!(state.cot.keys.len(), 1);
    assert_eq!(receiver.status().total_received, 1);
    server.join().expect("server");
}

#[test]
fn bridge_deduplication_is_bounded() {
    let mut seen = SeenEntries::default();
    for index in 0..SEEN_CAPACITY + 10 {
        seen.insert(format!("fixture-{index}"));
    }
    assert_eq!(seen.keys.len(), SEEN_CAPACITY);
    assert_eq!(seen.order.len(), SEEN_CAPACITY);
    assert!(!seen.contains("fixture-0"));
    assert!(seen.contains("fixture-4105"));
}

#[test]
fn stable_snapshot_larger_than_seen_capacity_finishes_without_replay_or_chat_starvation() {
    use std::io::Write;
    let total = SEEN_CAPACITY + 600;
    let telemetry = json!({"entries": (0..total).map(|index| json!({
        "peer_destination": format!("peer-{index}"), "timestamp": 1_714_000_001,
        "telemetry": {"location": {"latitude": 45, "longitude": -63}}
    })).collect::<Vec<_>>()})
    .to_string();
    let chat = json!([{"Direction":"outbound","Content":"chat must make progress","MessageID":"chat-large-snapshot","CreatedAt":"2026-05-11T00:00:00Z"}]).to_string();
    let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("listener");
    listener.set_nonblocking(true).expect("nonblocking fixture");
    let client = RchNorthboundClient::new(
        &format!("http://{}", listener.local_addr().expect("address")),
        None,
    )
    .expect("client");
    let stop = Arc::new(AtomicBool::new(false));
    let stopping = Arc::clone(&stop);
    let server = thread::spawn(move || {
        while !stopping.load(Ordering::SeqCst) {
            match listener.accept() {
                Ok((mut stream, _)) => {
                    stream
                        .set_read_timeout(Some(StdDuration::from_secs(2)))
                        .expect("timeout");
                    let request = crate::tests::read_http_request(&mut stream);
                    let body = if request.starts_with("GET /Telemetry") {
                        &telemetry
                    } else {
                        &chat
                    };
                    write!(
                        stream,
                        "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                        body.len()
                    )
                    .expect("response");
                }
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    thread::sleep(StdDuration::from_millis(1));
                }
                Err(error) => panic!("fixture accept: {error}"),
            }
        }
    });
    let sender = RetrySender {
        fail: Arc::new(AtomicBool::new(false)),
        sent: Arc::new(Mutex::new(Vec::new())),
    };
    let mut service = TakService::new(TakConnectionConfig::default(), 256, sender.clone());
    service.start();
    let mut state = BridgeState::default();
    for _ in 0..total.div_ceil(255) + 3 {
        let _ = bridge_rch_to_tak(&client, &mut service, &mut state);
    }
    stop.store(true, Ordering::SeqCst);
    server.join().expect("server");
    let sent = sender.sent.lock().expect("sent");
    assert_eq!(
        sent.len(),
        total + 1,
        "every location and the chat is sent once"
    );
    assert!(
        sent.iter()
            .take(256)
            .any(|payload| payload.contains("chat must make progress")),
        "chat cannot wait behind a large telemetry snapshot"
    );
    assert!(
        sent.iter()
            .any(|payload| payload.contains(&format!("peer-{}", total - 1))),
        "tail of snapshot must be admitted"
    );
    assert!(state.telemetry.keys.len() <= SEEN_CAPACITY);
}

#[test]
fn lost_committed_http_response_retries_the_same_idempotent_operation() {
    use std::io::Write;
    let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("listener");
    let client = RchNorthboundClient::new(
        &format!("http://{}", listener.local_addr().expect("address")),
        None,
    )
    .expect("client");
    let server = thread::spawn(move || {
        let mut requests = Vec::new();
        for attempt in 0..2 {
            let (mut stream, _) = listener.accept().expect("accept");
            requests.push(crate::tests::read_http_request(&mut stream));
            if attempt == 0 {
                // Simulate a durable operation whose 201 response is lost in
                // transit: the body is truncated after the success headers.
                stream
                    .write_all(
                        b"HTTP/1.1 201 Created\r\nContent-Length: 100\r\nConnection: close\r\n\r\n",
                    )
                    .expect("lost response headers");
            } else {
                stream
                    .write_all(
                        b"HTTP/1.1 201 Created\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}",
                    )
                    .expect("replayed response");
            }
        }
        let key = |request: &str| {
            request
                .lines()
                .find(|line| line.to_ascii_lowercase().starts_with("idempotency-key:"))
                .expect("key")
                .to_string()
        };
        assert_eq!(key(&requests[0]), key(&requests[1]));
        assert_eq!(
            requests[0].split_once("\r\n\r\n").expect("body").1,
            requests[1].split_once("\r\n\r\n").expect("body").1
        );
    });
    let mut state = BridgeState::default();
    state.pending_cot.push_back((
        "fixture-peer:time:stale".to_string(),
        json!({"lat": 1, "lon": 2}),
    ));
    assert!(flush_pending_cot(&client, &mut state).is_err());
    assert_eq!(state.pending_cot.len(), 1);
    assert!(state.cot.keys.is_empty());
    flush_pending_cot(&client, &mut state).expect("replayed operation");
    assert!(state.pending_cot.is_empty());
    assert_eq!(state.cot.keys.len(), 1);
    server.join().expect("server");
}
