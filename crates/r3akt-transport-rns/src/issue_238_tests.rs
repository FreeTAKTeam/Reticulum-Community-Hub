#[test]
fn issue_238_event_poll_waits_for_delayed_identity_restoration() {
    let (command, response) = unused_zmq_endpoint_pair_v4();
    let captured = Arc::new(Mutex::new(Vec::new()));
    let negotiation = serde_json::json!({"runtime_id": "recovery-runtime"});
    let identity = serde_json::json!({"identity": {
        "identity": "service-identity", "public_key": "public-key",
        "delivery_destination": "service-destination"
    }});
    let accepted = serde_json::json!({"accepted": true});
    let announced = serde_json::json!({"accepted": true, "identity": "service-identity", "delivery_destination": "service-destination"});
    let server = spawn_zmq_sequence_server_with_delay(command.clone(), vec![
        negotiation.clone(), identity.clone(), accepted.clone(), announced.clone(),
        serde_json::json!({"__rpc_error": {
            "code": "SDK_BROKER_SESSION_REQUIRED", "message": "daemon restarted",
            "machine_code": "SDK_BROKER_SESSION_REQUIRED", "category": "runtime", "retryable": true
        }}),
        negotiation, identity, accepted, announced,
        serde_json::json!({"events": [], "next_cursor": "recovered-cursor", "dropped_count": 0}),
    ], Arc::clone(&captured), Duration::from_millis(300));
    let plane = ZmqDataPlane::new_with_timeout(command, response, Duration::from_millis(400))
        .expect("data plane");
    plane.register_identity(RchServiceIdentityConfig {
        private_key: vec![7; 64], display_name: "RCH".to_string(),
        capabilities: vec!["r3akt".to_string()], metadata: BTreeMap::new(),
    }).expect("register identity");
    plane.poll_events(None, 8).expect_err("restart invalidates session");
    let restored = plane.poll_events(None, 8).expect("poll waits for negotiation and all identity restore RPCs");
    assert_eq!(restored.next_cursor.as_deref(), Some("recovered-cursor"));
    plane.shutdown().expect("shutdown");
    server.join().expect("fixture");
    let methods = captured.lock().expect("methods");
    assert_eq!(methods.iter().filter(|request| request.method == "sdk_identity_import_v2").count(), 2);
    assert_eq!(plane.stats().failed_total, 1);
}

#[test]
fn issue_238_unavailable_daemon_returns_sdk_timeout_and_recovers_same_actor() {
    let (command, response) = unused_zmq_endpoint_pair_v4();
    let plane = ZmqDataPlane::new_with_timeout(command.clone(), response, Duration::from_millis(250))
        .expect("data plane");
    for _ in 0..2 {
        let started = Instant::now();
        let error = plane.poll_events(None, 8).expect_err("daemon absent");
        assert!(matches!(error, TransportError::Sdk {ref code, ..} if code == "SDK_TRANSPORT_ZMQ_TIMEOUT"), "{error:?}");
        assert!(started.elapsed() < Duration::from_secs(1), "connection is bounded");
    }
    let captured = Arc::new(Mutex::new(Vec::new()));
    let server = spawn_zmq_sequence_server(command, vec![
        serde_json::json!({"runtime_id": "recovered-daemon"}),
        serde_json::json!({"events": [], "next_cursor": "recovered-cursor", "dropped_count": 0}),
    ], captured);
    let recovered = plane.poll_events(None, 8).expect("same actor reconnects");
    assert_eq!(recovered.next_cursor.as_deref(), Some("recovered-cursor"));
    plane.shutdown().expect("shutdown");
    server.join().expect("fixture");
}
