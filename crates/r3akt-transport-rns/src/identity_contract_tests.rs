fn identity_contract_bundle() -> serde_json::Value {
    serde_json::json!({"identity": {
        "identity": "rch-identity", "delivery_destination": "rch-destination",
        "public_key": "public-key", "display_name": "RCH"
    }})
}

fn identity_contract_announce() -> serde_json::Value {
    serde_json::json!({"accepted": true, "identity": "rch-identity",
        "delivery_destination": "rch-destination"})
}

fn identity_contract_config() -> RchServiceIdentityConfig {
    RchServiceIdentityConfig {
        private_key: vec![7; 64],
        display_name: "RCH".into(),
        capabilities: vec!["r3akt".into()],
        metadata: BTreeMap::from([("service".into(), serde_json::json!("rch"))]),
    }
}

#[test]
fn registered_announces_bind_sdk_identity_without_reimport_or_activation() {
    let (command, response) = unused_zmq_endpoint_pair_v4();
    let captured = Arc::new(Mutex::new(Vec::new()));
    let server = spawn_zmq_sequence_server(
        command.clone(),
        vec![
            serde_json::json!({"runtime_id": "registered"}),
            identity_contract_bundle(),
            serde_json::json!({"accepted": true}),
            identity_contract_announce(),
            identity_contract_announce(),
            identity_contract_announce(),
        ],
        Arc::clone(&captured),
    );
    let plane = ZmqDataPlane::new(command, response).expect("plane");
    plane
        .register_identity(identity_contract_config())
        .expect("registered");
    for _ in 0..2 {
        assert_eq!(plane.announce_identity().expect("announce"), None);
    }
    plane.shutdown().expect("shutdown");
    server.join().expect("server");
    let requests = captured.lock().expect("requests");
    assert_eq!(requests.len(), 6);
    assert_eq!(
        requests
            .iter()
            .filter(|r| r.method == "sdk_identity_import_v2")
            .count(),
        1
    );
    assert_eq!(
        requests
            .iter()
            .filter(|r| r.method == "sdk_identity_activate_v2")
            .count(),
        1
    );
    for request in &requests[3..] {
        assert_eq!(request.method, "sdk_identity_announce_now_v2");
        assert_eq!(request.params["identity"], "rch-identity");
        assert_eq!(request.params["display_name"], "RCH");
        assert_eq!(request.params["capabilities"], serde_json::json!(["r3akt"]));
        assert_eq!(request.params["metadata"]["service"], "rch");
    }
}

#[test]
fn rejected_activation_prevents_registration_announce() {
    let (command, response) = unused_zmq_endpoint_pair_v4();
    let captured = Arc::new(Mutex::new(Vec::new()));
    let server = spawn_zmq_sequence_server(
        command.clone(),
        vec![
            serde_json::json!({"runtime_id": "rejected"}),
            identity_contract_bundle(),
            serde_json::json!({"accepted": false}),
        ],
        Arc::clone(&captured),
    );
    let plane = ZmqDataPlane::new(command, response).expect("plane");
    let error = plane
        .register_identity(identity_contract_config())
        .expect_err("rejected activation");
    assert!(error.to_string().contains("rejected activation"));
    plane.shutdown().expect("shutdown");
    server.join().expect("server");
    assert_eq!(captured.lock().expect("requests").len(), 3);
}

#[test]
fn incomplete_imported_identity_never_reaches_activation_or_announce() {
    for (field, value) in [
        ("delivery_destination", serde_json::Value::Null),
        ("delivery_destination", serde_json::json!(" ")),
        ("identity", serde_json::json!(" ")),
    ] {
        let (command, response) = unused_zmq_endpoint_pair_v4();
        let captured = Arc::new(Mutex::new(Vec::new()));
        let mut bundle = identity_contract_bundle();
        bundle["identity"][field] = value;
        let server = spawn_zmq_sequence_server(
            command.clone(),
            vec![serde_json::json!({"runtime_id": "incomplete"}), bundle],
            Arc::clone(&captured),
        );
        let plane = ZmqDataPlane::new(command, response).expect("plane");
        let error = plane
            .register_identity(identity_contract_config())
            .expect_err("incomplete import");
        assert!(
            error
                .to_string()
                .contains("without an identity or delivery destination")
        );
        plane.shutdown().expect("shutdown");
        server.join().expect("server");
        assert_eq!(captured.lock().expect("requests").len(), 2);
    }
}

#[test]
fn standalone_announce_preserves_existing_acknowledgement_contract() {
    let (command, response) = unused_zmq_endpoint_pair_v4();
    let captured = Arc::new(Mutex::new(Vec::new()));
    let server = spawn_zmq_sequence_server(
        command.clone(),
        vec![
            serde_json::json!({"runtime_id": "standalone"}),
            serde_json::json!({"accepted": false}),
        ],
        Arc::clone(&captured),
    );
    let plane = ZmqDataPlane::new(command, response).expect("plane");
    assert_eq!(
        plane
            .announce_identity()
            .expect("existing standalone contract"),
        None
    );
    plane.shutdown().expect("shutdown");
    server.join().expect("server");
    let requests = captured.lock().expect("requests");
    assert_eq!(requests[1].params, serde_json::json!({}));
}

#[test]
fn registration_rejects_unaccepted_or_mismatched_announce_binding() {
    for bad in [
        serde_json::json!({"accepted": false, "identity": "rch-identity", "delivery_destination": "rch-destination"}),
        serde_json::json!({"accepted": true, "identity": "default", "delivery_destination": "rch-destination"}),
        serde_json::json!({"accepted": true, "delivery_destination": "rch-destination"}),
        serde_json::json!({"accepted": true, "identity": "rch-identity", "delivery_destination": "default"}),
        serde_json::json!({"accepted": true, "identity": "rch-identity"}),
    ] {
        let (command, response) = unused_zmq_endpoint_pair_v4();
        let captured = Arc::new(Mutex::new(Vec::new()));
        let server = spawn_zmq_sequence_server(
            command.clone(),
            vec![
                serde_json::json!({"runtime_id": "bad-binding"}),
                identity_contract_bundle(),
                serde_json::json!({"accepted": true}),
                bad,
            ],
            captured,
        );
        let plane = ZmqDataPlane::new(command, response).expect("plane");
        let error = plane
            .register_identity(identity_contract_config())
            .expect_err("binding rejected");
        assert!(
            error
                .to_string()
                .contains("registered RCH identity/destination")
        );
        plane.shutdown().expect("shutdown");
        server.join().expect("server");
    }
}

#[test]
fn failed_update_retains_prior_config_and_existing_session() {
    let (command, response) = unused_zmq_endpoint_pair_v4();
    let captured = Arc::new(Mutex::new(Vec::new()));
    let negotiation = serde_json::json!({"runtime_id": "recovered"});
    let accepted = serde_json::json!({"accepted": true});
    let server = spawn_zmq_sequence_server(
        command.clone(),
        vec![
            negotiation.clone(),
            identity_contract_bundle(),
            accepted.clone(),
            identity_contract_announce(),
            identity_contract_bundle(),
            accepted.clone(),
            serde_json::json!({"accepted": false, "identity": "rch-identity", "delivery_destination": "rch-destination"}),
            identity_contract_announce(),
        ],
        Arc::clone(&captured),
    );
    let plane = ZmqDataPlane::new(command, response).expect("plane");
    plane
        .register_identity(identity_contract_config())
        .expect("registered");
    plane
        .update_identity_announce("Unapproved", vec!["changed".into()], BTreeMap::new())
        .expect_err("update rejected");
    plane
        .announce_identity()
        .expect("recovered registered announce");
    plane.shutdown().expect("shutdown");
    server.join().expect("server");
    let requests = captured.lock().expect("requests");
    assert_eq!(requests.len(), 8);
    assert_eq!(requests[0].session_id, requests[7].session_id);
    assert_eq!(requests[4].params["display_name"], "Unapproved");
    assert_eq!(requests[7].method, "sdk_identity_announce_now_v2");
    assert_eq!(requests[7].params["display_name"], "RCH");
}

#[test]
fn registered_later_announce_rejects_wrong_destination() {
    let (command, response) = unused_zmq_endpoint_pair_v4();
    let captured = Arc::new(Mutex::new(Vec::new()));
    let server = spawn_zmq_sequence_server(
        command.clone(),
        vec![
            serde_json::json!({"runtime_id": "wrong-later"}),
            identity_contract_bundle(),
            serde_json::json!({"accepted": true}),
            identity_contract_announce(),
            serde_json::json!({"accepted": true, "identity": "rch-identity", "delivery_destination": "default"}),
        ],
        captured,
    );
    let plane = ZmqDataPlane::new(command, response).expect("plane");
    plane
        .register_identity(identity_contract_config())
        .expect("registered");
    plane
        .announce_identity()
        .expect_err("wrong later destination");
    plane.shutdown().expect("shutdown");
    server.join().expect("server");
}
