#![allow(clippy::missing_errors_doc)]

use std::collections::VecDeque;
use std::fs;
use std::io::Read;
use std::io::Write;
use std::net::TcpStream;
use std::net::UdpSocket;
use std::sync::Arc;
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;
use std::time::Duration as StdDuration;
use std::time::Instant;

use native_tls::Certificate;
use native_tls::Identity;
use native_tls::TlsConnector;
use prost::Message;
use quick_xml::Reader;
use quick_xml::events::BytesStart;
use quick_xml::events::Event as XmlEvent;
use time::OffsetDateTime;
use time::format_description::well_known::Rfc3339;
use uuid::Uuid;

pub const EVENT_TYPE_LOCATION: &str = "a-f-G-U-C";
pub const EVENT_HOW: &str = "h-g-i-g-o";
pub const CHAT_LINK_TYPE: &str = "a-f-G-U-C-I";
pub const CHAT_EVENT_TYPE: &str = "b-t-f";
pub const TAKV_VERSION: &str = "0.44.0";
pub const TAKV_PLATFORM: &str = "RetTAK";
pub const TAKV_OS: &str = "ubuntu";
pub const TAKV_DEVICE: &str = "not your business";
pub const GROUP_NAME: &str = "Yellow";
pub const GROUP_ROLE: &str = "Team Member";
pub const STATUS_BATTERY: f64 = 0.0;
pub const KEEPALIVE_EVENT_TYPE: &str = "t-x-d-d";
pub const KEEPALIVE_HOW: &str = "m-g";
pub const PING_UID: &str = "takPing";
pub const PONG_UID: &str = "takPong";
pub const DEFAULT_COT_VALUE: &str = "9999999.0";
const TAK_WORKER_MAX_BACKOFF: StdDuration = StdDuration::from_secs(30);
const TAK_PROTO_MAGIC_BYTE: u8 = 0xbf;

#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum TakConnectorError {
    #[error("chat content is required to build a CoT event")]
    EmptyChatContent,
    #[error("TAK outbound queue is full")]
    QueueFull,
    #[error("unsupported TAK COT URL scheme: {0}")]
    UnsupportedScheme(String),
    #[error("invalid TAK COT URL: {0}")]
    InvalidCotUrl(String),
    #[error("TAK send failed: {0}")]
    Send(String),
    #[error("TAK service is not running")]
    ServiceStopped,
}

#[derive(Clone, PartialEq, Message)]
struct TakProtoMessage {
    #[prost(message, optional, tag = "2")]
    cot_event: Option<TakProtoCotEvent>,
}

#[derive(Clone, PartialEq, Message)]
struct TakProtoCotEvent {
    #[prost(string, tag = "1")]
    r#type: String,
    #[prost(string, tag = "2")]
    access: String,
    #[prost(string, tag = "3")]
    qos: String,
    #[prost(string, tag = "4")]
    opex: String,
    #[prost(string, tag = "5")]
    uid: String,
    #[prost(uint64, tag = "6")]
    send_time: u64,
    #[prost(uint64, tag = "7")]
    start_time: u64,
    #[prost(uint64, tag = "8")]
    stale_time: u64,
    #[prost(string, tag = "9")]
    how: String,
    #[prost(double, tag = "10")]
    lat: f64,
    #[prost(double, tag = "11")]
    lon: f64,
    #[prost(double, tag = "12")]
    hae: f64,
    #[prost(double, tag = "13")]
    ce: f64,
    #[prost(double, tag = "14")]
    le: f64,
    #[prost(message, optional, tag = "15")]
    detail: Option<TakProtoDetail>,
}

#[derive(Clone, PartialEq, Message)]
struct TakProtoDetail {
    #[prost(string, tag = "1")]
    xml_detail: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct TakConnectionConfig {
    pub cot_url: String,
    pub callsign: String,
    pub poll_interval_seconds: f64,
    pub keepalive_interval_seconds: f64,
    pub tls_client_cert: Option<String>,
    pub tls_client_key: Option<String>,
    pub tls_ca: Option<String>,
    pub tls_insecure: bool,
    pub tls_client_password: Option<String>,
    pub pytak_tls_dont_verify: u8,
    pub tak_proto: u8,
    pub fts_compat: u8,
}

#[derive(Debug, Clone, PartialEq)]
pub struct TakInboundCotEvent {
    pub version: String,
    pub uid: String,
    pub event_type: String,
    pub how: String,
    pub time: String,
    pub start: String,
    pub stale: String,
    pub access: Option<String>,
    pub point: TakInboundCotPoint,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct TakInboundCotPoint {
    pub lat: f64,
    pub lon: f64,
    pub hae: f64,
    pub ce: f64,
    pub le: f64,
}

impl Default for TakInboundCotPoint {
    fn default() -> Self {
        Self {
            lat: 0.0,
            lon: 0.0,
            hae: 0.0,
            ce: 0.0,
            le: 0.0,
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum TakInboundCotResult {
    Parsed(Box<TakInboundCotEvent>),
    Raw(String),
}

impl Default for TakConnectionConfig {
    fn default() -> Self {
        Self {
            cot_url: "tcp://127.0.0.1:8087".to_string(),
            callsign: "R3AKT".to_string(),
            poll_interval_seconds: 30.0,
            keepalive_interval_seconds: 60.0,
            tls_client_cert: None,
            tls_client_key: None,
            tls_ca: None,
            tls_insecure: true,
            tls_client_password: None,
            pytak_tls_dont_verify: 1,
            tak_proto: 0,
            fts_compat: 1,
        }
    }
}

#[must_use]
pub fn parse_inbound_cot_payload(data: impl AsRef<[u8]>, parse: bool) -> TakInboundCotResult {
    let raw = String::from_utf8_lossy(data.as_ref()).to_string();
    if !parse {
        return TakInboundCotResult::Raw(raw);
    }
    parse_inbound_cot_event(raw.as_str()).map_or(TakInboundCotResult::Raw(raw), |event| {
        TakInboundCotResult::Parsed(Box::new(event))
    })
}

fn encode_outbound_cot_payload(payload: &CotPayload, tak_proto: u8) -> Vec<u8> {
    if tak_proto == 0 {
        return payload.xml.as_bytes().to_vec();
    }
    cot_xml_to_tak_proto_frame(payload.xml.as_str())
        .unwrap_or_else(|| payload.xml.as_bytes().to_vec())
}

fn cot_xml_to_tak_proto_frame(xml: &str) -> Option<Vec<u8>> {
    let event = parse_inbound_cot_event(xml)?;
    let message = TakProtoMessage {
        cot_event: Some(TakProtoCotEvent {
            r#type: event.event_type,
            access: event.access.unwrap_or_default(),
            qos: String::new(),
            opex: String::new(),
            uid: event.uid,
            send_time: parse_cot_timestamp_millis(event.time.as_str())?,
            start_time: parse_cot_timestamp_millis(event.start.as_str())?,
            stale_time: parse_cot_timestamp_millis(event.stale.as_str())?,
            how: event.how,
            lat: event.point.lat,
            lon: event.point.lon,
            hae: event.point.hae,
            ce: event.point.ce,
            le: event.point.le,
            detail: cot_detail_xml(xml).map(|xml_detail| TakProtoDetail { xml_detail }),
        }),
    };
    let mut proto_payload = Vec::new();
    message.encode(&mut proto_payload).ok()?;
    let mut frame = Vec::with_capacity(1 + 10 + proto_payload.len());
    frame.push(TAK_PROTO_MAGIC_BYTE);
    encode_u64_varint(proto_payload.len() as u64, &mut frame);
    frame.extend_from_slice(proto_payload.as_slice());
    Some(frame)
}

fn encode_u64_varint(mut value: u64, output: &mut Vec<u8>) {
    loop {
        let mut byte = (value & 0x7f) as u8;
        value >>= 7;
        if value != 0 {
            byte |= 0x80;
        }
        output.push(byte);
        if value == 0 {
            break;
        }
    }
}

fn parse_cot_timestamp_millis(value: &str) -> Option<u64> {
    let timestamp = OffsetDateTime::parse(value, &Rfc3339).ok()?;
    let nanos = timestamp.unix_timestamp_nanos();
    if nanos.is_negative() {
        return None;
    }
    u64::try_from(nanos / 1_000_000).ok()
}

fn cot_detail_xml(xml: &str) -> Option<String> {
    let detail_start = xml.find("<detail")?;
    let content_start = xml[detail_start..].find('>')? + detail_start + 1;
    let content_end = xml[content_start..].find("</detail>")? + content_start;
    let detail = xml[content_start..content_end].trim();
    if detail.is_empty() {
        None
    } else {
        Some(detail.to_string())
    }
}

fn parse_inbound_cot_event(raw: &str) -> Option<TakInboundCotEvent> {
    let mut reader = Reader::from_str(raw);
    reader.config_mut().trim_text(true);
    let mut event: Option<TakInboundCotEvent> = None;
    let mut root_depth: Option<usize> = None;
    let mut depth = 0usize;

    loop {
        match reader.read_event() {
            Ok(XmlEvent::Start(element)) => {
                depth = depth.saturating_add(1);
                if event.is_none() {
                    event = Some(event_from_xml_start(&reader, &element)?);
                    root_depth = Some(depth);
                } else if root_depth.is_some_and(|root| depth == root + 1)
                    && element.name().as_ref() == b"point"
                {
                    if let Some(parsed_event) = event.as_mut() {
                        parsed_event.point = point_from_xml_start(&reader, &element)?;
                    }
                }
            }
            Ok(XmlEvent::Empty(element)) => {
                let element_depth = depth.saturating_add(1);
                if event.is_none() {
                    event = Some(event_from_xml_start(&reader, &element)?);
                    root_depth = Some(element_depth);
                } else if root_depth.is_some_and(|root| element_depth == root + 1)
                    && element.name().as_ref() == b"point"
                {
                    if let Some(parsed_event) = event.as_mut() {
                        parsed_event.point = point_from_xml_start(&reader, &element)?;
                    }
                }
            }
            Ok(XmlEvent::End(_)) => depth = depth.saturating_sub(1),
            Ok(XmlEvent::Eof) => break,
            Ok(_) => {}
            Err(_) => return None,
        }
    }

    event
}

fn event_from_xml_start(
    reader: &Reader<&[u8]>,
    element: &BytesStart<'_>,
) -> Option<TakInboundCotEvent> {
    Some(TakInboundCotEvent {
        version: xml_attr(reader, element, b"version")
            .ok()?
            .unwrap_or_default(),
        uid: xml_attr(reader, element, b"uid").ok()?.unwrap_or_default(),
        event_type: xml_attr(reader, element, b"type").ok()?.unwrap_or_default(),
        how: xml_attr(reader, element, b"how").ok()?.unwrap_or_default(),
        time: xml_attr(reader, element, b"time").ok()?.unwrap_or_default(),
        start: xml_attr(reader, element, b"start")
            .ok()?
            .unwrap_or_default(),
        stale: xml_attr(reader, element, b"stale")
            .ok()?
            .unwrap_or_default(),
        access: xml_attr(reader, element, b"access").ok()?,
        point: TakInboundCotPoint::default(),
    })
}

fn point_from_xml_start(
    reader: &Reader<&[u8]>,
    element: &BytesStart<'_>,
) -> Option<TakInboundCotPoint> {
    Some(TakInboundCotPoint {
        lat: xml_attr(reader, element, b"lat")
            .ok()?
            .unwrap_or_else(|| "0".to_string())
            .parse()
            .ok()?,
        lon: xml_attr(reader, element, b"lon")
            .ok()?
            .unwrap_or_else(|| "0".to_string())
            .parse()
            .ok()?,
        hae: xml_attr(reader, element, b"hae")
            .ok()?
            .unwrap_or_else(|| "0".to_string())
            .parse()
            .ok()?,
        ce: xml_attr(reader, element, b"ce")
            .ok()?
            .unwrap_or_else(|| "0".to_string())
            .parse()
            .ok()?,
        le: xml_attr(reader, element, b"le")
            .ok()?
            .unwrap_or_else(|| "0".to_string())
            .parse()
            .ok()?,
    })
}

fn xml_attr(
    reader: &Reader<&[u8]>,
    element: &BytesStart<'_>,
    key: &[u8],
) -> Result<Option<String>, ()> {
    for attr in element.attributes() {
        let attr = attr.map_err(|_| ())?;
        if attr.key.as_ref() == key {
            let value = attr
                .decode_and_unescape_value(reader.decoder())
                .map_err(|_| ())?;
            return Ok(Some(value.into_owned()));
        }
    }
    Ok(None)
}

#[derive(Debug, Clone, PartialEq)]
pub struct LocationSnapshot {
    pub latitude: f64,
    pub longitude: f64,
    pub altitude: f64,
    pub speed: f64,
    pub bearing: f64,
    pub accuracy: f64,
    pub updated_at: OffsetDateTime,
    pub peer_hash: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ChatEventInput {
    pub content: String,
    pub sender_label: String,
    pub topic_id: Option<String>,
    pub source_hash: Option<String>,
    pub timestamp: OffsetDateTime,
    pub message_uuid: Option<String>,
}

#[derive(Debug, Clone)]
pub struct TakConnector {
    config: TakConnectionConfig,
}

impl TakConnector {
    #[must_use]
    pub fn new(config: TakConnectionConfig) -> Self {
        Self { config }
    }

    #[must_use]
    pub fn config(&self) -> &TakConnectionConfig {
        &self.config
    }

    #[must_use]
    pub fn build_location_xml(
        &self,
        snapshot: &LocationSnapshot,
        now: OffsetDateTime,
        identity_label: Option<&str>,
    ) -> String {
        let uid = uid_from_hash(snapshot.peer_hash.as_deref(), &self.config.callsign);
        let callsign = identity_label
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map_or_else(|| uid.clone(), ToOwned::to_owned);
        let stale_delta = self.config.poll_interval_seconds.max(1.0) * 2.0;
        let stale = now + time::Duration::seconds_f64(stale_delta);
        let endpoint = cot_endpoint(self.config.cot_url.as_str());
        let endpoint_attr = endpoint
            .as_ref()
            .map(|value| format!(" endpoint=\"{}\"", escape_attr(value)))
            .unwrap_or_default();

        format!(
            "<event version=\"2.0\" uid=\"{}\" type=\"{}\" how=\"{}\" time=\"{}\" start=\"{}\" stale=\"{}\"><point lat=\"{}\" lon=\"{}\" hae=\"{}\" ce=\"{}\" le=\"{}\" /><detail><takv version=\"{}\" platform=\"{}\" os=\"{}\" device=\"{}\" /><contact callsign=\"{}\"{} /><__group name=\"{}\" role=\"{}\" /><track course=\"{}\" speed=\"{}\" /><uid Droid=\"{}\" /><status battery=\"{}\" /></detail></event>",
            escape_attr(uid.as_str()),
            EVENT_TYPE_LOCATION,
            EVENT_HOW,
            format_cot_seconds(now),
            format_cot_seconds(snapshot.updated_at),
            format_cot_seconds(stale),
            format_float(snapshot.latitude),
            format_float(snapshot.longitude),
            format_float(snapshot.altitude),
            format_float(snapshot.accuracy),
            format_float(snapshot.accuracy),
            TAKV_VERSION,
            TAKV_PLATFORM,
            TAKV_OS,
            TAKV_DEVICE,
            escape_attr(callsign.as_str()),
            endpoint_attr,
            GROUP_NAME,
            GROUP_ROLE,
            format_float(snapshot.bearing),
            format_float(snapshot.speed),
            escape_attr(callsign.as_str()),
            format_float(STATUS_BATTERY),
        )
    }

    pub fn build_chat_xml(&self, input: &ChatEventInput) -> Result<String, TakConnectorError> {
        let content = input.content.trim();
        if content.is_empty() {
            return Err(TakConnectorError::EmptyChatContent);
        }
        let chatroom = input.topic_id.as_deref().unwrap_or("All Chat Rooms");
        let sender_uid = uid_from_hash(input.source_hash.as_deref(), &self.config.callsign);
        let message_id = input
            .message_uuid
            .clone()
            .unwrap_or_else(|| Uuid::new_v4().to_string());
        let event_uid = format!("GeoChat.{sender_uid}.{chatroom}.{message_id}");
        let stale = input.timestamp + time::Duration::hours(24);
        let remarks_source = if sender_uid.is_empty() {
            "LXMF.CLIENT".to_string()
        } else {
            format!("LXMF.CLIENT.{sender_uid}")
        };

        Ok(format!(
            "<event version=\"2.0\" uid=\"{}\" type=\"{}\" how=\"{}\" time=\"{}\" start=\"{}\" stale=\"{}\" access=\"Undefined\"><point lat=\"0.0\" lon=\"0.0\" hae=\"9999999.0\" ce=\"9999999.0\" le=\"9999999.0\" /><detail><__chat id=\"{}\" chatroom=\"{}\" senderCallsign=\"{}\" groupOwner=\"false\" messageId=\"{}\"><chatgrp id=\"{}\" uid0=\"{}\" uid1=\"{}\" /></__chat><link uid=\"{}\" type=\"{}\" relation=\"p-p\" /><remarks source=\"{}\" sourceID=\"{}\" to=\"{}\" time=\"{}\">{}</remarks><marti><dest /></marti><__serverdestination /></detail></event>",
            escape_attr(event_uid.as_str()),
            CHAT_EVENT_TYPE,
            EVENT_HOW,
            format_cot_millis(input.timestamp),
            format_cot_millis(input.timestamp),
            format_cot_millis(stale),
            escape_attr(chatroom),
            escape_attr(chatroom),
            escape_attr(input.sender_label.as_str()),
            escape_attr(message_id.as_str()),
            escape_attr(chatroom),
            escape_attr(sender_uid.as_str()),
            escape_attr(chatroom),
            escape_attr(sender_uid.as_str()),
            CHAT_LINK_TYPE,
            escape_attr(remarks_source.as_str()),
            escape_attr(sender_uid.as_str()),
            escape_attr(chatroom),
            format_cot_millis(input.timestamp),
            escape_text(content),
        ))
    }

    #[must_use]
    pub fn build_ping_xml(&self, now: OffsetDateTime) -> String {
        let stale = now + time::Duration::seconds(120);
        let flow_tag_name = format!("{}-v0.0.0", sanitize_flow_tag_name(&self.config.callsign));
        format!(
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\" ?>\n<event version=\"2.0\" type=\"{}\" uid=\"{}\" how=\"{}\" time=\"{}\" start=\"{}\" stale=\"{}\"><point lat=\"0.0\" lon=\"0.0\" le=\"{}\" hae=\"{}\" ce=\"{}\" /><detail><_flow-tags_ {}=\"{}\" /></detail></event>",
            KEEPALIVE_EVENT_TYPE,
            PING_UID,
            KEEPALIVE_HOW,
            format_cot_micros(now),
            format_cot_micros(now),
            format_cot_micros(stale),
            DEFAULT_COT_VALUE,
            DEFAULT_COT_VALUE,
            DEFAULT_COT_VALUE,
            flow_tag_name,
            format_cot_micros(now),
        )
    }

    #[must_use]
    pub fn build_keepalive_xml(&self, now: OffsetDateTime) -> String {
        let stale = now + time::Duration::hours(1);
        format!(
            "<event version=\"2.0\" type=\"{}\" uid=\"{}\" how=\"{}\" time=\"{}\" start=\"{}\" stale=\"{}\" />",
            KEEPALIVE_EVENT_TYPE,
            PONG_UID,
            KEEPALIVE_HOW,
            format_cot_micros(now),
            format_cot_micros(now),
            format_cot_micros(stale),
        )
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CotPayloadKind {
    Location,
    Chat,
    Ping,
    Keepalive,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CotPayload {
    pub kind: CotPayloadKind,
    pub xml: String,
}

#[derive(Debug, Clone)]
pub struct TakOutboundQueue {
    capacity: usize,
    pending: VecDeque<CotPayload>,
    enqueued: u64,
    dropped_full: u64,
}

impl TakOutboundQueue {
    #[must_use]
    pub fn new(capacity: usize) -> Self {
        Self {
            capacity,
            pending: VecDeque::new(),
            enqueued: 0,
            dropped_full: 0,
        }
    }

    pub fn push(&mut self, payload: CotPayload) -> Result<(), TakConnectorError> {
        if self.pending.len() >= self.capacity {
            self.dropped_full = self.dropped_full.saturating_add(1);
            return Err(TakConnectorError::QueueFull);
        }
        self.pending.push_back(payload);
        self.enqueued = self.enqueued.saturating_add(1);
        Ok(())
    }

    pub fn enqueue_location(
        &mut self,
        connector: &TakConnector,
        snapshot: &LocationSnapshot,
        now: OffsetDateTime,
        identity_label: Option<&str>,
    ) -> Result<(), TakConnectorError> {
        self.push(CotPayload {
            kind: CotPayloadKind::Location,
            xml: connector.build_location_xml(snapshot, now, identity_label),
        })
    }

    pub fn enqueue_chat(
        &mut self,
        connector: &TakConnector,
        input: &ChatEventInput,
    ) -> Result<(), TakConnectorError> {
        self.push(CotPayload {
            kind: CotPayloadKind::Chat,
            xml: connector.build_chat_xml(input)?,
        })
    }

    pub fn enqueue_ping(
        &mut self,
        connector: &TakConnector,
        now: OffsetDateTime,
    ) -> Result<(), TakConnectorError> {
        self.push(CotPayload {
            kind: CotPayloadKind::Ping,
            xml: connector.build_ping_xml(now),
        })
    }

    pub fn enqueue_keepalive(
        &mut self,
        connector: &TakConnector,
        now: OffsetDateTime,
    ) -> Result<(), TakConnectorError> {
        self.push(CotPayload {
            kind: CotPayloadKind::Keepalive,
            xml: connector.build_keepalive_xml(now),
        })
    }

    pub fn pop(&mut self) -> Option<CotPayload> {
        self.pending.pop_front()
    }

    #[must_use]
    pub fn len(&self) -> usize {
        self.pending.len()
    }

    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.pending.is_empty()
    }

    #[must_use]
    pub fn stats(&self) -> TakQueueStats {
        TakQueueStats {
            capacity: self.capacity,
            pending: self.pending.len(),
            enqueued: self.enqueued,
            dropped_full: self.dropped_full,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TakQueueStats {
    pub capacity: usize,
    pub pending: usize,
    pub enqueued: u64,
    pub dropped_full: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CotUrl {
    pub scheme: String,
    pub host_port: String,
}

impl CotUrl {
    pub fn parse(cot_url: &str) -> Result<Self, TakConnectorError> {
        let (scheme, rest) = cot_url
            .split_once("://")
            .ok_or_else(|| TakConnectorError::InvalidCotUrl(cot_url.to_string()))?;
        let host_port_path = rest.split('/').next().unwrap_or_default();
        let host_port = host_port_path
            .split('@')
            .next_back()
            .unwrap_or(host_port_path)
            .trim();
        if scheme.is_empty() || host_port.is_empty() {
            return Err(TakConnectorError::InvalidCotUrl(cot_url.to_string()));
        }
        Ok(Self {
            scheme: scheme.to_ascii_lowercase(),
            host_port: host_port.to_string(),
        })
    }

    fn tls_server_name(&self) -> Result<String, TakConnectorError> {
        let host = if let Some(rest) = self.host_port.strip_prefix('[') {
            rest.split_once(']')
                .map(|(host, _)| host)
                .filter(|host| !host.is_empty())
        } else {
            self.host_port
                .split_once(':')
                .map(|(host, _)| host)
                .or(Some(self.host_port.as_str()))
                .filter(|host| !host.is_empty())
        };
        host.map(ToOwned::to_owned)
            .ok_or_else(|| TakConnectorError::InvalidCotUrl(self.host_port.clone()))
    }
}

pub trait TakCotSender {
    fn send(&self, payload: &CotPayload) -> Result<(), TakConnectorError>;
}

pub trait TakCotReceiver {
    fn receive(&mut self) -> Result<Option<Vec<u8>>, TakConnectorError>;
}

fn build_tls_connector(
    tls_ca: Option<&str>,
    tls_client_cert: Option<&str>,
    tls_client_key: Option<&str>,
    tls_client_password: Option<&str>,
    tls_insecure: bool,
    pytak_tls_dont_verify: u8,
) -> Result<TlsConnector, TakConnectorError> {
    let mut builder = TlsConnector::builder();
    if tls_insecure || pytak_tls_dont_verify != 0 {
        builder.danger_accept_invalid_certs(true);
        builder.danger_accept_invalid_hostnames(true);
    }
    if let Some(ca_path) = tls_ca {
        let ca_bytes =
            fs::read(ca_path).map_err(|error| TakConnectorError::Send(error.to_string()))?;
        let ca = Certificate::from_pem(ca_bytes.as_slice())
            .map_err(|error| TakConnectorError::Send(error.to_string()))?;
        builder.add_root_certificate(ca);
    }
    match (tls_client_cert, tls_client_key, tls_client_password) {
        (Some(cert_path), None, Some(password)) => {
            let identity_bytes =
                fs::read(cert_path).map_err(|error| TakConnectorError::Send(error.to_string()))?;
            let identity = Identity::from_pkcs12(identity_bytes.as_slice(), password)
                .map_err(|error| TakConnectorError::Send(error.to_string()))?;
            builder.identity(identity);
        }
        (Some(cert_path), Some(key_path), None) => {
            let cert_bytes =
                fs::read(cert_path).map_err(|error| TakConnectorError::Send(error.to_string()))?;
            let key_bytes =
                fs::read(key_path).map_err(|error| TakConnectorError::Send(error.to_string()))?;
            let identity = Identity::from_pkcs8(cert_bytes.as_slice(), key_bytes.as_slice())
                .map_err(|error| TakConnectorError::Send(error.to_string()))?;
            builder.identity(identity);
        }
        (Some(_), Some(_), Some(_)) => {
            return Err(TakConnectorError::Send(
                "TAK TLS client password requires a PKCS#12/PFX identity path in tls_client_cert without tls_client_key; encrypted PEM keys are not supported by native-tls".to_string(),
            ));
        }
        (Some(_), None, None) | (None, Some(_), _) => {
            return Err(TakConnectorError::Send(
                "TAK TLS client certificate and key must both be configured, or tls_client_cert must point to a PKCS#12/PFX identity when tls_client_password is configured".to_string(),
            ));
        }
        (None, None, _) => {}
    }
    builder
        .build()
        .map_err(|error| TakConnectorError::Send(error.to_string()))
}

#[derive(Debug, Clone)]
pub struct TakClearSender {
    url: CotUrl,
    tls_client_cert: Option<String>,
    tls_client_key: Option<String>,
    tls_ca: Option<String>,
    tls_insecure: bool,
    tls_client_password: Option<String>,
    pytak_tls_dont_verify: u8,
    tak_proto: u8,
}

impl TakClearSender {
    pub fn new(cot_url: &str) -> Result<Self, TakConnectorError> {
        Ok(Self {
            url: CotUrl::parse(cot_url)?,
            tls_client_cert: None,
            tls_client_key: None,
            tls_ca: None,
            tls_insecure: TakConnectionConfig::default().tls_insecure,
            tls_client_password: None,
            pytak_tls_dont_verify: TakConnectionConfig::default().pytak_tls_dont_verify,
            tak_proto: TakConnectionConfig::default().tak_proto,
        })
    }

    pub fn from_config(config: &TakConnectionConfig) -> Result<Self, TakConnectorError> {
        Ok(Self {
            url: CotUrl::parse(config.cot_url.as_str())?,
            tls_client_cert: config.tls_client_cert.clone(),
            tls_client_key: config.tls_client_key.clone(),
            tls_ca: config.tls_ca.clone(),
            tls_insecure: config.tls_insecure,
            tls_client_password: config.tls_client_password.clone(),
            pytak_tls_dont_verify: config.pytak_tls_dont_verify,
            tak_proto: config.tak_proto,
        })
    }

    fn tls_connector(&self) -> Result<TlsConnector, TakConnectorError> {
        build_tls_connector(
            self.tls_ca.as_deref(),
            self.tls_client_cert.as_deref(),
            self.tls_client_key.as_deref(),
            self.tls_client_password.as_deref(),
            self.tls_insecure,
            self.pytak_tls_dont_verify,
        )
    }

    fn send_tls(&self, payload: &CotPayload) -> Result<(), TakConnectorError> {
        let stream = TcpStream::connect(self.url.host_port.as_str())
            .map_err(|error| TakConnectorError::Send(error.to_string()))?;
        let server_name = self.url.tls_server_name()?;
        let connector = self.tls_connector()?;
        let mut stream = connector
            .connect(server_name.as_str(), stream)
            .map_err(|error| TakConnectorError::Send(format!("{error:?}")))?;
        let encoded = encode_outbound_cot_payload(payload, self.tak_proto);
        stream
            .write_all(encoded.as_slice())
            .map_err(|error| TakConnectorError::Send(error.to_string()))?;
        stream
            .flush()
            .map_err(|error| TakConnectorError::Send(error.to_string()))?;
        stream
            .shutdown()
            .map_err(|error| TakConnectorError::Send(error.to_string()))
    }
}

impl TakCotSender for TakClearSender {
    fn send(&self, payload: &CotPayload) -> Result<(), TakConnectorError> {
        match self.url.scheme.as_str() {
            "tcp" => {
                let mut stream = TcpStream::connect(self.url.host_port.as_str())
                    .map_err(|error| TakConnectorError::Send(error.to_string()))?;
                let encoded = encode_outbound_cot_payload(payload, self.tak_proto);
                stream
                    .write_all(encoded.as_slice())
                    .map_err(|error| TakConnectorError::Send(error.to_string()))?;
                stream
                    .flush()
                    .map_err(|error| TakConnectorError::Send(error.to_string()))
            }
            "udp" => {
                let socket = UdpSocket::bind("0.0.0.0:0")
                    .map_err(|error| TakConnectorError::Send(error.to_string()))?;
                let encoded = encode_outbound_cot_payload(payload, self.tak_proto);
                socket
                    .send_to(encoded.as_slice(), self.url.host_port.as_str())
                    .map(|_| ())
                    .map_err(|error| TakConnectorError::Send(error.to_string()))
            }
            "ssl" | "tls" => self.send_tls(payload),
            other => Err(TakConnectorError::UnsupportedScheme(other.to_string())),
        }
    }
}

#[derive(Debug, Clone)]
pub struct TakSocketReceiver {
    url: CotUrl,
    tls_client_cert: Option<String>,
    tls_client_key: Option<String>,
    tls_ca: Option<String>,
    tls_insecure: bool,
    tls_client_password: Option<String>,
    pytak_tls_dont_verify: u8,
    read_timeout: StdDuration,
    max_bytes: usize,
}

impl TakSocketReceiver {
    pub fn new(cot_url: &str) -> Result<Self, TakConnectorError> {
        Ok(Self {
            url: CotUrl::parse(cot_url)?,
            tls_client_cert: None,
            tls_client_key: None,
            tls_ca: None,
            tls_insecure: TakConnectionConfig::default().tls_insecure,
            tls_client_password: None,
            pytak_tls_dont_verify: TakConnectionConfig::default().pytak_tls_dont_verify,
            read_timeout: StdDuration::from_secs(2),
            max_bytes: 64 * 1024,
        })
    }

    pub fn from_config(config: &TakConnectionConfig) -> Result<Self, TakConnectorError> {
        Ok(Self {
            url: CotUrl::parse(config.cot_url.as_str())?,
            tls_client_cert: config.tls_client_cert.clone(),
            tls_client_key: config.tls_client_key.clone(),
            tls_ca: config.tls_ca.clone(),
            tls_insecure: config.tls_insecure,
            tls_client_password: config.tls_client_password.clone(),
            pytak_tls_dont_verify: config.pytak_tls_dont_verify,
            read_timeout: StdDuration::from_secs(2),
            max_bytes: 64 * 1024,
        })
    }

    #[must_use]
    pub fn with_read_timeout(mut self, read_timeout: StdDuration) -> Self {
        self.read_timeout = read_timeout;
        self
    }

    #[must_use]
    pub fn with_max_bytes(mut self, max_bytes: usize) -> Self {
        self.max_bytes = max_bytes.max(1);
        self
    }

    fn read_from_stream(
        &self,
        stream: &mut dyn Read,
    ) -> Result<Option<Vec<u8>>, TakConnectorError> {
        let mut buffer = vec![0_u8; self.max_bytes];
        match stream.read(buffer.as_mut_slice()) {
            Ok(0) => Ok(None),
            Ok(read) => {
                buffer.truncate(read);
                Ok(Some(buffer))
            }
            Err(error)
                if matches!(
                    error.kind(),
                    std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut
                ) =>
            {
                Ok(None)
            }
            Err(error) => Err(TakConnectorError::Send(error.to_string())),
        }
    }

    fn receive_tcp(&self) -> Result<Option<Vec<u8>>, TakConnectorError> {
        let mut stream = TcpStream::connect(self.url.host_port.as_str())
            .map_err(|error| TakConnectorError::Send(error.to_string()))?;
        stream
            .set_read_timeout(Some(self.read_timeout))
            .map_err(|error| TakConnectorError::Send(error.to_string()))?;
        self.read_from_stream(&mut stream)
    }

    fn receive_udp(&self) -> Result<Option<Vec<u8>>, TakConnectorError> {
        let socket = UdpSocket::bind(self.url.host_port.as_str())
            .map_err(|error| TakConnectorError::Send(error.to_string()))?;
        socket
            .set_read_timeout(Some(self.read_timeout))
            .map_err(|error| TakConnectorError::Send(error.to_string()))?;
        let mut buffer = vec![0_u8; self.max_bytes];
        match socket.recv(buffer.as_mut_slice()) {
            Ok(read) => {
                buffer.truncate(read);
                Ok(Some(buffer))
            }
            Err(error)
                if matches!(
                    error.kind(),
                    std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut
                ) =>
            {
                Ok(None)
            }
            Err(error) => Err(TakConnectorError::Send(error.to_string())),
        }
    }

    fn receive_tls(&self) -> Result<Option<Vec<u8>>, TakConnectorError> {
        let stream = TcpStream::connect(self.url.host_port.as_str())
            .map_err(|error| TakConnectorError::Send(error.to_string()))?;
        stream
            .set_read_timeout(Some(self.read_timeout))
            .map_err(|error| TakConnectorError::Send(error.to_string()))?;
        let server_name = self.url.tls_server_name()?;
        let connector = build_tls_connector(
            self.tls_ca.as_deref(),
            self.tls_client_cert.as_deref(),
            self.tls_client_key.as_deref(),
            self.tls_client_password.as_deref(),
            self.tls_insecure,
            self.pytak_tls_dont_verify,
        )?;
        let mut stream = connector
            .connect(server_name.as_str(), stream)
            .map_err(|error| TakConnectorError::Send(format!("{error:?}")))?;
        self.read_from_stream(&mut stream)
    }
}

impl TakCotReceiver for TakSocketReceiver {
    fn receive(&mut self) -> Result<Option<Vec<u8>>, TakConnectorError> {
        match self.url.scheme.as_str() {
            "tcp" => self.receive_tcp(),
            "udp" => self.receive_udp(),
            "ssl" | "tls" => self.receive_tls(),
            other => Err(TakConnectorError::UnsupportedScheme(other.to_string())),
        }
    }
}

pub fn drain_queue_to_sender(
    queue: &mut TakOutboundQueue,
    sender: &dyn TakCotSender,
) -> Result<usize, TakConnectorError> {
    let mut sent = 0;
    while let Some(payload) = queue.pending.front().cloned() {
        sender.send(&payload)?;
        let _ = queue.pop();
        sent += 1;
    }
    Ok(sent)
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TakInboundStatus {
    pub state: TakServiceState,
    pub parse_inbound: bool,
    pub total_received: u64,
    pub total_failed: u64,
    pub last_error: Option<String>,
    pub last_result_kind: Option<TakInboundResultKind>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TakInboundResultKind {
    Parsed,
    Raw,
}

#[derive(Debug, Clone, PartialEq)]
pub struct TakInboundPollReport {
    pub received: bool,
    pub result: Option<TakInboundCotResult>,
    pub status: TakInboundStatus,
    pub error: Option<String>,
}

#[derive(Debug, Clone)]
pub struct TakInboundService<R> {
    receiver: R,
    parse_inbound: bool,
    state: TakServiceState,
    total_received: u64,
    total_failed: u64,
    last_error: Option<String>,
    last_result_kind: Option<TakInboundResultKind>,
}

impl<R: TakCotReceiver> TakInboundService<R> {
    #[must_use]
    pub fn new(receiver: R, parse_inbound: bool) -> Self {
        Self {
            receiver,
            parse_inbound,
            state: TakServiceState::Stopped,
            total_received: 0,
            total_failed: 0,
            last_error: None,
            last_result_kind: None,
        }
    }

    pub fn start(&mut self) {
        self.state = TakServiceState::Running;
    }

    pub fn stop(&mut self) {
        self.state = TakServiceState::Stopped;
    }

    pub fn set_parse_inbound(&mut self, parse_inbound: bool) {
        self.parse_inbound = parse_inbound;
    }

    #[must_use]
    pub fn status(&self) -> TakInboundStatus {
        TakInboundStatus {
            state: self.state,
            parse_inbound: self.parse_inbound,
            total_received: self.total_received,
            total_failed: self.total_failed,
            last_error: self.last_error.clone(),
            last_result_kind: self.last_result_kind,
        }
    }

    pub fn poll_once(&mut self) -> Result<TakInboundPollReport, TakConnectorError> {
        if self.state != TakServiceState::Running {
            return Err(TakConnectorError::ServiceStopped);
        }
        match self.receiver.receive() {
            Ok(Some(payload)) => {
                let result = parse_inbound_cot_payload(payload, self.parse_inbound);
                self.total_received = self.total_received.saturating_add(1);
                self.last_error = None;
                self.last_result_kind = Some(match &result {
                    TakInboundCotResult::Parsed(_) => TakInboundResultKind::Parsed,
                    TakInboundCotResult::Raw(_) => TakInboundResultKind::Raw,
                });
                Ok(TakInboundPollReport {
                    received: true,
                    result: Some(result),
                    status: self.status(),
                    error: None,
                })
            }
            Ok(None) => Ok(TakInboundPollReport {
                received: false,
                result: None,
                status: self.status(),
                error: None,
            }),
            Err(error) => {
                self.total_failed = self.total_failed.saturating_add(1);
                self.last_error = Some(error.to_string());
                Ok(TakInboundPollReport {
                    received: false,
                    result: None,
                    status: self.status(),
                    error: Some(error.to_string()),
                })
            }
        }
    }
}

pub struct TakInboundWorker<R> {
    service: Arc<Mutex<TakInboundService<R>>>,
    stop: Arc<AtomicBool>,
    handle: Option<thread::JoinHandle<()>>,
}

impl<R> TakInboundWorker<R>
where
    R: TakCotReceiver + Send + 'static,
{
    pub fn spawn(mut service: TakInboundService<R>, retry_interval: StdDuration) -> Self {
        service.start();
        let service = Arc::new(Mutex::new(service));
        let stop = Arc::new(AtomicBool::new(false));
        let worker_service = Arc::clone(&service);
        let worker_stop = Arc::clone(&stop);
        let interval = retry_interval.max(StdDuration::from_millis(1));
        let handle = thread::spawn(move || {
            let mut current_interval = interval;
            while !worker_stop.load(Ordering::SeqCst) {
                if let Ok(mut service) = worker_service.lock() {
                    if let Ok(report) = service.poll_once() {
                        current_interval =
                            tak_inbound_interval_after_report(current_interval, interval, &report);
                    }
                }
                thread::sleep(current_interval);
            }
        });

        Self {
            service,
            stop,
            handle: Some(handle),
        }
    }

    #[must_use]
    pub fn service(&self) -> Arc<Mutex<TakInboundService<R>>> {
        Arc::clone(&self.service)
    }

    pub fn shutdown(&mut self) -> Option<TakInboundStatus> {
        self.stop.store(true, Ordering::SeqCst);
        if let Some(handle) = self.handle.take() {
            let _ = handle.join();
        }
        self.service.lock().ok().map(|mut service| {
            service.stop();
            service.status()
        })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TakServiceState {
    Stopped,
    Running,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TakServiceStatus {
    pub state: TakServiceState,
    pub queue: TakQueueStats,
    pub total_sent: u64,
    pub total_failed: u64,
    pub last_error: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TakServiceDispatchReport {
    pub enqueued: bool,
    pub sent: usize,
    pub status: TakServiceStatus,
    pub error: Option<String>,
}

#[derive(Debug, Clone)]
pub struct TakService<S> {
    connector: TakConnector,
    queue: TakOutboundQueue,
    sender: S,
    state: TakServiceState,
    total_sent: u64,
    total_failed: u64,
    last_error: Option<String>,
}

impl<S: TakCotSender> TakService<S> {
    #[must_use]
    pub fn new(config: TakConnectionConfig, queue_capacity: usize, sender: S) -> Self {
        Self {
            connector: TakConnector::new(config),
            queue: TakOutboundQueue::new(queue_capacity.max(1)),
            sender,
            state: TakServiceState::Stopped,
            total_sent: 0,
            total_failed: 0,
            last_error: None,
        }
    }

    pub fn start(&mut self) {
        self.state = TakServiceState::Running;
    }

    pub fn stop(&mut self) {
        self.state = TakServiceState::Stopped;
    }

    #[must_use]
    pub fn is_running(&self) -> bool {
        self.state == TakServiceState::Running
    }

    #[must_use]
    pub fn status(&self) -> TakServiceStatus {
        TakServiceStatus {
            state: self.state,
            queue: self.queue.stats(),
            total_sent: self.total_sent,
            total_failed: self.total_failed,
            last_error: self.last_error.clone(),
        }
    }

    #[must_use]
    pub fn config(&self) -> &TakConnectionConfig {
        self.connector.config()
    }

    pub fn enqueue_chat(
        &mut self,
        input: &ChatEventInput,
    ) -> Result<TakServiceDispatchReport, TakConnectorError> {
        self.ensure_running()?;
        let enqueue_result = self.queue.enqueue_chat(&self.connector, input);
        Ok(self.flush_after_enqueue(enqueue_result))
    }

    pub fn enqueue_location(
        &mut self,
        snapshot: &LocationSnapshot,
        now: OffsetDateTime,
        identity_label: Option<&str>,
    ) -> Result<TakServiceDispatchReport, TakConnectorError> {
        self.ensure_running()?;
        let enqueue_result =
            self.queue
                .enqueue_location(&self.connector, snapshot, now, identity_label);
        Ok(self.flush_after_enqueue(enqueue_result))
    }

    pub fn enqueue_ping(
        &mut self,
        now: OffsetDateTime,
    ) -> Result<TakServiceDispatchReport, TakConnectorError> {
        self.ensure_running()?;
        let enqueue_result = self.queue.enqueue_ping(&self.connector, now);
        Ok(self.flush_after_enqueue(enqueue_result))
    }

    pub fn enqueue_keepalive(
        &mut self,
        now: OffsetDateTime,
    ) -> Result<TakServiceDispatchReport, TakConnectorError> {
        self.ensure_running()?;
        let enqueue_result = self.queue.enqueue_keepalive(&self.connector, now);
        Ok(self.flush_after_enqueue(enqueue_result))
    }

    pub fn flush_once(&mut self) -> Result<TakServiceDispatchReport, TakConnectorError> {
        self.ensure_running()?;
        Ok(self.flush_after_enqueue(Ok(())))
    }

    fn ensure_running(&self) -> Result<(), TakConnectorError> {
        if self.is_running() {
            Ok(())
        } else {
            Err(TakConnectorError::ServiceStopped)
        }
    }

    fn flush_after_enqueue(
        &mut self,
        enqueue_result: Result<(), TakConnectorError>,
    ) -> TakServiceDispatchReport {
        if let Err(error) = enqueue_result {
            self.total_failed = self.total_failed.saturating_add(1);
            self.last_error = Some(error.to_string());
            return TakServiceDispatchReport {
                enqueued: false,
                sent: 0,
                status: self.status(),
                error: Some(error.to_string()),
            };
        }

        match drain_queue_to_sender(&mut self.queue, &self.sender) {
            Ok(sent) => {
                self.total_sent = self.total_sent.saturating_add(sent as u64);
                self.last_error = None;
                TakServiceDispatchReport {
                    enqueued: true,
                    sent,
                    status: self.status(),
                    error: None,
                }
            }
            Err(error) => {
                self.total_failed = self.total_failed.saturating_add(1);
                self.last_error = Some(error.to_string());
                TakServiceDispatchReport {
                    enqueued: true,
                    sent: 0,
                    status: self.status(),
                    error: Some(error.to_string()),
                }
            }
        }
    }
}

pub struct TakServiceWorker<S> {
    service: Arc<Mutex<TakService<S>>>,
    stop: Arc<AtomicBool>,
    handle: Option<thread::JoinHandle<()>>,
}

impl<S> TakServiceWorker<S>
where
    S: TakCotSender + Send + 'static,
{
    pub fn spawn(mut service: TakService<S>, retry_interval: StdDuration) -> Self {
        let keepalive_interval = StdDuration::from_secs_f64(
            service
                .connector
                .config()
                .keepalive_interval_seconds
                .max(1.0),
        );
        service.start();
        let service = Arc::new(Mutex::new(service));
        let stop = Arc::new(AtomicBool::new(false));
        let worker_service = Arc::clone(&service);
        let worker_stop = Arc::clone(&stop);
        let interval = retry_interval.max(StdDuration::from_millis(1));
        let handle = thread::spawn(move || {
            let mut last_ping: Option<Instant> = None;
            let mut last_keepalive: Option<Instant> = None;
            let mut current_interval = interval;
            while !worker_stop.load(Ordering::SeqCst) {
                if let Ok(mut service) = worker_service.lock() {
                    let mut send_failed = false;
                    if service.is_running() && !service.queue.is_empty() {
                        if let Ok(report) = service.flush_once() {
                            current_interval = tak_worker_interval_after_report(
                                current_interval,
                                interval,
                                &report,
                            );
                            send_failed = report.error.is_some();
                        }
                    }
                    if service.is_running() && !send_failed {
                        let now = Instant::now();
                        if last_ping
                            .is_none_or(|last| now.duration_since(last) >= keepalive_interval)
                        {
                            if let Ok(report) = service.enqueue_ping(OffsetDateTime::now_utc()) {
                                current_interval = tak_worker_interval_after_report(
                                    current_interval,
                                    interval,
                                    &report,
                                );
                                send_failed = report.error.is_some();
                            }
                            last_ping = Some(now);
                        }
                        if !send_failed
                            && last_keepalive
                                .is_none_or(|last| now.duration_since(last) >= keepalive_interval)
                        {
                            if let Ok(report) = service.enqueue_keepalive(OffsetDateTime::now_utc())
                            {
                                current_interval = tak_worker_interval_after_report(
                                    current_interval,
                                    interval,
                                    &report,
                                );
                            }
                            last_keepalive = Some(now);
                        }
                    }
                }
                thread::sleep(current_interval);
            }
        });

        Self {
            service,
            stop,
            handle: Some(handle),
        }
    }

    #[must_use]
    pub fn service(&self) -> Arc<Mutex<TakService<S>>> {
        Arc::clone(&self.service)
    }

    pub fn shutdown(&mut self) -> Option<TakServiceStatus> {
        self.stop.store(true, Ordering::SeqCst);
        if let Some(handle) = self.handle.take() {
            let _ = handle.join();
        }
        self.service.lock().ok().map(|mut service| {
            service.stop();
            service.status()
        })
    }
}

fn tak_worker_interval_after_report(
    current_interval: StdDuration,
    base_interval: StdDuration,
    report: &TakServiceDispatchReport,
) -> StdDuration {
    if report.error.is_some() {
        return current_interval
            .saturating_mul(2)
            .min(TAK_WORKER_MAX_BACKOFF);
    }
    base_interval
}

fn tak_inbound_interval_after_report(
    current_interval: StdDuration,
    base_interval: StdDuration,
    report: &TakInboundPollReport,
) -> StdDuration {
    if report.error.is_some() {
        return current_interval
            .saturating_mul(2)
            .min(TAK_WORKER_MAX_BACKOFF);
    }
    base_interval
}

impl<S> Drop for TakServiceWorker<S> {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::SeqCst);
        if let Some(handle) = self.handle.take() {
            let _ = handle.join();
        }
    }
}

impl<R> Drop for TakInboundWorker<R> {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::SeqCst);
        if let Some(handle) = self.handle.take() {
            let _ = handle.join();
        }
    }
}

#[must_use]
pub fn normalize_hash(peer_hash: Option<&str>) -> String {
    peer_hash.unwrap_or_default().trim().replace(':', "")
}

#[must_use]
pub fn uid_from_hash(peer_hash: Option<&str>, fallback_callsign: &str) -> String {
    let normalized = normalize_hash(peer_hash);
    if normalized.is_empty() {
        fallback_callsign.to_string()
    } else {
        normalized
    }
}

#[must_use]
pub fn cot_endpoint(cot_url: &str) -> Option<String> {
    let parsed = CotUrl::parse(cot_url).ok()?;
    Some(format!("{}:{}", parsed.host_port, parsed.scheme))
}

fn format_cot_seconds(timestamp: OffsetDateTime) -> String {
    let timestamp = timestamp
        .to_offset(time::UtcOffset::UTC)
        .replace_nanosecond(0)
        .expect("zero nanosecond is valid");
    timestamp
        .format(&Rfc3339)
        .expect("UTC timestamp should format")
        .replace("+00:00", "Z")
}

fn format_cot_millis(timestamp: OffsetDateTime) -> String {
    let timestamp = timestamp.to_offset(time::UtcOffset::UTC);
    let nanos = timestamp.nanosecond();
    let millis_nanos = (nanos / 1_000_000) * 1_000_000;
    let timestamp = timestamp
        .replace_nanosecond(millis_nanos)
        .expect("millisecond nanosecond is valid");
    timestamp
        .format(&Rfc3339)
        .expect("UTC timestamp should format")
        .replace("+00:00", "Z")
}

fn format_cot_micros(timestamp: OffsetDateTime) -> String {
    let timestamp = timestamp.to_offset(time::UtcOffset::UTC);
    format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}.{:06}Z",
        timestamp.year(),
        u8::from(timestamp.month()),
        timestamp.day(),
        timestamp.hour(),
        timestamp.minute(),
        timestamp.second(),
        timestamp.microsecond(),
    )
}

fn format_float(value: f64) -> String {
    if value.fract() == 0.0 {
        format!("{value:.1}")
    } else {
        value.to_string()
    }
}

fn escape_attr(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('"', "&quot;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

fn escape_text(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

fn sanitize_flow_tag_name(value: &str) -> String {
    let sanitized = value
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || matches!(ch, '_' | '-' | '.') {
                ch
            } else {
                '-'
            }
        })
        .collect::<String>();
    if sanitized.is_empty() {
        "R3AKT".to_string()
    } else {
        sanitized
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::ErrorKind;
    use std::io::Read;
    use std::net::TcpListener;
    use std::net::UdpSocket;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::mpsc;
    use std::thread;
    use time::macros::datetime;

    const TEST_TLS_CERT: &str = r"-----BEGIN CERTIFICATE-----
MIIDJTCCAg2gAwIBAgIUb/3y7pel5CjZq//+KyM8mXbo70IwDQYJKoZIhvcNAQEL
BQAwFDESMBAGA1UEAwwJMTI3LjAuMC4xMB4XDTI2MDUwNTA1NTA0M1oXDTM2MDUw
MjA1NTA0M1owFDESMBAGA1UEAwwJMTI3LjAuMC4xMIIBIjANBgkqhkiG9w0BAQEF
AAOCAQ8AMIIBCgKCAQEA3yHJqHSjSKUuqI2h2m+BxEqhZRIHUCLMzaQRVtC9Lx+E
mdJuzu4Df0IsdvtusJsCUsktL+oNA7EX9h4RfS9V2MTrBSwIVdEvA/L/SVhTlZUp
G94jBT4KvvKSkLPRfT+C0ZHrktJlOSkTzb+0VSmPIejUEvnt3+iYRv+GCb4SMrxj
18nifkSloxEviYLnE+V6r+I1E6VVhSoIXLFNMeizNb6EQ9NcMvkNpPMisYPS0p7e
qa9mCGAwD5QqsfAkexG/IhsxhLVDC+mdSfb9p6qqFmmR3bY6obD8lcjxakhQ/1Au
f+G0M0JsgEu/2Jr7XBaqYuwWr/mg3CS7XRj7Z3qK1wIDAQABo28wbTAdBgNVHQ4E
FgQUYgwoarOTrt7izJquESYZ1qdpsMcwHwYDVR0jBBgwFoAUYgwoarOTrt7izJqu
ESYZ1qdpsMcwDwYDVR0TAQH/BAUwAwEB/zAaBgNVHREEEzARhwR/AAABgglsb2Nh
bGhvc3QwDQYJKoZIhvcNAQELBQADggEBAL7BXiEd5rgwJuTKDzD4OV11G/u+HHZ9
nB4MYBddoA+VH1SBy5Od2wIwh6xc2wGSF2pQWOfIICycYGk1DGTa9rUx5ZMDiPdn
4/LQZYbEOJ8enwiuy7gd+KYeGobqd8i/6Kx5ctr89Spw+0nFoxOORySnc7j/GAyG
0xgT8VrmHODUc0rYaF1ZZGlnF3vCE2v8UW9WiXD1zVHGKwPcK/HhJRKrZc1iJfL3
a6zu487UDTxMXLI87v39mcPy+elj8aPb397nhNiCidzsHT2T2dk4SIZh4AzC132G
ah+jdX9LcXBgpUEFSGYmeiN7cQQCr0u1TBUzdzrTVcTt+vj5pOMwj7c=
-----END CERTIFICATE-----";

    const TEST_TLS_KEY: &str = r"-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDfIcmodKNIpS6o
jaHab4HESqFlEgdQIszNpBFW0L0vH4SZ0m7O7gN/Qix2+26wmwJSyS0v6g0DsRf2
HhF9L1XYxOsFLAhV0S8D8v9JWFOVlSkb3iMFPgq+8pKQs9F9P4LRkeuS0mU5KRPN
v7RVKY8h6NQS+e3f6JhG/4YJvhIyvGPXyeJ+RKWjES+JgucT5Xqv4jUTpVWFKghc
sU0x6LM1voRD01wy+Q2k8yKxg9LSnt6pr2YIYDAPlCqx8CR7Eb8iGzGEtUML6Z1J
9v2nqqoWaZHdtjqhsPyVyPFqSFD/UC5/4bQzQmyAS7/YmvtcFqpi7Bav+aDcJLtd
GPtneorXAgMBAAECggEALYACUyuVsFaesRhQjO54E8L0LlwCycCO6tAuCPn/2gAf
Vg6nMeMvK2AfGRQkejbhvmfvovmjNcGDFVkET/a7Frzw/9j+yiEh6Tg//oDYaoRE
Ib6mfYctQcrNQFyqt1OgJYQP+ZyVr5ZEx4v0Bfm3ij6kIEp+y03u32tztcDgjR+j
yTlrUA80i9cm7mRZFF/PXAtWmF409A6VNOPg1fU6wiXU8SzvJNY3LVsblybBwcmP
tZKftK7vWR9Mt6M6fxrQkqoySC6qz9wwxnwBTi0BTtNE/VBlnJilaXYVTE0HFQP1
pPv7AR/ARA+Tf7tr/ui65yMqJeauJittnEZiQ2REgQKBgQD9RggdkR7kxUImnsl2
qQwZX3xtW9914xGCXejkBpqIzrCDoyP7naxx7rXtD1i1mfYbROzTPRnakN16SBkR
JICL+1p+5NS7vVWjR6MsPvAThdHl5+sW28xpDJD0xzMVz4+pRQppThJsc6DzKqKf
TX/88lAoT95AU93yu7dyjamS8QKBgQDhiLE1ThrceCKAa56N51iBCgFaOmaueVdB
C0Bye2oK/62M8d7NIAnx/5nUWslmxQwJ+w0alaoFWG16af6SkMawesGFwQl3A6i6
vkVDdcmKJ674CU5XF4fStdLKZx5ceo4grm9kFVTAwwjm5e0Z4tKQBNYj/dwCHZYE
U3RpektqRwKBgQDvo6igGSRq/v11Pz6NyKtLAp7fdlM73qo9eI+X2Wu0UCSRmPW9
6FU2w89cyu17fn5vFMsjn6drty/nuHoHT0tVp3DbqbZjIGT8BhctESvkvPR6HPLC
ARwqtRoekLAUTfy3Az0zoAwsk0dRbSDLq++SrM8NJWy73t6dAeI0QDeXcQKBgEND
m2aEhupeQhv+/OjhqLnDnCem51z9/5H8oxoByNzC6KXytTqEZbLxQpXdBdhKyI5p
e70EChNSDkTGPBDGcRvNYM5dhk8inj4j5VB7XsJ/l2WOkPjUocOsStPm8V0viBgj
LkGxQvfCs3L5/D8OMTKW3q8ZVXakEEv1//A9cySdAoGAc7SWRHNQ8/YC04xS8rCr
cdCjOoMsOstpyO2lrHf5azS8xBnd/C68w3qWgr61UW0jcIc+Q1Oy72Yu7OtHDzMV
0SZeoMTZeJkM9T3wtGSZf1+2cjKp3c35LUh0PYTw93qMOKbj8Sk//PoQwrN0ismK
fN59G+INtr0cPXmM6zCYs+c=
-----END PRIVATE KEY-----";

    const TEST_TLS_PKCS12_BASE64: &str = "MIIKDwIBAzCCCcUGCSqGSIb3DQEHAaCCCbYEggmyMIIJrjCCBBoGCSqGSIb3DQEHBqCCBAswggQHAgEAMIIEAAYJKoZIhvcNAQcBMF8GCSqGSIb3DQEFDTBSMDEGCSqGSIb3DQEFDDAkBBCxqVcgWCneMRd0S26GKKHTAgIIADAMBggqhkiG9w0CCQUAMB0GCWCGSAFlAwQBKgQQL4QSU8Rv1gTjm7P0rMStpYCCA5De53qtK+umM9amW0lJbYMtoLiDqAIXrMIaSRsmxT68d6APs8NvXSnRk/peEpyiGIIIVa3WW/xw6WMRXwpmVRdEbncQ7vLil4Xi65RgvVBmOvaE9tIKdIeMNWBUqH3zI06RZ84REzEqAE7jbLrNaSHas3G6i+rtUqhlApOv1ieGEM5/Hjcc/PCkPV2IfVRP1NoBmTJndM+Fpric19n3lH0LlsZSg9A6D0b2m6llHJsiZB/QBzA8DdBcQqBTAHUaK8OvUyqhvuWP3WT78NEOhQDF9IXWsqkS2bolX6vXUyFkZdUB+TyK7KlgLfOGPMjj3mQQoH2EzudRAcM8RL+quXZGx7VelgZtcstqNAT5C0KJ3NgzgzjXRVYt9Xzav5Kad/pMhVy/uzTVHWyeSFpcWNd7rDR3oscqJ1hXCXjWw7XH30FFqpVoPfUmQ4X2zS1D/zTSlhmh/QAdyDYTHyO5I/dI7f1gS2JpXq84+gJrTvYECHHK39pLlIluD07yQpITKzR1yol3ykUeZR3pn5qIZAcNVW9GnT09bqfA0UtviG77qsrPr7H2oiRmaVY2BpEC3TVa4LH1ddfTZ9Durfm00IdHD+45bue+uwfYrWFyVSw4gUvYlhUBQY06I2PeJLvhita/qEVE/7lcabKB0si8mLQJQgODhzPgN4AnE+/oeMrmkdQlL2kw5Lg2oBlwGBYWYL6yjm4dSeNkrKQR9VagZcxsF0vNTPF2+Wahk2PHGQbUhMbnhUZ70U72E8nx6Cc9sQTK/SHwBA1uB7biwMDOWAmIV6SxkYEfkyXn5SVSL3IMyXuhaRwYUFs0Oi7gx50GHQTFJXicbK8vIa292CrjW5T1S3WTfeb2OTakXAikUF9p2tIJ2tbVsHCRntQX06OkBxMW8ykg2i7mid4UpdMHQm2OvImarAPUc1wUyQEzf7HeMh34GZo1dkFyin/THeuAUOOA2AicRL3U77GP1wMiXmprqvhugufK2vLiO6Uveo2mUYSvEqf4W2KdCXhhGpKzBaw/Gz8rA/e0wMoQuOfp5KeRlvugNzeku+4LngXj+rAY57fCDOjeG/ZemArYEblTNgHTWrm8I75SjJeT1MSgyLm9b2btzR8EAON8OYjELH8e+G9tPC7SNg9aIMSHq7191zaVT++nTVbIK8Zcx4jvvdf2e5lI97EjTTjiUgiYP/5fR/yMmFX7qYVVwxfF35EIDU4wggWMBgkqhkiG9w0BBwGgggV9BIIFeTCCBXUwggVxBgsqhkiG9w0BDAoBAqCCBTkwggU1MF8GCSqGSIb3DQEFDTBSMDEGCSqGSIb3DQEFDDAkBBCIDLDhuY8oVTrX+ugK+X2gAgIIADAMBggqhkiG9w0CCQUAMB0GCWCGSAFlAwQBKgQQT+VhpRLxMbVgaLUx08iJVwSCBNCgnRoNTnm3+r8Ck3Toxd1rwyBXbghcYlbI1MkinB0Y587Nh8gFIdTig1cY5radYMOYM5lWAcjwFt72Y+QLqZ+ykiXVFZI+6r3FIfQovEX+b071BZVcFXbB2nHNcFgo2O/ul++CfIKi69xX6VH0TF/zSvU1XKFFxBtX5I4FAOA0DKQBCbDfZXr/opUGYbIKTizh9cH7jpbm6rEvyGjAUaks1sNy4+zfrWV/QUQU7c2L/3//nK6bmWoBcePrhV5V4KPEPGp0JftbhglNX12AFH2WrQ3ZIMPl7T2jAIqba+loDKP5Rl4Zpo5O8MxNkBBmtWqQI6jB2gfFh+GX8cgiQhRVRSOweY5XFNck+iX6FDhaNhWFmAEKhjY3WcuVL4oc5goR5SWklPnmR5MQUWGe1doNPsYI7lpyPy84JT6bDuxEy7LfqJOaQzxkvkN1wadIvezBEmVmLA93MVdl8MDp7EsuFcqEQvleiA/qDxL0tfgplGOkVW1CN329rM+HTOHHAXJBHgQAgUe5G7J8dPc8xui4yf/6uW0iWyN3FRHTzhYP4R+kOKt47fNqzsbyEs11eiSqYGHD5j0sSRPHPUiU/pw1MlHrsvTcseZcV9iPhftcRHFSRW6z+AkjQ7hJm/cT0kwjaHYs6/btgpM0GTmNPfHD37vvg7I2gIjaAr333vt0ZgmN7c+oMj52ODIRxmVAdCMYDAFonw4OMZkcqGlO7mo4+GUeRq/atLauGCrBXFZh68PbSVF83zaHEEjv+CEYvQUFfEU8fExUfflEvcHouZtZpbSvFJjVgB12unI8PE6pHheDfm/ocVy0ot87Wfbii3S4Ym4CpEIkdwkGQ01Zts76Q3IVZZ283w+8yfNUQ7bd7FJBXOCDKWcvUyeo+D+nrelP8Pw4PpwWffCkUFeEwKAAs3Ae2jfcvNnRpM5XGOi7w+tmMkf8kgjmYlKdf4QRTR+Mq8wRuWjewCipYX7284WwSDPvn6600PPXIqyDfkp3YMUahB9EMkt3UKNhz+LzGXNUWotDGGEJNPWBrbMmJ9PsUkBWQyyxOiToVg9EMReP3RJneSvSxmvcqjMYcrxXPr5ER7An5PTYrgTjA7gnkWub7o0ZkGrfHqvLkn1v9z1xwAn2/wGjKKy0AB16edrKPXZQENvuhD/u1bRM2ubezOqYvohSgbmrE0xLqwHkAc7vzc83SD/vfgTv47856rj/qO8yHLwEGerfgWRBKkMU+07wkklt9A78NWAEhrWEZgvZONEfKMZiMvG1tmYYqwPl0LSXAgWgHG05uxjEjgV2iNGDni+9kxNUrf5Q5Z21v+kHN6dnkIGZMpCBkiFqt2OR6wgLEeyjD2P+a6FV2EyDZo2urc/JunNEkmIkxX+hWzIGLk2a4guB5YvqGTwdNWDQDfspkupL5u4MEM9H09+0mgKT4XweHHFGpWa6KFSeeieHcmzWCBfRUAcL4+hSoGoU6arUsxa9WitYOq5U3130LzRN+/qnfOB+NYxt3Oyd+vdFVCXePIZb8MXokxqVF/tOswWvw8IrEv8weNnau4zvyqDhvGDnj0TOViJWQ+JdCaVf3F6PJozdoDiIdJCPfRPua9JRKUMa85YVm2apEKVAXd0grEHy3RU7llbbNdwrvrknbTElMCMGCSqGSIb3DQEJFTEWBBQSOu5LkY1AOoCbbZ64EishPhGjvDBBMDEwDQYJYIZIAWUDBAIBBQAEIN8Xu1+osut1gR7muxpITLShMNY4brls8bHg3F5IC+NkBAg3gOXIxyT5vQICCAA=";

    #[test]
    fn inbound_cot_parse_disabled_returns_raw_payload_like_python_receive_worker() {
        let xml = "<event uid=\"alpha\" />";

        assert_eq!(
            parse_inbound_cot_payload(xml, false),
            TakInboundCotResult::Raw(xml.to_string())
        );
    }

    #[test]
    fn inbound_cot_parser_extracts_event_and_point_fields() {
        let xml = r#"<event version="2.0" uid="alpha" type="a-f-G-U-C" how="m-g" time="2025-01-01T00:00:00Z" start="2025-01-01T00:00:00Z" stale="2025-01-01T00:01:00Z" access="Undefined"><point lat="45.5" lon="-73.6" hae="12.3" ce="4.0" le="5.0" /><detail><contact callsign="ALPHA" /></detail></event>"#;

        assert_eq!(
            parse_inbound_cot_payload(xml.as_bytes(), true),
            TakInboundCotResult::Parsed(Box::new(TakInboundCotEvent {
                version: "2.0".to_string(),
                uid: "alpha".to_string(),
                event_type: "a-f-G-U-C".to_string(),
                how: "m-g".to_string(),
                time: "2025-01-01T00:00:00Z".to_string(),
                start: "2025-01-01T00:00:00Z".to_string(),
                stale: "2025-01-01T00:01:00Z".to_string(),
                access: Some("Undefined".to_string()),
                point: TakInboundCotPoint {
                    lat: 45.5,
                    lon: -73.6,
                    hae: 12.3,
                    ce: 4.0,
                    le: 5.0,
                },
            }))
        );
    }

    #[test]
    fn inbound_cot_parser_uses_python_default_event_values_when_point_is_missing() {
        let xml = "<event uid=\"alpha\" />";

        assert_eq!(
            parse_inbound_cot_payload(xml, true),
            TakInboundCotResult::Parsed(Box::new(TakInboundCotEvent {
                version: String::new(),
                uid: "alpha".to_string(),
                event_type: String::new(),
                how: String::new(),
                time: String::new(),
                start: String::new(),
                stale: String::new(),
                access: None,
                point: TakInboundCotPoint::default(),
            }))
        );
    }

    #[test]
    fn inbound_cot_parser_matches_python_root_and_direct_point_boundary() {
        let xml = r#"<not_event uid="root"><detail><point lat="45.5" lon="-73.6" /></detail></not_event>"#;

        assert_eq!(
            parse_inbound_cot_payload(xml, true),
            TakInboundCotResult::Parsed(Box::new(TakInboundCotEvent {
                version: String::new(),
                uid: "root".to_string(),
                event_type: String::new(),
                how: String::new(),
                time: String::new(),
                start: String::new(),
                stale: String::new(),
                access: None,
                point: TakInboundCotPoint::default(),
            }))
        );
    }

    #[test]
    fn inbound_cot_parser_falls_back_to_raw_on_invalid_xml_like_python_receive_worker() {
        let xml = "<event uid=\"alpha\"><point lat=\"not-a-number\" /></event>";

        assert_eq!(
            parse_inbound_cot_payload(xml, true),
            TakInboundCotResult::Raw(xml.to_string())
        );
    }

    #[test]
    fn inbound_service_polls_receiver_and_records_parsed_result() {
        #[derive(Debug)]
        struct QueueReceiver {
            payloads: VecDeque<Vec<u8>>,
        }

        impl TakCotReceiver for QueueReceiver {
            fn receive(&mut self) -> Result<Option<Vec<u8>>, TakConnectorError> {
                Ok(self.payloads.pop_front())
            }
        }

        let mut service = TakInboundService::new(
            QueueReceiver {
                payloads: VecDeque::from([br#"<event uid="alpha"><point lat="1" lon="2" hae="3" ce="4" le="5" /></event>"#.to_vec()]),
            },
            true,
        );

        assert_eq!(service.poll_once(), Err(TakConnectorError::ServiceStopped));

        service.start();
        let report = service.poll_once().expect("inbound poll");

        assert!(report.received);
        assert_eq!(report.status.total_received, 1);
        assert_eq!(
            report.status.last_result_kind,
            Some(TakInboundResultKind::Parsed)
        );
        assert!(matches!(
            report.result,
            Some(TakInboundCotResult::Parsed(event)) if event.uid == "alpha"
        ));

        let empty = service.poll_once().expect("empty inbound poll");
        assert!(!empty.received);
        assert_eq!(empty.status.total_received, 1);
    }

    #[test]
    fn inbound_service_can_record_raw_results_when_parse_is_disabled() {
        #[derive(Debug)]
        struct OneReceiver(Option<Vec<u8>>);

        impl TakCotReceiver for OneReceiver {
            fn receive(&mut self) -> Result<Option<Vec<u8>>, TakConnectorError> {
                Ok(self.0.take())
            }
        }

        let mut service = TakInboundService::new(
            OneReceiver(Some(b"<event uid=\"alpha\" />".to_vec())),
            false,
        );
        service.start();
        let report = service.poll_once().expect("inbound poll");

        assert_eq!(
            report.result,
            Some(TakInboundCotResult::Raw(
                "<event uid=\"alpha\" />".to_string()
            ))
        );
        assert_eq!(
            report.status.last_result_kind,
            Some(TakInboundResultKind::Raw)
        );
    }

    #[test]
    fn inbound_service_reports_receiver_errors_without_stopping() {
        #[derive(Debug)]
        struct ErrorReceiver;

        impl TakCotReceiver for ErrorReceiver {
            fn receive(&mut self) -> Result<Option<Vec<u8>>, TakConnectorError> {
                Err(TakConnectorError::Send("inbound offline".to_string()))
            }
        }

        let mut service = TakInboundService::new(ErrorReceiver, true);
        service.start();
        let report = service.poll_once().expect("inbound error report");

        assert!(!report.received);
        assert_eq!(report.status.state, TakServiceState::Running);
        assert_eq!(report.status.total_failed, 1);
        assert_eq!(
            report.error.as_deref(),
            Some("TAK send failed: inbound offline")
        );
    }

    #[test]
    fn location_cot_xml_matches_python_connector_shape() {
        let connector = TakConnector::new(TakConnectionConfig {
            cot_url: "udp://example:8087".to_string(),
            callsign: "HUB".to_string(),
            poll_interval_seconds: 10.0,
            ..TakConnectionConfig::default()
        });
        let snapshot = LocationSnapshot {
            latitude: 40.7128,
            longitude: -74.006,
            altitude: 12.0,
            speed: 2.5,
            bearing: 180.0,
            accuracy: 4.0,
            updated_at: datetime!(2025-01-01 00:00:00 UTC),
            peer_hash: Some("userhash1".to_string()),
        };

        let xml = connector.build_location_xml(&snapshot, datetime!(2025-01-01 00:00:05 UTC), None);

        assert!(xml.contains("uid=\"userhash1\""));
        assert!(xml.contains("type=\"a-f-G-U-C\""));
        assert!(xml.contains("start=\"2025-01-01T00:00:00Z\""));
        assert!(xml.contains("stale=\"2025-01-01T00:00:25Z\""));
        assert!(xml.contains(
            "<point lat=\"40.7128\" lon=\"-74.006\" hae=\"12.0\" ce=\"4.0\" le=\"4.0\" />"
        ));
        assert!(xml.contains("<takv version=\"0.44.0\" platform=\"RetTAK\" os=\"ubuntu\" device=\"not your business\" />"));
        assert!(xml.contains("<contact callsign=\"userhash1\" endpoint=\"example:8087:udp\" />"));
        assert!(xml.contains("<__group name=\"Yellow\" role=\"Team Member\" />"));
        assert!(xml.contains("<track course=\"180.0\" speed=\"2.5\" />"));
        assert!(xml.contains("<uid Droid=\"userhash1\" />"));
        assert!(xml.contains("<status battery=\"0.0\" />"));
    }

    #[test]
    fn location_cot_prefers_identity_label_for_callsign() {
        let connector = TakConnector::new(TakConnectionConfig::default());
        let snapshot = LocationSnapshot {
            latitude: 1.0,
            longitude: 2.0,
            altitude: 0.0,
            speed: 0.0,
            bearing: 0.0,
            accuracy: 0.0,
            updated_at: datetime!(2025-01-01 00:00:00 UTC),
            peer_hash: Some("aa:bb:cc:dd".to_string()),
        };

        let xml = connector.build_location_xml(
            &snapshot,
            datetime!(2025-01-01 00:00:00 UTC),
            Some("Display Name"),
        );

        assert!(xml.contains("uid=\"aabbccdd\""));
        assert!(
            xml.contains("<contact callsign=\"Display Name\" endpoint=\"127.0.0.1:8087:tcp\" />")
        );
        assert!(xml.contains("<uid Droid=\"Display Name\" />"));
    }

    #[test]
    fn chat_cot_xml_matches_python_connector_shape() {
        let connector = TakConnector::new(TakConnectionConfig {
            callsign: "HUB".to_string(),
            ..TakConnectionConfig::default()
        });
        let input = ChatEventInput {
            content: " hello <team> ".to_string(),
            sender_label: "Peer A".to_string(),
            topic_id: Some("mission.alpha".to_string()),
            source_hash: Some("aa:bb:cc:dd".to_string()),
            timestamp: datetime!(2025-01-01 00:00:00.123 UTC),
            message_uuid: Some("message-1".to_string()),
        };

        let xml = connector.build_chat_xml(&input).expect("chat xml");

        assert!(xml.contains("uid=\"GeoChat.aabbccdd.mission.alpha.message-1\""));
        assert!(xml.contains("type=\"b-t-f\""));
        assert!(xml.contains("access=\"Undefined\""));
        assert!(xml.contains(
            "<point lat=\"0.0\" lon=\"0.0\" hae=\"9999999.0\" ce=\"9999999.0\" le=\"9999999.0\" />"
        ));
        assert!(xml.contains("<__chat id=\"mission.alpha\" chatroom=\"mission.alpha\" senderCallsign=\"Peer A\" groupOwner=\"false\" messageId=\"message-1\"><chatgrp id=\"mission.alpha\" uid0=\"aabbccdd\" uid1=\"mission.alpha\" /></__chat>"));
        assert!(xml.contains("<link uid=\"aabbccdd\" type=\"a-f-G-U-C-I\" relation=\"p-p\" />"));
        assert!(xml.contains("<remarks source=\"LXMF.CLIENT.aabbccdd\" sourceID=\"aabbccdd\" to=\"mission.alpha\" time=\"2025-01-01T00:00:00.123Z\">hello &lt;team&gt;</remarks>"));
        assert!(xml.contains("<marti><dest /></marti>"));
        assert!(xml.contains("<__serverdestination />"));
    }

    #[test]
    fn chat_cot_rejects_empty_content() {
        let connector = TakConnector::new(TakConnectionConfig::default());
        let input = ChatEventInput {
            content: "   ".to_string(),
            sender_label: "Peer A".to_string(),
            topic_id: None,
            source_hash: None,
            timestamp: datetime!(2025-01-01 00:00:00 UTC),
            message_uuid: None,
        };

        assert_eq!(
            connector.build_chat_xml(&input),
            Err(TakConnectorError::EmptyChatContent)
        );
    }

    #[test]
    fn tak_keepalive_xml_matches_python_pytak_shapes() {
        let connector = TakConnector::new(TakConnectionConfig {
            callsign: "Hub@Node".to_string(),
            ..TakConnectionConfig::default()
        });
        let now = datetime!(2025-01-01 00:00:00.123456 UTC);

        let ping = connector.build_ping_xml(now);
        let keepalive = connector.build_keepalive_xml(now);

        assert!(
            ping.starts_with(
                "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\" ?>\n<event"
            )
        );
        assert!(ping.contains("type=\"t-x-d-d\""));
        assert!(ping.contains("uid=\"takPing\""));
        assert!(ping.contains("how=\"m-g\""));
        assert!(ping.contains("time=\"2025-01-01T00:00:00.123456Z\""));
        assert!(ping.contains("stale=\"2025-01-01T00:02:00.123456Z\""));
        assert!(ping.contains(
            "<point lat=\"0.0\" lon=\"0.0\" le=\"9999999.0\" hae=\"9999999.0\" ce=\"9999999.0\" />"
        ));
        assert!(ping.contains("<_flow-tags_ Hub-Node-v0.0.0=\"2025-01-01T00:00:00.123456Z\" />"));
        assert_eq!(
            keepalive,
            "<event version=\"2.0\" type=\"t-x-d-d\" uid=\"takPong\" how=\"m-g\" time=\"2025-01-01T00:00:00.123456Z\" start=\"2025-01-01T00:00:00.123456Z\" stale=\"2025-01-01T01:00:00.123456Z\" />"
        );
    }

    #[test]
    fn cot_endpoint_matches_python_url_derivation() {
        assert_eq!(
            cot_endpoint("udp://example:8087"),
            Some("example:8087:udp".to_string())
        );
        assert_eq!(
            cot_endpoint("tcp://127.0.0.1:8087"),
            Some("127.0.0.1:8087:tcp".to_string())
        );
        assert_eq!(cot_endpoint("not-a-url"), None);
    }

    #[test]
    fn cot_url_extracts_tls_server_name_from_host_port() {
        assert_eq!(
            CotUrl::parse("ssl://tak.example:8089")
                .expect("url")
                .tls_server_name(),
            Ok("tak.example".to_string())
        );
        assert_eq!(
            CotUrl::parse("tls://[::1]:8089")
                .expect("url")
                .tls_server_name(),
            Ok("::1".to_string())
        );
    }

    #[test]
    fn tak_tls_sender_preserves_python_tls_config() {
        let config = TakConnectionConfig {
            cot_url: "ssl://tak.example:8089".to_string(),
            tls_client_cert: Some("client.pem".to_string()),
            tls_client_key: Some("client.key".to_string()),
            tls_ca: Some("ca.pem".to_string()),
            tls_insecure: false,
            tls_client_password: Some("secret".to_string()),
            pytak_tls_dont_verify: 0,
            ..TakConnectionConfig::default()
        };

        let sender = TakClearSender::from_config(&config).expect("tls sender");

        assert_eq!(sender.url.scheme, "ssl");
        assert_eq!(sender.url.host_port, "tak.example:8089");
        assert_eq!(sender.tls_client_cert.as_deref(), Some("client.pem"));
        assert_eq!(sender.tls_client_key.as_deref(), Some("client.key"));
        assert_eq!(sender.tls_ca.as_deref(), Some("ca.pem"));
        assert!(!sender.tls_insecure);
        assert_eq!(sender.tls_client_password.as_deref(), Some("secret"));
        assert_eq!(sender.pytak_tls_dont_verify, 0);
    }

    #[test]
    fn tls_sender_rejects_password_with_separate_pem_key() {
        let sender = TakClearSender::from_config(&TakConnectionConfig {
            cot_url: "ssl://tak.example:8089".to_string(),
            tls_client_cert: Some("client.pem".to_string()),
            tls_client_key: Some("client.key".to_string()),
            tls_client_password: Some("secret".to_string()),
            ..TakConnectionConfig::default()
        })
        .expect("tls sender");

        let error = sender.tls_connector().expect_err("passworded pem rejected");

        assert_eq!(
            error,
            TakConnectorError::Send(
                "TAK TLS client password requires a PKCS#12/PFX identity path in tls_client_cert without tls_client_key; encrypted PEM keys are not supported by native-tls".to_string()
            )
        );
    }

    #[test]
    fn tls_sender_pushes_xml_payload() {
        let identity = Identity::from_pkcs8(TEST_TLS_CERT.as_bytes(), TEST_TLS_KEY.as_bytes())
            .expect("test identity");
        let acceptor = native_tls::TlsAcceptor::new(identity).expect("tls acceptor");
        let listener = TcpListener::bind("127.0.0.1:0").expect("tls listener");
        let addr = listener.local_addr().expect("tls listener addr");
        let (tx, rx) = mpsc::channel();
        let handle = thread::spawn(move || {
            let (stream, _) = listener.accept().expect("tls accept");
            let mut tls_stream = acceptor.accept(stream).expect("tls handshake");
            let mut buffer = Vec::new();
            let mut chunk = [0_u8; 1024];
            loop {
                match tls_stream.read(&mut chunk) {
                    Ok(0) => break,
                    Ok(read) => buffer.extend_from_slice(&chunk[..read]),
                    Err(error)
                        if matches!(
                            error.kind(),
                            ErrorKind::ConnectionReset | ErrorKind::ConnectionAborted
                        ) && !buffer.is_empty() =>
                    {
                        break;
                    }
                    Err(error) => panic!("read tls payload: {error}"),
                }
            }
            let received = String::from_utf8(buffer).expect("utf8 tls payload");
            tx.send(received).expect("send received payload");
        });
        let ca_path = std::env::temp_dir().join(format!("r3akt-tak-ca-{}.pem", Uuid::new_v4()));
        std::fs::write(&ca_path, TEST_TLS_CERT).expect("write test ca");
        let config = TakConnectionConfig {
            cot_url: format!("tls://{addr}"),
            tls_ca: Some(ca_path.to_string_lossy().to_string()),
            tls_insecure: false,
            pytak_tls_dont_verify: 0,
            ..TakConnectionConfig::default()
        };
        let sender = TakClearSender::from_config(&config).expect("tls sender");
        let connector = TakConnector::new(config);
        let payload = CotPayload {
            kind: CotPayloadKind::Keepalive,
            xml: connector.build_keepalive_xml(datetime!(2025-01-01 00:00:00 UTC)),
        };

        sender.send(&payload).expect("send tls payload");
        let received = rx.recv().expect("received tls payload");
        handle.join().expect("join tls server");
        let _ = std::fs::remove_file(ca_path);

        assert_eq!(received, payload.xml);
    }

    #[test]
    fn tls_sender_accepts_passworded_pkcs12_client_identity() {
        let identity = Identity::from_pkcs8(TEST_TLS_CERT.as_bytes(), TEST_TLS_KEY.as_bytes())
            .expect("test identity");
        let acceptor = native_tls::TlsAcceptor::new(identity).expect("tls acceptor");
        let listener = TcpListener::bind("127.0.0.1:0").expect("tls listener");
        let addr = listener.local_addr().expect("tls listener addr");
        let (tx, rx) = mpsc::channel();
        let handle = thread::spawn(move || {
            let (stream, _) = listener.accept().expect("tls accept");
            let mut tls_stream = acceptor.accept(stream).expect("tls handshake");
            let mut buffer = Vec::new();
            let mut chunk = [0_u8; 1024];
            loop {
                match tls_stream.read(&mut chunk) {
                    Ok(0) => break,
                    Ok(read) => buffer.extend_from_slice(&chunk[..read]),
                    Err(error)
                        if matches!(
                            error.kind(),
                            ErrorKind::ConnectionReset | ErrorKind::ConnectionAborted
                        ) && !buffer.is_empty() =>
                    {
                        break;
                    }
                    Err(error) => panic!("read tls payload: {error}"),
                }
            }
            let received = String::from_utf8(buffer).expect("utf8 tls payload");
            tx.send(received).expect("send received payload");
        });
        let ca_path = std::env::temp_dir().join(format!("r3akt-tak-ca-{}.pem", Uuid::new_v4()));
        let p12_path =
            std::env::temp_dir().join(format!("r3akt-tak-identity-{}.p12", Uuid::new_v4()));
        std::fs::write(&ca_path, TEST_TLS_CERT).expect("write test ca");
        let p12_bytes = {
            use base64::Engine as _;
            base64::engine::general_purpose::STANDARD
                .decode(TEST_TLS_PKCS12_BASE64)
                .expect("decode test pkcs12")
        };
        std::fs::write(&p12_path, p12_bytes).expect("write test pkcs12");
        let config = TakConnectionConfig {
            cot_url: format!("tls://{addr}"),
            tls_client_cert: Some(p12_path.to_string_lossy().to_string()),
            tls_client_password: Some("secret".to_string()),
            tls_ca: Some(ca_path.to_string_lossy().to_string()),
            tls_insecure: false,
            pytak_tls_dont_verify: 0,
            ..TakConnectionConfig::default()
        };
        let sender = TakClearSender::from_config(&config).expect("tls sender");
        let connector = TakConnector::new(config);
        let payload = CotPayload {
            kind: CotPayloadKind::Keepalive,
            xml: connector.build_keepalive_xml(datetime!(2025-01-01 00:00:00 UTC)),
        };

        sender.send(&payload).expect("send tls payload");
        let received = rx.recv().expect("received tls payload");
        handle.join().expect("join tls server");
        let _ = std::fs::remove_file(ca_path);
        let _ = std::fs::remove_file(p12_path);

        assert_eq!(received, payload.xml);
    }

    #[test]
    fn socket_receiver_reads_tcp_cot_payload() {
        let listener = TcpListener::bind("127.0.0.1:0").expect("tcp listener");
        let addr = listener.local_addr().expect("tcp listener addr");
        let payload = b"<event uid=\"tcp-inbound\" />".to_vec();
        let expected = payload.clone();
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("tcp accept");
            stream.write_all(payload.as_slice()).expect("write tcp cot");
            stream.flush().expect("flush tcp cot");
        });
        let mut socket_receiver = TakSocketReceiver::new(format!("tcp://{addr}").as_str())
            .expect("tcp receiver")
            .with_read_timeout(StdDuration::from_secs(1));

        let inbound_payload = socket_receiver.receive().expect("receive tcp cot");
        server.join().expect("join tcp server");

        assert_eq!(inbound_payload, Some(expected));
    }

    #[test]
    fn socket_receiver_reads_udp_cot_payload() {
        let reserved = UdpSocket::bind("127.0.0.1:0").expect("reserve udp addr");
        let addr = reserved.local_addr().expect("udp addr");
        drop(reserved);
        let payload = b"<event uid=\"udp-inbound\" />".to_vec();
        let expected = payload.clone();
        let receiver_thread = thread::spawn(move || {
            let mut receiver = TakSocketReceiver::new(format!("udp://{addr}").as_str())
                .expect("udp receiver")
                .with_read_timeout(StdDuration::from_secs(2));
            receiver.receive().expect("receive udp cot")
        });
        thread::sleep(StdDuration::from_millis(50));
        let sender = UdpSocket::bind("127.0.0.1:0").expect("udp sender");
        sender
            .send_to(payload.as_slice(), addr)
            .expect("send udp cot");

        assert_eq!(
            receiver_thread.join().expect("join udp receiver"),
            Some(expected)
        );
    }

    #[test]
    fn socket_receiver_reads_tls_cot_payload() {
        let identity = Identity::from_pkcs8(TEST_TLS_CERT.as_bytes(), TEST_TLS_KEY.as_bytes())
            .expect("test identity");
        let acceptor = native_tls::TlsAcceptor::new(identity).expect("tls acceptor");
        let listener = TcpListener::bind("127.0.0.1:0").expect("tls listener");
        let addr = listener.local_addr().expect("tls listener addr");
        let payload = b"<event uid=\"tls-inbound\" />".to_vec();
        let expected = payload.clone();
        let server = thread::spawn(move || {
            let (stream, _) = listener.accept().expect("tls accept");
            let mut tls_stream = acceptor.accept(stream).expect("tls handshake");
            tls_stream
                .write_all(payload.as_slice())
                .expect("write tls cot");
            tls_stream.flush().expect("flush tls cot");
        });
        let ca_path = std::env::temp_dir().join(format!("r3akt-tak-ca-{}.pem", Uuid::new_v4()));
        std::fs::write(&ca_path, TEST_TLS_CERT).expect("write test ca");
        let config = TakConnectionConfig {
            cot_url: format!("tls://{addr}"),
            tls_ca: Some(ca_path.to_string_lossy().to_string()),
            tls_insecure: false,
            pytak_tls_dont_verify: 0,
            ..TakConnectionConfig::default()
        };
        let mut socket_receiver = TakSocketReceiver::from_config(&config)
            .expect("tls receiver")
            .with_read_timeout(StdDuration::from_secs(1));

        let inbound_payload = socket_receiver.receive().expect("receive tls cot");
        server.join().expect("join tls server");
        let _ = std::fs::remove_file(ca_path);

        assert_eq!(inbound_payload, Some(expected));
    }

    #[test]
    fn outbound_queue_preserves_fifo_and_reports_backpressure() {
        let connector = TakConnector::new(TakConnectionConfig::default());
        let mut queue = TakOutboundQueue::new(1);
        let snapshot = LocationSnapshot {
            latitude: 40.0,
            longitude: -70.0,
            altitude: 1.0,
            speed: 0.0,
            bearing: 0.0,
            accuracy: 3.0,
            updated_at: datetime!(2025-01-01 00:00:00 UTC),
            peer_hash: Some("peer-a".to_string()),
        };
        queue
            .enqueue_location(
                &connector,
                &snapshot,
                datetime!(2025-01-01 00:00:01 UTC),
                None,
            )
            .expect("enqueue location");
        let second = queue.enqueue_location(
            &connector,
            &snapshot,
            datetime!(2025-01-01 00:00:02 UTC),
            None,
        );

        assert_eq!(second, Err(TakConnectorError::QueueFull));
        assert_eq!(
            queue.stats(),
            TakQueueStats {
                capacity: 1,
                pending: 1,
                enqueued: 1,
                dropped_full: 1,
            }
        );
        let payload = queue.pop().expect("payload");
        assert_eq!(payload.kind, CotPayloadKind::Location);
        assert!(payload.xml.contains("uid=\"peer-a\""));
        assert!(queue.is_empty());
    }

    #[test]
    fn outbound_queue_enqueues_chat_payloads() {
        let connector = TakConnector::new(TakConnectionConfig::default());
        let mut queue = TakOutboundQueue::new(2);
        let input = ChatEventInput {
            content: "status green".to_string(),
            sender_label: "Peer A".to_string(),
            topic_id: Some("ops".to_string()),
            source_hash: Some("peer-a".to_string()),
            timestamp: datetime!(2025-01-01 00:00:00 UTC),
            message_uuid: Some("msg-1".to_string()),
        };

        queue
            .enqueue_chat(&connector, &input)
            .expect("enqueue chat");

        let payload = queue.pop().expect("payload");
        assert_eq!(payload.kind, CotPayloadKind::Chat);
        assert!(payload.xml.contains("GeoChat.peer-a.ops.msg-1"));
        assert!(payload.xml.contains(">status green</remarks>"));
    }

    #[test]
    fn tak_service_dispatches_ping_and_keepalive_payloads() {
        #[derive(Debug, Clone)]
        struct RecordingSender {
            payloads: Arc<Mutex<Vec<CotPayload>>>,
        }

        impl TakCotSender for RecordingSender {
            fn send(&self, payload: &CotPayload) -> Result<(), TakConnectorError> {
                self.payloads
                    .lock()
                    .expect("payload lock")
                    .push(payload.clone());
                Ok(())
            }
        }

        let payloads = Arc::new(Mutex::new(Vec::new()));
        let mut service = TakService::new(
            TakConnectionConfig::default(),
            4,
            RecordingSender {
                payloads: Arc::clone(&payloads),
            },
        );
        service.start();

        let ping = service
            .enqueue_ping(datetime!(2025-01-01 00:00:00 UTC))
            .expect("ping dispatch");
        let keepalive = service
            .enqueue_keepalive(datetime!(2025-01-01 00:00:01 UTC))
            .expect("keepalive dispatch");

        assert_eq!(ping.sent, 1);
        assert_eq!(keepalive.sent, 1);
        let payloads = payloads.lock().expect("payload lock");
        assert_eq!(payloads[0].kind, CotPayloadKind::Ping);
        assert!(payloads[0].xml.contains("uid=\"takPing\""));
        assert_eq!(payloads[1].kind, CotPayloadKind::Keepalive);
        assert!(payloads[1].xml.contains("uid=\"takPong\""));
    }

    #[test]
    fn clear_tcp_sender_pushes_xml_payload() {
        let listener = TcpListener::bind("127.0.0.1:0").expect("listener");
        let addr = listener.local_addr().expect("addr");
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("accept");
            let mut body = String::new();
            stream.read_to_string(&mut body).expect("read");
            body
        });
        let payload = CotPayload {
            kind: CotPayloadKind::Keepalive,
            xml: "<event uid=\"takPong\" />".to_string(),
        };
        let sender = TakClearSender::new(format!("tcp://{addr}").as_str()).expect("sender");

        sender.send(&payload).expect("send");

        assert_eq!(server.join().expect("server"), payload.xml);
    }

    #[test]
    fn clear_tcp_sender_reconnects_after_server_closes_socket() {
        let listener = TcpListener::bind("127.0.0.1:0").expect("listener");
        let addr = listener.local_addr().expect("addr");
        let server = thread::spawn(move || {
            let mut received = Vec::new();
            for _ in 0..2 {
                let (mut stream, _) = listener.accept().expect("accept");
                let mut body = String::new();
                stream.read_to_string(&mut body).expect("read");
                received.push(body);
            }
            received
        });
        let first = CotPayload {
            kind: CotPayloadKind::Keepalive,
            xml: "<event uid=\"takPong-1\" />".to_string(),
        };
        let second = CotPayload {
            kind: CotPayloadKind::Keepalive,
            xml: "<event uid=\"takPong-2\" />".to_string(),
        };
        let sender = TakClearSender::new(format!("tcp://{addr}").as_str()).expect("sender");

        sender.send(&first).expect("send first");
        sender.send(&second).expect("send second after close");

        assert_eq!(server.join().expect("server"), vec![first.xml, second.xml]);
    }

    #[test]
    fn tak_proto_tcp_sender_pushes_stream_framed_protobuf_payload() {
        let listener = TcpListener::bind("127.0.0.1:0").expect("listener");
        let addr = listener.local_addr().expect("addr");
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("accept");
            let mut body = Vec::new();
            stream.read_to_end(&mut body).expect("read");
            body
        });
        let config = TakConnectionConfig {
            cot_url: format!("tcp://{addr}"),
            callsign: "RCH-PROTO".to_string(),
            tak_proto: 1,
            ..TakConnectionConfig::default()
        };
        let connector = TakConnector::new(config.clone());
        let sender = TakClearSender::from_config(&config).expect("sender");
        let payload = CotPayload {
            kind: CotPayloadKind::Location,
            xml: connector.build_location_xml(
                &LocationSnapshot {
                    latitude: 45.0,
                    longitude: -63.0,
                    altitude: 10.0,
                    speed: 2.5,
                    bearing: 180.0,
                    accuracy: 5.0,
                    updated_at: datetime!(2026-05-11 12:00:00 UTC),
                    peer_hash: Some("proto-peer".to_string()),
                },
                datetime!(2026-05-11 12:00:01 UTC),
                Some("Proto Peer"),
            ),
        };

        sender.send(&payload).expect("send");
        let received = server.join().expect("server");

        assert_eq!(received.first(), Some(&TAK_PROTO_MAGIC_BYTE));
        assert_ne!(received.first(), Some(&b'<'));
        assert!(
            received
                .windows(b"proto-peer".len())
                .any(|window| window == b"proto-peer")
        );
        assert!(
            received
                .windows(EVENT_TYPE_LOCATION.len())
                .any(|window| window == EVENT_TYPE_LOCATION.as_bytes())
        );
    }

    #[test]
    fn tak_tcp_loopback_validates_bidirectional_cot_workflow() {
        let outbound_listener = TcpListener::bind("127.0.0.1:0").expect("outbound listener");
        let outbound_addr = outbound_listener.local_addr().expect("outbound addr");
        let outbound_server = thread::spawn(move || {
            let (mut stream, _) = outbound_listener.accept().expect("outbound accept");
            let mut body = String::new();
            stream.read_to_string(&mut body).expect("read outbound cot");
            body
        });
        let outbound_config = TakConnectionConfig {
            cot_url: format!("tcp://{outbound_addr}"),
            callsign: "RCH-LOOPBACK".to_string(),
            ..TakConnectionConfig::default()
        };
        let outbound_connector = TakConnector::new(outbound_config.clone());
        let outbound_sender =
            TakClearSender::from_config(&outbound_config).expect("outbound sender");
        let keepalive = CotPayload {
            kind: CotPayloadKind::Keepalive,
            xml: outbound_connector.build_keepalive_xml(datetime!(2026-05-11 12:00:00 UTC)),
        };

        outbound_sender.send(&keepalive).expect("send outbound cot");
        let outbound_xml = outbound_server.join().expect("join outbound server");
        assert!(outbound_xml.contains("uid=\"takPong\""));
        assert!(outbound_xml.contains("type=\"t-x-d-d\""));

        let inbound_listener = TcpListener::bind("127.0.0.1:0").expect("inbound listener");
        let inbound_addr = inbound_listener.local_addr().expect("inbound addr");
        let inbound_server = thread::spawn(move || {
            let (mut stream, _) = inbound_listener.accept().expect("inbound accept");
            let cot = r#"<event version="2.0" uid="loopback-peer" type="a-f-G-U-C" how="m-g" time="2026-05-11T12:00:00Z" start="2026-05-11T12:00:00Z" stale="2026-05-11T12:05:00Z"><point lat="45.0" lon="-63.0" hae="10.0" ce="5.0" le="5.0" /></event>"#;
            stream.write_all(cot.as_bytes()).expect("write inbound cot");
            stream.flush().expect("flush inbound cot");
        });
        let mut inbound_receiver = TakSocketReceiver::new(format!("tcp://{inbound_addr}").as_str())
            .expect("inbound receiver")
            .with_read_timeout(StdDuration::from_secs(1));

        let inbound_payload = inbound_receiver
            .receive()
            .expect("receive inbound cot")
            .expect("inbound payload");
        inbound_server.join().expect("join inbound server");
        let parsed = parse_inbound_cot_payload(inbound_payload, true);

        match parsed {
            TakInboundCotResult::Parsed(event) => {
                assert_eq!(event.uid, "loopback-peer");
                assert_eq!(event.event_type, EVENT_TYPE_LOCATION);
                assert!((event.point.lat - 45.0).abs() < f64::EPSILON);
                assert!((event.point.lon + 63.0).abs() < f64::EPSILON);
            }
            TakInboundCotResult::Raw(raw) => panic!("expected parsed inbound CoT, got raw {raw}"),
        }
    }

    #[test]
    fn clear_udp_sender_pushes_xml_payload() {
        let socket = UdpSocket::bind("127.0.0.1:0").expect("udp listener");
        socket
            .set_read_timeout(Some(std::time::Duration::from_secs(2)))
            .expect("timeout");
        let addr = socket.local_addr().expect("addr");
        let server = thread::spawn(move || {
            let mut buf = [0_u8; 1024];
            let (len, _) = socket.recv_from(&mut buf).expect("recv");
            String::from_utf8(buf[..len].to_vec()).expect("utf8")
        });
        let payload = CotPayload {
            kind: CotPayloadKind::Keepalive,
            xml: "<event uid=\"takPong\" />".to_string(),
        };
        let sender = TakClearSender::new(format!("udp://{addr}").as_str()).expect("sender");

        sender.send(&payload).expect("send");

        assert_eq!(server.join().expect("server"), payload.xml);
    }

    #[test]
    fn live_tak_server_accepts_keepalive_when_configured() {
        let Some(config) = live_tak_config() else {
            eprintln!("skipping live TAK test: R3AKT_TAK_LIVE_COT_URL is unset");
            return;
        };
        let sender = TakClearSender::from_config(&config).expect("live TAK sender");
        let connector = TakConnector::new(config);
        let payload = CotPayload {
            kind: CotPayloadKind::Keepalive,
            xml: connector.build_keepalive_xml(OffsetDateTime::now_utc()),
        };

        sender.send(&payload).expect("send live TAK keepalive");
    }

    #[test]
    fn live_tak_server_accepts_reconnect_when_configured() {
        let Some(config) = live_tak_config() else {
            eprintln!("skipping live TAK reconnect test: R3AKT_TAK_LIVE_COT_URL is unset");
            return;
        };
        let sender = TakClearSender::from_config(&config).expect("live TAK sender");
        let connector = TakConnector::new(config);
        for _ in 0..2 {
            let payload = CotPayload {
                kind: CotPayloadKind::Keepalive,
                xml: connector.build_keepalive_xml(OffsetDateTime::now_utc()),
            };
            sender
                .send(&payload)
                .expect("send live TAK keepalive after reconnect");
            thread::sleep(StdDuration::from_millis(250));
        }
    }

    #[test]
    fn live_tak_server_provides_inbound_cot_when_configured() {
        let Some(config) = live_tak_config_from_url_env("R3AKT_TAK_LIVE_INBOUND_COT_URL") else {
            eprintln!("skipping live TAK inbound test: R3AKT_TAK_LIVE_INBOUND_COT_URL is unset");
            return;
        };
        let expected_uid = optional_env("R3AKT_TAK_LIVE_INBOUND_EXPECT_UID");
        let mut receiver = TakSocketReceiver::from_config(&config)
            .expect("live TAK receiver")
            .with_read_timeout(StdDuration::from_secs(5));

        let payload = receiver
            .receive()
            .expect("receive live TAK CoT")
            .expect("live TAK server should provide one CoT payload");
        let parsed = parse_inbound_cot_payload(payload, true);

        match parsed {
            TakInboundCotResult::Parsed(event) => {
                if let Some(expected_uid) = expected_uid {
                    assert_eq!(event.uid, expected_uid);
                } else {
                    assert!(!event.uid.trim().is_empty());
                }
            }
            TakInboundCotResult::Raw(raw) => panic!("expected parsed live TAK CoT, got raw {raw}"),
        }
    }

    fn live_tak_config() -> Option<TakConnectionConfig> {
        live_tak_config_from_url_env("R3AKT_TAK_LIVE_COT_URL")
    }

    fn live_tak_config_from_url_env(url_env: &str) -> Option<TakConnectionConfig> {
        let cot_url = optional_env(url_env)?;
        let tls_insecure = optional_env("R3AKT_TAK_LIVE_TLS_INSECURE")
            .as_deref()
            .is_some_and(parse_env_bool);
        Some(TakConnectionConfig {
            cot_url,
            callsign: optional_env("R3AKT_TAK_LIVE_CALLSIGN")
                .unwrap_or_else(|| "R3AKT-LIVE-TEST".to_string()),
            tls_ca: optional_env("R3AKT_TAK_LIVE_TLS_CA"),
            tls_client_cert: optional_env("R3AKT_TAK_LIVE_TLS_CLIENT_CERT"),
            tls_client_key: optional_env("R3AKT_TAK_LIVE_TLS_CLIENT_KEY"),
            tls_client_password: optional_env("R3AKT_TAK_LIVE_TLS_CLIENT_PASSWORD"),
            tls_insecure,
            pytak_tls_dont_verify: u8::from(tls_insecure),
            ..TakConnectionConfig::default()
        })
    }

    fn optional_env(name: &str) -> Option<String> {
        std::env::var(name)
            .ok()
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty())
    }

    fn parse_env_bool(value: &str) -> bool {
        matches!(
            value.trim().to_ascii_lowercase().as_str(),
            "1" | "true" | "yes" | "on"
        )
    }

    #[test]
    fn drain_queue_to_sender_stops_on_send_error() {
        struct FailingSender;

        impl TakCotSender for FailingSender {
            fn send(&self, _: &CotPayload) -> Result<(), TakConnectorError> {
                Err(TakConnectorError::Send("offline".to_string()))
            }
        }

        let mut queue = TakOutboundQueue::new(1);
        queue
            .push(CotPayload {
                kind: CotPayloadKind::Keepalive,
                xml: "<event uid=\"takPong\" />".to_string(),
            })
            .expect("push");

        assert_eq!(
            drain_queue_to_sender(&mut queue, &FailingSender),
            Err(TakConnectorError::Send("offline".to_string()))
        );
        assert_eq!(queue.len(), 1);
    }

    #[test]
    fn tak_service_requires_start_and_reports_lifecycle_state() {
        #[derive(Debug, Clone)]
        struct RecordingSender;

        impl TakCotSender for RecordingSender {
            fn send(&self, _: &CotPayload) -> Result<(), TakConnectorError> {
                Ok(())
            }
        }

        let input = ChatEventInput {
            content: "status green".to_string(),
            sender_label: "Peer A".to_string(),
            topic_id: Some("ops".to_string()),
            source_hash: Some("peer-a".to_string()),
            timestamp: datetime!(2025-01-01 00:00:00 UTC),
            message_uuid: Some("msg-1".to_string()),
        };
        let mut service = TakService::new(TakConnectionConfig::default(), 4, RecordingSender);

        assert_eq!(
            service.enqueue_chat(&input),
            Err(TakConnectorError::ServiceStopped)
        );
        assert_eq!(service.status().state, TakServiceState::Stopped);

        service.start();
        let report = service.enqueue_chat(&input).expect("dispatch");
        assert!(report.enqueued);
        assert_eq!(report.sent, 1);
        assert_eq!(report.status.state, TakServiceState::Running);
        assert_eq!(report.status.queue.pending, 0);
        assert_eq!(report.status.total_sent, 1);

        service.stop();
        assert_eq!(service.status().state, TakServiceState::Stopped);
    }

    #[test]
    fn tak_service_preserves_pending_payload_after_send_failure() {
        #[derive(Debug, Clone)]
        struct FailingSender;

        impl TakCotSender for FailingSender {
            fn send(&self, _: &CotPayload) -> Result<(), TakConnectorError> {
                Err(TakConnectorError::Send("offline".to_string()))
            }
        }

        let input = ChatEventInput {
            content: "status red".to_string(),
            sender_label: "Peer A".to_string(),
            topic_id: Some("ops".to_string()),
            source_hash: Some("peer-a".to_string()),
            timestamp: datetime!(2025-01-01 00:00:00 UTC),
            message_uuid: Some("msg-1".to_string()),
        };
        let mut service = TakService::new(TakConnectionConfig::default(), 4, FailingSender);
        service.start();

        let report = service.enqueue_chat(&input).expect("dispatch report");

        assert_eq!(report.sent, 0);
        assert_eq!(report.status.queue.pending, 1);
        assert_eq!(report.status.total_failed, 1);
        assert_eq!(report.error.as_deref(), Some("TAK send failed: offline"));
    }

    #[test]
    fn tak_worker_retry_interval_backs_off_and_resets_like_python_manager() {
        let status = TakServiceStatus {
            state: TakServiceState::Running,
            queue: TakQueueStats {
                capacity: 4,
                pending: 1,
                enqueued: 1,
                dropped_full: 0,
            },
            total_sent: 0,
            total_failed: 1,
            last_error: Some("TAK send failed: offline".to_string()),
        };
        let failed_report = TakServiceDispatchReport {
            enqueued: true,
            sent: 0,
            status: status.clone(),
            error: Some("TAK send failed: offline".to_string()),
        };
        let ok_report = TakServiceDispatchReport {
            enqueued: true,
            sent: 1,
            status,
            error: None,
        };
        let base = StdDuration::from_millis(500);

        let first = tak_worker_interval_after_report(base, base, &failed_report);
        let second = tak_worker_interval_after_report(first, base, &failed_report);
        let capped =
            tak_worker_interval_after_report(StdDuration::from_secs(29), base, &failed_report);
        let reset = tak_worker_interval_after_report(second, base, &ok_report);

        assert_eq!(first, StdDuration::from_secs(1));
        assert_eq!(second, StdDuration::from_secs(2));
        assert_eq!(capped, TAK_WORKER_MAX_BACKOFF);
        assert_eq!(reset, base);
    }

    #[test]
    fn tak_inbound_worker_retry_interval_backs_off_and_resets_like_python_manager() {
        let status = TakInboundStatus {
            state: TakServiceState::Running,
            parse_inbound: true,
            total_received: 0,
            total_failed: 1,
            last_error: Some("TAK send failed: inbound offline".to_string()),
            last_result_kind: None,
        };
        let failed_report = TakInboundPollReport {
            received: false,
            result: None,
            status: status.clone(),
            error: Some("TAK send failed: inbound offline".to_string()),
        };
        let ok_report = TakInboundPollReport {
            received: true,
            result: Some(TakInboundCotResult::Raw("<event />".to_string())),
            status,
            error: None,
        };
        let base = StdDuration::from_millis(500);

        let first = tak_inbound_interval_after_report(base, base, &failed_report);
        let second = tak_inbound_interval_after_report(first, base, &failed_report);
        let capped =
            tak_inbound_interval_after_report(StdDuration::from_secs(29), base, &failed_report);
        let reset = tak_inbound_interval_after_report(second, base, &ok_report);

        assert_eq!(first, StdDuration::from_secs(1));
        assert_eq!(second, StdDuration::from_secs(2));
        assert_eq!(capped, TAK_WORKER_MAX_BACKOFF);
        assert_eq!(reset, base);
    }

    #[test]
    fn tak_inbound_worker_retries_after_temporary_receive_failure() {
        #[derive(Debug, Clone)]
        struct FlakyReceiver {
            attempts: Arc<AtomicUsize>,
        }

        impl TakCotReceiver for FlakyReceiver {
            fn receive(&mut self) -> Result<Option<Vec<u8>>, TakConnectorError> {
                let attempt = self.attempts.fetch_add(1, Ordering::SeqCst);
                match attempt.cmp(&2) {
                    std::cmp::Ordering::Less => {
                        Err(TakConnectorError::Send("inbound offline".to_string()))
                    }
                    std::cmp::Ordering::Equal => Ok(Some(b"<event uid=\"recovered\" />".to_vec())),
                    std::cmp::Ordering::Greater => Ok(None),
                }
            }
        }

        let attempts = Arc::new(AtomicUsize::new(0));
        let service = TakInboundService::new(
            FlakyReceiver {
                attempts: Arc::clone(&attempts),
            },
            true,
        );
        let mut worker = TakInboundWorker::spawn(service, StdDuration::from_millis(10));
        let service = worker.service();

        for _ in 0..20 {
            {
                let service = service.lock().expect("inbound service lock");
                if service.status().total_received == 1 {
                    break;
                }
            }
            thread::sleep(StdDuration::from_millis(10));
        }

        let status = service.lock().expect("inbound service lock").status();
        assert_eq!(status.total_failed, 2);
        assert_eq!(status.total_received, 1);
        assert_eq!(status.last_error, None);
        assert_eq!(status.last_result_kind, Some(TakInboundResultKind::Parsed));

        let shutdown = worker.shutdown().expect("shutdown inbound status");
        assert_eq!(shutdown.state, TakServiceState::Stopped);
        assert!(attempts.load(Ordering::SeqCst) >= 3);
    }

    #[test]
    fn tak_service_worker_retries_pending_payloads_after_temporary_send_failure() {
        #[derive(Debug, Clone)]
        struct FlakySender {
            attempts: Arc<AtomicUsize>,
        }

        impl TakCotSender for FlakySender {
            fn send(&self, _: &CotPayload) -> Result<(), TakConnectorError> {
                if self.attempts.fetch_add(1, Ordering::SeqCst) == 0 {
                    Err(TakConnectorError::Send("offline".to_string()))
                } else {
                    Ok(())
                }
            }
        }

        let attempts = Arc::new(AtomicUsize::new(0));
        let input = ChatEventInput {
            content: "status amber".to_string(),
            sender_label: "Peer A".to_string(),
            topic_id: Some("ops".to_string()),
            source_hash: Some("peer-a".to_string()),
            timestamp: datetime!(2025-01-01 00:00:00 UTC),
            message_uuid: Some("msg-1".to_string()),
        };
        let mut service = TakService::new(
            TakConnectionConfig::default(),
            4,
            FlakySender {
                attempts: Arc::clone(&attempts),
            },
        );

        service.start();
        let report = service.enqueue_chat(&input).expect("dispatch report");
        assert_eq!(report.sent, 0);
        assert_eq!(report.status.queue.pending, 1);
        assert_eq!(report.status.total_failed, 1);

        let mut worker = TakServiceWorker::spawn(service, StdDuration::from_millis(10));
        let service = worker.service();

        for _ in 0..50 {
            let status = service.lock().expect("service lock").status();
            if status.queue.pending == 0 && status.total_sent == 3 {
                break;
            }
            thread::sleep(StdDuration::from_millis(10));
        }

        let status = service.lock().expect("service lock").status();
        assert_eq!(status.queue.pending, 0);
        assert_eq!(status.total_sent, 3);
        assert_eq!(status.total_failed, 1);
        assert_eq!(attempts.load(Ordering::SeqCst), 4);

        let shutdown = worker.shutdown().expect("shutdown status");
        assert_eq!(shutdown.state, TakServiceState::Stopped);
    }
}
