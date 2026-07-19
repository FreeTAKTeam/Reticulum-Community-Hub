#![cfg_attr(
    not(test),
    deny(
        clippy::expect_used,
        clippy::let_underscore_must_use,
        clippy::panic,
        clippy::unwrap_used
    )
)]

use std::collections::HashSet;
use std::env;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::thread;
use std::time::Duration as StdDuration;

use chrono::{DateTime, Utc};
use r3akt_tak_connector::{
    ChatEventInput, CotPayload, CotPayloadKind, LocationSnapshot, TakClearSender,
    TakConnectionConfig, TakConnector, TakCotReceiver, TakCotSender, TakInboundCotEvent,
    TakInboundCotResult, TakInboundService, TakSocketReceiver,
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
    client.get_json("/Status")?;

    let connector = TakConnector::new(config.tak.clone());
    let sender = TakClearSender::from_config(&config.tak)?;
    let mut receiver = if config.mode.enable_tak_to_rch() {
        Some(TakInboundService::new(
            TakSocketReceiver::from_config(&config.tak)?
                .with_read_timeout(StdDuration::from_secs_f64(config.poll_interval_seconds)),
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
        if config.mode.enable_rch_to_tak() {
            bridge_rch_to_tak(&client, &sender, &connector, &mut state)?;
        }
        if let Some(receiver) = receiver.as_mut() {
            bridge_tak_to_rch(&client, receiver, &mut state)?;
        }
        if config.once {
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
            rch_base_url: env_nonempty("R3AKT_TAK_RCH_BASE_URL")
                .unwrap_or_else(|| "http://127.0.0.1:8080".to_string()),
            rch_api_key: env_nonempty("R3AKT_TAK_RCH_API_KEY"),
            tak: tak_config_from_env(),
            poll_interval_seconds: env_f64("R3AKT_TAK_SERVICE_INTERVAL_SECONDS").unwrap_or(5.0),
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
        config.poll_interval_seconds = config.poll_interval_seconds.max(0.25);
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

fn tak_config_from_env() -> TakConnectionConfig {
    let mut config = TakConnectionConfig::default();
    if let Some(value) = env_nonempty("COT_URL") {
        config.cot_url = value;
    }
    if let Some(value) = env_nonempty("TAK_CALLSIGN") {
        config.callsign = value;
    }
    if let Some(value) = env_f64("PYTAK_SLEEP") {
        config.poll_interval_seconds = value;
    }
    if let Some(value) = env_f64("RTH_TAK_KEEPALIVE_INTERVAL_SECONDS") {
        config.keepalive_interval_seconds = value;
    }
    if let Some(value) = env_u8("TAK_PROTO") {
        config.tak_proto = value;
    }
    if let Some(value) = env_u8("FTS_COMPAT") {
        config.fts_compat = value;
    }
    if let Some(value) = env_u8("PYTAK_TLS_DONT_VERIFY") {
        config.pytak_tls_dont_verify = value;
        config.tls_insecure = value != 0;
    }
    config.tls_ca = env_nonempty("R3AKT_TAK_TLS_CA");
    config.tls_client_cert = env_nonempty("R3AKT_TAK_TLS_CLIENT_CERT");
    config.tls_client_key = env_nonempty("R3AKT_TAK_TLS_CLIENT_KEY");
    config.tls_client_password = env_nonempty("R3AKT_TAK_TLS_CLIENT_PASSWORD");
    if let Some(value) = env_bool("R3AKT_TAK_TLS_INSECURE") {
        config.tls_insecure = value;
    }
    config
}

fn env_nonempty(name: &str) -> Option<String> {
    env::var(name)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn env_f64(name: &str) -> Option<f64> {
    env_nonempty(name)?.parse().ok()
}

fn env_u8(name: &str) -> Option<u8> {
    env_nonempty(name)?.parse().ok()
}

fn env_bool(name: &str) -> Option<bool> {
    let value = env_nonempty(name)?.to_ascii_lowercase();
    Some(matches!(value.as_str(), "1" | "true" | "yes" | "on"))
}

#[derive(Default)]
struct BridgeState {
    telemetry: HashSet<String>,
    chat: HashSet<String>,
    cot: HashSet<String>,
}

fn bridge_rch_to_tak(
    client: &RchNorthboundClient,
    sender: &TakClearSender,
    connector: &TakConnector,
    state: &mut BridgeState,
) -> Result<(), Box<dyn std::error::Error>> {
    let telemetry = client.get_json("/Telemetry?since=0")?;
    for entry in telemetry["entries"].as_array().into_iter().flatten() {
        let Some((snapshot, label, key)) = location_snapshot_from_entry(entry) else {
            continue;
        };
        if state.telemetry.insert(key) {
            let payload = CotPayload {
                kind: CotPayloadKind::Location,
                xml: connector.build_location_xml(&snapshot, Utc::now(), label.as_deref()),
            };
            sender.send(&payload)?;
        }
    }

    let messages = client.get_json("/Chat/Messages?limit=100")?;
    for message in messages.as_array().into_iter().flatten() {
        if message["Direction"].as_str() != Some("outbound") {
            continue;
        }
        let Some(input) = chat_input_from_message(message) else {
            continue;
        };
        let key = input
            .message_uuid
            .clone()
            .unwrap_or_else(|| format!("{}:{}", input.timestamp.timestamp(), input.content));
        if state.chat.insert(key) {
            let payload = CotPayload {
                kind: CotPayloadKind::Chat,
                xml: connector.build_chat_xml(&input)?,
            };
            sender.send(&payload)?;
        }
    }
    Ok(())
}

fn bridge_tak_to_rch<R: TakCotReceiver>(
    client: &RchNorthboundClient,
    receiver: &mut TakInboundService<R>,
    state: &mut BridgeState,
) -> Result<(), Box<dyn std::error::Error>> {
    let report = receiver.poll_once()?;
    let Some(TakInboundCotResult::Parsed(event)) = report.result else {
        return Ok(());
    };
    let key = format!("{}:{}:{}", event.uid, event.time, event.stale);
    if state.cot.insert(key) {
        client.post_json("/api/markers", marker_payload_from_cot(&event))?;
    }
    Ok(())
}

fn location_snapshot_from_entry(
    entry: &Value,
) -> Option<(LocationSnapshot, Option<String>, String)> {
    let location = entry.get("telemetry")?.get("location")?;
    let timestamp = entry.get("timestamp")?.as_i64()?;
    let peer = entry.get("peer_destination")?.as_str()?.to_string();
    let label = entry
        .get("identity_label")
        .and_then(Value::as_str)
        .or_else(|| entry.get("display_name").and_then(Value::as_str))
        .map(ToOwned::to_owned);
    let key = format!("{peer}:{timestamp}");
    Some((
        LocationSnapshot {
            latitude: json_f64(location, "latitude")?,
            longitude: json_f64(location, "longitude")?,
            altitude: json_f64(location, "altitude").unwrap_or(0.0),
            speed: json_f64(location, "speed").unwrap_or(0.0),
            bearing: json_f64(location, "bearing").unwrap_or(0.0),
            accuracy: json_f64(location, "accuracy").unwrap_or(0.0),
            updated_at: DateTime::from_timestamp(timestamp, 0)?,
            peer_hash: Some(peer),
        },
        label,
        key,
    ))
}

fn chat_input_from_message(message: &Value) -> Option<ChatEventInput> {
    let content = message.get("Content")?.as_str()?.trim();
    if content.is_empty() {
        return None;
    }
    let timestamp = message
        .get("CreatedAt")
        .and_then(Value::as_str)
        .and_then(|value| DateTime::parse_from_rfc3339(value).ok())
        .map_or_else(Utc::now, |value| value.with_timezone(&Utc));
    Some(ChatEventInput {
        content: content.to_string(),
        sender_label: "RCH".to_string(),
        topic_id: message
            .get("TopicID")
            .and_then(Value::as_str)
            .map(ToOwned::to_owned),
        source_hash: None,
        timestamp,
        message_uuid: message
            .get("MessageID")
            .and_then(Value::as_str)
            .map(ToOwned::to_owned),
    })
}

fn marker_payload_from_cot(event: &TakInboundCotEvent) -> Value {
    let symbol = marker_symbol_for_cot_type(event.event_type.as_str());
    json!({
        "type": symbol,
        "symbol": symbol,
        "name": event.uid,
        "category": "tak",
        "lat": event.point.lat,
        "lon": event.point.lon,
        "notes": format!(
            "TAK CoT type={} how={} hae={} ce={} le={}",
            event.event_type, event.how, event.point.hae, event.point.ce, event.point.le
        )
    })
}

fn marker_symbol_for_cot_type(event_type: &str) -> &'static str {
    if event_type.contains("-h-") || event_type.starts_with("a-h") {
        "hostile"
    } else if event_type.contains("-n-") || event_type.starts_with("a-n") {
        "neutral"
    } else if event_type.contains("-u-") || event_type.starts_with("a-u") {
        "unknown"
    } else if event_type.contains("-f-") || event_type.starts_with("a-f") {
        "friendly"
    } else {
        "marker"
    }
}

fn json_f64(value: &Value, key: &str) -> Option<f64> {
    match value.get(key)? {
        Value::Number(number) => number.as_f64(),
        Value::String(text) => text.parse::<f64>().ok(),
        _ => None,
    }
}

#[derive(Debug, Clone)]
struct RchNorthboundClient {
    base: HttpBase,
    api_key: Option<String>,
}

impl RchNorthboundClient {
    fn new(base_url: &str, api_key: Option<String>) -> Result<Self, Box<dyn std::error::Error>> {
        Ok(Self {
            base: HttpBase::parse(base_url)?,
            api_key,
        })
    }

    fn get_json(&self, path: &str) -> Result<Value, Box<dyn std::error::Error>> {
        self.request_json("GET", path, None)
    }

    fn post_json(&self, path: &str, body: Value) -> Result<Value, Box<dyn std::error::Error>> {
        self.request_json("POST", path, Some(body))
    }

    fn request_json(
        &self,
        method: &str,
        path: &str,
        body: Option<Value>,
    ) -> Result<Value, Box<dyn std::error::Error>> {
        let body_text = body.map(|value| value.to_string()).unwrap_or_default();
        let request_path = self.base.path_for(path);
        let mut request = format!(
            "{method} {request_path} HTTP/1.1\r\nHost: {}\r\nAccept: application/json\r\nConnection: close\r\n",
            self.base.host_header
        );
        if let Some(api_key) = &self.api_key {
            request.push_str(format!("X-API-Key: {api_key}\r\n").as_str());
            request.push_str(format!("Authorization: Bearer {api_key}\r\n").as_str());
        }
        if body_text.is_empty() {
            request.push_str("\r\n");
        } else {
            request.push_str("Content-Type: application/json\r\n");
            request.push_str(format!("Content-Length: {}\r\n\r\n", body_text.len()).as_str());
            request.push_str(body_text.as_str());
        }

        let mut stream = TcpStream::connect((self.base.host.as_str(), self.base.port))?;
        stream.write_all(request.as_bytes())?;
        stream.flush()?;
        let mut response = String::new();
        stream.read_to_string(&mut response)?;
        parse_http_json_response(response.as_str())
    }
}

#[derive(Debug, Clone)]
struct HttpBase {
    host: String,
    port: u16,
    host_header: String,
    path_prefix: String,
}

impl HttpBase {
    fn parse(base_url: &str) -> Result<Self, Box<dyn std::error::Error>> {
        let without_scheme = base_url
            .trim()
            .strip_prefix("http://")
            .ok_or("only http:// RCH northbound URLs are supported")?;
        let (authority, path_prefix) = without_scheme
            .split_once('/')
            .map_or((without_scheme, ""), |(authority, path)| (authority, path));
        let (host, port) = authority
            .rsplit_once(':')
            .map_or((authority.to_string(), 80), |(host, port)| {
                (host.to_string(), port.parse::<u16>().unwrap_or(80))
            });
        if host.is_empty() {
            return Err("RCH base URL host is required".into());
        }
        Ok(Self {
            host: host.clone(),
            port,
            host_header: if port == 80 {
                host
            } else {
                format!("{host}:{port}")
            },
            path_prefix: path_prefix.trim_matches('/').to_string(),
        })
    }

    fn path_for(&self, path: &str) -> String {
        let path = path.trim_start_matches('/');
        if self.path_prefix.is_empty() {
            format!("/{path}")
        } else {
            format!("/{}/{}", self.path_prefix, path)
        }
    }
}

fn parse_http_json_response(response: &str) -> Result<Value, Box<dyn std::error::Error>> {
    let (head, body) = response
        .split_once("\r\n\r\n")
        .or_else(|| response.split_once("\n\n"))
        .ok_or("invalid HTTP response")?;
    let status = head
        .lines()
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .and_then(|value| value.parse::<u16>().ok())
        .ok_or("missing HTTP response status")?;
    if !(200..300).contains(&status) {
        return Err(format!("RCH northbound request failed with HTTP {status}: {body}").into());
    }
    if body.trim().is_empty() {
        Ok(Value::Null)
    } else {
        Ok(serde_json::from_str(body)?)
    }
}

#[cfg(test)]
mod tests {
    use std::net::{Shutdown, TcpListener, TcpStream};
    use std::sync::mpsc;

    use super::*;

    #[test]
    fn http_base_builds_prefixed_paths() {
        let base = HttpBase::parse("http://127.0.0.1:8080/api").expect("base");
        assert_eq!(base.host, "127.0.0.1");
        assert_eq!(base.port, 8080);
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
            assert!(request.contains("X-API-Key: secret"));
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

    fn spawn_rch_server(
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

    fn read_http_request(stream: &mut TcpStream) -> String {
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
            .find_map(|line| line.strip_prefix("Content-Length: "))
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
