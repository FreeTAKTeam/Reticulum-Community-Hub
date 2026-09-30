#![cfg_attr(
    not(test),
    deny(
        clippy::expect_used,
        clippy::let_underscore_must_use,
        clippy::panic,
        clippy::unwrap_used
    )
)]

use std::env;
use std::thread;
use std::time::Duration as StdDuration;

mod service_bridge;
mod service_http;
use service_bridge::{BridgeState, bridge_rch_to_tak, bridge_tak_to_rch};
#[cfg(test)]
use service_bridge::{location_snapshot_from_entry, marker_payload_from_cot};
#[cfg(test)]
use service_http::HttpBase;
use service_http::RchNorthboundClient;

use chrono::{DateTime, Utc};
use r3akt_tak_connector::{
    ChatEventInput, LocationSnapshot, TakClearSender, TakConnectionConfig, TakCotReceiver,
    TakCotSender, TakInboundCotEvent, TakInboundCotResult, TakInboundService, TakService,
    TakSocketReceiver,
};
use serde_json::{Value, json};

fn main() {
    if let Err(error) = run() {
        eprintln!("r3akt-tak-service error: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let config = ServiceConfig::parse(env::args().skip(1))?;
    if config.help {
        print_help();
        return Ok(());
    }
    run_service(&config)
}

fn run_service(config: &ServiceConfig) -> Result<(), Box<dyn std::error::Error>> {
    let client =
        RchNorthboundClient::new(config.rch_base_url.as_str(), config.rch_api_key.clone())?;
    if let Err(error) = client.get_json("/Status") {
        if config.once {
            return Err(error);
        }
        eprintln!("RCH startup check failed; bridge will retry: {error}");
    }

    let sender = TakClearSender::from_config(&config.tak)?;
    let mut service = TakService::new(config.tak.clone(), 256, sender);
    service.start();
    let status = service.status();
    eprintln!(
        "TAK bridge started; TLS enabled={}, certificate verification enabled={}",
        status.tls_enabled, status.tls_verification_enabled
    );
    let mut receiver = if config.mode.enable_tak_to_rch() {
        Some(TakInboundService::new(
            TakSocketReceiver::from_config(&config.tak)?.with_read_timeout(
                StdDuration::from_secs_f64(config.poll_interval_seconds)
                    .min(StdDuration::from_secs(5)),
            ),
            true,
        ))
    } else {
        None
    };
    if let Some(receiver) = receiver.as_mut() {
        receiver.start();
    }

    let mut state = BridgeState::default();
    loop {
        let mut failures = Vec::new();
        if config.mode.enable_rch_to_tak() {
            if let Err(error) = bridge_rch_to_tak(&client, &mut service, &mut state) {
                eprintln!(
                    "RCH to TAK bridge will retry; pending={}: {error}",
                    service.status().queue.pending
                );
                failures.push(error.to_string());
            }
        }
        if let Some(receiver) = receiver.as_mut() {
            if let Err(error) = bridge_tak_to_rch(&client, receiver, &mut state) {
                eprintln!("TAK to RCH bridge will retry: {error}");
                failures.push(error.to_string());
            }
        }
        if config.once {
            if !failures.is_empty() {
                return Err(failures.join("; ").into());
            }
            break;
        }
        thread::sleep(StdDuration::from_secs_f64(config.poll_interval_seconds));
    }

    Ok(())
}

fn print_help() {
    println!(
        "Usage: r3akt-tak-service [--rch-base-url URL] [--rch-api-key KEY] [--tak-cot-url URL] [--interval-seconds N] [--once] [--rch-to-tak-only|--tak-to-rch-only]\n\
         Environment: R3AKT_TAK_RCH_BASE_URL, R3AKT_TAK_RCH_API_KEY, COT_URL, TAK_PROTO, FTS_COMPAT, PYTAK_TLS_DONT_VERIFY, R3AKT_TAK_TLS_CA, R3AKT_TAK_TLS_CLIENT_CERT, R3AKT_TAK_TLS_CLIENT_KEY, R3AKT_TAK_TLS_CLIENT_PASSWORD, R3AKT_TAK_TLS_INSECURE"
    );
}

#[derive(Debug, Clone)]
struct ServiceConfig {
    rch_base_url: String,
    rch_api_key: Option<String>,
    tak: TakConnectionConfig,
    poll_interval_seconds: f64,
    mode: BridgeMode,
    once: bool,
    help: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum BridgeMode {
    Bidirectional,
    RchToTakOnly,
    TakToRchOnly,
}

impl BridgeMode {
    const fn enable_rch_to_tak(self) -> bool {
        matches!(self, Self::Bidirectional | Self::RchToTakOnly)
    }

    const fn enable_tak_to_rch(self) -> bool {
        matches!(self, Self::Bidirectional | Self::TakToRchOnly)
    }
}

impl ServiceConfig {
    fn parse(args: impl IntoIterator<Item = String>) -> Result<Self, Box<dyn std::error::Error>> {
        let mut config = Self {
            rch_base_url: env_nonempty("R3AKT_TAK_RCH_BASE_URL")?
                .unwrap_or_else(|| "http://127.0.0.1:8000".to_string()),
            rch_api_key: env_nonempty("R3AKT_TAK_RCH_API_KEY")?,
            tak: tak_config_from_env()?,
            poll_interval_seconds: env_f64("R3AKT_TAK_SERVICE_INTERVAL_SECONDS")?.unwrap_or(5.0),
            mode: BridgeMode::Bidirectional,
            once: false,
            help: false,
        };
        let mut args = args.into_iter();
        while let Some(arg) = args.next() {
            match arg.as_str() {
                "--help" | "-h" => config.help = true,
                "--once" => config.once = true,
                "--rch-to-tak-only" => config.mode = BridgeMode::RchToTakOnly,
                "--tak-to-rch-only" => config.mode = BridgeMode::TakToRchOnly,
                "--rch-base-url" => config.rch_base_url = next_arg(&mut args, "--rch-base-url")?,
                "--rch-api-key" => config.rch_api_key = Some(next_arg(&mut args, "--rch-api-key")?),
                "--tak-cot-url" => config.tak.cot_url = next_arg(&mut args, "--tak-cot-url")?,
                "--callsign" => config.tak.callsign = next_arg(&mut args, "--callsign")?,
                "--interval-seconds" => {
                    config.poll_interval_seconds =
                        next_arg(&mut args, "--interval-seconds")?.parse::<f64>()?;
                }
                "--tak-proto" => {
                    config.tak.tak_proto = next_arg(&mut args, "--tak-proto")?.parse()?;
                }
                other => return Err(format!("unknown argument {other}").into()),
            }
        }
        validate_interval(config.poll_interval_seconds, "service interval")?;
        config.poll_interval_seconds = config.poll_interval_seconds.max(0.25);
        if config.tak.tak_proto > 1 || config.tak.fts_compat > 1 {
            return Err("TAK_PROTO and FTS_COMPAT must be 0 or 1".into());
        }
        Ok(config)
    }
}

fn next_arg(
    args: &mut impl Iterator<Item = String>,
    name: &str,
) -> Result<String, Box<dyn std::error::Error>> {
    args.next()
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| format!("{name} requires a value").into())
}

fn tak_config_from_env() -> Result<TakConnectionConfig, Box<dyn std::error::Error>> {
    let mut config = TakConnectionConfig::default();
    if let Some(value) = env_nonempty("COT_URL")? {
        config.cot_url = value;
    }
    if let Some(value) = env_nonempty("TAK_CALLSIGN")? {
        config.callsign = value;
    }
    if let Some(value) = env_f64("PYTAK_SLEEP")? {
        config.poll_interval_seconds = value;
    }
    if let Some(value) = env_f64("RTH_TAK_KEEPALIVE_INTERVAL_SECONDS")? {
        config.keepalive_interval_seconds = value;
    }
    if let Some(value) = env_u8("TAK_PROTO")? {
        config.tak_proto = value;
    }
    if let Some(value) = env_u8("FTS_COMPAT")? {
        config.fts_compat = value;
    }
    if let Some(value) = env_u8("PYTAK_TLS_DONT_VERIFY")? {
        config.pytak_tls_dont_verify = value;
        config.tls_insecure = value != 0;
    }
    config.tls_ca = env_nonempty("R3AKT_TAK_TLS_CA")?;
    config.tls_client_cert = env_nonempty("R3AKT_TAK_TLS_CLIENT_CERT")?;
    config.tls_client_key = env_nonempty("R3AKT_TAK_TLS_CLIENT_KEY")?;
    config.tls_client_password = env_nonempty("R3AKT_TAK_TLS_CLIENT_PASSWORD")?;
    if let Some(value) = env_bool("R3AKT_TAK_TLS_INSECURE")? {
        config.tls_insecure = value;
        config.pytak_tls_dont_verify = u8::from(value);
    }
    Ok(config)
}

fn env_nonempty(name: &str) -> Result<Option<String>, Box<dyn std::error::Error>> {
    match env::var(name) {
        Ok(value) => Ok(Some(value.trim().to_string()).filter(|value| !value.is_empty())),
        Err(env::VarError::NotPresent) => Ok(None),
        Err(env::VarError::NotUnicode(_)) => Err(format!("{name} must contain valid UTF-8").into()),
    }
}

fn env_f64(name: &str) -> Result<Option<f64>, Box<dyn std::error::Error>> {
    env_nonempty(name)?
        .map(|value| {
            let parsed = value
                .parse::<f64>()
                .map_err(|error| format!("Invalid {name}: {error}"))?;
            validate_interval(parsed, name)?;
            Ok(parsed)
        })
        .transpose()
}

fn validate_interval(value: f64, name: &str) -> Result<(), Box<dyn std::error::Error>> {
    if !value.is_finite() || value <= 0.0 || StdDuration::try_from_secs_f64(value).is_err() {
        return Err(format!("{name} must be a finite positive duration").into());
    }
    Ok(())
}

fn env_u8(name: &str) -> Result<Option<u8>, Box<dyn std::error::Error>> {
    env_nonempty(name)?
        .map(|value| {
            value
                .parse::<u8>()
                .map_err(|error| format!("Invalid {name}: {error}").into())
        })
        .transpose()
}

fn env_bool(name: &str) -> Result<Option<bool>, Box<dyn std::error::Error>> {
    env_nonempty(name)?
        .map(|value| match value.to_ascii_lowercase().as_str() {
            "1" | "true" | "yes" | "on" => Ok(true),
            "0" | "false" | "no" | "off" => Ok(false),
            _ => Err(format!("{name} must be a boolean").into()),
        })
        .transpose()
}

#[cfg(test)]
mod tests {
    use std::io::{Read, Write};
    use std::net::{Shutdown, TcpListener, TcpStream};
    use std::sync::mpsc;

    use super::*;

    #[test]
    fn service_rejects_non_finite_or_non_positive_intervals() {
        for interval in ["NaN", "inf", "-inf", "0", "-1", "1e300"] {
            assert!(
                ServiceConfig::parse(["--interval-seconds".to_string(), interval.to_string()])
                    .is_err(),
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
        let (rch_url, rch_handle) = spawn_rch_server(3, |request| {
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
        let (rch_url, rch_handle) = spawn_rch_server(2, |request| {
            if request.starts_with("GET /Status ") {
                json!({"status":"ok"}).to_string()
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
}
