use crate::*;
use rns_rpc::rpc::{RpcRequest, RpcResponse, codec, zmq};
use zeromq::{PullSocket, PushSocket, Socket, SocketRecv, SocketSend, ZmqMessage};

struct StatusServer {
    command: String,
    response: String,
    requests: Arc<Mutex<Vec<RpcRequest>>>,
    stop: Option<tokio::sync::oneshot::Sender<()>>,
    thread: Option<std::thread::JoinHandle<()>>,
}

impl StatusServer {
    fn new(reply: impl Fn(&RpcRequest) -> Value + Send + 'static) -> Self {
        let response = std::net::TcpListener::bind("127.0.0.1:0").expect("response port");
        let response_endpoint = format!("tcp://{}", response.local_addr().expect("address"));
        drop(response);
        let requests = Arc::new(Mutex::new(Vec::new()));
        let captured = Arc::clone(&requests);
        let (ready, endpoint) = std::sync::mpsc::channel();
        let (stop, mut stopped) = tokio::sync::oneshot::channel();
        let thread = std::thread::spawn(move || {
            tokio::runtime::Runtime::new()
                .expect("runtime")
                .block_on(async move {
                    let mut commands = PullSocket::new();
                    let endpoint = commands.bind("tcp://127.0.0.1:0").await.expect("bind");
                    ready.send(endpoint.to_string()).expect("ready");
                    loop {
                        let message = tokio::select! {
                            _ = &mut stopped => break,
                            message = commands.recv() => message.expect("request"),
                        };
                        let bytes = Vec::<u8>::try_from(message).expect("single frame");
                        let envelope = zmq::decode_envelope(&bytes).expect("envelope");
                        let request: RpcRequest =
                            codec::decode_frame(&envelope.payload).expect("RPC");
                        let result = if request.method == "sdk_negotiate_v2" {
                            negotiation(&request)
                        } else {
                            reply(&request)
                        };
                        captured.lock().expect("capture").push(request);
                        let rpc = RpcResponse {
                            id: envelope.request_id,
                            error: result
                                .get("__rpc_error")
                                .map(|error| serde_json::from_value(error.clone()).expect("error")),
                            result: result.get("__rpc_error").is_none().then_some(result),
                        };
                        let response = zmq::ZmqRpcEnvelope::response(
                            envelope.session_id,
                            envelope.request_id,
                            codec::encode_frame(&rpc).expect("response frame"),
                        );
                        tokio::time::timeout(Duration::from_secs(2), async {
                            let mut socket = PushSocket::new();
                            socket
                                .connect(envelope.response_endpoint.as_deref().expect("endpoint"))
                                .await
                                .expect("connect");
                            tokio::time::sleep(Duration::from_millis(20)).await;
                            socket
                                .send(ZmqMessage::from(
                                    zmq::encode_envelope(&response).expect("response envelope"),
                                ))
                                .await
                                .expect("send");
                        })
                        .await
                        .expect("bounded response");
                    }
                });
        });
        Self {
            command: endpoint
                .recv_timeout(Duration::from_secs(3))
                .expect("server ready"),
            response: response_endpoint,
            requests,
            stop: Some(stop),
            thread: Some(thread),
        }
    }

    fn plane(&self) -> ZmqDataPlane {
        ZmqDataPlane::new_with_timeout(
            self.command.clone(),
            self.response.clone(),
            Duration::from_secs(2),
        )
        .expect("SDK actor")
    }

    fn status_ids(&self) -> Vec<String> {
        self.requests
            .lock()
            .expect("requests")
            .iter()
            .filter(|request| request.method == "sdk_status_v2")
            .map(|request| {
                request.params.as_ref().expect("params")["message_id"]
                    .as_str()
                    .expect("ID")
                    .to_string()
            })
            .collect()
    }
}

impl Drop for StatusServer {
    fn drop(&mut self) {
        if let Some(stop) = self.stop.take() {
            // The receiver may already have exited after a test failure.
            let _ = stop.send(());
        }
        if let Some(thread) = self.thread.take() {
            let result = thread.join();
            if !std::thread::panicking() {
                result.expect("server joined");
            }
        }
    }
}

fn negotiation(request: &RpcRequest) -> Value {
    let mut capabilities =
        request.params.as_ref().expect("negotiate params")["requested_capabilities"]
            .as_array()
            .expect("requested capabilities")
            .clone();
    // Desktop-local profile requirements are negotiated in addition to the
    // application's explicitly requested optional capabilities.
    for required in [
        "sdk.capability.cursor_replay",
        "sdk.capability.receipt_terminality",
        "sdk.capability.config_revision_cas",
        "sdk.capability.idempotency_ttl",
    ] {
        capabilities.push(json!(required));
    }
    json!({
        "runtime_id": "receipt-contract", "active_contract_version": 2,
        "effective_capabilities": capabilities,
        "effective_limits": {"max_poll_events":256,"max_event_bytes":1_048_576,
            "max_batch_bytes":16_777_216,"max_extension_keys":64,"idempotency_ttl_ms":86_400_000},
        "contract_release":"v2.5","schema_namespace":"v2","sdk_version":"0.13.0"
    })
}

fn pending_message(state: &AppState, targets: &[&str]) -> OutboundMessageRecord {
    let message = record_outbound_message_deferred_with_metadata(
        state,
        "receipt contract",
        None,
        Some("destination".to_string()),
        Vec::new(),
        false,
        json!({}),
    )
    .expect("parent");
    let mut report = DispatchReport::default();
    record_zmq_batch_results(
        &mut report,
        targets
            .iter()
            .map(|id| LxmfSdkOutboundBatchResult {
                id: format!("correlation-{id}"),
                message_id: (*id).to_string(),
                destination: format!("destination-{id}"),
                accepted: true,
                error: None,
            })
            .collect(),
    );
    update_outbound_delivery_state(
        state,
        &message.message_id,
        "sent",
        json!({
            "dispatch_status":"accepted","reticulumd_dispatch_count":report.count,
            "reticulumd_receipt_targets":reticulumd_receipt_targets_json(&report.receipts),
            "receipt_pending":true
        }),
    )
    .expect("persist SDK admission");
    message
}

#[test]
fn sdk_receipt_poll_uses_only_the_admitted_opaque_id_and_commits_terminal_state() {
    for id in ["Opaque-SDK-id42", "sdk-Already-Prefixed42"] {
        let server = StatusServer::new(move |request| {
            assert_eq!(request.method, "sdk_status_v2");
            // An invented alias has no row in the daemon, as in populated attempt 8.
            let found = request.params.as_ref().expect("params")["message_id"] == id;
            json!({"message": found.then(|| json!({"id":id,"receipt_status":"delivered","timestamp":1,"attempts":1}))})
        });
        let directory = std::env::temp_dir().join(format!("rch-exact-receipt-{}", Uuid::new_v4()));
        std::fs::create_dir(&directory).expect("directory");
        let mut state = AppState::from_sqlite_path(directory.join("state.db")).expect("state");
        let parent = pending_message(&state, &[id]);
        assert_ne!(parent.message_id, id);
        state.lxmf_zmq_data_plane = Some(Arc::new(server.plane()));
        poll_reticulumd_delivery_receipts(&state).expect("poll");
        assert_eq!(server.status_ids(), [id]);
        let current = message_persistence::current(&state, &parent.message_id).expect("projection");
        assert_eq!(current.delivery_state, "delivered");
        assert_eq!(current.delivery_metadata["sdk_message_id"], id);
        assert_eq!(current.delivery_metadata["sdk_terminal"], true);
        assert_eq!(current.delivery_metadata["receipt_pending"], false);
        state
            .lxmf_zmq_data_plane
            .as_ref()
            .expect("plane")
            .shutdown()
            .expect("shutdown");
        drop(state);
        let reopened = AppState::from_sqlite_path(directory.join("state.db")).expect("reopen");
        let durable = message_persistence::current(&reopened, &parent.message_id).expect("durable");
        assert_eq!(durable.delivery_state, "delivered");
        assert_eq!(
            durable.delivery_metadata["reticulumd_receipt_targets"][0]["message_id"],
            id
        );
        drop(reopened);
        std::fs::remove_dir_all(directory).expect("cleanup");
    }
}

#[test]
fn sdk_receipt_not_found_spends_one_call_without_alias_retry() {
    let server = StatusServer::new(|_| json!({"message":null}));
    let plane = server.plane();
    let mut budget = RETICULUMD_RECEIPT_STATUS_RPC_BUDGET_PER_PASS;
    assert!(matches!(
        zmq_delivery_status(&plane, "Missing-Opaque42", &mut budget),
        ReticulumdStatusPollResult::NotFound
    ));
    assert_eq!(budget, RETICULUMD_RECEIPT_STATUS_RPC_BUDGET_PER_PASS - 1);
    assert_eq!(server.status_ids(), ["Missing-Opaque42"]);
    budget = 0;
    assert!(matches!(
        zmq_delivery_status(&plane, "no-budget", &mut budget),
        ReticulumdStatusPollResult::Stopped { error: None }
    ));
    assert_eq!(server.status_ids(), ["Missing-Opaque42"]);
    plane.shutdown().expect("shutdown");
}

#[test]
fn sdk_receipt_error_stops_the_pass_and_preserves_pending_with_diagnostics() {
    let server = StatusServer::new(|_| {
        json!({"__rpc_error":{
            "code":"SDK_RUNTIME_NOT_READY","message":"fixture unavailable"
        }})
    });
    let mut state = AppState::default();
    let parent = pending_message(&state, &["Opaque-error42", "unpolled42"]);
    state.lxmf_zmq_data_plane = Some(Arc::new(server.plane()));
    poll_reticulumd_delivery_receipts(&state).expect("observable reconciliation failure");
    assert_eq!(server.status_ids(), ["Opaque-error42"]);
    let current = message_persistence::current(&state, &parent.message_id).expect("current");
    assert_eq!(current.delivery_state, "sent");
    assert_eq!(current.delivery_metadata["receipt_pending"], true);
    assert!(
        current.delivery_metadata["sdk_reconciliation_error"]
            .as_str()
            .expect("diagnostic")
            .contains("fixture unavailable")
    );
    state
        .lxmf_zmq_data_plane
        .as_ref()
        .expect("plane")
        .shutdown()
        .expect("shutdown");
}

#[test]
fn sdk_receipt_more_than_four_opaque_targets_respects_the_original_budget() {
    let server = StatusServer::new(|_| json!({"message":null}));
    let mut state = AppState::default();
    let ids = ["opaque-0", "opaque-1", "opaque-2", "opaque-3", "opaque-4"];
    pending_message(&state, &ids);
    state.lxmf_zmq_data_plane = Some(Arc::new(server.plane()));
    poll_reticulumd_delivery_receipts(&state).expect("poll");
    assert_eq!(
        server.status_ids(),
        ids[..RETICULUMD_RECEIPT_STATUS_RPC_BUDGET_PER_PASS]
    );
    state
        .lxmf_zmq_data_plane
        .as_ref()
        .expect("plane")
        .shutdown()
        .expect("shutdown");
}
