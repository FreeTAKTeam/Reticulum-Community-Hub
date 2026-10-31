use std::io::{Read, Write};
use std::net::{Shutdown, TcpListener, TcpStream};
use std::sync::mpsc;

use super::*;

#[test]
fn service_rejects_non_finite_or_non_positive_intervals() {
    for interval in ["NaN", "inf", "-inf", "0", "-1", "1e300"] {
        assert!(
            ServiceConfig::parse(["--interval-seconds".to_string(), interval.to_string()]).is_err(),
            "{interval}"
        );
    }
}

#[test]
fn http_base_builds_prefixed_paths() {
    let base = HttpBase::parse("http://127.0.0.1:8080/api").expect("base");
    assert_eq!(base.path_for("/Status"), "/api/Status");
}

#[test]
fn telemetry_entry_maps_to_location_snapshot() {
    let entry = json!({
        "peer_destination": "abc123",
        "timestamp": 1_714_000_001,
        "display_name": "Team One",
        "telemetry": {
            "location": {
                "latitude": "45.5",
                "longitude": -63.5,
                "altitude": 10.0,
                "speed": 2.5,
                "bearing": 180.0,
                "accuracy": 4.0
            }
        }
    });
    let (snapshot, label, key) = location_snapshot_from_entry(&entry).expect("snapshot");
    assert!((snapshot.latitude - 45.5).abs() < f64::EPSILON);
    assert!((snapshot.longitude - -63.5).abs() < f64::EPSILON);
    assert_eq!(snapshot.peer_hash.as_deref(), Some("abc123"));
    assert_eq!(label.as_deref(), Some("Team One"));
    assert_eq!(key, "abc123:1714000001");
}

#[test]
fn parsed_cot_maps_to_marker_payload() {
    let event = TakInboundCotEvent {
        sensor: None,
        sensor_diagnostic: None,
        version: "2.0".to_string(),
        uid: "tak-peer".to_string(),
        event_type: "a-f-G-U-C".to_string(),
        how: "m-g".to_string(),
        time: "2026-05-11T00:00:00Z".to_string(),
        start: "2026-05-11T00:00:00Z".to_string(),
        stale: "2026-05-11T00:10:00Z".to_string(),
        access: None,
        point: r3akt_tak_connector::TakInboundCotPoint {
            lat: 45.0,
            lon: -63.0,
            hae: 12.0,
            ce: 5.0,
            le: 5.0,
        },
    };
    let payload = marker_payload_from_cot(&event);
    assert_eq!(payload["type"], "friendly");
    assert_eq!(payload["symbol"], "friendly");
    assert_eq!(payload["name"], "tak-peer");
    assert_eq!(payload["lat"], 45.0);
    assert_eq!(payload["lon"], -63.0);
}

#[test]
fn service_bridges_rch_telemetry_and_chat_to_tak_cot_socket() {
    let (tak_url, tak_rx, tak_handle) = spawn_tak_capture_server(2);
    let (rch_url, rch_handle) = spawn_rch_server(4, |request| {
        assert!(request.to_ascii_lowercase().contains("x-api-key: secret"));
        if request.starts_with("GET /Status ") {
            json!({"status":"ok"}).to_string()
        } else if request.starts_with("GET /Telemetry?since=0 ") {
            json!({
                "entries": [{
                    "peer_destination": "peer-alpha",
                    "timestamp": 1_714_000_001,
                    "identity_label": "Alpha",
                    "telemetry": {
                        "location": {
                            "latitude": 45.5,
                            "longitude": -63.5,
                            "altitude": 10.0,
                            "speed": 2.5,
                            "bearing": 180.0,
                            "accuracy": 4.0
                        }
                    }
                }]
            })
            .to_string()
        } else if request.starts_with("GET /Sensors ") {
            json!({"items":[],"ttlMs":300_000}).to_string()
        } else if request.starts_with("GET /Chat/Messages?limit=100 ") {
            json!([{
                "Direction": "outbound",
                "Content": "hello TAK",
                "TopicID": "ops",
                "MessageID": "msg-1",
                "CreatedAt": "2026-05-11T00:00:00Z"
            }])
            .to_string()
        } else {
            panic!("unexpected RCH request: {request}");
        }
    });

    run_service(&ServiceConfig {
        rch_base_url: rch_url,
        rch_api_key: Some("secret".to_string()),
        tak: TakConnectionConfig {
            cot_url: tak_url,
            callsign: "HUB".to_string(),
            ..TakConnectionConfig::default()
        },
        poll_interval_seconds: 0.25,
        mode: BridgeMode::RchToTakOnly,
        once: true,
        help: false,
    })
    .expect("service run");

    let payloads = (0..2)
        .map(|_| {
            tak_rx
                .recv_timeout(StdDuration::from_secs(2))
                .expect("tak payload")
        })
        .collect::<Vec<_>>();
    assert!(payloads.iter().any(|payload| {
        payload.contains("type=\"a-f-G-U-C\"")
            && payload.contains("lat=\"45.5\"")
            && payload.contains("callsign=\"Alpha\"")
    }));
    assert!(payloads.iter().any(|payload| {
        payload.contains("GeoChat.") && payload.contains(">hello TAK</remarks>")
    }));
    rch_handle.join().expect("rch server");
    tak_handle.join().expect("tak server");
}

#[test]
fn service_bridges_inbound_tak_cot_to_rch_marker_route() {
    let (tak_url, tak_handle) = spawn_tak_source_server(
        r#"<event version="2.0" uid="tak-alpha" type="a-f-G-U-C" how="m-g" time="2026-05-11T00:00:00Z" start="2026-05-11T00:00:00Z" stale="2026-05-11T00:10:00Z"><point lat="45.25" lon="-63.75" hae="12" ce="5" le="5" /></event>"#,
    );
    let (rch_url, rch_handle) = spawn_rch_server(3, |request| {
        if request.starts_with("GET /Status ") {
            json!({"status":"ok"}).to_string()
        } else if request.starts_with("GET /api/markers ") {
            json!([]).to_string()
        } else if request.starts_with("POST /api/markers ") {
            assert!(request.contains(r#""name":"tak-alpha""#));
            assert!(request.contains(r#""type":"friendly""#));
            assert!(request.contains(r#""lat":45.25"#));
            json!({"object_destination_hash":"marker-1"}).to_string()
        } else {
            panic!("unexpected RCH request: {request}");
        }
    });

    run_service(&ServiceConfig {
        rch_base_url: rch_url,
        rch_api_key: None,
        tak: TakConnectionConfig {
            cot_url: tak_url,
            ..TakConnectionConfig::default()
        },
        poll_interval_seconds: 0.25,
        mode: BridgeMode::TakToRchOnly,
        once: true,
        help: false,
    })
    .expect("service run");

    rch_handle.join().expect("rch server");
    tak_handle.join().expect("tak server");
}

pub(super) fn spawn_rch_server(
    expected_requests: usize,
    respond: impl Fn(&str) -> String + Send + 'static,
) -> (String, thread::JoinHandle<()>) {
    let listener = TcpListener::bind("127.0.0.1:0").expect("rch listener");
    let addr = listener.local_addr().expect("rch addr");
    let handle = thread::spawn(move || {
        for _ in 0..expected_requests {
            let (mut stream, _) = listener.accept().expect("rch accept");
            let request = read_http_request(&mut stream);
            let body = respond(request.as_str());
            write_http_response(&mut stream, body.as_str());
        }
    });
    (format!("http://{addr}"), handle)
}

fn spawn_tak_capture_server(
    expected_payloads: usize,
) -> (String, mpsc::Receiver<String>, thread::JoinHandle<()>) {
    let listener = TcpListener::bind("127.0.0.1:0").expect("tak listener");
    let addr = listener.local_addr().expect("tak addr");
    let (tx, rx) = mpsc::channel();
    let handle = thread::spawn(move || {
        for _ in 0..expected_payloads {
            let (mut stream, _) = listener.accept().expect("tak accept");
            let mut payload = String::new();
            stream.read_to_string(&mut payload).expect("tak read");
            tx.send(payload).expect("tak send payload");
        }
    });
    (format!("tcp://{addr}"), rx, handle)
}

fn spawn_tak_source_server(payload: &'static str) -> (String, thread::JoinHandle<()>) {
    let listener = TcpListener::bind("127.0.0.1:0").expect("tak listener");
    let addr = listener.local_addr().expect("tak addr");
    let handle = thread::spawn(move || {
        let (mut stream, _) = listener.accept().expect("tak accept");
        stream.write_all(payload.as_bytes()).expect("tak write");
        stream.shutdown(Shutdown::Write).expect("tak shutdown");
    });
    (format!("tcp://{addr}"), handle)
}

pub(super) fn read_http_request(stream: &mut TcpStream) -> String {
    stream
        .set_read_timeout(Some(StdDuration::from_secs(2)))
        .expect("read timeout");
    let mut bytes = Vec::new();
    let mut buffer = [0_u8; 1024];
    loop {
        let read = stream.read(&mut buffer).expect("request read");
        assert_ne!(read, 0, "connection closed before complete request");
        bytes.extend_from_slice(&buffer[..read]);
        if request_complete(bytes.as_slice()) {
            break;
        }
    }
    String::from_utf8(bytes).expect("utf8 request")
}

fn request_complete(bytes: &[u8]) -> bool {
    let Some(header_end) = bytes.windows(4).position(|window| window == b"\r\n\r\n") else {
        return false;
    };
    let header = String::from_utf8_lossy(&bytes[..header_end]);
    let content_length = header
        .lines()
        .find_map(|line| {
            line.split_once(':')
                .filter(|(name, _)| name.eq_ignore_ascii_case("content-length"))
                .map(|(_, value)| value)
        })
        .and_then(|value| value.trim().parse::<usize>().ok())
        .unwrap_or(0);
    bytes.len() >= header_end + 4 + content_length
}

fn write_http_response(stream: &mut TcpStream, body: &str) {
    write!(
        stream,
        "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        body.len(),
        body
    )
    .expect("response write");
}
