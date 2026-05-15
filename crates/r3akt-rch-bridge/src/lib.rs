#![allow(clippy::missing_errors_doc)]

use r3akt_profile_rch::{CommandResultEnvelope, CommandResultStatus, MissionCommandEnvelope};
use r3akt_rch_core::{MissionSyncResponse, RchCore, RchCoreError, RchSqliteStore};
use serde::{Deserialize, Serialize, de::DeserializeOwned};
use serde_json::Value as JsonValue;
use std::io::{self, Read, Write};
use std::net::{Shutdown, TcpStream};
use std::time::Duration;
use thiserror::Error;

const RETICULUMD_RPC_TIMEOUT: Duration = Duration::from_secs(30);

#[derive(Debug, Error)]
pub enum BridgeError {
    #[error("bridge request decode failed: {0}")]
    Decode(String),
    #[error("bridge response encode failed: {0}")]
    Encode(String),
    #[error("outbound request failed: {0}")]
    Outbound(String),
    #[error(transparent)]
    RchCore(#[from] RchCoreError),
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct OutboundSendRequest {
    pub message_id: String,
    pub source: String,
    pub destination: String,
    #[serde(default)]
    pub title: String,
    pub content: String,
    #[serde(default)]
    pub fields: Option<JsonValue>,
    #[serde(default)]
    pub method: Option<String>,
}

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

pub trait ReticulumdRpc {
    fn call(
        &mut self,
        method: &str,
        params: Option<JsonValue>,
    ) -> Result<ReticulumdRpcResponse, BridgeError>;
}

#[derive(Debug, Clone)]
pub struct ReticulumdRpcClient {
    endpoint: String,
    next_request_id: u64,
}

impl ReticulumdRpcClient {
    #[must_use]
    pub fn new(endpoint: impl Into<String>) -> Self {
        Self {
            endpoint: endpoint.into(),
            next_request_id: 1,
        }
    }
}

impl ReticulumdRpc for ReticulumdRpcClient {
    fn call(
        &mut self,
        method: &str,
        params: Option<JsonValue>,
    ) -> Result<ReticulumdRpcResponse, BridgeError> {
        let request = ReticulumdRpcRequest {
            id: self.next_request_id,
            method: method.to_string(),
            params,
        };
        self.next_request_id = self.next_request_id.wrapping_add(1);
        rpc_call(&self.endpoint, &request)
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum BridgeRequest {
    MissionCommand {
        command: MissionCommandEnvelope,
        #[serde(default)]
        source_identity: Option<String>,
    },
    ChecklistCommand {
        command: MissionCommandEnvelope,
        #[serde(default)]
        source_identity: Option<String>,
    },
    GrantCapability {
        identity: String,
        capability: String,
    },
    RevokeCapability {
        identity: String,
        capability: String,
    },
    RecordIdentityAnnounce {
        identity: String,
        #[serde(default)]
        announced_identity_hash: Option<String>,
        #[serde(default)]
        display_name: Option<String>,
        #[serde(default)]
        source_interface: Option<String>,
        #[serde(default)]
        announce_capabilities: Vec<String>,
    },
    SetIdentityState {
        identity: String,
        is_banned: bool,
        is_blackholed: bool,
    },
    SetRemMode {
        identity: String,
        mode: String,
    },
    AssignMissionAccessRole {
        mission_uid: String,
        subject_type: String,
        subject_id: String,
        role: String,
    },
    GrantOperationRight {
        subject_type: String,
        subject_id: String,
        operation: String,
        #[serde(default)]
        scope_type: String,
        #[serde(default)]
        scope_id: String,
    },
    RevokeOperationRight {
        subject_type: String,
        subject_id: String,
        operation: String,
        #[serde(default)]
        scope_type: String,
        #[serde(default)]
        scope_id: String,
    },
    SetAuthorization {
        required: bool,
    },
    ListTopics,
    ListSubscribers,
    ListMarkers,
    ListZones,
    StateSnapshot,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum BridgeResponse {
    MissionCommand {
        responses: Vec<MissionSyncResponse>,
        topics: usize,
        messages: usize,
    },
    ChecklistCommand {
        responses: Vec<MissionSyncResponse>,
        checklists: usize,
    },
    ListTopics {
        topics: Vec<r3akt_rch_core::TopicRecord>,
    },
    ListSubscribers {
        subscribers: Vec<r3akt_rch_core::SubscriberRecord>,
    },
    ListMarkers {
        markers: Vec<r3akt_rch_core::MarkerRecord>,
    },
    ListZones {
        zones: Vec<r3akt_rch_core::ZoneRecord>,
    },
    StateSnapshot {
        snapshot: Box<r3akt_rch_core::RchCoreSnapshot>,
    },
    StateUpdated {
        ok: bool,
    },
    OutboundSend {
        ok: bool,
        message_id: String,
        transport: String,
    },
}

pub fn handle_json_request(core: &mut RchCore, input: &str) -> Result<String, BridgeError> {
    let request: BridgeRequest =
        serde_json::from_str(input).map_err(|error| BridgeError::Decode(error.to_string()))?;
    let response = handle_request(core, request);
    serde_json::to_string(&response).map_err(|error| BridgeError::Encode(error.to_string()))
}

pub fn handle_outbound_json_request(
    client: &mut impl ReticulumdRpc,
    input: &str,
) -> Result<String, BridgeError> {
    #[derive(Deserialize)]
    #[serde(tag = "type", rename_all = "snake_case")]
    enum Request {
        OutboundSend(OutboundSendRequest),
    }

    let request: Request =
        serde_json::from_str(input).map_err(|error| BridgeError::Decode(error.to_string()))?;
    let Request::OutboundSend(request) = request;
    let response = handle_outbound_send(client, request)?;
    serde_json::to_string(&response).map_err(|error| BridgeError::Encode(error.to_string()))
}

pub fn handle_outbound_json_request_with_reticulumd(
    endpoint: &str,
    input: &str,
) -> Result<String, BridgeError> {
    let mut client = ReticulumdRpcClient::new(endpoint);
    handle_outbound_json_request(&mut client, input)
}

fn handle_outbound_send(
    client: &mut impl ReticulumdRpc,
    request: OutboundSendRequest,
) -> Result<BridgeResponse, BridgeError> {
    let rpc_method = if request.method.as_deref() == Some("direct") {
        "sdk_send_v2"
    } else {
        "send_message_v2"
    };
    let rpc_message_id = if rpc_method == "sdk_send_v2" {
        format!("sdk-{}", request.message_id)
    } else {
        request.message_id.clone()
    };
    let mut params = serde_json::Map::new();
    params.insert("id".to_string(), JsonValue::String(rpc_message_id));
    params.insert("source".to_string(), JsonValue::String(request.source));
    params.insert(
        "destination".to_string(),
        JsonValue::String(request.destination),
    );
    params.insert("title".to_string(), JsonValue::String(request.title));
    params.insert("content".to_string(), JsonValue::String(request.content));
    params.insert(
        "fields".to_string(),
        request.fields.unwrap_or(JsonValue::Null),
    );
    if rpc_method == "send_message_v2" {
        if let Some(method) = request.method {
            params.insert("method".to_string(), JsonValue::String(method));
        }
    }
    let response = client.call(rpc_method, Some(JsonValue::Object(params)))?;
    if let Some(error) = response.error {
        return Err(BridgeError::Outbound(format!(
            "reticulumd RPC {}: {}",
            error.code, error.message
        )));
    }
    Ok(BridgeResponse::OutboundSend {
        ok: true,
        message_id: request.message_id,
        transport: "reticulumd_rpc".to_string(),
    })
}

#[must_use]
pub fn handle_request(core: &mut RchCore, request: BridgeRequest) -> BridgeResponse {
    match request {
        BridgeRequest::MissionCommand {
            command,
            source_identity,
        } => {
            if command.command_type.starts_with("rem.registry.")
                && source_identity
                    .as_deref()
                    .is_none_or(|identity| identity.trim().is_empty())
            {
                return BridgeResponse::MissionCommand {
                    responses: vec![rem_rejected_result(
                        &command,
                        "unauthorized",
                        "Source identity is required",
                    )],
                    topics: core.topics().len(),
                    messages: core.messages().len(),
                };
            }
            if let Some(rejected) = reject_source_mismatch(&command, source_identity.as_deref()) {
                let rejected = if command.command_type.starts_with("rem.registry.") {
                    rem_rejected_result(
                        &command,
                        rejected
                            .results_field()
                            .and_then(|value| value.get("reason_code"))
                            .and_then(serde_json::Value::as_str)
                            .unwrap_or("unauthorized"),
                        rejected
                            .results_field()
                            .and_then(|value| value.get("reason"))
                            .and_then(serde_json::Value::as_str)
                            .unwrap_or("Envelope source identity does not match transport sender"),
                    )
                } else {
                    rejected
                };
                return BridgeResponse::MissionCommand {
                    responses: vec![rejected],
                    topics: core.topics().len(),
                    messages: core.messages().len(),
                };
            }
            let responses = core.handle_mission_sync_command(&command);
            BridgeResponse::MissionCommand {
                responses,
                topics: core.topics().len(),
                messages: core.messages().len(),
            }
        }
        BridgeRequest::ChecklistCommand {
            command,
            source_identity,
        } => {
            if let Some(rejected) = reject_source_mismatch(&command, source_identity.as_deref()) {
                return BridgeResponse::ChecklistCommand {
                    responses: vec![rejected],
                    checklists: core.checklists().len(),
                };
            }
            let responses = core.handle_checklist_sync_command(&command);
            BridgeResponse::ChecklistCommand {
                responses,
                checklists: core.checklists().len(),
            }
        }
        request @ (BridgeRequest::GrantCapability { .. }
        | BridgeRequest::RevokeCapability { .. }
        | BridgeRequest::RecordIdentityAnnounce { .. }
        | BridgeRequest::SetIdentityState { .. }
        | BridgeRequest::SetRemMode { .. }
        | BridgeRequest::AssignMissionAccessRole { .. }
        | BridgeRequest::GrantOperationRight { .. }
        | BridgeRequest::RevokeOperationRight { .. }
        | BridgeRequest::SetAuthorization { .. }) => handle_state_update_request(core, request),
        BridgeRequest::ListTopics => BridgeResponse::ListTopics {
            topics: core.topics(),
        },
        BridgeRequest::ListSubscribers => BridgeResponse::ListSubscribers {
            subscribers: core.snapshot().subscribers,
        },
        BridgeRequest::ListMarkers => BridgeResponse::ListMarkers {
            markers: core.snapshot().markers,
        },
        BridgeRequest::ListZones => BridgeResponse::ListZones {
            zones: core.snapshot().zones,
        },
        BridgeRequest::StateSnapshot => BridgeResponse::StateSnapshot {
            snapshot: Box::new(core.snapshot()),
        },
    }
}

fn handle_state_update_request(core: &mut RchCore, request: BridgeRequest) -> BridgeResponse {
    let ok = match request {
        BridgeRequest::GrantCapability {
            identity,
            capability,
        } => {
            core.grant_identity_capability(identity, capability);
            true
        }
        BridgeRequest::RevokeCapability {
            identity,
            capability,
        } => {
            core.revoke_identity_capability(identity, capability);
            true
        }
        BridgeRequest::RecordIdentityAnnounce {
            identity,
            announced_identity_hash,
            display_name,
            source_interface,
            announce_capabilities,
        } => core
            .record_identity_announce(
                identity,
                announced_identity_hash,
                display_name,
                source_interface,
                announce_capabilities,
            )
            .is_ok(),
        BridgeRequest::SetIdentityState {
            identity,
            is_banned,
            is_blackholed,
        } => core
            .set_identity_state(identity, is_banned, is_blackholed)
            .is_ok(),
        BridgeRequest::SetRemMode { identity, mode } => {
            core.set_identity_rem_mode(identity, mode).is_ok()
        }
        BridgeRequest::AssignMissionAccessRole {
            mission_uid,
            subject_type,
            subject_id,
            role,
        } => core
            .assign_mission_access_role(mission_uid, subject_type, subject_id, role)
            .is_ok(),
        BridgeRequest::GrantOperationRight {
            subject_type,
            subject_id,
            operation,
            scope_type,
            scope_id,
        } => core
            .grant_operation_right(subject_type, subject_id, operation, scope_type, scope_id)
            .is_ok(),
        BridgeRequest::RevokeOperationRight {
            subject_type,
            subject_id,
            operation,
            scope_type,
            scope_id,
        } => core
            .revoke_operation_right(subject_type, subject_id, operation, scope_type, scope_id)
            .is_ok(),
        BridgeRequest::SetAuthorization { required } => {
            core.set_authorization_required(required);
            true
        }
        BridgeRequest::MissionCommand { .. }
        | BridgeRequest::ChecklistCommand { .. }
        | BridgeRequest::ListTopics
        | BridgeRequest::ListSubscribers
        | BridgeRequest::ListMarkers
        | BridgeRequest::ListZones
        | BridgeRequest::StateSnapshot => unreachable!("non-state bridge request"),
    };
    BridgeResponse::StateUpdated { ok }
}

fn reject_source_mismatch(
    command: &MissionCommandEnvelope,
    source_identity: Option<&str>,
) -> Option<MissionSyncResponse> {
    let source_identity = source_identity?.trim().to_ascii_lowercase();
    let envelope_source = command.source.rns_identity.trim().to_ascii_lowercase();
    if source_identity.is_empty() {
        return Some(MissionSyncResponse::results(CommandResultEnvelope {
            command_id: command.command_id.clone(),
            status: CommandResultStatus::Rejected,
            detail: Some("Source identity is required".to_string()),
            reason_code: Some("unauthorized".to_string()),
            reason: Some("Source identity is required".to_string()),
            required_capabilities: Vec::new(),
            accepted_at: None,
            by_identity: None,
            correlation_id: command.correlation_id.clone(),
            result: serde_json::Value::Null,
        }));
    }
    if envelope_source.is_empty() || source_identity == envelope_source {
        return None;
    }
    Some(MissionSyncResponse::results(CommandResultEnvelope {
        command_id: command.command_id.clone(),
        status: CommandResultStatus::Rejected,
        detail: Some("Envelope source identity does not match transport sender".to_string()),
        reason_code: Some("unauthorized".to_string()),
        reason: Some("Envelope source identity does not match transport sender".to_string()),
        required_capabilities: Vec::new(),
        accepted_at: None,
        by_identity: None,
        correlation_id: command.correlation_id.clone(),
        result: serde_json::Value::Null,
    }))
}

fn rem_rejected_result(
    command: &MissionCommandEnvelope,
    reason_code: &str,
    reason: &str,
) -> MissionSyncResponse {
    MissionSyncResponse::rem_results(CommandResultEnvelope {
        command_id: command.command_id.clone(),
        status: CommandResultStatus::Rejected,
        detail: Some(reason.to_string()),
        reason_code: Some(reason_code.to_string()),
        reason: Some(reason.to_string()),
        required_capabilities: Vec::new(),
        accepted_at: None,
        by_identity: None,
        correlation_id: command.correlation_id.clone(),
        result: serde_json::Value::Null,
    })
}

pub fn handle_json_request_with_sqlite(db_path: &str, input: &str) -> Result<String, BridgeError> {
    let mut store = RchSqliteStore::open(db_path)?;
    let mut core = RchCore::load_from_sqlite(&store)?.unwrap_or_default();
    let response = handle_json_request(&mut core, input)?;
    core.save_to_sqlite(&mut store)?;
    Ok(response)
}

pub fn handle_json_request_with_sqlite_or_reticulumd(
    db_path: &str,
    reticulumd_rpc: Option<&str>,
    input: &str,
) -> Result<String, BridgeError> {
    let request_type = serde_json::from_str::<JsonValue>(input)
        .ok()
        .and_then(|value| {
            value
                .get("type")
                .and_then(JsonValue::as_str)
                .map(str::to_string)
        });
    if request_type.as_deref() == Some("outbound_send") {
        let endpoint = reticulumd_rpc.ok_or_else(|| {
            BridgeError::Outbound("outbound_send requires --reticulumd-rpc".to_string())
        })?;
        return handle_outbound_json_request_with_reticulumd(endpoint, input);
    }
    handle_json_request_with_sqlite(db_path, input)
}

fn rpc_call(
    endpoint: &str,
    request: &ReticulumdRpcRequest,
) -> Result<ReticulumdRpcResponse, BridgeError> {
    rpc_call_with_timeout(endpoint, request, RETICULUMD_RPC_TIMEOUT)
}

fn rpc_call_with_timeout(
    endpoint: &str,
    request: &ReticulumdRpcRequest,
    timeout: Duration,
) -> Result<ReticulumdRpcResponse, BridgeError> {
    let frame = encode_frame(request).map_err(|error| BridgeError::Outbound(error.to_string()))?;
    let http_request = build_http_post("/rpc", endpoint, &frame);
    let mut stream =
        TcpStream::connect(endpoint).map_err(|error| BridgeError::Outbound(error.to_string()))?;
    stream
        .set_read_timeout(Some(timeout))
        .map_err(|error| BridgeError::Outbound(error.to_string()))?;
    stream
        .set_write_timeout(Some(timeout))
        .map_err(|error| BridgeError::Outbound(error.to_string()))?;
    stream
        .write_all(&http_request)
        .map_err(|error| BridgeError::Outbound(error.to_string()))?;
    stream
        .shutdown(Shutdown::Write)
        .map_err(|error| BridgeError::Outbound(error.to_string()))?;
    let mut response = Vec::new();
    stream
        .read_to_end(&mut response)
        .map_err(|error| BridgeError::Outbound(error.to_string()))?;
    let body = parse_http_response_body(&response)
        .map_err(|error| BridgeError::Outbound(error.to_string()))?;
    decode_frame(&body).map_err(|error| BridgeError::Outbound(error.to_string()))
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
    use r3akt_profile_rch::{RchSource, decode_results, encode_results};
    use std::net::TcpListener;
    use std::thread;
    use std::time::{Duration, Instant};

    use super::*;

    #[derive(Debug, Clone)]
    struct RecordedRpcCall {
        method: String,
        params: serde_json::Value,
    }

    #[derive(Debug, Default)]
    struct RecordingReticulumdRpc {
        calls: Vec<RecordedRpcCall>,
    }

    impl ReticulumdRpc for RecordingReticulumdRpc {
        fn call(
            &mut self,
            method: &str,
            params: Option<serde_json::Value>,
        ) -> Result<ReticulumdRpcResponse, BridgeError> {
            self.calls.push(RecordedRpcCall {
                method: method.to_string(),
                params: params.unwrap_or(serde_json::Value::Null),
            });
            Ok(ReticulumdRpcResponse {
                id: 1,
                result: Some(serde_json::json!({ "message_id": "rch-msg-1" })),
                error: None,
            })
        }
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
        let error = rpc_call_with_timeout(&endpoint, &request, Duration::from_millis(100))
            .expect_err("timeout error");
        let elapsed = started.elapsed();
        server.join().expect("server");

        assert!(matches!(error, BridgeError::Outbound(_)));
        assert!(
            elapsed < Duration::from_millis(450),
            "RPC call did not honor timeout; elapsed={elapsed:?}"
        );
    }

    #[test]
    fn json_bridge_handles_mission_command_and_returns_rch_responses() {
        let mut core = RchCore::new();
        let input = serde_json::json!({
            "type": "mission_command",
            "command": {
                "command_id": "cmd-bridge-1",
                "source": { "rns_identity": "ABCDEF", "display_name": "Field Agent" },
                "timestamp": "2026-05-03T12:00:00Z",
                "command_type": "topic.create",
                "args": {
                    "topic_path": "mission-bridge",
                    "topic_name": "Mission Bridge"
                },
                "correlation_id": "corr-bridge-1",
                "topics": ["mission-bridge"]
            }
        })
        .to_string();

        let output = handle_json_request(&mut core, &input).expect("bridge");
        let response: serde_json::Value = serde_json::from_str(&output).expect("response");

        let responses = response["responses"].as_array().expect("responses");
        assert_eq!(responses.len(), 2);
        assert_eq!(response["topics"], 1);
        assert_eq!(responses[0]["fields"]["10"]["status"], "accepted");
        assert_eq!(responses[1]["fields"]["10"]["status"], "result");
    }

    #[test]
    fn bridge_response_results_are_rch_field_results_compatible() {
        let mut core = RchCore::new();
        let command = MissionCommandEnvelope {
            command_id: "cmd-bridge-2".to_string(),
            source: RchSource::new("ABCDEF"),
            timestamp: "2026-05-03T12:00:00Z".to_string(),
            command_type: "topic.create".to_string(),
            args: serde_json::json!({ "topic_path": "mission-2" }),
            correlation_id: None,
            topics: vec!["mission-2".to_string()],
        };
        let responses = core.handle_mission_sync_command(&command);
        let result = responses[1].results_field().expect("result").clone();
        let encoded = encode_results(&[serde_json::from_value(result).expect("result envelope")])
            .expect("encode results");

        assert_eq!(decode_results(&encoded).expect("decode").len(), 1);
    }

    #[test]
    fn json_bridge_can_enable_authorization_and_grant_capability() {
        let mut core = RchCore::new();
        handle_json_request(&mut core, r#"{"type":"set_authorization","required":true}"#)
            .expect("set authorization");
        let rejected = handle_json_request(
            &mut core,
            r#"{"type":"mission_command","command":{"command_id":"cmd-auth-1","source":{"rns_identity":"ABCDEF"},"timestamp":"2026-05-03T12:00:00Z","command_type":"topic.create","args":{"topic_path":"auth-topic","topic_name":"Auth Topic"},"topics":[]}}"#,
        )
        .expect("rejected");
        handle_json_request(
            &mut core,
            r#"{"type":"grant_capability","identity":"ABCDEF","capability":"topic.create"}"#,
        )
        .expect("grant");
        let accepted = handle_json_request(
            &mut core,
            r#"{"type":"mission_command","command":{"command_id":"cmd-auth-2","source":{"rns_identity":"ABCDEF"},"timestamp":"2026-05-03T12:00:00Z","command_type":"topic.create","args":{"topic_path":"auth-topic","topic_name":"Auth Topic"},"topics":[]}}"#,
        )
        .expect("accepted");

        assert!(rejected.contains("\"reason_code\":\"unauthorized\""));
        assert!(accepted.contains("\"status\":\"accepted\""));
        assert!(accepted.contains("\"status\":\"result\""));

        handle_json_request(
            &mut core,
            r#"{"type":"revoke_capability","identity":"ABCDEF","capability":"topic.create"}"#,
        )
        .expect("revoke");
        let revoked = handle_json_request(
            &mut core,
            r#"{"type":"mission_command","command":{"command_id":"cmd-auth-3","source":{"rns_identity":"ABCDEF"},"timestamp":"2026-05-03T12:00:00Z","command_type":"topic.create","args":{"topic_path":"auth-topic-revoked","topic_name":"Revoked Auth Topic"},"topics":[]}}"#,
        )
        .expect("revoked");
        assert!(revoked.contains("\"reason_code\":\"unauthorized\""));
    }

    #[test]
    fn json_bridge_enforces_rem_transport_source_and_announce_capabilities() {
        let mut core = RchCore::new();
        let command = serde_json::json!({
            "command_id": "cmd-rem-bridge",
            "source": { "rns_identity": "ABCDEF" },
            "timestamp": "2026-05-03T12:00:00Z",
            "command_type": "rem.registry.mode.set",
            "args": { "mode": "connected" },
            "correlation_id": "corr-rem-bridge",
            "topics": []
        });

        let missing_source = handle_json_request(
            &mut core,
            &serde_json::json!({
                "type": "mission_command",
                "command": command.clone(),
            })
            .to_string(),
        )
        .expect("missing source");
        let missing_source_payload: serde_json::Value =
            serde_json::from_str(&missing_source).expect("missing source json");
        assert_eq!(
            missing_source_payload["responses"][0]["fields"]["10"]["reason"],
            "Source identity is required"
        );
        assert_eq!(missing_source_payload["responses"][0]["content"], "");

        let mismatch = handle_json_request(
            &mut core,
            &serde_json::json!({
                "type": "mission_command",
                "source_identity": "OTHER",
                "command": command.clone(),
            })
            .to_string(),
        )
        .expect("mismatch");
        let mismatch_payload: serde_json::Value =
            serde_json::from_str(&mismatch).expect("mismatch json");
        assert_eq!(
            mismatch_payload["responses"][0]["fields"]["10"]["reason"],
            "Envelope source identity does not match transport sender"
        );
        assert_eq!(mismatch_payload["responses"][0]["content"], "");

        let missing_caps = handle_json_request(
            &mut core,
            &serde_json::json!({
                "type": "mission_command",
                "source_identity": "ABCDEF",
                "command": command.clone(),
            })
            .to_string(),
        )
        .expect("missing capabilities");
        assert!(missing_caps.contains("REM announce capabilities are required"));

        handle_json_request(
            &mut core,
            r#"{"type":"record_identity_announce","identity":"ABCDEF","source_interface":"identity","announce_capabilities":["r3akt","EmergencyMessages"]}"#,
        )
        .expect("record announce");
        let accepted = handle_json_request(
            &mut core,
            &serde_json::json!({
                "type": "mission_command",
                "source_identity": "ABCDEF",
                "command": command.clone(),
            })
            .to_string(),
        )
        .expect("accepted");
        let accepted_payload: serde_json::Value =
            serde_json::from_str(&accepted).expect("accepted json");
        assert_eq!(
            accepted_payload["responses"][0]["fields"]["10"]["status"],
            "accepted"
        );
        assert_eq!(
            accepted_payload["responses"][1]["fields"]["10"]["status"],
            "result"
        );
        assert_eq!(
            accepted_payload["responses"][1]["fields"]["13"]["event_type"],
            "rem.registry.mode.updated"
        );
        assert_eq!(
            accepted_payload["responses"][1]["fields"]["10"]["result"]["mode"],
            "connected"
        );
    }

    #[test]
    fn json_bridge_handles_silent_checklist_command() {
        let mut core = RchCore::new();
        let input = serde_json::json!({
            "type": "checklist_command",
            "command": {
                "command_id": "cmd-checklist-1",
                "source": { "rns_identity": "ABCDEF", "display_name": "Field Agent" },
                "timestamp": "2026-05-03T12:00:00Z",
                "command_type": "checklist.create.offline",
                "args": {
                    "checklist_uid": "checklist-bridge",
                    "name": "Bridge Checklist",
                    "origin_type": "BLANK_TEMPLATE"
                },
                "topics": []
            }
        })
        .to_string();

        let output = handle_json_request(&mut core, &input).expect("bridge");
        let response: serde_json::Value = serde_json::from_str(&output).expect("response");

        assert_eq!(
            response["responses"].as_array().expect("responses").len(),
            0
        );
        assert_eq!(response["checklists"], 1);
    }

    #[test]
    fn json_bridge_lists_subscribers() {
        let mut core = RchCore::new();
        handle_json_request(
            &mut core,
            &serde_json::json!({
                "type": "mission_command",
                "command": {
                    "command_id": "cmd-topic-1",
                    "source": { "rns_identity": "ABCDEF" },
                    "timestamp": "2026-05-03T12:00:00Z",
                    "command_type": "topic.create",
                    "args": {
                        "topic_id": "mission-1",
                        "topic_path": "mission-1",
                        "topic_name": "Mission 1"
                    },
                    "topics": []
                }
            })
            .to_string(),
        )
        .expect("create topic");
        handle_json_request(
            &mut core,
            &serde_json::json!({
                "type": "mission_command",
                "command": {
                    "command_id": "cmd-subscribe-1",
                    "source": { "rns_identity": "ABCDEF" },
                    "timestamp": "2026-05-03T12:00:00Z",
                    "command_type": "topic.subscribe",
                    "args": {
                        "topic_id": "mission-1",
                        "destination": "dest-1",
                        "metadata": { "role": "watcher" }
                    },
                    "topics": []
                }
            })
            .to_string(),
        )
        .expect("subscribe topic");

        let output =
            handle_json_request(&mut core, r#"{"type":"list_subscribers"}"#).expect("list");
        let response: serde_json::Value = serde_json::from_str(&output).expect("response");
        let subscribers = response["subscribers"].as_array().expect("subscribers");

        assert_eq!(subscribers.len(), 1);
        assert_eq!(subscribers[0]["node_id"], "dest-1");
        assert_eq!(subscribers[0]["topic_id"], "mission-1");
        assert_eq!(subscribers[0]["metadata"]["role"], "watcher");
    }

    #[test]
    fn json_bridge_returns_state_snapshot() {
        let mut core = RchCore::new();
        handle_json_request(
            &mut core,
            &serde_json::json!({
                "type": "mission_command",
                "command": {
                    "command_id": "cmd-topic-snapshot-1",
                    "source": { "rns_identity": "ABCDEF" },
                    "timestamp": "2026-05-03T12:00:00Z",
                    "command_type": "topic.create",
                    "args": {
                        "topic_id": "snapshot-topic",
                        "topic_path": "snapshot-topic",
                        "topic_name": "Snapshot Topic"
                    },
                    "topics": []
                }
            })
            .to_string(),
        )
        .expect("create topic");

        let output =
            handle_json_request(&mut core, r#"{"type":"state_snapshot"}"#).expect("snapshot");
        let response: serde_json::Value = serde_json::from_str(&output).expect("response");

        assert_eq!(
            response["snapshot"]["topics"][0]["topic_id"],
            "snapshot-topic"
        );
        assert_eq!(response["snapshot"]["authorization_required"], false);
    }

    #[test]
    fn json_bridge_lists_markers_and_zones() {
        let mut core = RchCore::new();
        handle_json_request(
            &mut core,
            &serde_json::json!({
                "type": "mission_command",
                "command": {
                    "command_id": "cmd-marker-1",
                    "source": { "rns_identity": "ABCDEF" },
                    "timestamp": "2026-05-03T12:00:00Z",
                    "command_type": "mission.marker.create",
                    "args": {
                        "name": "Marker One",
                        "marker_type": "marker",
                        "symbol": "marker",
                        "category": "marker",
                        "lat": 45.0,
                        "lon": -93.0
                    },
                    "topics": []
                }
            })
            .to_string(),
        )
        .expect("create marker");
        handle_json_request(
            &mut core,
            &serde_json::json!({
                "type": "mission_command",
                "command": {
                    "command_id": "cmd-zone-1",
                    "source": { "rns_identity": "ABCDEF" },
                    "timestamp": "2026-05-03T12:00:00Z",
                    "command_type": "mission.zone.create",
                    "args": {
                        "zone_id": "zone-1",
                        "name": "Zone One",
                        "points": [
                            { "lat": 45.0, "lon": -93.0 },
                            { "lat": 45.1, "lon": -93.0 },
                            { "lat": 45.1, "lon": -92.9 }
                        ]
                    },
                    "topics": []
                }
            })
            .to_string(),
        )
        .expect("create zone");

        let marker_output =
            handle_json_request(&mut core, r#"{"type":"list_markers"}"#).expect("markers");
        let zone_output =
            handle_json_request(&mut core, r#"{"type":"list_zones"}"#).expect("zones");
        let markers: serde_json::Value = serde_json::from_str(&marker_output).expect("markers");
        let zones: serde_json::Value = serde_json::from_str(&zone_output).expect("zones");

        assert_eq!(markers["markers"][0]["name"], "Marker One");
        assert!(
            !zones["zones"][0]["zone_id"]
                .as_str()
                .expect("zone id")
                .is_empty()
        );
        assert_eq!(zones["zones"][0]["name"], "Zone One");
        assert_eq!(
            zones["zones"][0]["points"]
                .as_array()
                .expect("points")
                .len(),
            3
        );
    }

    #[test]
    fn outbound_send_request_calls_reticulumd_rpc() {
        let mut client = RecordingReticulumdRpc::default();
        let input = serde_json::json!({
            "type": "outbound_send",
            "message_id": "rch-msg-1",
            "source": "source-destination",
            "destination": "target-destination",
            "title": "RCH",
            "content": "hello from rust",
            "fields": { "10": { "status": "result" } },
            "method": "direct"
        })
        .to_string();

        let output =
            handle_outbound_json_request(&mut client, &input).expect("outbound bridge response");
        let response: serde_json::Value = serde_json::from_str(&output).expect("response");

        assert_eq!(response["type"], "outbound_send");
        assert_eq!(response["ok"], true);
        assert_eq!(response["message_id"], "rch-msg-1");
        assert_eq!(response["transport"], "reticulumd_rpc");
        assert_eq!(client.calls.len(), 1);
        assert_eq!(client.calls[0].method, "sdk_send_v2");
        assert_eq!(client.calls[0].params["id"], "sdk-rch-msg-1");
        assert_eq!(client.calls[0].params["source"], "source-destination");
        assert_eq!(client.calls[0].params["destination"], "target-destination");
        assert_eq!(client.calls[0].params["title"], "RCH");
        assert_eq!(client.calls[0].params["content"], "hello from rust");
        assert_eq!(client.calls[0].params["fields"]["10"]["status"], "result");
        assert!(client.calls[0].params.get("method").is_none());
    }

    #[test]
    fn live_reticulumd_outbound_send_request_is_accepted_when_configured() {
        let endpoint = match std::env::var("R3AKT_RETICULUMD_RPC_ENDPOINT") {
            Ok(value) if !value.trim().is_empty() => value,
            _ => {
                eprintln!(
                    "skipping live bridge reticulumd test: R3AKT_RETICULUMD_RPC_ENDPOINT is unset"
                );
                return;
            }
        };
        let source = std::env::var("R3AKT_RETICULUMD_SOURCE")
            .ok()
            .filter(|value| !value.trim().is_empty())
            .unwrap_or_else(|| "r3akt-live-source".to_string());
        let destination = std::env::var("R3AKT_RETICULUMD_DESTINATION")
            .ok()
            .filter(|value| !value.trim().is_empty())
            .unwrap_or_else(|| source.clone());
        let nonce = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("system clock")
            .as_millis();
        let message_id = format!("r3akt-live-bridge-{nonce}");
        let input = serde_json::json!({
            "type": "outbound_send",
            "message_id": message_id,
            "source": source,
            "destination": destination,
            "title": "R3AKT live bridge",
            "content": "live bridge outbound smoke",
            "fields": { "10": { "status": "result" } },
            "method": "direct"
        })
        .to_string();

        let output = handle_outbound_json_request_with_reticulumd(endpoint.as_str(), &input)
            .expect("live bridge outbound response");
        let response: serde_json::Value = serde_json::from_str(&output).expect("response");

        assert_eq!(response["type"], "outbound_send");
        assert_eq!(response["ok"], true);
        assert_eq!(response["message_id"], message_id);
        assert_eq!(response["transport"], "reticulumd_rpc");
    }
}
