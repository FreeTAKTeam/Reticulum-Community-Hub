#![allow(clippy::items_after_test_module, clippy::missing_errors_doc)]

use std::collections::{BTreeMap, VecDeque};
use std::future::Future;
use std::io::{self, Read, Write};
use std::net::{Shutdown, TcpStream};
use std::pin::Pin;
use std::sync::OnceLock;
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use base64::Engine;
use lxmf_sdk::{
    Client as LxmfSdkClient, EventBatch as LxmfSdkEventBatch, EventCursor as LxmfSdkEventCursor,
    LxmfSdk, SdkConfig as LxmfSdkConfig, SdkEvent as LxmfSdkEvent,
    SendRequest as LxmfSdkSendRequest, StartRequest as LxmfSdkStartRequest, ZmqEndpointRole,
    ZmqPipelineBackendClient, ZmqPipelineBackendConfig,
};
use r3akt_protocol::{
    Destination, NodeId, Payload, ProtocolEnvelope, TelemetrySample, Topic, TopicAttachment,
    TopicMessage,
};
use rns_rpc::rpc::zmq::{self, ZmqRpcEnvelope, ZmqRpcEnvelopeKind};
use serde::{Deserialize, Serialize, de::DeserializeOwned};
use serde_json::Value as JsonValue;
use thiserror::Error;
use zeromq::{PullSocket, PushSocket, Socket, SocketRecv, SocketSend, ZmqMessage};

pub type TransportFuture<'a, T> =
    Pin<Box<dyn Future<Output = Result<T, TransportError>> + Send + 'a>>;

const RETICULUMD_RPC_TIMEOUT: Duration = Duration::from_secs(30);
// Match RCH's outbound dispatch deadline so a stuck ZeroMQ SDK response cannot
// leave the operator UI waiting on a long-lived local transport operation.
const LXMF_ZMQ_SEND_REQUEST_TIMEOUT: Duration = Duration::from_secs(30);
const LXMF_ZMQ_SEND_QUEUE_CAPACITY: usize = 20_000;
static ZMQ_SDK_OPERATION_LOCK: Mutex<()> = Mutex::new(());
static ZMQ_SDK_SEND_ACTORS: OnceLock<
    Mutex<BTreeMap<String, mpsc::SyncSender<ZmqSdkActorRequest>>>,
> = OnceLock::new();

#[derive(Debug, Error)]
pub enum TransportError {
    #[error("LXMF-rs adapter is not configured")]
    AdapterUnavailable,
    #[error("transport queue is full: {0}")]
    Backpressure(String),
    #[error("transport encode failed: {0}")]
    Encode(String),
    #[error("transport send failed: {0}")]
    Send(String),
    #[error("transport receive failed: {0}")]
    Receive(String),
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LxmfRsPeer {
    pub node_id: NodeId,
    pub lxmf_destination: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LxmfRsFrame {
    pub destination: String,
    pub bytes: Vec<u8>,
}

impl LxmfRsFrame {
    pub fn from_lxmf_wire_message(
        destination: impl Into<String>,
        message: &lxmf::WireMessage,
    ) -> Result<Self, TransportError> {
        let bytes = message
            .pack_storage()
            .map_err(|error| TransportError::Encode(error.to_string()))?;
        Ok(Self {
            destination: destination.into(),
            bytes,
        })
    }

    pub fn to_lxmf_wire_message(&self) -> Result<lxmf::WireMessage, TransportError> {
        lxmf::WireMessage::unpack_storage(&self.bytes)
            .map_err(|error| TransportError::Receive(error.to_string()))
    }
}

/// Boundary to the real LXMF-rs stack.
///
/// The inspected LXMF-rs checkout exposes `lxmf-wire`, `lxmf-sdk`,
/// `reticulum-rs-transport`, and `reticulumd`. This trait deliberately accepts
/// and emits raw LXMF payload bytes so product code can bind it to either the
/// SDK, the daemon RPC surface, or a future in-process runtime without coupling
/// R3AKT protocol crates to LXMF internals.
pub trait LxmfRsAdapter: Send {
    fn send_frame(&mut self, frame: LxmfRsFrame) -> TransportFuture<'_, ()>;
    fn receive_frame(&mut self) -> TransportFuture<'_, Option<LxmfRsFrame>>;
}

pub trait LxmfSdkRuntime: Send {
    fn send(&mut self, request: LxmfSdkSendRequest) -> Result<String, TransportError>;

    fn poll_events(
        &mut self,
        cursor: Option<LxmfSdkEventCursor>,
        max: usize,
    ) -> Result<LxmfSdkEventBatch, TransportError>;
}

impl LxmfSdkRuntime for LxmfSdkClient<ZmqPipelineBackendClient> {
    fn send(&mut self, request: LxmfSdkSendRequest) -> Result<String, TransportError> {
        LxmfSdk::send(self, request)
            .map(|message_id| message_id.to_string())
            .map_err(|error| TransportError::Send(format!("LXMF-rs ZeroMQ SDK: {error}")))
    }

    fn poll_events(
        &mut self,
        cursor: Option<LxmfSdkEventCursor>,
        max: usize,
    ) -> Result<LxmfSdkEventBatch, TransportError> {
        LxmfSdk::poll_events(self, cursor, max)
            .map_err(|error| TransportError::Receive(format!("LXMF-rs ZeroMQ SDK: {error}")))
    }
}

pub const R3AKT_LXMF_CONTENT: &str = "r3akt protocol envelope";
pub const R3AKT_LXMF_CONTENT_TYPE: &str = "application/x-r3akt-msgpack";
pub const R3AKT_LXMF_FIELD_CONTENT_TYPE: &str = "r3akt_content_type";
pub const R3AKT_LXMF_FIELD_PAYLOAD_B64: &str = "r3akt_payload_b64";

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ReticulumdRpcRequest {
    pub id: u64,
    pub method: String,
    pub params: Option<JsonValue>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ReticulumdRpcResponse {
    pub id: u64,
    pub result: Option<JsonValue>,
    pub error: Option<ReticulumdRpcError>,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct ReticulumdRpcError {
    pub code: String,
    pub message: String,
    #[serde(default)]
    pub machine_code: Option<String>,
    #[serde(default)]
    pub category: Option<String>,
    #[serde(default)]
    pub retryable: Option<bool>,
    #[serde(default)]
    pub is_user_actionable: Option<bool>,
    #[serde(default)]
    pub details: Option<JsonValue>,
    #[serde(default)]
    pub cause_code: Option<String>,
    #[serde(default)]
    pub extensions: Option<JsonValue>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ReticulumdEventRecord {
    pub event_id: String,
    #[serde(default)]
    pub runtime_id: Option<String>,
    #[serde(default)]
    pub stream_id: Option<String>,
    #[serde(default)]
    pub seq_no: Option<u64>,
    #[serde(default)]
    pub contract_version: Option<u16>,
    #[serde(default)]
    pub ts_ms: Option<u64>,
    pub event_type: String,
    #[serde(default)]
    pub severity: Option<String>,
    #[serde(default)]
    pub source_component: Option<String>,
    #[serde(default)]
    pub operation_id: Option<String>,
    #[serde(default)]
    pub message_id: Option<String>,
    #[serde(default)]
    pub peer_id: Option<String>,
    #[serde(default)]
    pub correlation_id: Option<String>,
    #[serde(default)]
    pub trace_id: Option<String>,
    #[serde(default)]
    pub payload: JsonValue,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ReticulumdEventBatch {
    #[serde(default)]
    pub events: Vec<ReticulumdEventRecord>,
    #[serde(default)]
    pub next_cursor: Option<String>,
    #[serde(default)]
    pub dropped_count: u64,
    #[serde(default)]
    pub snapshot_high_watermark_seq_no: Option<u64>,
}

pub trait ReticulumdRpcCall: Send {
    fn call(
        &mut self,
        method: &str,
        params: Option<JsonValue>,
    ) -> Result<ReticulumdRpcResponse, TransportError>;
}

pub enum ReticulumdRpcTransport<'a> {
    Endpoint {
        endpoint: String,
        next_request_id: u64,
    },
    Borrowed(&'a mut dyn ReticulumdRpcCall),
}

impl<'a> ReticulumdRpcTransport<'a> {
    #[must_use]
    pub fn new(endpoint: impl Into<String>) -> Self {
        Self::Endpoint {
            endpoint: endpoint.into(),
            next_request_id: 1,
        }
    }

    pub fn from_rpc(rpc: &'a mut dyn ReticulumdRpcCall) -> Self {
        Self::Borrowed(rpc)
    }

    fn call(
        &mut self,
        method: &str,
        params: Option<JsonValue>,
    ) -> Result<ReticulumdRpcResponse, TransportError> {
        match self {
            Self::Endpoint {
                endpoint,
                next_request_id,
            } => {
                let request = ReticulumdRpcRequest {
                    id: *next_request_id,
                    method: method.to_string(),
                    params,
                };
                *next_request_id = next_request_id.wrapping_add(1);
                reticulumd_rpc_call(endpoint, &request)
            }
            Self::Borrowed(rpc) => rpc.call(method, params),
        }
    }
}

pub struct ReticulumdRpcLxmfRsAdapter<'a> {
    source: String,
    rpc: ReticulumdRpcTransport<'a>,
    next_message_sequence: u64,
    seen_message_ids: VecDeque<String>,
    max_seen_message_ids: usize,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ReticulumdAnnounceRecord {
    pub id: String,
    pub peer: String,
    pub timestamp: i64,
    #[serde(default)]
    pub aspect: Option<String>,
    pub name: Option<String>,
    pub name_source: Option<String>,
    pub first_seen: i64,
    pub seen_count: u64,
    pub app_data_hex: Option<String>,
    #[serde(default)]
    pub capabilities: Vec<String>,
    pub rssi: Option<f64>,
    pub snr: Option<f64>,
    pub q: Option<f64>,
    #[serde(default)]
    pub interface: Option<String>,
    #[serde(default)]
    pub hops: Option<u64>,
    #[serde(default)]
    pub stamp_cost: Option<u32>,
    pub stamp_cost_flexibility: Option<u32>,
    pub peering_cost: Option<u32>,
}

pub fn list_reticulumd_announces(
    endpoint: &str,
    limit: usize,
) -> Result<Vec<ReticulumdAnnounceRecord>, TransportError> {
    let request = ReticulumdRpcRequest {
        id: 1,
        method: "list_announces".to_string(),
        params: Some(serde_json::json!({ "limit": limit.clamp(1, 5000) })),
    };
    let response = reticulumd_rpc_call(endpoint, &request)?;
    if let Some(error) = response.error {
        return Err(TransportError::Receive(format!(
            "reticulumd RPC {}: {}",
            error.code, error.message
        )));
    }
    let announces = response
        .result
        .as_ref()
        .and_then(|result| result.get("announces"))
        .and_then(JsonValue::as_array)
        .cloned()
        .unwrap_or_default();
    announces
        .into_iter()
        .map(|value| {
            serde_json::from_value(value)
                .map_err(|error| TransportError::Receive(error.to_string()))
        })
        .collect()
}

pub fn poll_reticulumd_events(
    endpoint: &str,
    cursor: Option<&str>,
    max: usize,
) -> Result<ReticulumdEventBatch, TransportError> {
    let request = ReticulumdRpcRequest {
        id: 1,
        method: "sdk_poll_events_v2".to_string(),
        params: Some(serde_json::json!({
            "cursor": cursor,
            "max": max.clamp(1, 256),
        })),
    };
    let response = reticulumd_rpc_call(endpoint, &request)?;
    if let Some(error) = response.error {
        return Err(TransportError::Receive(format!(
            "reticulumd RPC {}: {}",
            error.code, error.message
        )));
    }
    let result = response.result.unwrap_or_else(|| serde_json::json!({}));
    serde_json::from_value(result).map_err(|error| TransportError::Receive(error.to_string()))
}

impl<'a> ReticulumdRpcLxmfRsAdapter<'a> {
    #[must_use]
    pub fn new(source: impl Into<String>, rpc: ReticulumdRpcTransport<'a>) -> Self {
        Self {
            source: source.into(),
            rpc,
            next_message_sequence: 1,
            seen_message_ids: VecDeque::new(),
            max_seen_message_ids: 256,
        }
    }

    fn next_message_id(&mut self) -> String {
        let id = format!("r3akt-transport-{}", self.next_message_sequence);
        self.next_message_sequence = self.next_message_sequence.wrapping_add(1);
        id
    }

    fn remember_seen(&mut self, message_id: &str) {
        if self.seen_message_ids.iter().any(|seen| seen == message_id) {
            return;
        }
        self.seen_message_ids.push_back(message_id.to_string());
        while self.seen_message_ids.len() > self.max_seen_message_ids {
            self.seen_message_ids.pop_front();
        }
    }

    fn has_seen(&self, message_id: &str) -> bool {
        self.seen_message_ids.iter().any(|seen| seen == message_id)
    }
}

impl LxmfRsAdapter for ReticulumdRpcLxmfRsAdapter<'_> {
    fn send_frame(&mut self, frame: LxmfRsFrame) -> TransportFuture<'_, ()> {
        Box::pin(async move {
            let payload_b64 = base64::engine::general_purpose::STANDARD.encode(&frame.bytes);
            let params = serde_json::json!({
                "id": self.next_message_id(),
                "source": self.source,
                "destination": frame.destination,
                "title": "R3AKT",
                "content": R3AKT_LXMF_CONTENT,
                "fields": {
                    R3AKT_LXMF_FIELD_CONTENT_TYPE: R3AKT_LXMF_CONTENT_TYPE,
                    R3AKT_LXMF_FIELD_PAYLOAD_B64: payload_b64
                },
                "method": "direct"
            });
            let response = self.rpc.call("send_message_v2", Some(params))?;
            if let Some(error) = response.error {
                return Err(TransportError::Send(format!(
                    "reticulumd RPC {}: {}",
                    error.code, error.message
                )));
            }
            Ok(())
        })
    }

    fn receive_frame(&mut self) -> TransportFuture<'_, Option<LxmfRsFrame>> {
        Box::pin(async move {
            let response = self.rpc.call("list_messages", None)?;
            if let Some(error) = response.error {
                return Err(TransportError::Receive(format!(
                    "reticulumd RPC {}: {}",
                    error.code, error.message
                )));
            }
            let Some(messages) = response
                .result
                .as_ref()
                .and_then(|result| result.get("messages"))
                .and_then(JsonValue::as_array)
            else {
                return Ok(None);
            };
            for message in messages {
                let message_id = message
                    .get("id")
                    .and_then(JsonValue::as_str)
                    .unwrap_or_default();
                if message_id.is_empty() || self.has_seen(message_id) {
                    continue;
                }
                let payload_b64 = message
                    .get("fields")
                    .and_then(|fields| fields.get(R3AKT_LXMF_FIELD_PAYLOAD_B64))
                    .and_then(JsonValue::as_str);
                let bytes = if let Some(payload_b64) = payload_b64 {
                    base64::engine::general_purpose::STANDARD
                        .decode(payload_b64)
                        .map_err(|error| TransportError::Receive(error.to_string()))?
                } else if let Some(envelope) =
                    direct_lxmf_message_envelope(message, self.source.as_str())
                {
                    envelope
                        .encode_msgpack()
                        .map_err(|error| TransportError::Receive(error.to_string()))?
                } else {
                    continue;
                };
                self.remember_seen(message_id);
                let destination = message
                    .get("destination")
                    .and_then(JsonValue::as_str)
                    .unwrap_or(self.source.as_str())
                    .to_string();
                return Ok(Some(LxmfRsFrame { destination, bytes }));
            }
            Ok(None)
        })
    }
}

pub struct LxmfSdkLxmfRsAdapter<C> {
    source: String,
    runtime: C,
    next_message_sequence: u64,
    next_event_cursor: Option<String>,
    max_poll_events: usize,
}

impl<C> LxmfSdkLxmfRsAdapter<C>
where
    C: LxmfSdkRuntime,
{
    #[must_use]
    pub fn new(source: impl Into<String>, runtime: C) -> Self {
        Self {
            source: source.into(),
            runtime,
            next_message_sequence: 1,
            next_event_cursor: None,
            max_poll_events: 256,
        }
    }

    #[must_use]
    pub fn into_runtime(self) -> C {
        self.runtime
    }

    fn next_message_id(&mut self) -> String {
        let id = format!("r3akt-transport-{}", self.next_message_sequence);
        self.next_message_sequence = self.next_message_sequence.wrapping_add(1);
        id
    }
}

impl LxmfSdkLxmfRsAdapter<LxmfSdkClient<ZmqPipelineBackendClient>> {
    pub fn from_zmq_endpoints(
        source: impl Into<String>,
        command_endpoint: impl Into<String>,
        response_endpoint: impl Into<String>,
    ) -> Result<Self, TransportError> {
        let mut config = ZmqPipelineBackendConfig::local_tcp(command_endpoint, response_endpoint);
        config.request_timeout = LXMF_ZMQ_SEND_REQUEST_TIMEOUT;
        Self::from_zmq_config(source, config)
    }

    pub fn from_zmq_config(
        source: impl Into<String>,
        config: ZmqPipelineBackendConfig,
    ) -> Result<Self, TransportError> {
        let source = source.into();
        run_zmq_sdk_operation(move || {
            let backend = ZmqPipelineBackendClient::new(config)
                .map_err(|error| TransportError::Send(format!("LXMF-rs ZeroMQ SDK: {error}")))?;
            let client = LxmfSdkClient::new(backend);
            LxmfSdk::start(
                &client,
                LxmfSdkStartRequest::new(LxmfSdkConfig::desktop_local_default()),
            )
            .map_err(|error| TransportError::Send(format!("LXMF-rs ZeroMQ SDK start: {error}")))?;
            Ok(Self::new(source, client))
        })
    }
}

impl<C> LxmfRsAdapter for LxmfSdkLxmfRsAdapter<C>
where
    C: LxmfSdkRuntime,
{
    fn send_frame(&mut self, frame: LxmfRsFrame) -> TransportFuture<'_, ()> {
        Box::pin(async move {
            let payload_b64 = base64::engine::general_purpose::STANDARD.encode(&frame.bytes);
            let correlation_id = self.next_message_id();
            let payload = serde_json::json!({
                "title": "R3AKT",
                "content": R3AKT_LXMF_CONTENT,
                R3AKT_LXMF_FIELD_CONTENT_TYPE: R3AKT_LXMF_CONTENT_TYPE,
                R3AKT_LXMF_FIELD_PAYLOAD_B64: payload_b64
            });
            let request = LxmfSdkSendRequest::new(self.source.clone(), frame.destination, payload)
                .with_correlation_id(correlation_id.clone())
                .with_idempotency_key(correlation_id);
            self.runtime.send(request)?;
            Ok(())
        })
    }

    fn receive_frame(&mut self) -> TransportFuture<'_, Option<LxmfRsFrame>> {
        Box::pin(async move {
            let cursor = self.next_event_cursor.clone().map(LxmfSdkEventCursor);
            let batch = self.runtime.poll_events(cursor, self.max_poll_events)?;
            self.next_event_cursor = Some(batch.next_cursor.0.clone());
            for event in batch.events {
                let record = lxmf_sdk_event_to_reticulumd_event_record(event);
                if let Some(envelope) = reticulumd_event_to_envelope(&record, self.source.as_str())?
                {
                    let bytes = envelope
                        .encode_msgpack()
                        .map_err(|error| TransportError::Receive(error.to_string()))?;
                    return Ok(Some(LxmfRsFrame {
                        destination: destination_hint(&envelope),
                        bytes,
                    }));
                }
            }
            Ok(None)
        })
    }
}

pub struct LxmfSdkOutboundMessage {
    pub source: String,
    pub destination: String,
    pub title: String,
    pub content: String,
    pub fields: JsonValue,
    pub delivery_method: Option<String>,
    pub try_propagation_on_fail: bool,
    pub correlation_id: String,
}

pub fn send_lxmf_zmq_outbound_message(
    command_endpoint: impl Into<String>,
    response_endpoint: impl Into<String>,
    message: LxmfSdkOutboundMessage,
) -> Result<String, TransportError> {
    let mut config = rch_local_zmq_pipeline_config(command_endpoint, response_endpoint);
    config.request_timeout = LXMF_ZMQ_SEND_REQUEST_TIMEOUT;
    send_lxmf_zmq_outbound_message_via_actor(&config, message)
}

pub fn poll_lxmf_zmq_events(
    command_endpoint: impl Into<String>,
    response_endpoint: impl Into<String>,
    cursor: Option<String>,
    max: usize,
) -> Result<ReticulumdEventBatch, TransportError> {
    let config = rch_local_zmq_pipeline_config(command_endpoint, response_endpoint);
    run_zmq_sdk_operation(move || {
        let backend = ZmqPipelineBackendClient::new(config)
            .map_err(|error| TransportError::Receive(format!("LXMF-rs ZeroMQ SDK: {error}")))?;
        let client = LxmfSdkClient::new(backend);
        LxmfSdk::start(
            &client,
            LxmfSdkStartRequest::new(LxmfSdkConfig::desktop_local_default()),
        )
        .map_err(|error| TransportError::Receive(format!("LXMF-rs ZeroMQ SDK start: {error}")))?;
        let batch =
            LxmfSdk::poll_events(&client, cursor.map(LxmfSdkEventCursor), max.clamp(1, 256))
                .map_err(|error| TransportError::Receive(format!("LXMF-rs ZeroMQ SDK: {error}")))?;
        Ok(ReticulumdEventBatch {
            events: batch
                .events
                .into_iter()
                .map(lxmf_sdk_event_to_reticulumd_event_record)
                .collect(),
            next_cursor: Some(batch.next_cursor.0),
            dropped_count: batch.dropped_count,
            snapshot_high_watermark_seq_no: batch.snapshot_high_watermark_seq_no,
        })
    })
}

fn rch_local_zmq_pipeline_config(
    command_endpoint: impl Into<String>,
    response_endpoint: impl Into<String>,
) -> ZmqPipelineBackendConfig {
    ZmqPipelineBackendConfig {
        command_endpoint: command_endpoint.into(),
        command_role: ZmqEndpointRole::Connect,
        response_endpoint: response_endpoint.into(),
        response_role: ZmqEndpointRole::Bind,
        request_timeout: Duration::from_secs(5),
        max_envelope_bytes: zmq::ZMQ_RPC_MAX_ENVELOPE_BYTES,
        token_auth: None,
    }
}

fn run_zmq_sdk_operation<T>(
    operation: impl FnOnce() -> Result<T, TransportError> + Send + 'static,
) -> Result<T, TransportError>
where
    T: Send + 'static,
{
    std::thread::spawn(move || {
        let _guard = ZMQ_SDK_OPERATION_LOCK.lock().map_err(|error| {
            TransportError::Send(format!(
                "LXMF-rs ZeroMQ SDK operation lock poisoned: {error}"
            ))
        })?;
        operation()
    })
    .join()
    .map_err(|_| TransportError::Send("LXMF-rs ZeroMQ SDK worker panicked".to_string()))?
}

pub fn send_lxmf_sdk_outbound_message_with_runtime(
    runtime: &mut impl LxmfSdkRuntime,
    message: LxmfSdkOutboundMessage,
) -> Result<String, TransportError> {
    let mut payload = match message.fields {
        JsonValue::Object(map) => JsonValue::Object(map),
        other => serde_json::json!({ "fields": other }),
    };
    if let JsonValue::Object(map) = &mut payload {
        map.insert("title".to_string(), JsonValue::String(message.title));
        map.insert("content".to_string(), JsonValue::String(message.content));
    }
    let request = LxmfSdkSendRequest::new(message.source, message.destination, payload)
        .with_correlation_id(message.correlation_id.clone())
        .with_idempotency_key(message.correlation_id);
    runtime.send(request)
}

#[cfg(test)]
#[allow(dead_code)]
fn send_lxmf_zmq_outbound_message_direct(
    config: ZmqPipelineBackendConfig,
    message: LxmfSdkOutboundMessage,
) -> Result<String, TransportError> {
    let params = lxmf_sdk_outbound_send_params(message);
    let runtime = tokio::runtime::Runtime::new()
        .map_err(|error| TransportError::Send(format!("LXMF-rs ZeroMQ SDK runtime: {error}")))?;
    let result = runtime.block_on(async move {
        let mut command = PushSocket::new();
        command
            .connect(config.command_endpoint.as_str())
            .await
            .map_err(|error| TransportError::Send(format!("LXMF-rs ZeroMQ command: {error}")))?;
        let mut responses = PullSocket::new();
        responses
            .bind(config.response_endpoint.as_str())
            .await
            .map_err(|error| {
                TransportError::Receive(format!("LXMF-rs ZeroMQ response: {error}"))
            })?;
        tokio::time::sleep(Duration::from_millis(50)).await;
        let session_id = lxmf_zmq_session_id();
        let negotiation = serde_json::json!({
            "supported_contract_versions": [2],
            "requested_capabilities": [],
            "config": {
                "profile": "desktop-local-runtime",
                "bind_mode": "local_only",
                "auth_mode": "local_trusted",
                "overflow_policy": "reject",
                "block_timeout_ms": null,
                "rpc_backend": {
                    "listen_addr": "unix:/tmp/lxmf-rpc.sock",
                    "read_timeout_ms": 5000,
                    "write_timeout_ms": 5000,
                    "max_header_bytes": 16384,
                    "max_body_bytes": 1_048_576,
                    "token_auth": null,
                    "mtls_auth": null
                }
            }
        });
        let _ = lxmf_zmq_rpc_call(
            &mut command,
            &mut responses,
            &config,
            session_id.as_str(),
            1,
            "sdk_negotiate_v2",
            Some(negotiation),
        )
        .await?;
        lxmf_zmq_rpc_call(
            &mut command,
            &mut responses,
            &config,
            session_id.as_str(),
            2,
            "sdk_send_v2",
            Some(params),
        )
        .await
    })?;
    result
        .get("message_id")
        .and_then(JsonValue::as_str)
        .map(str::to_string)
        .ok_or_else(|| {
            TransportError::Send("LXMF-rs ZeroMQ SDK response missing message_id".to_string())
        })
}

struct ZmqSdkActorRequest {
    message: LxmfSdkOutboundMessage,
    response: mpsc::Sender<Result<String, TransportError>>,
}

struct ZmqSdkActorSession {
    command: PushSocket,
    responses: PullSocket,
    session_id: String,
    next_request_id: u64,
}

fn send_lxmf_zmq_outbound_message_via_actor(
    config: &ZmqPipelineBackendConfig,
    message: LxmfSdkOutboundMessage,
) -> Result<String, TransportError> {
    let sender = zmq_sdk_actor_sender(config)?;
    let (response_tx, response_rx) = mpsc::channel();
    sender
        .try_send(ZmqSdkActorRequest {
            message,
            response: response_tx,
        })
        .map_err(|error| match error {
            mpsc::TrySendError::Full(_) => TransportError::Backpressure(format!(
                "LXMF-rs ZeroMQ SDK send queue is full (capacity {LXMF_ZMQ_SEND_QUEUE_CAPACITY})"
            )),
            mpsc::TrySendError::Disconnected(_) => {
                TransportError::Send("LXMF-rs ZeroMQ SDK send actor stopped".to_string())
            }
        })?;
    response_rx
        .recv_timeout(
            config
                .request_timeout
                .saturating_add(Duration::from_secs(1)),
        )
        .map_err(|error| match error {
            mpsc::RecvTimeoutError::Timeout => TransportError::Receive(
                "LXMF-rs ZeroMQ SDK actor timed out waiting for send result".to_string(),
            ),
            mpsc::RecvTimeoutError::Disconnected => {
                TransportError::Send("LXMF-rs ZeroMQ SDK send actor stopped".to_string())
            }
        })?
}

fn zmq_sdk_actor_sender(
    config: &ZmqPipelineBackendConfig,
) -> Result<mpsc::SyncSender<ZmqSdkActorRequest>, TransportError> {
    let key = zmq_sdk_actor_key(config);
    let actors = ZMQ_SDK_SEND_ACTORS.get_or_init(|| Mutex::new(BTreeMap::new()));
    let mut actors = actors
        .lock()
        .map_err(|error| TransportError::Send(format!("LXMF-rs ZeroMQ SDK actor map: {error}")))?;
    if let Some(sender) = actors.get(&key) {
        return Ok(sender.clone());
    }
    let (sender, receiver) = mpsc::sync_channel(LXMF_ZMQ_SEND_QUEUE_CAPACITY);
    let actor_config = config.clone();
    std::thread::Builder::new()
        .name("rch-lxmf-zmq-send-actor".to_string())
        .spawn(move || run_zmq_sdk_actor(actor_config, receiver))
        .map_err(|error| TransportError::Send(format!("LXMF-rs ZeroMQ SDK actor: {error}")))?;
    actors.insert(key, sender.clone());
    Ok(sender)
}

fn zmq_sdk_actor_key(config: &ZmqPipelineBackendConfig) -> String {
    format!("{}|{}", config.command_endpoint, config.response_endpoint)
}

#[allow(clippy::needless_pass_by_value)]
fn run_zmq_sdk_actor(
    config: ZmqPipelineBackendConfig,
    receiver: mpsc::Receiver<ZmqSdkActorRequest>,
) {
    let runtime = match tokio::runtime::Runtime::new() {
        Ok(runtime) => runtime,
        Err(error) => {
            while let Ok(request) = receiver.recv() {
                let _ = request.response.send(Err(TransportError::Send(format!(
                    "LXMF-rs ZeroMQ SDK runtime: {error}"
                ))));
            }
            return;
        }
    };
    let mut session: Option<ZmqSdkActorSession> = None;
    while let Ok(request) = receiver.recv() {
        if session.is_none() {
            match runtime.block_on(open_zmq_sdk_actor_session(&config)) {
                Ok(opened) => session = Some(opened),
                Err(error) => {
                    let _ = request.response.send(Err(error));
                    continue;
                }
            }
        }
        let Some(active_session) = session.as_mut() else {
            let _ = request.response.send(Err(TransportError::Send(
                "LXMF-rs ZeroMQ SDK session unavailable".to_string(),
            )));
            continue;
        };
        let result = runtime.block_on(send_lxmf_zmq_actor_message(
            active_session,
            &config,
            request.message,
        ));
        if result.is_err() {
            session = None;
        }
        let _ = request.response.send(result);
    }
}

async fn open_zmq_sdk_actor_session(
    config: &ZmqPipelineBackendConfig,
) -> Result<ZmqSdkActorSession, TransportError> {
    let mut command = PushSocket::new();
    command
        .connect(config.command_endpoint.as_str())
        .await
        .map_err(|error| TransportError::Send(format!("LXMF-rs ZeroMQ command: {error}")))?;
    let mut responses = PullSocket::new();
    responses
        .bind(config.response_endpoint.as_str())
        .await
        .map_err(|error| TransportError::Receive(format!("LXMF-rs ZeroMQ response: {error}")))?;
    tokio::time::sleep(Duration::from_millis(50)).await;
    let session_id = lxmf_zmq_session_id();
    let negotiation = serde_json::json!({
        "supported_contract_versions": [2],
        "requested_capabilities": [],
        "config": {
            "profile": "desktop-local-runtime",
            "bind_mode": "local_only",
            "auth_mode": "local_trusted",
            "overflow_policy": "reject",
            "block_timeout_ms": null,
            "rpc_backend": {
                "listen_addr": "unix:/tmp/lxmf-rpc.sock",
                "read_timeout_ms": 5000,
                "write_timeout_ms": 5000,
                "max_header_bytes": 16384,
                "max_body_bytes": 1_048_576,
                "token_auth": null,
                "mtls_auth": null
            }
        }
    });
    let _ = lxmf_zmq_rpc_call(
        &mut command,
        &mut responses,
        config,
        session_id.as_str(),
        1,
        "sdk_negotiate_v2",
        Some(negotiation),
    )
    .await?;
    Ok(ZmqSdkActorSession {
        command,
        responses,
        session_id,
        next_request_id: 2,
    })
}

async fn send_lxmf_zmq_actor_message(
    session: &mut ZmqSdkActorSession,
    config: &ZmqPipelineBackendConfig,
    message: LxmfSdkOutboundMessage,
) -> Result<String, TransportError> {
    let request_id = session.next_request_id;
    session.next_request_id = session.next_request_id.saturating_add(1);
    let result = lxmf_zmq_rpc_call(
        &mut session.command,
        &mut session.responses,
        config,
        session.session_id.as_str(),
        request_id,
        "sdk_send_v2",
        Some(lxmf_sdk_outbound_send_params(message)),
    )
    .await?;
    result
        .get("message_id")
        .and_then(JsonValue::as_str)
        .map(str::to_string)
        .ok_or_else(|| {
            TransportError::Send("LXMF-rs ZeroMQ SDK response missing message_id".to_string())
        })
}

fn lxmf_sdk_outbound_send_params(message: LxmfSdkOutboundMessage) -> JsonValue {
    let mut fields = match message.fields {
        JsonValue::Object(map) => JsonValue::Object(map),
        other => serde_json::json!({ "fields": other }),
    };
    if let JsonValue::Object(map) = &mut fields {
        map.insert(
            "title".to_string(),
            JsonValue::String(message.title.clone()),
        );
        map.insert(
            "content".to_string(),
            JsonValue::String(message.content.clone()),
        );
        map.insert(
            "_sdk".to_string(),
            serde_json::json!({
                "correlation_id": message.correlation_id,
                "idempotency_key": message.correlation_id,
            }),
        );
    }
    serde_json::json!({
        "id": lxmf_zmq_message_id(),
        "source": message.source,
        "destination": message.destination,
        "title": message.title,
        "content": message.content,
        "fields": fields,
        "method": message.delivery_method,
        "try_propagation_on_fail": message.try_propagation_on_fail,
    })
}

async fn lxmf_zmq_rpc_call(
    command: &mut PushSocket,
    responses: &mut PullSocket,
    config: &ZmqPipelineBackendConfig,
    session_id: &str,
    request_id: u64,
    method: &str,
    params: Option<JsonValue>,
) -> Result<JsonValue, TransportError> {
    let rpc_request = ReticulumdRpcRequest {
        id: request_id,
        method: method.to_string(),
        params,
    };
    let payload =
        encode_frame(&rpc_request).map_err(|error| TransportError::Send(error.to_string()))?;
    let envelope = ZmqRpcEnvelope::request(
        session_id.to_string(),
        request_id,
        config.response_endpoint.clone(),
        payload,
        None,
    );
    let encoded = zmq::encode_envelope(&envelope)
        .map_err(|error| TransportError::Send(format!("LXMF-rs ZeroMQ envelope: {error}")))?;
    command
        .send(ZmqMessage::from(encoded))
        .await
        .map_err(|error| TransportError::Send(format!("LXMF-rs ZeroMQ command: {error}")))?;
    let deadline = tokio::time::sleep(config.request_timeout);
    tokio::pin!(deadline);
    loop {
        tokio::select! {
            () = &mut deadline => {
                return Err(TransportError::Receive(
                    "LXMF-rs ZeroMQ SDK request timed out waiting for correlated response".to_string(),
                ));
            }
            message = responses.recv() => {
                let message = message
                    .map_err(|error| TransportError::Receive(format!("LXMF-rs ZeroMQ response: {error}")))?;
                let bytes = Vec::<u8>::try_from(message)
                    .map_err(|error| TransportError::Receive(format!("LXMF-rs ZeroMQ response bytes: {error}")))?;
                let envelope = zmq::decode_envelope(&bytes)
                    .map_err(|error| TransportError::Receive(format!("LXMF-rs ZeroMQ envelope: {error}")))?;
                if envelope.kind != ZmqRpcEnvelopeKind::Response
                    || envelope.session_id != session_id
                    || envelope.request_id != request_id
                {
                    continue;
                }
                let response: ReticulumdRpcResponse = decode_frame(&envelope.payload)
                    .map_err(|error| TransportError::Receive(format!("LXMF-rs ZeroMQ RPC frame: {error}")))?;
                if let Some(error) = response.error {
                    return Err(TransportError::Send(format!(
                        "LXMF-rs ZeroMQ SDK {}: {}",
                        error.code, error.message
                    )));
                }
                return Ok(response.result.unwrap_or(JsonValue::Null));
            }
        }
    }
}

fn lxmf_zmq_session_id() -> String {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or(0);
    format!("r3akt-rch-{}-{now}", std::process::id())
}

fn lxmf_zmq_message_id() -> String {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or(0);
    format!("sdk-zmq-rch-{now}")
}

fn lxmf_sdk_event_to_reticulumd_event_record(event: LxmfSdkEvent) -> ReticulumdEventRecord {
    ReticulumdEventRecord {
        event_id: event.event_id,
        runtime_id: Some(event.runtime_id),
        stream_id: Some(event.stream_id),
        seq_no: Some(event.seq_no),
        contract_version: Some(event.contract_version),
        ts_ms: Some(event.ts_ms),
        event_type: event.event_type,
        severity: Some(format!("{:?}", event.severity).to_ascii_lowercase()),
        source_component: Some(event.source_component),
        operation_id: event.operation_id,
        message_id: event.message_id,
        peer_id: event.peer_id,
        correlation_id: event.correlation_id,
        trace_id: event.trace_id,
        payload: event.payload,
    }
}

fn direct_lxmf_message_envelope(
    message: &JsonValue,
    local_source: &str,
) -> Option<ProtocolEnvelope> {
    let fields = message.get("fields").and_then(JsonValue::as_object);
    let source = optional_message_string(message, &["source", "source_hash", "source_id"])
        .unwrap_or("unknown");
    if let Some(telemetry) = direct_lxmf_telemetry(fields, message) {
        let topic = Topic::new("telemetry");
        return Some(
            ProtocolEnvelope::new(
                NodeId::new(source),
                Destination::Topic(topic.clone()),
                topic,
                Payload::TelemetrySample(telemetry),
            )
            .with_dedupe_key(
                message
                    .get("id")
                    .and_then(JsonValue::as_str)
                    .unwrap_or(local_source),
            ),
        );
    }
    let attachments = direct_lxmf_attachments(fields);
    let content = optional_message_string(message, &["content", "text", "body"])
        .unwrap_or_default()
        .to_string();
    if content.is_empty() && attachments.is_empty() {
        return None;
    }
    let topic_id = fields
        .and_then(|fields| {
            optional_field_string(fields, &["TopicID", "topic_id", "topic", "Topic"])
        })
        .or_else(|| optional_message_string(message, &["topic", "topic_id", "TopicID"]))
        .unwrap_or("direct");
    let content_type = optional_message_string(message, &["content_type", "contentType"])
        .or_else(|| {
            fields
                .and_then(|fields| optional_field_string(fields, &["content_type", "contentType"]))
        })
        .unwrap_or("text/plain");
    let correlation_id = optional_message_string(message, &["correlation_id", "correlationId"])
        .or_else(|| {
            fields.and_then(|fields| {
                optional_field_string(fields, &["correlation_id", "correlationId"])
            })
        })
        .map(ToString::to_string);
    let topic = Topic::new(topic_id);
    Some(
        ProtocolEnvelope::new(
            NodeId::new(source),
            Destination::Topic(topic.clone()),
            topic,
            Payload::TopicMessage(TopicMessage {
                body: content,
                content_type: content_type.to_string(),
                correlation_id,
                attachments,
            }),
        )
        .with_dedupe_key(
            message
                .get("id")
                .and_then(JsonValue::as_str)
                .unwrap_or(local_source),
        ),
    )
}

pub fn reticulumd_message_to_envelope(
    message: &JsonValue,
    local_source: &str,
) -> Result<Option<ProtocolEnvelope>, TransportError> {
    let payload_b64 = message
        .get("fields")
        .and_then(|fields| fields.get(R3AKT_LXMF_FIELD_PAYLOAD_B64))
        .and_then(JsonValue::as_str);
    if let Some(payload_b64) = payload_b64 {
        let bytes = base64::engine::general_purpose::STANDARD
            .decode(payload_b64)
            .map_err(|error| TransportError::Receive(error.to_string()))?;
        let envelope = ProtocolEnvelope::decode_msgpack(&bytes)
            .map_err(|error| TransportError::Receive(error.to_string()))?;
        return Ok(Some(envelope));
    }
    Ok(direct_lxmf_message_envelope(message, local_source))
}

pub fn reticulumd_event_to_envelope(
    event: &ReticulumdEventRecord,
    local_source: &str,
) -> Result<Option<ProtocolEnvelope>, TransportError> {
    match event.event_type.as_str() {
        "inbound" | "InboundMessageReceived" => {
            let message = event.payload.get("message").unwrap_or(&event.payload);
            reticulumd_message_to_envelope(message, local_source)
        }
        _ => Ok(None),
    }
}

fn direct_lxmf_telemetry(
    fields: Option<&serde_json::Map<String, JsonValue>>,
    message: &JsonValue,
) -> Option<TelemetrySample> {
    let fields = fields?;
    let payload = optional_field_value(fields, &["telemetry", "FIELD_TELEMETRY", "2"])?;
    let telemetry = parse_lxmf_telemetry_payload(payload)?;
    let telemetry = humanize_lxmf_telemetry_payload(telemetry);
    let timestamp_s = lxmf_telemetry_timestamp(&telemetry)
        .or_else(|| optional_message_i64(message, &["timestamp", "timestamp_s", "time"]));
    Some(TelemetrySample {
        telemetry,
        timestamp_s,
    })
}

fn parse_lxmf_telemetry_payload(value: &JsonValue) -> Option<JsonValue> {
    if value.as_object().is_some() {
        return Some(value.clone());
    }
    let bytes = attachment_data_bytes(value);
    if bytes.is_empty() {
        return None;
    }
    parse_lxmf_msgpack_json(&bytes).or_else(|| {
        rmp_serde::from_slice::<BTreeMap<i64, LxmfTelemetryValue>>(&bytes)
            .ok()
            .map(numeric_lxmf_telemetry_map_to_json)
            .or_else(|| {
                rmp_serde::from_slice::<BTreeMap<u64, LxmfTelemetryValue>>(&bytes)
                    .ok()
                    .map(unsigned_lxmf_telemetry_map_to_json)
            })
            .or_else(|| {
                rmp_serde::from_slice::<BTreeMap<i64, JsonValue>>(&bytes)
                    .ok()
                    .map(numeric_key_map_to_json)
            })
            .or_else(|| rmp_serde::from_slice::<JsonValue>(&bytes).ok())
    })
}

#[derive(Debug)]
enum LxmfMsgpackValue {
    Nil,
    Bool(bool),
    I64(i64),
    U64(u64),
    F64(f64),
    String(String),
    Bytes(Vec<u8>),
    Array(Vec<LxmfMsgpackValue>),
    Map(Vec<(LxmfMsgpackValue, LxmfMsgpackValue)>),
}

fn parse_lxmf_msgpack_json(bytes: &[u8]) -> Option<JsonValue> {
    let (value, offset) = parse_lxmf_msgpack_value(bytes, 0)?;
    (offset == bytes.len()).then(|| lxmf_msgpack_value_to_json(value))
}

fn parse_lxmf_msgpack_value(bytes: &[u8], offset: usize) -> Option<(LxmfMsgpackValue, usize)> {
    let marker = *bytes.get(offset)?;
    let next = offset + 1;
    match marker {
        0x00..=0x7f => Some((LxmfMsgpackValue::U64(u64::from(marker)), next)),
        0x80..=0x8f => parse_lxmf_msgpack_map(bytes, next, usize::from(marker & 0x0f)),
        0x90..=0x9f => parse_lxmf_msgpack_array(bytes, next, usize::from(marker & 0x0f)),
        0xa0..=0xbf => parse_lxmf_msgpack_string(bytes, next, usize::from(marker & 0x1f)),
        0xc0 => Some((LxmfMsgpackValue::Nil, next)),
        0xc2 => Some((LxmfMsgpackValue::Bool(false), next)),
        0xc3 => Some((LxmfMsgpackValue::Bool(true), next)),
        0xc4 => {
            let len = usize::from(*bytes.get(next)?);
            parse_lxmf_msgpack_bytes(bytes, next + 1, len)
        }
        0xc5 => {
            let len = usize::from(read_be_u16_at(bytes, next)?);
            parse_lxmf_msgpack_bytes(bytes, next + 2, len)
        }
        0xc6 => {
            let len = usize::try_from(read_be_u32_at(bytes, next)?).ok()?;
            parse_lxmf_msgpack_bytes(bytes, next + 4, len)
        }
        0xca => {
            let value = f64::from(f32::from_bits(read_be_u32_at(bytes, next)?));
            Some((LxmfMsgpackValue::F64(value), next + 4))
        }
        0xcb => {
            let value = f64::from_bits(read_be_u64_at(bytes, next)?);
            Some((LxmfMsgpackValue::F64(value), next + 8))
        }
        0xcc => Some((
            LxmfMsgpackValue::U64(u64::from(*bytes.get(next)?)),
            next + 1,
        )),
        0xcd => Some((
            LxmfMsgpackValue::U64(u64::from(read_be_u16_at(bytes, next)?)),
            next + 2,
        )),
        0xce => Some((
            LxmfMsgpackValue::U64(u64::from(read_be_u32_at(bytes, next)?)),
            next + 4,
        )),
        0xcf => Some((
            LxmfMsgpackValue::U64(read_be_u64_at(bytes, next)?),
            next + 8,
        )),
        0xd0 => Some((
            LxmfMsgpackValue::I64(i64::from(i8::from_be_bytes([*bytes.get(next)?]))),
            next + 1,
        )),
        0xd1 => Some((
            LxmfMsgpackValue::I64(i64::from(i16::from_be_bytes(
                bytes.get(next..next + 2)?.try_into().ok()?,
            ))),
            next + 2,
        )),
        0xd2 => Some((
            LxmfMsgpackValue::I64(i64::from(i32::from_be_bytes(
                bytes.get(next..next + 4)?.try_into().ok()?,
            ))),
            next + 4,
        )),
        0xd3 => Some((
            LxmfMsgpackValue::I64(i64::from_be_bytes(
                bytes.get(next..next + 8)?.try_into().ok()?,
            )),
            next + 8,
        )),
        0xd9 => {
            let len = usize::from(*bytes.get(next)?);
            parse_lxmf_msgpack_string(bytes, next + 1, len)
        }
        0xda => {
            let len = usize::from(read_be_u16_at(bytes, next)?);
            parse_lxmf_msgpack_string(bytes, next + 2, len)
        }
        0xdb => {
            let len = usize::try_from(read_be_u32_at(bytes, next)?).ok()?;
            parse_lxmf_msgpack_string(bytes, next + 4, len)
        }
        0xdc => {
            parse_lxmf_msgpack_array(bytes, next + 2, usize::from(read_be_u16_at(bytes, next)?))
        }
        0xdd => parse_lxmf_msgpack_array(
            bytes,
            next + 4,
            usize::try_from(read_be_u32_at(bytes, next)?).ok()?,
        ),
        0xde => parse_lxmf_msgpack_map(bytes, next + 2, usize::from(read_be_u16_at(bytes, next)?)),
        0xdf => parse_lxmf_msgpack_map(
            bytes,
            next + 4,
            usize::try_from(read_be_u32_at(bytes, next)?).ok()?,
        ),
        0xe0..=0xff => Some((
            LxmfMsgpackValue::I64(i64::from(i8::from_be_bytes([marker]))),
            next,
        )),
        _ => None,
    }
}

fn parse_lxmf_msgpack_array(
    bytes: &[u8],
    mut offset: usize,
    len: usize,
) -> Option<(LxmfMsgpackValue, usize)> {
    let mut items = Vec::with_capacity(len);
    for _ in 0..len {
        let (value, next) = parse_lxmf_msgpack_value(bytes, offset)?;
        items.push(value);
        offset = next;
    }
    Some((LxmfMsgpackValue::Array(items), offset))
}

fn parse_lxmf_msgpack_map(
    bytes: &[u8],
    mut offset: usize,
    len: usize,
) -> Option<(LxmfMsgpackValue, usize)> {
    let mut items = Vec::with_capacity(len);
    for _ in 0..len {
        let (key, next) = parse_lxmf_msgpack_value(bytes, offset)?;
        let (value, next) = parse_lxmf_msgpack_value(bytes, next)?;
        items.push((key, value));
        offset = next;
    }
    Some((LxmfMsgpackValue::Map(items), offset))
}

fn parse_lxmf_msgpack_bytes(
    bytes: &[u8],
    offset: usize,
    len: usize,
) -> Option<(LxmfMsgpackValue, usize)> {
    let end = offset.checked_add(len)?;
    Some((
        LxmfMsgpackValue::Bytes(bytes.get(offset..end)?.to_vec()),
        end,
    ))
}

fn parse_lxmf_msgpack_string(
    bytes: &[u8],
    offset: usize,
    len: usize,
) -> Option<(LxmfMsgpackValue, usize)> {
    let end = offset.checked_add(len)?;
    let value = std::str::from_utf8(bytes.get(offset..end)?)
        .ok()?
        .to_string();
    Some((LxmfMsgpackValue::String(value), end))
}

fn lxmf_msgpack_value_to_json(value: LxmfMsgpackValue) -> JsonValue {
    match value {
        LxmfMsgpackValue::Nil => JsonValue::Null,
        LxmfMsgpackValue::Bool(value) => JsonValue::Bool(value),
        LxmfMsgpackValue::I64(value) => JsonValue::from(value),
        LxmfMsgpackValue::U64(value) => JsonValue::from(value),
        LxmfMsgpackValue::F64(value) => JsonValue::from(value),
        LxmfMsgpackValue::String(value) => JsonValue::String(value),
        LxmfMsgpackValue::Bytes(bytes) => {
            JsonValue::Array(bytes.into_iter().map(JsonValue::from).collect())
        }
        LxmfMsgpackValue::Array(items) => {
            JsonValue::Array(items.into_iter().map(lxmf_msgpack_value_to_json).collect())
        }
        LxmfMsgpackValue::Map(items) => JsonValue::Object(
            items
                .into_iter()
                .filter_map(|(key, value)| {
                    lxmf_msgpack_key_to_string(key)
                        .map(|key| (key, lxmf_msgpack_value_to_json(value)))
                })
                .collect(),
        ),
    }
}

fn lxmf_msgpack_key_to_string(value: LxmfMsgpackValue) -> Option<String> {
    match value {
        LxmfMsgpackValue::I64(value) => Some(value.to_string()),
        LxmfMsgpackValue::U64(value) => Some(value.to_string()),
        LxmfMsgpackValue::String(value) => Some(value),
        _ => None,
    }
}

fn read_be_u16_at(bytes: &[u8], offset: usize) -> Option<u16> {
    Some(u16::from_be_bytes(
        bytes.get(offset..offset + 2)?.try_into().ok()?,
    ))
}

fn read_be_u32_at(bytes: &[u8], offset: usize) -> Option<u32> {
    Some(u32::from_be_bytes(
        bytes.get(offset..offset + 4)?.try_into().ok()?,
    ))
}

fn read_be_u64_at(bytes: &[u8], offset: usize) -> Option<u64> {
    Some(u64::from_be_bytes(
        bytes.get(offset..offset + 8)?.try_into().ok()?,
    ))
}

#[derive(Debug, Deserialize)]
#[serde(untagged)]
enum LxmfTelemetryValue {
    Null(()),
    Bool(bool),
    Integer(i64),
    Unsigned(u64),
    Float(f64),
    String(String),
    Binary(Vec<u8>),
    Array(Vec<LxmfTelemetryValue>),
    StringMap(BTreeMap<String, LxmfTelemetryValue>),
    IntegerMap(BTreeMap<i64, LxmfTelemetryValue>),
}

fn numeric_lxmf_telemetry_map_to_json(map: BTreeMap<i64, LxmfTelemetryValue>) -> JsonValue {
    let object = map
        .into_iter()
        .map(|(key, value)| (key.to_string(), lxmf_telemetry_value_to_json(value)))
        .collect::<serde_json::Map<_, _>>();
    JsonValue::Object(object)
}

fn unsigned_lxmf_telemetry_map_to_json(map: BTreeMap<u64, LxmfTelemetryValue>) -> JsonValue {
    let object = map
        .into_iter()
        .map(|(key, value)| (key.to_string(), lxmf_telemetry_value_to_json(value)))
        .collect::<serde_json::Map<_, _>>();
    JsonValue::Object(object)
}

fn lxmf_telemetry_value_to_json(value: LxmfTelemetryValue) -> JsonValue {
    match value {
        LxmfTelemetryValue::Null(()) => JsonValue::Null,
        LxmfTelemetryValue::Bool(value) => JsonValue::Bool(value),
        LxmfTelemetryValue::Integer(value) => JsonValue::from(value),
        LxmfTelemetryValue::Unsigned(value) => JsonValue::from(value),
        LxmfTelemetryValue::Float(value) => JsonValue::from(value),
        LxmfTelemetryValue::String(value) => JsonValue::String(value),
        LxmfTelemetryValue::Binary(bytes) => {
            JsonValue::Array(bytes.into_iter().map(JsonValue::from).collect())
        }
        LxmfTelemetryValue::Array(items) => JsonValue::Array(
            items
                .into_iter()
                .map(lxmf_telemetry_value_to_json)
                .collect(),
        ),
        LxmfTelemetryValue::StringMap(map) => JsonValue::Object(
            map.into_iter()
                .map(|(key, value)| (key, lxmf_telemetry_value_to_json(value)))
                .collect(),
        ),
        LxmfTelemetryValue::IntegerMap(map) => numeric_lxmf_telemetry_map_to_json(map),
    }
}

fn numeric_key_map_to_json(map: BTreeMap<i64, JsonValue>) -> JsonValue {
    let object = map
        .into_iter()
        .map(|(key, value)| (key.to_string(), value))
        .collect::<serde_json::Map<_, _>>();
    JsonValue::Object(object)
}

fn humanize_lxmf_telemetry_payload(payload: JsonValue) -> JsonValue {
    let Some(object) = payload.as_object() else {
        return payload;
    };
    if object.contains_key("location") || object.contains_key("time") {
        return payload;
    }
    let mut humanized = serde_json::Map::new();
    if let Some(timestamp) = object.get("1").and_then(json_number_to_f64) {
        humanized.insert(
            "time".to_string(),
            serde_json::json!({
                "timestamp": json_number_from_f64(timestamp),
                "iso": unix_timestamp_iso(timestamp),
            }),
        );
    }
    if let Some(location) = object.get("2").and_then(decode_lxmf_location_sensor) {
        humanized.insert("location".to_string(), location);
    }
    for (sid, name, field) in [
        ("3", "pressure", "mbar"),
        ("7", "temperature", "c"),
        ("8", "humidity", "percent_relative"),
        ("10", "ambient_light", "lux"),
        ("14", "proximity", "triggered"),
    ] {
        if let Some(sensor) = object
            .get(sid)
            .and_then(|value| decode_lxmf_scalar_sensor(value, field))
        {
            humanized.insert(name.to_string(), sensor);
        }
    }
    for (sid, name, fields) in [
        ("5", "physical_link", ["rssi", "snr", "q"]),
        ("6", "acceleration", ["x", "y", "z"]),
        ("9", "magnetic_field", ["x", "y", "z"]),
        ("11", "gravity", ["x", "y", "z"]),
        ("12", "angular_velocity", ["x", "y", "z"]),
    ] {
        if let Some(sensor) = object
            .get(sid)
            .and_then(|value| decode_lxmf_triplet_sensor(value, fields))
        {
            humanized.insert(name.to_string(), sensor);
        }
    }
    for (sid, name) in [
        ("24", "lxmf_propagation"),
        ("25", "rns_transport"),
        ("26", "connection_map"),
    ] {
        if let Some(sensor) = object.get(sid).filter(|value| value.as_object().is_some()) {
            humanized.insert(name.to_string(), sensor.clone());
        }
    }
    if let Some(received) = object.get("16").and_then(decode_lxmf_received_sensor) {
        humanized.insert("received".to_string(), received);
    }
    for (sid, name) in [
        ("17", "power_consumption"),
        ("18", "power_production"),
        ("19", "processor"),
        ("20", "ram"),
        ("21", "nvm"),
        ("22", "tank"),
        ("23", "fuel"),
        ("255", "custom"),
    ] {
        if let Some(sensor) = object.get(sid).and_then(decode_lxmf_collection_sensor) {
            humanized.insert(name.to_string(), sensor);
        }
    }
    if let Some(battery) = object.get("4").and_then(decode_lxmf_battery_sensor) {
        humanized.insert("battery".to_string(), battery);
    }
    if let Some(information) = object.get("15").and_then(decode_lxmf_information_sensor) {
        humanized.insert("information".to_string(), information);
    }
    if humanized.is_empty() {
        payload
    } else {
        JsonValue::Object(humanized)
    }
}

fn lxmf_telemetry_timestamp(telemetry: &JsonValue) -> Option<i64> {
    telemetry
        .get("time")
        .and_then(|time| time.get("timestamp"))
        .and_then(json_number_to_i64)
}

fn decode_lxmf_location_sensor(value: &JsonValue) -> Option<JsonValue> {
    let items = value.as_array()?;
    if items.len() < 7 {
        return None;
    }
    let latitude = f64::from(read_i32_be(&attachment_data_bytes(&items[0]))?) / 1_000_000.0;
    let longitude = f64::from(read_i32_be(&attachment_data_bytes(&items[1]))?) / 1_000_000.0;
    let altitude = f64::from(read_u32_be(&attachment_data_bytes(&items[2]))?) / 100.0;
    let speed = f64::from(read_u32_be(&attachment_data_bytes(&items[3]))?) / 100.0;
    let bearing = f64::from(read_u32_be(&attachment_data_bytes(&items[4]))?) / 100.0;
    let accuracy = f64::from(read_u16_be(&attachment_data_bytes(&items[5]))?) / 100.0;
    let last_update = json_number_to_f64(&items[6])?;
    Some(serde_json::json!({
        "latitude": latitude,
        "longitude": longitude,
        "altitude": altitude,
        "speed": speed,
        "bearing": bearing,
        "accuracy": accuracy,
        "last_update_timestamp": last_update,
        "last_update_iso": unix_timestamp_iso(last_update),
    }))
}

fn decode_lxmf_scalar_sensor(value: &JsonValue, field: &str) -> Option<JsonValue> {
    if value.is_null() {
        return None;
    }
    let mut object = serde_json::Map::new();
    object.insert(field.to_string(), value.clone());
    Some(JsonValue::Object(object))
}

fn decode_lxmf_triplet_sensor(value: &JsonValue, fields: [&str; 3]) -> Option<JsonValue> {
    let items = value.as_array()?;
    let mut object = serde_json::Map::new();
    object.insert(fields[0].to_string(), items.first()?.clone());
    object.insert(fields[1].to_string(), items.get(1)?.clone());
    object.insert(fields[2].to_string(), items.get(2)?.clone());
    Some(JsonValue::Object(object))
}

fn decode_lxmf_received_sensor(value: &JsonValue) -> Option<JsonValue> {
    let items = value.as_array()?;
    Some(serde_json::json!({
        "by": items.first()?.clone(),
        "via": items.get(1)?.clone(),
        "distance": {
            "geodesic": items.get(2)?.clone(),
            "euclidian": items.get(3)?.clone(),
        },
    }))
}

fn decode_lxmf_collection_sensor(value: &JsonValue) -> Option<JsonValue> {
    let records = value.as_array()?;
    let mut object = serde_json::Map::new();
    for record in records {
        let Some(items) = record.as_array() else {
            continue;
        };
        if items.len() < 2 {
            continue;
        }
        let Some(label) = lxmf_collection_label(&items[0]) else {
            continue;
        };
        object.insert(label, items[1].clone());
    }
    (!object.is_empty()).then_some(JsonValue::Object(object))
}

fn lxmf_collection_label(value: &JsonValue) -> Option<String> {
    if value.is_null() {
        return Some("0".to_string());
    }
    if let Some(label) = value
        .as_str()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        return Some(label.to_string());
    }
    if let Some(label) = json_number_to_i64(value) {
        return Some(label.to_string());
    }
    let bytes = attachment_data_bytes(value);
    if bytes.is_empty() {
        return None;
    }
    std::str::from_utf8(&bytes)
        .ok()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string)
}

fn decode_lxmf_battery_sensor(value: &JsonValue) -> Option<JsonValue> {
    let items = value.as_array()?;
    let charge_percent = items.first().map(|value| {
        if value.is_null() {
            JsonValue::Null
        } else {
            json_number_to_f64(value)
                .map_or(JsonValue::Null, |value| JsonValue::from(round_1(value)))
        }
    })?;
    let charging = items.get(1).cloned().unwrap_or(JsonValue::Null);
    let temperature = items.get(2).cloned().unwrap_or(JsonValue::Null);
    Some(serde_json::json!({
        "charge_percent": charge_percent,
        "charging": charging,
        "temperature": temperature,
    }))
}

fn decode_lxmf_information_sensor(value: &JsonValue) -> Option<JsonValue> {
    let contents = value.as_str().map(ToString::to_string)?;
    Some(serde_json::json!({
        "contents": contents,
    }))
}

fn read_i32_be(bytes: &[u8]) -> Option<i32> {
    Some(i32::from_be_bytes(bytes.try_into().ok()?))
}

fn read_u32_be(bytes: &[u8]) -> Option<u32> {
    Some(u32::from_be_bytes(bytes.try_into().ok()?))
}

fn read_u16_be(bytes: &[u8]) -> Option<u16> {
    Some(u16::from_be_bytes(bytes.try_into().ok()?))
}

fn json_number_to_f64(value: &JsonValue) -> Option<f64> {
    value.as_f64()
}

fn json_number_to_i64(value: &JsonValue) -> Option<i64> {
    value
        .as_i64()
        .or_else(|| value.as_u64().and_then(|value| i64::try_from(value).ok()))
        .or_else(|| {
            value.as_f64().and_then(|value| {
                if value.is_finite() && value.fract() == 0.0 {
                    format!("{value:.0}").parse().ok()
                } else {
                    None
                }
            })
        })
}

fn json_number_from_f64(value: f64) -> JsonValue {
    if value.is_finite() && value.fract() == 0.0 {
        if let Ok(integer) = format!("{value:.0}").parse::<i64>() {
            return JsonValue::from(integer);
        }
    }
    JsonValue::from(value)
}

fn round_1(value: f64) -> f64 {
    (value * 10.0).round() / 10.0
}

fn unix_timestamp_iso(value: f64) -> String {
    format!("{value}")
}

fn direct_lxmf_attachments(
    fields: Option<&serde_json::Map<String, JsonValue>>,
) -> Vec<TopicAttachment> {
    let Some(fields) = fields else {
        return Vec::new();
    };
    let mut attachments = Vec::new();
    for (keys, category) in [
        (
            &["attachments", "file_attachments", "files", "5"][..],
            "file",
        ),
        (&["image", "images", "6"][..], "image"),
    ] {
        if let Some(value) = optional_field_value(fields, keys) {
            attachments.extend(parse_attachment_payload(value, category));
        }
    }
    attachments
}

fn parse_attachment_payload(value: &JsonValue, category: &str) -> Vec<TopicAttachment> {
    if value.is_null() || value.as_object().is_some_and(serde_json::Map::is_empty) {
        return Vec::new();
    }
    if let Some(items) = value.as_array() {
        if items.is_empty() {
            return Vec::new();
        }
        if is_single_attachment_array(items) {
            return parse_attachment_entry(value, category)
                .into_iter()
                .collect();
        }
        let mut attachments = Vec::new();
        for item in items {
            if let Some(attachment) = parse_attachment_entry(item, category) {
                attachments.push(attachment);
            }
        }
        return attachments;
    }
    parse_attachment_entry(value, category)
        .into_iter()
        .collect()
}

fn parse_attachment_entry(entry: &JsonValue, category: &str) -> Option<TopicAttachment> {
    let (name, data, media_type) = if let Some(object) = entry.as_object() {
        (
            optional_field_string(object, &["name", "filename", "file_name", "title"])
                .unwrap_or("attachment")
                .to_string(),
            optional_field_value(object, &["data", "bytes", "content", "blob"]),
            optional_field_string(object, &["media_type", "mime", "mime_type", "type"])
                .map(ToString::to_string),
        )
    } else if let Some(items) = entry.as_array() {
        let parsed = parse_attachment_array_entry(items, category)?;
        if parsed.data.is_empty() {
            return None;
        }
        return Some(TopicAttachment {
            name: parsed.name,
            data: parsed.data,
            media_type: parsed.media_type,
            category: category.to_string(),
        });
    } else {
        (default_attachment_name(category), Some(entry), None)
    };
    let data = data?;
    let bytes = attachment_data_bytes(data);
    if bytes.is_empty() {
        return None;
    }
    Some(TopicAttachment {
        name,
        data: bytes,
        media_type,
        category: category.to_string(),
    })
}

struct ParsedAttachmentArray {
    name: String,
    data: Vec<u8>,
    media_type: Option<String>,
}

fn parse_attachment_array_entry(
    items: &[JsonValue],
    category: &str,
) -> Option<ParsedAttachmentArray> {
    if items.iter().all(JsonValue::is_number) {
        return Some(ParsedAttachmentArray {
            name: default_attachment_name(category),
            data: attachment_data_bytes(&JsonValue::Array(items.to_vec())),
            media_type: None,
        });
    }
    let data_index = items
        .iter()
        .position(is_binary_attachment_candidate)
        .unwrap_or(usize::from(items.len() >= 2));
    let data = items.get(data_index)?;
    let strings = items
        .iter()
        .enumerate()
        .filter_map(|(index, value)| {
            (index != data_index)
                .then(|| value.as_str().map(str::trim))
                .flatten()
                .filter(|value| !value.is_empty())
        })
        .collect::<Vec<_>>();
    let media_type = strings
        .iter()
        .find(|value| looks_like_media_type(value))
        .map(|value| (*value).to_string());
    let name = strings
        .iter()
        .find(|value| media_type.as_deref() != Some(**value))
        .map_or_else(
            || default_attachment_name(category),
            |value| (*value).to_string(),
        );
    Some(ParsedAttachmentArray {
        name,
        data: attachment_data_bytes(data),
        media_type,
    })
}

fn attachment_data_bytes(value: &JsonValue) -> Vec<u8> {
    if let Some(text) = value.as_str() {
        return decode_attachment_text(text);
    }
    if let Some(items) = value.as_array() {
        let mut bytes = Vec::with_capacity(items.len());
        for item in items {
            let Some(value) = item.as_u64() else {
                return Vec::new();
            };
            let Ok(byte) = u8::try_from(value) else {
                return Vec::new();
            };
            bytes.push(byte);
        }
        return bytes;
    }
    Vec::new()
}

fn decode_attachment_text(text: &str) -> Vec<u8> {
    let trimmed = text.trim();
    let encoded = trimmed
        .strip_prefix("base64:")
        .or_else(|| trimmed.split_once("base64,").map(|(_, encoded)| encoded));
    if let Some(encoded) = encoded {
        if let Ok(bytes) = decode_base64_attachment(encoded) {
            return bytes;
        }
    }
    if should_decode_base64_attachment(trimmed) {
        if let Ok(bytes) = decode_base64_attachment(trimmed) {
            return bytes;
        }
    }
    trimmed.as_bytes().to_vec()
}

fn decode_base64_attachment(text: &str) -> Result<Vec<u8>, base64::DecodeError> {
    let compact = text.split_whitespace().collect::<String>();
    base64::engine::general_purpose::STANDARD.decode(compact)
}

fn should_decode_base64_attachment(text: &str) -> bool {
    let compact = text.split_whitespace().collect::<String>();
    if compact.starts_with("data:") && compact.contains("base64,") {
        return true;
    }
    if compact
        .chars()
        .any(|value| matches!(value, '=' | '+' | '/'))
    {
        return true;
    }
    compact.len() >= 12 && compact.len() % 4 == 0 && compact.chars().all(is_base64_attachment_char)
}

fn is_base64_attachment_char(value: char) -> bool {
    value.is_ascii_alphanumeric() || matches!(value, '+' | '/' | '=')
}

fn optional_message_string<'a>(message: &'a JsonValue, keys: &[&str]) -> Option<&'a str> {
    keys.iter()
        .find_map(|key| message.get(*key).and_then(JsonValue::as_str))
        .map(str::trim)
        .filter(|value| !value.is_empty())
}

fn optional_message_i64(message: &JsonValue, keys: &[&str]) -> Option<i64> {
    keys.iter().find_map(|key| {
        message.get(*key).and_then(|value| {
            value
                .as_i64()
                .or_else(|| value.as_u64().and_then(|value| i64::try_from(value).ok()))
        })
    })
}

fn optional_field_value<'a>(
    fields: &'a serde_json::Map<String, JsonValue>,
    keys: &[&str],
) -> Option<&'a JsonValue> {
    for key in keys {
        if let Some(value) = fields.get(*key) {
            return Some(value);
        }
        if let Some((_, value)) = fields
            .iter()
            .find(|(candidate, _)| candidate.eq_ignore_ascii_case(key))
        {
            return Some(value);
        }
    }
    None
}

fn optional_field_string<'a>(
    fields: &'a serde_json::Map<String, JsonValue>,
    keys: &[&str],
) -> Option<&'a str> {
    optional_field_value(fields, keys)
        .and_then(JsonValue::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
}

fn is_single_attachment_array(items: &[JsonValue]) -> bool {
    items.iter().all(JsonValue::is_number)
        || items
            .first()
            .is_some_and(|value| !value.is_object() && !value.is_array())
}

fn is_binary_attachment_candidate(value: &JsonValue) -> bool {
    value.as_str().is_some_and(|text| !text.trim().is_empty())
        || value
            .as_array()
            .is_some_and(|items| !items.is_empty() && items.iter().all(JsonValue::is_number))
}

fn looks_like_media_type(value: &str) -> bool {
    let Some((left, right)) = value.split_once('/') else {
        return false;
    };
    !left.is_empty()
        && !right.is_empty()
        && left.chars().all(is_media_type_char)
        && right.chars().all(is_media_type_char)
}

fn is_media_type_char(value: char) -> bool {
    value.is_ascii_alphanumeric()
        || matches!(value, '!' | '#' | '$' | '&' | '^' | '_' | '.' | '+' | '-')
}

fn default_attachment_name(category: &str) -> String {
    if category == "image" {
        "image".to_string()
    } else {
        "attachment".to_string()
    }
}

pub trait MessageBus: Send {
    fn publish(&mut self, envelope: ProtocolEnvelope) -> TransportFuture<'_, ()>;
    fn poll(&mut self) -> TransportFuture<'_, Option<ProtocolEnvelope>>;
}

pub trait RnsTransport: MessageBus {}

impl<T> RnsTransport for T where T: MessageBus {}

#[derive(Debug, Clone)]
pub struct LxmfRsTransport<A> {
    adapter: A,
}

impl<A> LxmfRsTransport<A>
where
    A: LxmfRsAdapter,
{
    #[must_use]
    pub fn new(adapter: A) -> Self {
        Self { adapter }
    }
}

impl<A> MessageBus for LxmfRsTransport<A>
where
    A: LxmfRsAdapter,
{
    fn publish(&mut self, envelope: ProtocolEnvelope) -> TransportFuture<'_, ()> {
        Box::pin(async move {
            let bytes = envelope
                .encode_msgpack()
                .map_err(|error| TransportError::Encode(error.to_string()))?;
            self.adapter
                .send_frame(LxmfRsFrame {
                    destination: destination_hint(&envelope),
                    bytes,
                })
                .await
        })
    }

    fn poll(&mut self) -> TransportFuture<'_, Option<ProtocolEnvelope>> {
        Box::pin(async move {
            let Some(frame) = self.adapter.receive_frame().await? else {
                return Ok(None);
            };
            let envelope = ProtocolEnvelope::decode_msgpack(&frame.bytes)
                .map_err(|error| TransportError::Receive(error.to_string()))?;
            Ok(Some(envelope))
        })
    }
}

#[derive(Debug, Clone, Default)]
pub struct MockTransport {
    inbound: Arc<Mutex<VecDeque<ProtocolEnvelope>>>,
    outbound: Arc<Mutex<Vec<ProtocolEnvelope>>>,
    max_inbound: usize,
    max_outbound: usize,
}

impl MockTransport {
    #[must_use]
    pub fn new() -> Self {
        Self::with_capacity(1024, 1024)
    }

    #[must_use]
    pub fn with_capacity(max_inbound: usize, max_outbound: usize) -> Self {
        Self {
            inbound: Arc::new(Mutex::new(VecDeque::new())),
            outbound: Arc::new(Mutex::new(Vec::new())),
            max_inbound,
            max_outbound,
        }
    }

    pub fn push_inbound(&mut self, envelope: ProtocolEnvelope) -> Result<(), TransportError> {
        let mut inbound = self
            .inbound
            .lock()
            .map_err(|error| TransportError::Receive(error.to_string()))?;
        if inbound.len() >= self.max_inbound {
            return Err(TransportError::Backpressure("inbound".to_string()));
        }
        inbound.push_back(envelope);
        Ok(())
    }

    pub fn outbound(&self) -> Result<Vec<ProtocolEnvelope>, TransportError> {
        let outbound = self
            .outbound
            .lock()
            .map_err(|error| TransportError::Send(error.to_string()))?;
        Ok(outbound.clone())
    }
}

impl MessageBus for MockTransport {
    fn publish(&mut self, envelope: ProtocolEnvelope) -> TransportFuture<'_, ()> {
        Box::pin(async move {
            let mut outbound = self
                .outbound
                .lock()
                .map_err(|error| TransportError::Send(error.to_string()))?;
            if outbound.len() >= self.max_outbound {
                return Err(TransportError::Backpressure("outbound".to_string()));
            }
            outbound.push(envelope);
            Ok(())
        })
    }

    fn poll(&mut self) -> TransportFuture<'_, Option<ProtocolEnvelope>> {
        Box::pin(async move {
            let mut inbound = self
                .inbound
                .lock()
                .map_err(|error| TransportError::Receive(error.to_string()))?;
            Ok(inbound.pop_front())
        })
    }
}

fn destination_hint(envelope: &ProtocolEnvelope) -> String {
    match &envelope.destination {
        r3akt_protocol::Destination::Node(node_id) => node_id.to_string(),
        r3akt_protocol::Destination::Topic(topic) => topic.to_string(),
        r3akt_protocol::Destination::Broadcast => "broadcast".to_string(),
    }
}

fn reticulumd_rpc_call(
    endpoint: &str,
    request: &ReticulumdRpcRequest,
) -> Result<ReticulumdRpcResponse, TransportError> {
    reticulumd_rpc_call_with_timeout(endpoint, request, RETICULUMD_RPC_TIMEOUT)
}

fn reticulumd_rpc_call_with_timeout(
    endpoint: &str,
    request: &ReticulumdRpcRequest,
    timeout: Duration,
) -> Result<ReticulumdRpcResponse, TransportError> {
    let frame = encode_frame(request).map_err(|error| TransportError::Send(error.to_string()))?;
    let http_request = build_http_post("/rpc", endpoint, &frame);
    let mut stream =
        TcpStream::connect(endpoint).map_err(|error| TransportError::Send(error.to_string()))?;
    stream
        .set_read_timeout(Some(timeout))
        .map_err(|error| TransportError::Send(error.to_string()))?;
    stream
        .set_write_timeout(Some(timeout))
        .map_err(|error| TransportError::Send(error.to_string()))?;
    stream
        .write_all(&http_request)
        .map_err(|error| TransportError::Send(error.to_string()))?;
    stream
        .shutdown(Shutdown::Write)
        .map_err(|error| TransportError::Send(error.to_string()))?;
    let mut response = Vec::new();
    stream
        .read_to_end(&mut response)
        .map_err(|error| TransportError::Receive(error.to_string()))?;
    let body = parse_http_response_body(&response)
        .map_err(|error| TransportError::Receive(error.to_string()))?;
    decode_frame(&body).map_err(|error| TransportError::Receive(error.to_string()))
}

fn encode_frame<T: Serialize>(message: &T) -> io::Result<Vec<u8>> {
    let mut framed = Vec::with_capacity(512);
    framed.extend_from_slice(&[0_u8; 4]);
    message
        .serialize(&mut rmp_serde::Serializer::new(&mut framed))
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
    let payload_len = framed
        .len()
        .checked_sub(4)
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "missing frame payload"))?;
    let len = u32::try_from(payload_len)
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "frame too large"))?;
    framed[..4].copy_from_slice(&len.to_be_bytes());
    Ok(framed)
}

fn decode_frame<T: DeserializeOwned>(bytes: &[u8]) -> io::Result<T> {
    if bytes.len() < 4 {
        return Err(io::Error::new(
            io::ErrorKind::UnexpectedEof,
            "missing frame header",
        ));
    }
    let mut len_buf = [0_u8; 4];
    len_buf.copy_from_slice(&bytes[..4]);
    let len = u32::from_be_bytes(len_buf) as usize;
    if bytes.len() < 4 + len {
        return Err(io::Error::new(
            io::ErrorKind::UnexpectedEof,
            "incomplete frame",
        ));
    }
    rmp_serde::from_slice(&bytes[4..4 + len])
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))
}

fn build_http_post(path: &str, host: &str, body: &[u8]) -> Vec<u8> {
    let mut request = Vec::new();
    request.extend_from_slice(format!("POST {path} HTTP/1.1\r\n").as_bytes());
    request.extend_from_slice(format!("Host: {host}\r\n").as_bytes());
    request.extend_from_slice(b"Content-Type: application/msgpack\r\n");
    request.extend_from_slice(format!("Content-Length: {}\r\n", body.len()).as_bytes());
    request.extend_from_slice(b"\r\n");
    request.extend_from_slice(body);
    request
}

fn parse_http_response_body(response: &[u8]) -> io::Result<Vec<u8>> {
    let header_end = response
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "missing headers"))?;
    let headers = &response[..header_end];
    let body_start = header_end + 4;
    let headers_text = std::str::from_utf8(headers)
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
    let content_length = headers_text
        .lines()
        .find_map(|line| {
            let (name, value) = line.split_once(':')?;
            name.eq_ignore_ascii_case("content-length")
                .then(|| value.trim().parse::<usize>().ok())
                .flatten()
        })
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "missing content length"))?;
    if response.len() < body_start + content_length {
        return Err(io::Error::new(
            io::ErrorKind::UnexpectedEof,
            "response body incomplete",
        ));
    }
    Ok(response[body_start..body_start + content_length].to_vec())
}

#[cfg(test)]
mod tests {
    use lxmf_sdk::{EventBatch, EventCursor, SendRequest as LxmfSdkSendRequest};
    use r3akt_protocol::{Destination, HealthStatus, Heartbeat, NodeId, Payload, Topic};
    use std::env;
    use std::net::TcpListener;
    use std::thread;
    use std::time::{Duration, Instant};

    use super::*;

    #[derive(Debug, Clone)]
    struct RecordedRpcCall {
        method: String,
        params: serde_json::Value,
        response_endpoint: Option<String>,
    }

    #[derive(Debug, Default)]
    struct RecordingReticulumdRpc {
        calls: Vec<RecordedRpcCall>,
        responses: VecDeque<serde_json::Value>,
    }

    #[derive(Debug, Default)]
    struct RecordingLxmfSdkRuntime {
        send_requests: Vec<LxmfSdkSendRequest>,
        event_batches: VecDeque<EventBatch>,
    }

    impl LxmfSdkRuntime for RecordingLxmfSdkRuntime {
        fn send(&mut self, request: LxmfSdkSendRequest) -> Result<String, TransportError> {
            self.send_requests.push(request);
            Ok("sdk-recorded-1".to_string())
        }

        fn poll_events(
            &mut self,
            _cursor: Option<EventCursor>,
            _max: usize,
        ) -> Result<EventBatch, TransportError> {
            Ok(self
                .event_batches
                .pop_front()
                .unwrap_or_else(|| EventBatch::empty(EventCursor("cursor-0".to_string()))))
        }
    }

    impl RecordingReticulumdRpc {
        fn with_responses(responses: Vec<serde_json::Value>) -> Self {
            Self {
                calls: Vec::new(),
                responses: responses.into(),
            }
        }
    }

    impl ReticulumdRpcCall for RecordingReticulumdRpc {
        fn call(
            &mut self,
            method: &str,
            params: Option<serde_json::Value>,
        ) -> Result<ReticulumdRpcResponse, TransportError> {
            self.calls.push(RecordedRpcCall {
                method: method.to_string(),
                params: params.unwrap_or(serde_json::Value::Null),
                response_endpoint: None,
            });
            Ok(ReticulumdRpcResponse {
                id: 1,
                result: self
                    .responses
                    .pop_front()
                    .or_else(|| Some(serde_json::json!({}))),
                error: None,
            })
        }
    }

    fn fake_reticulumd_rpc_response(
        result: Option<serde_json::Value>,
        error: Option<ReticulumdRpcError>,
    ) -> (String, thread::JoinHandle<ReticulumdRpcRequest>) {
        let listener = TcpListener::bind("127.0.0.1:0").expect("listener");
        let endpoint = listener.local_addr().expect("addr").to_string();
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("accept");
            let mut request = Vec::new();
            stream.read_to_end(&mut request).expect("read request");
            let body = parse_http_response_body(&request).expect("request body");
            let decoded: ReticulumdRpcRequest = decode_frame(&body).expect("request frame");
            let response = ReticulumdRpcResponse {
                id: decoded.id,
                result,
                error,
            };
            let body = encode_frame(&response).expect("response frame");
            let http = [
                b"HTTP/1.1 200 OK\r\nContent-Type: application/msgpack\r\nContent-Length: "
                    .as_slice(),
                body.len().to_string().as_bytes(),
                b"\r\n\r\n",
                body.as_slice(),
            ]
            .concat();
            stream.write_all(&http).expect("write response");
            decoded
        });
        (endpoint, server)
    }

    fn unused_zmq_endpoint() -> String {
        let listener = TcpListener::bind("127.0.0.1:0").expect("reserve tcp port");
        let port = listener.local_addr().expect("local addr").port();
        drop(listener);
        format!("tcp://localhost:{port}")
    }

    fn unused_zmq_endpoint_v4() -> String {
        let listener = TcpListener::bind("127.0.0.1:0").expect("reserve tcp port");
        let port = listener.local_addr().expect("local addr").port();
        drop(listener);
        format!("tcp://127.0.0.1:{port}")
    }

    fn spawn_zmq_sequence_server(
        command_endpoint: String,
        responses: Vec<serde_json::Value>,
        captured: Arc<Mutex<Vec<RecordedRpcCall>>>,
    ) -> thread::JoinHandle<()> {
        thread::spawn(move || {
            let runtime = tokio::runtime::Runtime::new().expect("test runtime");
            runtime.block_on(async move {
                let mut commands = PullSocket::new();
                commands
                    .bind(command_endpoint.as_str())
                    .await
                    .expect("bind command endpoint");
                for response in responses {
                    let Some(envelope) = recv_zmq_request_envelope(&mut commands).await else {
                        return;
                    };
                    let request: ReticulumdRpcRequest =
                        decode_frame(&envelope.payload).expect("decode rpc request");
                    captured
                        .lock()
                        .expect("captured requests")
                        .push(RecordedRpcCall {
                            method: request.method,
                            params: request.params.unwrap_or(serde_json::Value::Null),
                            response_endpoint: envelope.response_endpoint.clone(),
                        });
                    let rpc_response = ReticulumdRpcResponse {
                        id: envelope.request_id,
                        result: Some(response),
                        error: None,
                    };
                    let response_payload = encode_frame(&rpc_response).expect("encode response");
                    let mut response_socket = PushSocket::new();
                    response_socket
                        .connect(
                            envelope
                                .response_endpoint
                                .as_deref()
                                .expect("response endpoint"),
                        )
                        .await
                        .expect("connect response endpoint");
                    tokio::time::sleep(Duration::from_millis(50)).await;
                    response_socket
                        .send(ZmqMessage::from(
                            zmq::encode_envelope(&ZmqRpcEnvelope::response(
                                envelope.session_id,
                                envelope.request_id,
                                response_payload,
                            ))
                            .expect("encode zmq envelope"),
                        ))
                        .await
                        .expect("send response");
                }
            });
        })
    }

    async fn recv_zmq_request_envelope(commands: &mut PullSocket) -> Option<ZmqRpcEnvelope> {
        let message = tokio::time::timeout(Duration::from_secs(2), commands.recv())
            .await
            .ok()?
            .ok()?;
        let bytes = Vec::<u8>::try_from(message).ok()?;
        zmq::decode_envelope(&bytes).ok()
    }

    #[test]
    fn mock_transport_round_trips_inbound_and_outbound() {
        let envelope = ProtocolEnvelope::new(
            NodeId::new("alpha"),
            Destination::Broadcast,
            Topic::new("health"),
            Payload::Heartbeat(Heartbeat {
                status: HealthStatus::Nominal,
                sequence: 1,
            }),
        );
        let mut transport = MockTransport::new();
        transport.push_inbound(envelope.clone()).expect("queue");

        crate::test_block_on(transport.publish(envelope.clone())).expect("publish");
        let received = crate::test_block_on(transport.poll())
            .expect("poll")
            .expect("message");

        assert_eq!(received, envelope);
        assert_eq!(transport.outbound().expect("outbound"), vec![envelope]);
    }

    #[test]
    fn mock_transport_applies_backpressure() {
        let envelope = ProtocolEnvelope::new(
            NodeId::new("alpha"),
            Destination::Broadcast,
            Topic::new("health"),
            Payload::Heartbeat(Heartbeat {
                status: HealthStatus::Nominal,
                sequence: 1,
            }),
        );
        let mut transport = MockTransport::with_capacity(1, 1);
        transport
            .push_inbound(envelope.clone())
            .expect("first inbound");

        assert!(matches!(
            transport.push_inbound(envelope.clone()),
            Err(TransportError::Backpressure(_))
        ));

        crate::test_block_on(transport.publish(envelope.clone())).expect("first outbound");
        assert!(matches!(
            crate::test_block_on(transport.publish(envelope)),
            Err(TransportError::Backpressure(_))
        ));
    }

    #[test]
    fn reticulumd_rpc_adapter_sends_frame_with_base64_payload_field() {
        let mut rpc = RecordingReticulumdRpc::default();
        let mut adapter = ReticulumdRpcLxmfRsAdapter::new(
            "source-destination",
            ReticulumdRpcTransport::from_rpc(&mut rpc),
        );
        let frame = LxmfRsFrame {
            destination: "target-destination".to_string(),
            bytes: vec![1, 2, 3, 4],
        };

        crate::test_block_on(adapter.send_frame(frame)).expect("send frame");

        assert_eq!(rpc.calls.len(), 1);
        assert_eq!(rpc.calls[0].method, "send_message_v2");
        assert_eq!(rpc.calls[0].params["source"], "source-destination");
        assert_eq!(rpc.calls[0].params["destination"], "target-destination");
        assert_eq!(rpc.calls[0].params["content"], "r3akt protocol envelope");
        assert_eq!(
            rpc.calls[0].params["fields"]["r3akt_content_type"],
            "application/x-r3akt-msgpack"
        );
        assert_eq!(
            rpc.calls[0].params["fields"]["r3akt_payload_b64"],
            "AQIDBA=="
        );
        assert_eq!(rpc.calls[0].params["method"], "direct");
    }

    #[test]
    fn lxmf_sdk_adapter_sends_frame_with_zero_mq_sdk_payload() {
        let runtime = RecordingLxmfSdkRuntime::default();
        let mut adapter = LxmfSdkLxmfRsAdapter::new("source-destination", runtime);
        let frame = LxmfRsFrame {
            destination: "target-destination".to_string(),
            bytes: vec![1, 2, 3, 4],
        };

        crate::test_block_on(adapter.send_frame(frame)).expect("send frame");

        let runtime = adapter.into_runtime();
        assert_eq!(runtime.send_requests.len(), 1);
        let request = &runtime.send_requests[0];
        assert_eq!(request.source, "source-destination");
        assert_eq!(request.destination, "target-destination");
        assert_eq!(request.payload["title"], "R3AKT");
        assert_eq!(request.payload["content"], "r3akt protocol envelope");
        assert_eq!(
            request.payload["r3akt_content_type"],
            "application/x-r3akt-msgpack"
        );
        assert_eq!(request.payload["r3akt_payload_b64"], "AQIDBA==");
        assert_eq!(request.correlation_id.as_deref(), Some("r3akt-transport-1"));
    }

    #[test]
    fn lxmf_sdk_adapter_receives_inbound_event_batch() {
        let envelope = ProtocolEnvelope::new(
            NodeId::new("peer-alpha"),
            Destination::Topic(Topic::new("ops")),
            Topic::new("ops"),
            Payload::TopicMessage(TopicMessage {
                body: "event message".to_string(),
                content_type: "text/plain".to_string(),
                correlation_id: None,
                attachments: Vec::new(),
            }),
        )
        .with_dedupe_key("event-msg-1");
        let payload_b64 = base64::engine::general_purpose::STANDARD
            .encode(envelope.encode_msgpack().expect("msgpack"));
        let mut runtime = RecordingLxmfSdkRuntime::default();
        runtime.event_batches.push_back(
            serde_json::from_value(serde_json::json!({
                "events": [{
                    "event_id": "evt-inbound-1",
                    "runtime_id": "runtime-a",
                    "stream_id": "sdk-events",
                    "seq_no": 1,
                    "contract_version": 2,
                    "ts_ms": 1_700_000_000_000_u64,
                    "event_type": "inbound",
                    "severity": "info",
                    "source_component": "lxmf-sdk",
                    "message_id": "lxmf-1",
                    "peer_id": "peer-alpha",
                    "payload": {
                        "message": {
                            "id": "lxmf-1",
                            "destination": "local-destination",
                            "fields": {
                                "r3akt_payload_b64": payload_b64
                            }
                        }
                    }
                }],
                "next_cursor": "cursor-1",
                "dropped_count": 0,
                "snapshot_high_watermark_seq_no": 1
            }))
            .expect("sdk event batch"),
        );
        let mut adapter = LxmfSdkLxmfRsAdapter::new("local-destination", runtime);

        let frame = crate::test_block_on(adapter.receive_frame())
            .expect("receive frame")
            .expect("frame");
        let decoded = ProtocolEnvelope::decode_msgpack(&frame.bytes).expect("decode");

        assert_eq!(decoded.id, envelope.id);
        assert_eq!(decoded.source, envelope.source);
        assert_eq!(frame.destination, "ops");
    }

    #[test]
    fn lxmf_sdk_outbound_message_preserves_rch_fields() {
        let mut runtime = RecordingLxmfSdkRuntime::default();

        let message_id = send_lxmf_sdk_outbound_message_with_runtime(
            &mut runtime,
            LxmfSdkOutboundMessage {
                source: "source-destination".to_string(),
                destination: "target-destination".to_string(),
                title: "RCH".to_string(),
                content: "hello".to_string(),
                fields: serde_json::json!({
                    "9": [{"cmd": "mission.join"}],
                    "custom": "value"
                }),
                delivery_method: Some("direct".to_string()),
                try_propagation_on_fail: true,
                correlation_id: "message-1".to_string(),
            },
        )
        .expect("send");

        assert_eq!(message_id, "sdk-recorded-1");
        assert_eq!(runtime.send_requests.len(), 1);
        let request = &runtime.send_requests[0];
        assert_eq!(request.source, "source-destination");
        assert_eq!(request.destination, "target-destination");
        assert_eq!(request.payload["title"], "RCH");
        assert_eq!(request.payload["content"], "hello");
        assert_eq!(request.payload["9"][0]["cmd"], "mission.join");
        assert_eq!(request.payload["custom"], "value");
        assert_eq!(request.correlation_id.as_deref(), Some("message-1"));
        assert_eq!(request.idempotency_key.as_deref(), Some("message-1"));
    }

    #[test]
    fn lxmf_zmq_outbound_message_sends_delivery_options_over_sdk_rpc() {
        let command_endpoint = unused_zmq_endpoint();
        let response_endpoint = unused_zmq_endpoint();
        let captured = Arc::new(Mutex::new(Vec::new()));
        let server = spawn_zmq_sequence_server(
            command_endpoint.clone(),
            vec![
                serde_json::json!({"runtime_id": "runtime-rch-zmq"}),
                serde_json::json!({"message_id": "sdk-zmq-rch-1"}),
            ],
            Arc::clone(&captured),
        );

        let message_id = send_lxmf_zmq_outbound_message(
            command_endpoint,
            response_endpoint,
            LxmfSdkOutboundMessage {
                source: "source-destination".to_string(),
                destination: "target-destination".to_string(),
                title: "RCH".to_string(),
                content: "cmd".to_string(),
                fields: serde_json::json!({
                    "9": [{"command_type": "checklist.create.online"}],
                }),
                delivery_method: Some("propagated".to_string()),
                try_propagation_on_fail: false,
                correlation_id: "message-1".to_string(),
            },
        )
        .expect("send");
        server.join().expect("server joined");

        assert_eq!(message_id, "sdk-zmq-rch-1");
        let captured = captured.lock().expect("captured requests");
        assert_eq!(captured.len(), 2);
        assert_eq!(captured[0].method, "sdk_negotiate_v2");
        assert_eq!(captured[1].method, "sdk_send_v2");
        assert_eq!(captured[1].params["source"], "source-destination");
        assert_eq!(captured[1].params["destination"], "target-destination");
        assert_eq!(captured[1].params["method"], "propagated");
        assert_eq!(captured[1].params["try_propagation_on_fail"], false);
        assert_eq!(
            captured[1].params["fields"]["9"][0]["command_type"],
            "checklist.create.online"
        );
        assert_eq!(
            captured[1].params["fields"]["_sdk"]["correlation_id"],
            "message-1"
        );
    }

    #[test]
    fn lxmf_zmq_outbound_message_preserves_explicit_loopback_response_endpoint() {
        let command_endpoint = unused_zmq_endpoint_v4();
        let response_endpoint = unused_zmq_endpoint_v4();
        let captured = Arc::new(Mutex::new(Vec::new()));
        let server = spawn_zmq_sequence_server(
            command_endpoint.clone(),
            vec![
                serde_json::json!({"runtime_id": "runtime-rch-zmq"}),
                serde_json::json!({"message_id": "sdk-zmq-rch-1"}),
            ],
            Arc::clone(&captured),
        );

        let message_id = send_lxmf_zmq_outbound_message(
            command_endpoint,
            response_endpoint.clone(),
            LxmfSdkOutboundMessage {
                source: "source-destination".to_string(),
                destination: "target-destination".to_string(),
                title: "RCH".to_string(),
                content: "cmd".to_string(),
                fields: serde_json::json!({}),
                delivery_method: Some("direct".to_string()),
                try_propagation_on_fail: false,
                correlation_id: "message-1".to_string(),
            },
        )
        .expect("send");
        server.join().expect("server joined");

        assert_eq!(message_id, "sdk-zmq-rch-1");
        let captured = captured.lock().expect("captured requests");
        assert_eq!(captured.len(), 2);
        assert_eq!(
            captured[0].response_endpoint.as_deref(),
            Some(response_endpoint.as_str())
        );
        assert_eq!(
            captured[1].response_endpoint.as_deref(),
            Some(response_endpoint.as_str())
        );
    }

    #[test]
    fn zmq_sdk_start_inside_tokio_runtime_returns_error_without_panicking() {
        let runtime = tokio::runtime::Runtime::new().expect("tokio runtime");
        let outcome = std::panic::catch_unwind(|| {
            runtime.block_on(async {
                let mut config = ZmqPipelineBackendConfig::local_tcp(
                    "tcp://127.0.0.1:59100",
                    "tcp://127.0.0.1:59101",
                );
                config.request_timeout = Duration::from_millis(25);
                LxmfSdkLxmfRsAdapter::from_zmq_config("source-destination", config)
            })
        });

        assert!(outcome.is_ok(), "ZeroMQ SDK path panicked inside Tokio");
        assert!(
            outcome.expect("panic checked").is_err(),
            "unconnected ZeroMQ endpoints should return a transport error"
        );
    }

    #[test]
    fn reticulumd_rpc_adapter_receives_first_unseen_r3akt_payload() {
        let mut rpc = RecordingReticulumdRpc::with_responses(vec![serde_json::json!({
            "messages": [
                {
                    "id": "m-1",
                    "source": "source-destination",
                    "destination": "local-destination",
                    "fields": {
                        "r3akt_payload_b64": "CQgH"
                    }
                }
            ]
        })]);
        let mut adapter = ReticulumdRpcLxmfRsAdapter::new(
            "local-destination",
            ReticulumdRpcTransport::from_rpc(&mut rpc),
        );

        let frame = crate::test_block_on(adapter.receive_frame())
            .expect("receive")
            .expect("frame");
        let second = crate::test_block_on(adapter.receive_frame()).expect("receive");

        assert_eq!(frame.destination, "local-destination");
        assert_eq!(frame.bytes, vec![9, 8, 7]);
        assert!(second.is_none());
        assert_eq!(rpc.calls[0].method, "list_messages");
    }

    #[test]
    fn reticulumd_rpc_adapter_maps_direct_lxmf_attachment_fields_to_topic_envelope() {
        let mut rpc = RecordingReticulumdRpc::with_responses(vec![serde_json::json!({
            "messages": [
                {
                    "id": "direct-1",
                    "source": "peer-direct",
                    "destination": "local-destination",
                    "content": "Direct inbound",
                    "fields": {
                        "TopicID": "ops",
                        "attachments": [{
                            "name": "direct.txt",
                            "data": "ZGlyZWN0LWZpbGU=",
                            "media_type": "text/plain"
                        }]
                    }
                }
            ]
        })]);
        let mut adapter = ReticulumdRpcLxmfRsAdapter::new(
            "local-destination",
            ReticulumdRpcTransport::from_rpc(&mut rpc),
        );

        let frame = crate::test_block_on(adapter.receive_frame())
            .expect("receive")
            .expect("frame");
        let envelope = ProtocolEnvelope::decode_msgpack(&frame.bytes).expect("envelope");

        assert_eq!(frame.destination, "local-destination");
        assert_eq!(envelope.source.to_string(), "peer-direct");
        assert_eq!(envelope.topic.to_string(), "ops");
        assert_eq!(envelope.stable_dedupe_key(), "direct-1");
        let Payload::TopicMessage(message) = envelope.payload else {
            panic!("expected topic message");
        };
        assert_eq!(message.body, "Direct inbound");
        assert_eq!(message.content_type, "text/plain");
        assert_eq!(message.attachments.len(), 1);
        assert_eq!(message.attachments[0].name, "direct.txt");
        assert_eq!(message.attachments[0].data, b"direct-file");
        assert_eq!(
            message.attachments[0].media_type.as_deref(),
            Some("text/plain")
        );
        assert_eq!(message.attachments[0].category, "file");
        assert_eq!(rpc.calls[0].method, "list_messages");
    }

    #[test]
    fn reticulumd_rpc_adapter_maps_direct_lxmf_telemetry_field_to_envelope() {
        let mut rpc = RecordingReticulumdRpc::with_responses(vec![serde_json::json!({
            "messages": [
                {
                    "id": "telemetry-1",
                    "source": "peer-telemetry",
                    "destination": "local-destination",
                    "fields": {
                        "2": "ggHOZVPxAAKXxAQCn2MAxAT8PrJAxAQAAAPoxAQAAAAAxAQAAAAAxAIB9MtB2VT8QAAAAA=="
                    }
                }
            ]
        })]);
        let mut adapter = ReticulumdRpcLxmfRsAdapter::new(
            "local-destination",
            ReticulumdRpcTransport::from_rpc(&mut rpc),
        );

        let frame = crate::test_block_on(adapter.receive_frame())
            .expect("receive")
            .expect("frame");
        let envelope = ProtocolEnvelope::decode_msgpack(&frame.bytes).expect("envelope");

        assert_eq!(frame.destination, "local-destination");
        assert_eq!(envelope.source.to_string(), "peer-telemetry");
        assert_eq!(envelope.stable_dedupe_key(), "telemetry-1");
        let Payload::TelemetrySample(telemetry) = envelope.payload else {
            panic!("expected telemetry sample");
        };
        assert_eq!(telemetry.timestamp_s, Some(1_700_000_000));
        assert_eq!(telemetry.telemetry["time"]["timestamp"], 1_700_000_000);
        assert_eq!(telemetry.telemetry["location"]["latitude"], 44.0);
        assert_eq!(telemetry.telemetry["location"]["longitude"], -63.0);
        assert_eq!(rpc.calls[0].method, "list_messages");
    }

    #[test]
    fn parses_python_lxmf_telemetry_msgpack_payload() {
        let raw = serde_json::json!(
            "ggHOZVPxAAKXxAQCn2MAxAT8PrJAxAQAAAPoxAQAAAAAxAQAAAAAxAIB9MtB2VT8QAAAAA=="
        );

        let payload = parse_lxmf_telemetry_payload(&raw).expect("payload");
        let telemetry = humanize_lxmf_telemetry_payload(payload);

        assert_eq!(telemetry["time"]["timestamp"], 1_700_000_000);
        assert_eq!(telemetry["location"]["latitude"], 44.0);
        assert_eq!(telemetry["location"]["longitude"], -63.0);
    }

    #[test]
    fn parses_python_lxmf_battery_and_information_sensors() {
        let raw =
            serde_json::json!("gwHOZVPxAASTy0BV6PXCj1wpw8tAP4AAAAAAAA+wUlRIIGJhdHRlcnkgbm9kZQ==");

        let payload = parse_lxmf_telemetry_payload(&raw).expect("payload");
        let telemetry = humanize_lxmf_telemetry_payload(payload);

        assert_eq!(telemetry["time"]["timestamp"], 1_700_000_000);
        assert_eq!(telemetry["battery"]["charge_percent"], 87.6);
        assert_eq!(telemetry["battery"]["charging"], true);
        assert_eq!(telemetry["battery"]["temperature"], 31.5);
        assert_eq!(telemetry["information"]["contents"], "RTH battery node");
    }

    #[test]
    fn parses_python_lxmf_scalar_and_vector_sensors() {
        let raw = serde_json::json!(
            "iwHOZVPxAQPLQI+pmZmZmZoFk8vAUaAAAAAAAMtAIIAAAAAAAMtAVwAAAAAAAAaTyz+5mZmZmZmayz/JmZmZmZmayz/TMzMzMzMzB8tANoAAAAAAAAjLQEuAAAAAAAAJk8s/8AAAAAAAAMtAAAAAAAAAAMtACAAAAAAAAArLQHLIAAAAAAALk8sAAAAAAAAAAMsAAAAAAAAAAMtAI5mZmZmZmgyTyz+EeuFHrhR7yz+UeuFHrhR7yz+euFHrhR64DsM="
        );

        let payload = parse_lxmf_telemetry_payload(&raw).expect("payload");
        let telemetry = humanize_lxmf_telemetry_payload(payload);

        assert_eq!(telemetry["time"]["timestamp"], 1_700_000_001);
        assert_eq!(telemetry["pressure"]["mbar"], 1013.2);
        assert_eq!(telemetry["physical_link"]["rssi"], -70.5);
        assert_eq!(telemetry["physical_link"]["snr"], 8.25);
        assert_eq!(telemetry["physical_link"]["q"], 92.0);
        assert_eq!(telemetry["acceleration"]["x"], 0.1);
        assert_eq!(telemetry["acceleration"]["y"], 0.2);
        assert_eq!(telemetry["acceleration"]["z"], 0.3);
        assert_eq!(telemetry["temperature"]["c"], 22.5);
        assert_eq!(telemetry["humidity"]["percent_relative"], 55.0);
        assert_eq!(telemetry["magnetic_field"]["x"], 1.0);
        assert_eq!(telemetry["magnetic_field"]["y"], 2.0);
        assert_eq!(telemetry["magnetic_field"]["z"], 3.0);
        assert_eq!(telemetry["ambient_light"]["lux"], 300.5);
        assert_eq!(telemetry["gravity"]["x"], 0.0);
        assert_eq!(telemetry["gravity"]["y"], 0.0);
        assert_eq!(telemetry["gravity"]["z"], 9.8);
        assert_eq!(telemetry["angular_velocity"]["x"], 0.01);
        assert_eq!(telemetry["angular_velocity"]["y"], 0.02);
        assert_eq!(telemetry["angular_velocity"]["z"], 0.03);
        assert_eq!(telemetry["proximity"]["triggered"], true);
    }

    #[test]
    fn parses_python_lxmf_complex_dictionary_sensors() {
        let raw = serde_json::json!(
            "hQKXxAQCn2MAxAT8PrJAxAQAAAPoxAQAAAAAxAQAAAAAxAIB9MtB2VT8QIAAABneABCtY3VzdG9tX21ldHJpY8tAWPmZmZmZmrF0cmFuc3BvcnRfZW5hYmxlZMOydHJhbnNwb3J0X2lkZW50aXR5xBABAQEBAQEBAQEBAQEBAQEBsHRyYW5zcG9ydF91cHRpbWXNEJKrdHJhZmZpY19yeGLNJxCrdHJhZmZpY190eGLNTiCoc3BlZWRfcnjLQGAQAAAAAACoc3BlZWRfdHjLQHAMAAAAAACtc3BlZWRfcnhfaW5zdMtAYEAAAAAAAK1zcGVlZF90eF9pbnN0y0BwQAAAAAAAq21lbW9yeV91c2VkzgC8YU6vaW50ZXJmYWNlX2NvdW50AqpsaW5rX2NvdW50B6ppbnRlcmZhY2VzkoKkbmFtZaNpZjClc3RhdGWidXCCpG5hbWWjaWYxpXN0YXRlpGRvd26qcGF0aF90YWJsZZGEqWludGVyZmFjZaNpZjCjdmlhxAiqqqqqqqqqqqRoYXNoxBC7u7u7u7u7u7u7u7u7u7u7pGhvcHMBp2lmc3RhdHOFo3J4Ys0nEKN0eGLNTiCjcnhzy0B/QAAAAAAAo3R4c8tAgsAAAAAAAKppbnRlcmZhY2VzkoKkbmFtZaNpZjClcGF0aHMCgqRuYW1lo2lmMaVwYXRocwAY3gAYsGRlc3RpbmF0aW9uX2hhc2jEEBAQEBAQEBAQEBAQEBAQEBCtaWRlbnRpdHlfaGFzaMQQICAgICAgICAgICAgICAgIKZ1cHRpbWXNMDmuZGVsaXZlcnlfbGltaXTLQEVAAAAAAACxcHJvcGFnYXRpb25fbGltaXTLQHAAAAAAAACxYXV0b3BlZXJfbWF4ZGVwdGgDsGZyb21fc3RhdGljX29ubHnDvXVucGVlcmVkX3Byb3BhZ2F0aW9uX2luY29taW5nAr11bnBlZXJlZF9wcm9wYWdhdGlvbl9yeF9ieXRlc80EAKxzdGF0aWNfcGVlcnMBq3RvdGFsX3BlZXJzAqxhY3RpdmVfcGVlcnMBsXVucmVhY2hhYmxlX3BlZXJzAaltYXhfcGVlcnMKu3BlZXJlZF9wcm9wYWdhdGlvbl9yeF9ieXRlc80KALtwZWVyZWRfcHJvcGFnYXRpb25fdHhfYnl0ZXPNEQC6cGVlcmVkX3Byb3BhZ2F0aW9uX29mZmVyZWQEu3BlZXJlZF9wcm9wYWdhdGlvbl9vdXRnb2luZwK7cGVlcmVkX3Byb3BhZ2F0aW9uX2luY29taW5nAbxwZWVyZWRfcHJvcGFnYXRpb25fdW5oYW5kbGVkAdkgcGVlcmVkX3Byb3BhZ2F0aW9uX21heF91bmhhbmRsZWQBpXBlZXJzgsQQqqqqqqqqqqqqqqqqqqqqqo+kdHlwZapwcm9wYWdhdG9ypXN0YXRlpmFjdGl2ZaVhbGl2ZcOqbGFzdF9oZWFyZMtAk0oAAAAAALFuZXh0X3N5bmNfYXR0ZW1wdMtAolMzMzMzM7FsYXN0X3N5bmNfYXR0ZW1wdMtAkVwAAAAAAKxzeW5jX2JhY2tvZmbLQCQAAAAAAACwcGVlcmluZ190aW1lYmFzZctARQAAAAAAAKNsZXLLP+gAAAAAAACjc3Ryyz/gAAAAAAAArnRyYW5zZmVyX2xpbWl0zQIAsG5ldHdvcmtfZGlzdGFuY2UCqHJ4X2J5dGVzzQgAqHR4X2J5dGVzzRAAqG1lc3NhZ2VzhKdvZmZlcmVkA6hvdXRnb2luZwKoaW5jb21pbmcBqXVuaGFuZGxlZADEELu7u7u7u7u7u7u7u7u7u7uPpHR5cGWqcHJvcGFnYXRvcqVzdGF0ZaRkb3dupWFsaXZlwqpsYXN0X2hlYXJky0CpFDMzMzMzsW5leHRfc3luY19hdHRlbXB0wLFsYXN0X3N5bmNfYXR0ZW1wdMtAoVwAAAAAAKxzeW5jX2JhY2tvZmbLQDQAAAAAAACwcGVlcmluZ190aW1lYmFzZctAVQAAAAAAAKNsZXLLP+GZmZmZmZqjc3Ryyz/QAAAAAAAArnRyYW5zZmVyX2xpbWl0zQEAsG5ldHdvcmtfZGlzdGFuY2UEqHJ4X2J5dGVzzQIAqHR4X2J5dGVzzQEAqG1lc3NhZ2VzhKdvZmZlcmVkAahvdXRnb2luZwCoaW5jb21pbmcAqXVuaGFuZGxlZAGsbWVzc2FnZXN0b3Jlg6Vjb3VudAWlYnl0ZXPNEAClbGltaXTNIACnY2xpZW50c4LZJGNsaWVudF9wcm9wYWdhdGlvbl9tZXNzYWdlc19yZWNlaXZlZAfZImNsaWVudF9wcm9wYWdhdGlvbl9tZXNzYWdlc19zZXJ2ZWQJGoGkbWFwc4KkbWFpboKmcG9pbnRzgahkZWFkYmVlZoejbGF0y0BGAAAAAAAAo2xvbsvAT4AAAAAAAKNhbHTLQCQAAAAAAACkdHlwZaRwZWVypG5hbWWnR2F0ZXdhea9zaWduYWxfc3RyZW5ndGjQ2KNzbnLLQCkAAAAAAAClbGFiZWyoTWFpbiBNYXCmYmFja3VwgqZwb2ludHOBqGZlZWRmYWNlh6NsYXTLQEaAAAAAAACjbG9uy8BPAAAAAAAAo2FsdMtAKAAAAAAAAKR0eXBlpHBlZXKkbmFtZahSZXBlYXRlcq9zaWduYWxfc3RyZW5ndGjQyaNzbnLLQCQAAAAAAAClbGFiZWyqQmFja3VwIE1hcAHOZVPxAg=="
        );

        let payload = parse_lxmf_telemetry_payload(&raw).expect("payload");
        let telemetry = humanize_lxmf_telemetry_payload(payload);

        assert_eq!(telemetry["time"]["timestamp"], 1_700_000_002);
        assert_eq!(telemetry["rns_transport"]["transport_enabled"], true);
        assert_eq!(telemetry["rns_transport"]["transport_uptime"], 4_242);
        assert_eq!(telemetry["rns_transport"]["interface_count"], 2);
        assert_eq!(telemetry["rns_transport"]["link_count"], 7);
        assert_eq!(telemetry["rns_transport"]["custom_metric"], 99.9);
        assert_eq!(telemetry["lxmf_propagation"]["uptime"], 12_345);
        assert_eq!(telemetry["lxmf_propagation"]["total_peers"], 2);
        assert_eq!(telemetry["lxmf_propagation"]["active_peers"], 1);
        assert_eq!(telemetry["lxmf_propagation"]["unreachable_peers"], 1);
        assert_eq!(telemetry["lxmf_propagation"]["static_peers"], 1);
        assert_eq!(telemetry["lxmf_propagation"]["max_peers"], 10);
        assert_eq!(
            telemetry["connection_map"]["maps"]["main"]["points"]["deadbeef"]["signal_strength"],
            -40
        );
        assert_eq!(
            telemetry["connection_map"]["maps"]["backup"]["points"]["feedface"]["name"],
            "Repeater"
        );
    }

    #[test]
    fn parses_python_lxmf_received_and_collection_sensors() {
        let raw = serde_json::json!(
            "igHOZVPxAxCUxBCqqqqqqqqqqqqqqqqqqqqqxBC7u7u7u7u7u7u7u7u7u7u7y0CTSgAAAAAAy0CFNzMzMzMzEZKSAJLLQCkAAAAAAACkbG9hZJKlcmFkaW+Sy0AMAAAAAAAAwBKRkgCSy0AgAAAAAAAApXNvbGFyE5GSAJPLP+gAAAAAAACTyz+5mZmZmZmayz/JmZmZmZmayz/TMzMzMzMzy0CZAAAAAAAAFJGSAJLLQLAAAAAAAADLQKAAAAAAAAAVkZKjc3NkkstAYAAAAAAAAMtAUAAAAAAAABaRkgCUy0BZAAAAAAAAy0BAgAAAAAAAoUypdGFua19pY29uF5GSAJTLQEkAAAAAAADLQDkAAAAAAAChTMDM/5GSpm1hcmtlcpKBpnN5bWJvbKhmcmllbmRseaRpY29u"
        );

        let payload = parse_lxmf_telemetry_payload(&raw).expect("payload");
        let telemetry = humanize_lxmf_telemetry_payload(payload);

        assert_eq!(telemetry["time"]["timestamp"], 1_700_000_003);
        assert_eq!(telemetry["received"]["by"][0], 170);
        assert_eq!(telemetry["received"]["via"][0], 187);
        assert_eq!(telemetry["received"]["distance"]["geodesic"], 1234.5);
        assert_eq!(telemetry["received"]["distance"]["euclidian"], 678.9);
        assert_eq!(telemetry["power_consumption"]["0"][0], 12.5);
        assert_eq!(telemetry["power_consumption"]["0"][1], "load");
        assert_eq!(telemetry["power_consumption"]["radio"][0], 3.5);
        assert_eq!(telemetry["power_production"]["0"][1], "solar");
        assert_eq!(telemetry["processor"]["0"][0], 0.75);
        assert_eq!(telemetry["processor"]["0"][1][2], 0.3);
        assert_eq!(telemetry["processor"]["0"][2], 1600.0);
        assert_eq!(telemetry["ram"]["0"][0], 4096.0);
        assert_eq!(telemetry["nvm"]["ssd"][1], 64.0);
        assert_eq!(telemetry["tank"]["0"][2], "L");
        assert_eq!(telemetry["tank"]["0"][3], "tank_icon");
        assert_eq!(telemetry["fuel"]["0"][0], 50.0);
        assert_eq!(telemetry["custom"]["marker"][0]["symbol"], "friendly");
        assert_eq!(telemetry["custom"]["marker"][1], "icon");
    }

    #[test]
    fn reticulumd_rpc_transport_posts_http_msgpack_frame_to_endpoint() {
        let listener = TcpListener::bind("127.0.0.1:0").expect("listener");
        let endpoint = listener.local_addr().expect("addr").to_string();
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("accept");
            let mut request = Vec::new();
            stream.read_to_end(&mut request).expect("read request");
            let body = parse_http_response_body(&request).expect("request body");
            let decoded: ReticulumdRpcRequest = decode_frame(&body).expect("request frame");
            assert_eq!(decoded.method, "list_messages");

            let response = ReticulumdRpcResponse {
                id: decoded.id,
                result: Some(serde_json::json!({ "messages": [] })),
                error: None,
            };
            let body = encode_frame(&response).expect("response frame");
            let http = [
                b"HTTP/1.1 200 OK\r\nContent-Type: application/msgpack\r\nContent-Length: "
                    .as_slice(),
                body.len().to_string().as_bytes(),
                b"\r\n\r\n",
                body.as_slice(),
            ]
            .concat();
            stream.write_all(&http).expect("write response");
        });

        let mut transport = ReticulumdRpcTransport::new(endpoint);
        let response = transport.call("list_messages", None).expect("rpc response");
        server.join().expect("server");

        assert_eq!(response.result, Some(serde_json::json!({ "messages": [] })));
    }

    #[test]
    fn reticulumd_rpc_call_times_out_when_peer_accepts_without_response() {
        let listener = TcpListener::bind("127.0.0.1:0").expect("listener");
        let endpoint = listener.local_addr().expect("addr").to_string();
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("accept");
            let mut buffer = [0_u8; 512];
            let _ = stream.read(&mut buffer);
            thread::sleep(Duration::from_millis(500));
        });
        let request = ReticulumdRpcRequest {
            id: 1,
            method: "list_messages".to_string(),
            params: None,
        };

        let started = Instant::now();
        let error =
            reticulumd_rpc_call_with_timeout(&endpoint, &request, Duration::from_millis(100))
                .expect_err("timeout error");
        let elapsed = started.elapsed();
        server.join().expect("server");

        assert!(matches!(error, TransportError::Receive(_)));
        assert!(
            elapsed < Duration::from_millis(450),
            "RPC call did not honor timeout; elapsed={elapsed:?}"
        );
    }

    #[test]
    fn list_reticulumd_announces_parses_current_records_and_ignores_extra_fields() {
        let (endpoint, server) = fake_reticulumd_rpc_response(
            Some(serde_json::json!({
                "announces": [{
                    "id": "announce-1",
                    "peer": "7f3c0b2cc4bc423d25742b014c0e03b9",
                    "timestamp": 1_700_000_000,
                    "name": "Field REM",
                    "name_source": "app_data",
                    "first_seen": 1_700_000_000,
                    "seen_count": 2,
                    "app_data_hex": "72656d",
                    "capabilities": ["r3akt", "EmergencyMessages"],
                    "rssi": -72.5,
                    "snr": 8.25,
                    "q": 92.0,
                    "stamp_cost": 4,
                    "stamp_cost_flexibility": 3,
                    "peering_cost": 5
                }],
                "next_cursor": null
            })),
            None,
        );

        let announces = list_reticulumd_announces(endpoint.as_str(), 6_000).expect("announces");
        let request = server.join().expect("rpc server");

        assert_eq!(request.method, "list_announces");
        assert_eq!(request.params.expect("params")["limit"], 5_000);
        assert_eq!(announces.len(), 1);
        assert_eq!(announces[0].id, "announce-1");
        assert_eq!(announces[0].name.as_deref(), Some("Field REM"));
        assert_eq!(
            announces[0].capabilities,
            vec!["r3akt".to_string(), "EmergencyMessages".to_string()]
        );
        assert_eq!(announces[0].stamp_cost_flexibility, Some(3));
        assert_eq!(announces[0].peering_cost, Some(5));
    }

    #[test]
    fn list_reticulumd_announces_returns_empty_list() {
        let (endpoint, server) = fake_reticulumd_rpc_response(
            Some(serde_json::json!({
                "announces": [],
                "next_cursor": null
            })),
            None,
        );

        let announces = list_reticulumd_announces(endpoint.as_str(), 500).expect("announces");
        let request = server.join().expect("rpc server");

        assert_eq!(request.method, "list_announces");
        assert!(announces.is_empty());
    }

    #[test]
    fn list_reticulumd_announces_reports_rpc_error() {
        let (endpoint, server) = fake_reticulumd_rpc_response(
            None,
            Some(ReticulumdRpcError {
                code: "announce_unavailable".to_string(),
                message: "announce store offline".to_string(),
                category: Some("Storage".to_string()),
                retryable: Some(true),
                ..ReticulumdRpcError::default()
            }),
        );

        let error = list_reticulumd_announces(endpoint.as_str(), 500).expect_err("rpc error");
        let request = server.join().expect("rpc server");

        assert_eq!(request.method, "list_announces");
        assert!(error.to_string().contains("announce_unavailable"));
        assert!(error.to_string().contains("announce store offline"));
    }

    #[test]
    fn poll_reticulumd_events_parses_normal_batch() {
        let (endpoint, server) = fake_reticulumd_rpc_response(
            Some(serde_json::json!({
                "events": [{
                    "event_id": "evt-1",
                    "runtime_id": "runtime-a",
                    "stream_id": "sdk-events",
                    "seq_no": 1,
                    "contract_version": 2,
                    "ts_ms": 1_700_000_000_000_u64,
                    "event_type": "announce_received",
                    "severity": "info",
                    "source_component": "rns-rpc",
                    "payload": {
                        "id": "announce-1",
                        "peer": "7f3c0b2cc4bc423d25742b014c0e03b9",
                        "timestamp": 1_700_000_000,
                        "name": "Field REM",
                        "name_source": "app_data_utf8",
                        "first_seen": 1_700_000_000,
                        "seen_count": 3,
                        "app_data_hex": null,
                        "capabilities": [],
                        "interface": "35be322d094f9d154a8aba4733b8497f",
                        "hops": 2,
                        "stamp_cost": 4,
                        "stamp_cost_flexibility": null,
                        "peering_cost": null
                    }
                }],
                "next_cursor": "cursor-1",
                "dropped_count": 0,
                "snapshot_high_watermark_seq_no": 1
            })),
            None,
        );

        let batch =
            poll_reticulumd_events(endpoint.as_str(), Some("cursor-0"), 999).expect("events");
        let request = server.join().expect("rpc server");

        assert_eq!(request.method, "sdk_poll_events_v2");
        assert_eq!(
            request.params.as_ref().expect("params")["cursor"],
            "cursor-0"
        );
        assert_eq!(request.params.expect("params")["max"], 256);
        assert_eq!(batch.next_cursor.as_deref(), Some("cursor-1"));
        assert_eq!(batch.events.len(), 1);
        assert_eq!(batch.events[0].event_type, "announce_received");
        let announce: ReticulumdAnnounceRecord =
            serde_json::from_value(batch.events[0].payload.clone()).expect("announce");
        assert_eq!(
            announce.interface.as_deref(),
            Some("35be322d094f9d154a8aba4733b8497f")
        );
        assert_eq!(announce.hops, Some(2));
        assert_eq!(announce.stamp_cost, Some(4));
    }

    #[test]
    fn poll_reticulumd_events_parses_empty_batch() {
        let (endpoint, server) = fake_reticulumd_rpc_response(
            Some(serde_json::json!({
                "events": [],
                "next_cursor": "cursor-idle",
                "dropped_count": 0
            })),
            None,
        );

        let batch = poll_reticulumd_events(endpoint.as_str(), None, 32).expect("events");
        let request = server.join().expect("rpc server");

        assert_eq!(request.method, "sdk_poll_events_v2");
        assert_eq!(
            request.params.expect("params")["cursor"],
            serde_json::Value::Null
        );
        assert!(batch.events.is_empty());
        assert_eq!(batch.next_cursor.as_deref(), Some("cursor-idle"));
    }

    #[test]
    fn poll_reticulumd_events_parses_stream_gap() {
        let (endpoint, server) = fake_reticulumd_rpc_response(
            Some(serde_json::json!({
                "events": [{
                    "event_id": "gap-12",
                    "event_type": "StreamGap",
                    "payload": {
                        "expected_seq_no": 1,
                        "observed_seq_no": 12,
                        "dropped_count": 11
                    }
                }],
                "next_cursor": "cursor-gap",
                "dropped_count": 11
            })),
            None,
        );

        let batch = poll_reticulumd_events(endpoint.as_str(), None, 32).expect("events");
        let request = server.join().expect("rpc server");

        assert_eq!(request.method, "sdk_poll_events_v2");
        assert_eq!(batch.dropped_count, 11);
        assert_eq!(batch.events[0].event_type, "StreamGap");
    }

    #[test]
    fn poll_reticulumd_events_reports_rpc_error() {
        let (endpoint, server) = fake_reticulumd_rpc_response(
            None,
            Some(ReticulumdRpcError {
                code: "event_stream_unavailable".to_string(),
                message: "event stream offline".to_string(),
                retryable: Some(true),
                ..ReticulumdRpcError::default()
            }),
        );

        let error = poll_reticulumd_events(endpoint.as_str(), None, 32).expect_err("rpc error");
        let request = server.join().expect("rpc server");

        assert_eq!(request.method, "sdk_poll_events_v2");
        assert!(error.to_string().contains("event_stream_unavailable"));
        assert!(error.to_string().contains("event stream offline"));
    }

    #[test]
    fn reticulumd_inbound_event_message_decodes_r3akt_payload() {
        let envelope = ProtocolEnvelope::new(
            NodeId::new("peer-alpha"),
            Destination::Topic(Topic::new("ops")),
            Topic::new("ops"),
            Payload::TopicMessage(TopicMessage {
                body: "event message".to_string(),
                content_type: "text/plain".to_string(),
                correlation_id: None,
                attachments: Vec::new(),
            }),
        )
        .with_dedupe_key("event-msg-1");
        let payload_b64 = base64::engine::general_purpose::STANDARD
            .encode(envelope.encode_msgpack().expect("msgpack"));
        let event = ReticulumdEventRecord {
            event_id: "evt-inbound-1".to_string(),
            event_type: "inbound".to_string(),
            payload: serde_json::json!({
                "message": {
                    "id": "lxmf-1",
                    "destination": "local",
                    "fields": {
                        "r3akt_payload_b64": payload_b64
                    }
                }
            }),
            ..reticulumd_event_record_defaults()
        };

        let decoded = reticulumd_event_to_envelope(&event, "local")
            .expect("decode")
            .expect("envelope");

        assert_eq!(decoded.id, envelope.id);
        assert_eq!(decoded.source, envelope.source);
    }

    fn reticulumd_event_record_defaults() -> ReticulumdEventRecord {
        ReticulumdEventRecord {
            event_id: String::new(),
            runtime_id: None,
            stream_id: None,
            seq_no: None,
            contract_version: None,
            ts_ms: None,
            event_type: String::new(),
            severity: None,
            source_component: None,
            operation_id: None,
            message_id: None,
            peer_id: None,
            correlation_id: None,
            trace_id: None,
            payload: serde_json::Value::Null,
        }
    }

    #[test]
    fn live_reticulumd_rpc_adapter_lists_announces_when_configured() {
        let endpoint = match env::var("R3AKT_RETICULUMD_RPC_ENDPOINT") {
            Ok(value) if !value.trim().is_empty() => value,
            _ => {
                eprintln!(
                    "skipping live reticulumd announce test: R3AKT_RETICULUMD_RPC_ENDPOINT is unset"
                );
                return;
            }
        };
        let announces = list_reticulumd_announces(endpoint.as_str(), 500).expect("list announces");
        eprintln!("reticulumd returned {} announces", announces.len());
        if env::var("R3AKT_RETICULUMD_EXPECT_ANNOUNCE")
            .ok()
            .is_some_and(|value| value == "1" || value.eq_ignore_ascii_case("true"))
        {
            assert!(
                !announces.is_empty(),
                "expected at least one live Reticulum announce"
            );
        }
    }

    #[test]
    fn live_reticulumd_rpc_adapter_sends_and_receives_r3akt_envelope() {
        let endpoint = match env::var("R3AKT_RETICULUMD_RPC_ENDPOINT") {
            Ok(value) if !value.trim().is_empty() => value,
            _ => {
                eprintln!("skipping live reticulumd test: R3AKT_RETICULUMD_RPC_ENDPOINT is unset");
                return;
            }
        };
        let source = env::var("R3AKT_RETICULUMD_SOURCE")
            .ok()
            .filter(|value| !value.trim().is_empty())
            .unwrap_or_else(|| "r3akt-live-source".to_string());
        let destination = env::var("R3AKT_RETICULUMD_DESTINATION")
            .ok()
            .filter(|value| !value.trim().is_empty())
            .unwrap_or_else(|| source.clone());
        let poll_attempts = env::var("R3AKT_RETICULUMD_POLL_ATTEMPTS")
            .ok()
            .and_then(|value| value.parse::<usize>().ok())
            .unwrap_or(30);
        let poll_delay_ms = env::var("R3AKT_RETICULUMD_POLL_DELAY_MS")
            .ok()
            .and_then(|value| value.parse::<u64>().ok())
            .unwrap_or(500);

        let envelope = ProtocolEnvelope::new(
            NodeId::new(source.clone()),
            Destination::Node(NodeId::new(destination.clone())),
            Topic::new("r3akt-live-reticulumd"),
            Payload::Heartbeat(Heartbeat {
                status: HealthStatus::Nominal,
                sequence: 1,
            }),
        );
        let expected_id = envelope.id;
        let expected_source = source.clone();
        let adapter =
            ReticulumdRpcLxmfRsAdapter::new(source, ReticulumdRpcTransport::new(endpoint));
        let mut transport = LxmfRsTransport::new(adapter);

        crate::test_block_on(transport.publish(envelope)).expect("publish live envelope");
        let mut received = None;
        for _ in 0..poll_attempts {
            if let Some(envelope) = crate::test_block_on(transport.poll()).expect("poll live") {
                if envelope.id == expected_id {
                    received = Some(envelope);
                    break;
                }
            }
            thread::sleep(Duration::from_millis(poll_delay_ms));
        }

        let received = received.expect("live reticulumd did not return the sent R3AKT envelope");
        assert_eq!(received.id, expected_id);
        assert_eq!(received.topic.as_str(), "r3akt-live-reticulumd");
        assert_eq!(received.source.as_str(), expected_source.as_str());
    }
}

#[cfg(test)]
pub fn test_block_on<F>(future: F) -> F::Output
where
    F: Future,
{
    use std::sync::Arc;
    use std::task::{Context, Poll, Wake, Waker};

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
