fn control_reply(operation: &str, payload: &serde_json::Value) -> serde_json::Value {
    serde_json::json!({"response":{"operation_id":operation,"kind":"result","accepted":true,"correlation_id":null,"payload":payload,"extensions":{}}})
}

#[test]
fn sdk_known_path_preserves_daemon_metadata_and_requested_destination() {
    let destination = "00112233445566778899aabbccddeeff";
    let (command, response) = unused_zmq_endpoint_pair();
    let captured = Arc::new(Mutex::new(Vec::new()));
    let metadata = serde_json::json!({"destination":destination,"path_found":true,"known":true,"status":"found","next_hop":"ffeeddccbbaa99887766554433221100","hops":2,"interface":"TCP test"});
    let server = spawn_zmq_sequence_server(command.clone(), vec![
        serde_json::json!({"runtime_id":"routing"}),
        control_reply("rns.transport.path.status", &metadata),
        serde_json::json!({"batch_id":"batch","accepted_count":1,"rejected_count":0,"results":[{"id":"stable-id","message_id":"stable-id","accepted":true}]}),
    ], Arc::clone(&captured));
    let plane = super::ZmqDataPlane::new(command, response).expect("plane");
    assert_eq!(plane.resolve_path(destination).expect("path"), metadata);
    let batch = super::LxmfSdkOutboundBatch { batch_id:"batch".to_string(), source:"source".to_string(), messages:vec![super::LxmfSdkOutboundBatchMessage {
        destination:destination.to_string(),title:"test".to_string(),content:"test".to_string(),fields:serde_json::json!({}),delivery_method:None,stamp_cost:None,include_ticket:None,try_propagation_on_fail:true,correlation_id:"stable-id".to_string(),
    }] };
    assert!(plane.send_batch(batch).expect("batch")[0].accepted);
    server.join().expect("server");
    let calls = captured.lock().expect("calls");
    assert_eq!(calls.len(), 3);
    assert_eq!(calls[1].method, "sdk_envelope_execute_v2");
    assert_eq!(calls[1].params["operation_id"], "rns.transport.path.status");
    assert_eq!(calls[1].params["payload"]["destination"], destination);
    assert_eq!(calls[2].method, "sdk_send_batch_v2");
    assert_eq!(calls[2].params["messages"][0]["destination"], destination);
    assert_eq!(calls[2].params["messages"][0]["id"], "stable-id");
    assert!(calls[2].params["messages"][0]["method"].is_null());
    assert_eq!(calls[2].params["messages"][0]["try_propagation_on_fail"], true);
}

#[test]
fn sdk_missing_path_requests_discovery_without_local_routing_fallback() {
    let destination = "00112233445566778899aabbccddeeff";
    let (command, response) = unused_zmq_endpoint_pair();
    let captured = Arc::new(Mutex::new(Vec::new()));
    let requested = serde_json::json!({"path_found":false,"requested":true,"status":"timeout","destination":destination});
    let server = spawn_zmq_sequence_server(command.clone(), vec![
        serde_json::json!({"runtime_id":"routing"}),
        control_reply("rns.transport.path.status", &serde_json::json!({"path_found":false,"status":"unknown"})),
        control_reply("rns.transport.path.request", &requested),
    ], Arc::clone(&captured));
    let plane = super::ZmqDataPlane::new(command, response).expect("plane");
    assert_eq!(plane.resolve_path(destination).expect("request"), requested);
    server.join().expect("server");
    let calls = captured.lock().expect("calls");
    assert_eq!(calls[2].params["operation_id"], "rns.transport.path.request");
    assert_eq!(calls[2].params["payload"]["destination"], destination);
    assert_eq!(calls[2].params["payload"]["timeout_secs"], 0);
}

#[test]
fn sdk_malformed_path_status_is_visible_and_does_not_request_discovery() {
    let (command, response) = unused_zmq_endpoint_pair();
    let captured = Arc::new(Mutex::new(Vec::new()));
    let server = spawn_zmq_sequence_server(command.clone(), vec![serde_json::json!({"runtime_id":"routing"}),
        control_reply("rns.transport.path.status", &serde_json::json!({"path_found":"yes"})),
    ], Arc::clone(&captured));
    let plane = super::ZmqDataPlane::new(command, response).expect("plane");
    assert!(plane.resolve_path("00112233445566778899aabbccddeeff").expect_err("invalid response").to_string().contains("path_found"));
    server.join().expect("server");
    assert_eq!(captured.lock().expect("calls").len(), 2);
}

#[test]
fn sdk_sync_requires_daemon_selection_and_never_chooses_first_known_node() {
    let (command, response) = unused_zmq_endpoint_pair();
    let captured = Arc::new(Mutex::new(Vec::new()));
    let server = spawn_zmq_sequence_server(command.clone(), vec![serde_json::json!({"runtime_id":"routing"}),
        control_reply("app.propagation.node.get", &serde_json::json!({"peer":null})),
    ], Arc::clone(&captured));
    let plane = super::ZmqDataPlane::new(command, response).expect("plane");
    assert!(plane.sync_selected_propagation_node().expect_err("missing selection").to_string().contains("No propagation node selected"));
    server.join().expect("server");
    let calls = captured.lock().expect("calls");
    assert_eq!(calls.len(), 2);
    assert_eq!(calls[1].params["operation_id"], "app.propagation.node.get");
}

#[test]
fn sdk_sync_preserves_the_daemon_selected_node() {
    let peer = "ffeeddccbbaa99887766554433221100";
    let (command, response) = unused_zmq_endpoint_pair();
    let captured = Arc::new(Mutex::new(Vec::new()));
    let server = spawn_zmq_sequence_server(command.clone(), vec![
        serde_json::json!({"runtime_id":"routing"}),
        control_reply("app.propagation.node.get", &serde_json::json!({"peer":peer})),
        control_reply("app.propagation.peer_sync", &serde_json::json!({"peer":peer,"synced":true})),
        control_reply("app.propagation.remote_fetch", &serde_json::json!({"remote":peer})),
    ], Arc::clone(&captured));
    let plane = super::ZmqDataPlane::new(command, response).expect("plane");
    assert_eq!(plane.sync_selected_propagation_node().expect("sync")["propagation_node"], peer);
    server.join().expect("server");
    let calls = captured.lock().expect("calls");
    assert_eq!(calls.len(), 4);
    assert_eq!(calls[2].params["operation_id"], "app.propagation.peer_sync");
    assert_eq!(calls[2].params["payload"]["peer"], peer);
    assert_eq!(calls[3].params["operation_id"], "app.propagation.remote_fetch");
    assert_eq!(calls[3].params["payload"]["remote"], peer);
}

#[test]
fn malformed_batch_reply_is_an_internal_error_after_submission_without_resend() {
    let (command, response) = unused_zmq_endpoint_pair();
    let captured = Arc::new(Mutex::new(Vec::new()));
    let server = spawn_zmq_sequence_server(command.clone(), vec![
        serde_json::json!({"runtime_id":"routing"}),
        serde_json::json!({"batch_id":"batch"}),
    ], Arc::clone(&captured));
    let plane = super::ZmqDataPlane::new(command, response).expect("plane");
    let batch = super::LxmfSdkOutboundBatch {
        batch_id: "batch".to_string(), source: "source".to_string(),
        messages: vec![super::LxmfSdkOutboundBatchMessage {
            destination: "00112233445566778899aabbccddeeff".to_string(),
            title: "test".to_string(), content: "test".to_string(), fields: serde_json::json!({}),
            delivery_method: None, stamp_cost: None, include_ticket: None,
            try_propagation_on_fail: true, correlation_id: "stable-id".to_string(),
        }],
    };
    assert!(matches!(plane.send_batch(batch), Err(super::TransportError::Sdk {code, ..}) if code == "SDK_INTERNAL_ERROR"));
    server.join().expect("server");
    let calls = captured.lock().expect("calls");
    assert_eq!(calls.len(), 2);
    assert_eq!(calls[1].method, "sdk_send_batch_v2");
    assert_eq!(calls[1].params["messages"][0]["id"], "stable-id");
}

#[test]
fn incomplete_duplicate_and_unknown_batch_results_remain_ambiguous() {
    for ids in [vec![], vec!["first"], vec!["first", "first"], vec!["first", "unknown"]] {
        let (command, response) = unused_zmq_endpoint_pair();
        let captured = Arc::new(Mutex::new(Vec::new()));
        let results = ids.iter().map(|id| serde_json::json!({"id":id,"message_id":id,"accepted":true})).collect::<Vec<_>>();
        let server = spawn_zmq_sequence_server(command.clone(), vec![
            serde_json::json!({"runtime_id":"routing"}),
            serde_json::json!({"batch_id":"batch","accepted_count":results.len(),"rejected_count":0,"results":results}),
        ], Arc::clone(&captured));
        let plane = super::ZmqDataPlane::new(command, response).expect("plane");
        let batch = super::LxmfSdkOutboundBatch {
            batch_id:"batch".to_string(), source:"source".to_string(),
            messages: ["first", "second"].iter().map(|id| super::LxmfSdkOutboundBatchMessage {
                destination: format!("destination-{id}"), title:"test".to_string(), content:"test".to_string(), fields:serde_json::json!({}),
                delivery_method:None, stamp_cost:None, include_ticket:None, try_propagation_on_fail:true, correlation_id:(*id).to_string(),
            }).collect(),
        };
        assert!(matches!(plane.send_batch(batch), Err(super::TransportError::Receive(_))));
        server.join().expect("server");
        assert_eq!(captured.lock().expect("calls").len(), 2);
    }
}
