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
fn sqlite_bridge_preserves_counts_rejection_and_normalized_grant_identity() {
    let path = std::env::temp_dir().join(format!(
        "rch-bridge-scoped-{}-{}.db",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("clock")
            .as_nanos()
    ));
    let mut store = RchSqliteStore::open(&path).expect("store");
    let mut core = RchCore::new();
    core.set_authorization_required(false);
    core.handle_command(&MissionCommandEnvelope {
        command_id: "old-message".into(),
        source: RchSource::new("operator"),
        timestamp: String::new(),
        command_type: "mission.message.send".into(),
        args: serde_json::json!({"content":"Old history","destination":"peer"}),
        correlation_id: None,
        topics: vec![],
    });
    store.save_snapshot(&core.snapshot()).expect("state");
    let call = |request: BridgeRequest| -> JsonValue {
        serde_json::from_str(
            &handle_json_request_with_sqlite(
                path.to_str().expect("path"),
                &serde_json::to_string(&request).expect("request"),
            )
            .expect("bridge"),
        )
        .expect("response")
    };
    let command = MissionCommandEnvelope {
        command_id: "bridge-create".into(),
        source: RchSource::new("operator"),
        timestamp: "2026-10-10T00:00:00Z".into(),
        command_type: "topic.create".into(),
        args: serde_json::json!({"topic_id":"ops","topic_name":"Ops","topic_path":"ops"}),
        correlation_id: None,
        topics: vec![],
    };
    let response = call(BridgeRequest::MissionCommand {
        command: command.clone(),
        source_identity: None,
    });
    assert_eq!(response["type"], "mission_command");
    assert_eq!(response["topics"], 1);
    assert_eq!(response["messages"], 1);
    let mut denied = command;
    denied.command_id = "bridge-denied".into();
    denied.command_type = "mission.unknown".into();
    let response = call(BridgeRequest::MissionCommand {
        command: denied,
        source_identity: None,
    });
    assert_eq!(response["type"], "mission_command");
    assert_eq!(response["topics"], 1);
    assert_eq!(response["messages"], 1);
    for identity in [" AABB ", "aabb"] {
        let response = call(BridgeRequest::GrantOperationRight {
            subject_type: "identity".into(),
            subject_id: identity.into(),
            operation: "mission.read".into(),
            scope_type: "global".into(),
            scope_id: String::new(),
        });
        assert_eq!(response["type"], "state_updated");
        assert_eq!(response["ok"], true);
    }
    let rights = store
        .load_r3akt_read_snapshot()
        .expect("snapshot")
        .subject_operation_rights;
    assert_eq!(rights.len(), 1);
    assert_eq!(rights[0].subject_id, "aabb");
    assert_eq!(store.row_count("rch_command_results").expect("results"), 1);
    assert_eq!(store.row_count("rch_messages").expect("history"), 1);
    drop(store);
    std::fs::remove_file(path).expect("cleanup");
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

    let output = handle_json_request(&mut core, r#"{"type":"list_subscribers"}"#).expect("list");
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

    let output = handle_json_request(&mut core, r#"{"type":"state_snapshot"}"#).expect("snapshot");
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
    let zone_output = handle_json_request(&mut core, r#"{"type":"list_zones"}"#).expect("zones");
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
fn outbound_auto_send_requests_reticulumd_direct_with_propagation_fallback() {
    let mut client = RecordingReticulumdRpc::default();
    let input = serde_json::json!({
        "type": "outbound_send",
        "message_id": "rch-msg-auto",
        "source": "source-destination",
        "destination": "target-destination",
        "title": "",
        "content": "rem command",
        "fields": { "9": [{ "command_type": "checklist.create.online" }] },
        "method": "auto"
    })
    .to_string();

    handle_outbound_json_request(&mut client, &input).expect("outbound bridge response");

    assert_eq!(client.calls.len(), 1);
    assert_eq!(client.calls[0].method, "send_message_v2");
    assert_eq!(client.calls[0].params["id"], "rch-msg-auto");
    assert_eq!(client.calls[0].params["method"], "direct");
    assert_eq!(client.calls[0].params["try_propagation_on_fail"], true);
}

#[test]
fn outbound_propagated_send_preserves_method_for_reticulumd() {
    let mut client = RecordingReticulumdRpc::default();
    let input = serde_json::json!({
        "type": "outbound_send",
        "message_id": "rch-msg-propagated",
        "source": "source-destination",
        "destination": "target-destination",
        "title": "",
        "content": "relay command",
        "fields": { "9": [{ "command_type": "checklist.create.online" }] },
        "method": "propagated"
    })
    .to_string();

    handle_outbound_json_request(&mut client, &input).expect("outbound bridge response");

    assert_eq!(client.calls.len(), 1);
    assert_eq!(client.calls[0].method, "send_message_v2");
    assert_eq!(client.calls[0].params["id"], "rch-msg-propagated");
    assert_eq!(client.calls[0].params["method"], "propagated");
    assert!(
        client.calls[0]
            .params
            .get("try_propagation_on_fail")
            .is_none()
    );
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
