use super::*;

#[test]
fn inbound_plain_lxmf_chat_is_sanitized_and_capped_before_fanout() {
    let state = durable_inbound_test_state(&temp_db(), "hub-source");
    let source = "77b2539b72259af927e48c0f90721767";
    let peer = "4bede2a6ecab26f234aac9bb894a441a";
    for identity in [source, peer] {
        seed_client(&state, identity, crate::unix_now_ms());
    }
    let topic = r3akt_protocol::Topic::new("direct");
    let clean_envelope = r3akt_protocol::ProtocolEnvelope::new(
        r3akt_protocol::NodeId::new(source),
        r3akt_protocol::Destination::Topic(topic.clone()),
        topic.clone(),
        r3akt_protocol::Payload::TopicMessage(r3akt_protocol::TopicMessage {
            body: " hello\u{001b}[31m ".to_string(),
            content_type: "text/plain".to_string(),
            correlation_id: None,
            attachments: Vec::new(),
        }),
    );
    apply_envelope(&state, &clean_envelope);

    let oversized = "x".repeat(crate::GROUP_CHAT_INBOUND_TEXT_MAX_CHARS + 1);
    let oversized_envelope = r3akt_protocol::ProtocolEnvelope::new(
        r3akt_protocol::NodeId::new(source),
        r3akt_protocol::Destination::Topic(topic.clone()),
        topic,
        r3akt_protocol::Payload::TopicMessage(r3akt_protocol::TopicMessage {
            body: oversized,
            content_type: "text/plain".to_string(),
            correlation_id: None,
            attachments: Vec::new(),
        }),
    );
    apply_envelope(&state, &oversized_envelope);

    let requests = pending_broker_requests(&state_db(&state));
    assert_eq!(requests[0]["destination"], peer);
    assert_eq!(requests[0]["content"], "77b2539b > hello?[31m");
    assert_eq!(requests[1]["destination"], source);
    assert!(
        requests[1]["content"]
            .as_str()
            .expect("reply")
            .contains("500 characters")
    );
    let canonical_inbound_messages = state
        .messages
        .read()
        .expect("messages")
        .iter()
        .filter(|message| {
            message
                .delivery_metadata
                .get("reticulumd_inbound")
                .and_then(Value::as_bool)
                .unwrap_or(false)
        })
        .map(|message| message.content.clone())
        .collect::<Vec<_>>();
    assert_eq!(canonical_inbound_messages, vec!["hello?[31m".to_string()]);
    let oversized_stored = state
        .messages
        .read()
        .expect("messages")
        .iter()
        .any(|message| message.content.len() > crate::GROUP_CHAT_INBOUND_TEXT_MAX_CHARS);
    assert!(!oversized_stored);
}

#[test]
fn inbound_plain_lxmf_chat_updates_last_chat_timestamp() {
    let state = durable_inbound_test_state(&temp_db(), "hub-source");
    let source = "77b2539b72259af927e48c0f90721767";
    let topic = r3akt_protocol::Topic::new("direct");
    let envelope = r3akt_protocol::ProtocolEnvelope::new(
        r3akt_protocol::NodeId::new(source),
        r3akt_protocol::Destination::Topic(topic.clone()),
        topic,
        r3akt_protocol::Payload::TopicMessage(r3akt_protocol::TopicMessage {
            body: "hello from lxmf".to_string(),
            content_type: "text/plain".to_string(),
            correlation_id: None,
            attachments: Vec::new(),
        }),
    );

    apply_envelope(&state, &envelope);

    let client = state
        .clients
        .read()
        .expect("clients")
        .get(source)
        .cloned()
        .expect("client");
    assert!(client.last_chat_ts_ms.is_some());
    assert!(
        crate::unix_ms_from_iso8601(&client.last_seen).is_some_and(|last_seen| {
            client
                .last_chat_ts_ms
                .is_some_and(|last_chat| last_seen >= last_chat)
        })
    );
}

#[tokio::test]
async fn message_stream_receives_reticulumd_inbound_topic_messages() {
    let envelope = r3akt_protocol::ProtocolEnvelope::new(
        r3akt_protocol::NodeId::new("peer-ws"),
        r3akt_protocol::Destination::Topic(r3akt_protocol::Topic::new("ops")),
        r3akt_protocol::Topic::new("ops"),
        r3akt_protocol::Payload::TopicMessage(r3akt_protocol::TopicMessage {
            body: "Inbound WS".to_string(),
            content_type: "text/plain".to_string(),
            correlation_id: Some("ws-corr-1".to_string()),
            attachments: Vec::new(),
        }),
    );
    let payload_b64 = BASE64_STANDARD.encode(envelope.encode_msgpack().expect("msgpack"));
    let db_path = std::env::temp_dir().join(format!("r3akt-reticulumd-ws-{}.db", Uuid::new_v4()));
    let state = crate::AppState::from_sqlite_path(&db_path)
        .expect("state")
        .with_api_key("secret")
        .with_test_reticulumd_source("local-destination");
    let mut state = state;
    state.enable_durable_consumer().expect("durable consumer");
    let listener = TcpListener::bind("127.0.0.1:0").await.expect("bind");
    let addr = listener.local_addr().expect("addr");
    let server_state = state.clone();
    let server = tokio::spawn(async move {
        axum::serve(listener, crate::create_app_with_state(server_state))
            .await
            .expect("server");
    });
    let (mut socket, _) = connect_async(format!("ws://{addr}/messages/stream"))
        .await
        .expect("websocket connect");
    socket
        .send(Message::Text(
            json!({"type":"auth","data":{"api_key":"secret"}})
                .to_string()
                .into(),
        ))
        .await
        .expect("send auth");
    let auth_reply = socket
        .next()
        .await
        .expect("auth frame")
        .expect("auth reply");
    assert_eq!(
        serde_json::from_str::<serde_json::Value>(auth_reply.to_text().expect("auth text"))
            .expect("auth json")["type"],
        "auth.ok"
    );
    socket
        .send(Message::Text(
            json!({"type":"message.subscribe","data":{"topic_id":"ops","follow":true}})
                .to_string()
                .into(),
        ))
        .await
        .expect("send subscribe");
    let subscribed = socket
        .next()
        .await
        .expect("subscribed frame")
        .expect("subscribed reply");
    assert_eq!(
        serde_json::from_str::<serde_json::Value>(subscribed.to_text().expect("subscribed text"))
            .expect("subscribed json")["type"],
        "message.subscribed"
    );

    apply_daemon_messages(
        &state,
        json!([{
            "id": "lxmf-inbound-ws-1",
            "destination": "local-destination",
            "fields": {
                "r3akt_payload_b64": payload_b64
            }
        }]),
    );
    let receive_reply = tokio::time::timeout(Duration::from_secs(2), socket.next())
        .await
        .expect("receive timeout")
        .expect("receive frame")
        .expect("receive reply");
    let receive_payload: serde_json::Value =
        serde_json::from_str(receive_reply.to_text().expect("receive text")).expect("receive json");
    assert_eq!(receive_payload["type"], "message.receive");
    assert_eq!(receive_payload["data"]["entry"]["Direction"], "inbound");
    assert_eq!(receive_payload["data"]["entry"]["Content"], "Inbound WS");
    assert_eq!(receive_payload["data"]["entry"]["Source"], "peer-ws");
    assert_eq!(receive_payload["data"]["entry"]["TopicID"], "ops");
    drop(socket);
    server.abort();
    std::fs::remove_file(db_path).expect("cleanup db");
}

#[tokio::test]
async fn reticulumd_inbound_direct_topic_keeps_all_subscribers_independent_of_announce_freshness() {
    let source = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    let fresh_subscriber = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    let stale_subscriber = "cccccccccccccccccccccccccccccccc";
    let unrelated_active = "dddddddddddddddddddddddddddddddd";
    let envelope = r3akt_protocol::ProtocolEnvelope::new(
        r3akt_protocol::NodeId::new(source),
        r3akt_protocol::Destination::Topic(r3akt_protocol::Topic::new("direct")),
        r3akt_protocol::Topic::new("direct"),
        r3akt_protocol::Payload::TopicMessage(r3akt_protocol::TopicMessage {
            body: "phone to fresh subscriber".to_string(),
            content_type: "text/plain".to_string(),
            correlation_id: Some("direct-relay-fresh-sub-1".to_string()),
            attachments: Vec::new(),
        }),
    );
    let payload_b64 = BASE64_STANDARD.encode(envelope.encode_msgpack().expect("msgpack"));
    let db_path = std::env::temp_dir().join(format!(
        "r3akt-reticulumd-inbound-direct-fresh-sub-{}.db",
        Uuid::new_v4()
    ));
    let mut store = RchSqliteStore::open(&db_path).expect("sqlite");
    let now = crate::unix_now_ms();
    let mut snapshot = r3akt_rch_core::RchCore::new().snapshot();
    snapshot.subscribers = vec![
        r3akt_rch_core::SubscriberRecord {
            subscriber_id: None,
            node_id: stale_subscriber.to_string(),
            topic_id: "direct".to_string(),
            reject_tests: None,
            metadata: json!({ "source": "old_phone_hil" }),
            first_seen_ts_ms: now - r3akt_rch_core::RECENT_ANNOUNCE_WINDOW_MS - 10_000,
            last_seen_ts_ms: now - r3akt_rch_core::RECENT_ANNOUNCE_WINDOW_MS - 10_000,
        },
        r3akt_rch_core::SubscriberRecord {
            subscriber_id: None,
            node_id: fresh_subscriber.to_string(),
            topic_id: "direct".to_string(),
            reject_tests: None,
            metadata: json!({ "source": "sideband_hil" }),
            first_seen_ts_ms: now,
            last_seen_ts_ms: now,
        },
    ];
    snapshot.identity_announces = vec![
        r3akt_rch_core::IdentityAnnounceRecord {
            destination_hash: stale_subscriber.to_string(),
            announced_identity_hash: None,
            display_name: Some("stale phone".to_string()),
            source_interface: Some("reticulumd".to_string()),
            announce_capabilities: Vec::new(),
            client_type: "generic_lxmf".to_string(),
            first_seen_ts_ms: now - r3akt_rch_core::RECENT_ANNOUNCE_WINDOW_MS - 10_000,
            last_seen_ts_ms: now - r3akt_rch_core::RECENT_ANNOUNCE_WINDOW_MS - 10_000,
        },
        r3akt_rch_core::IdentityAnnounceRecord {
            destination_hash: fresh_subscriber.to_string(),
            announced_identity_hash: None,
            display_name: Some("fresh phone".to_string()),
            source_interface: Some("reticulumd".to_string()),
            announce_capabilities: Vec::new(),
            client_type: "generic_lxmf".to_string(),
            first_seen_ts_ms: now,
            last_seen_ts_ms: now,
        },
    ];
    store.save_snapshot(&snapshot).expect("save snapshot");
    drop(store);

    let state = crate::AppState::from_sqlite_path(&db_path)
        .expect("state")
        .with_test_reticulumd_source("local-destination");

    let mut state = state;

    state.enable_durable_consumer().expect("durable consumer");
    seed_client(&state, unrelated_active, now);

    apply_daemon_messages(
        &state,
        json!([{
            "id": "lxmf-inbound-direct-fresh-sub-1",
            "destination": "local-destination",
            "fields": {
                "r3akt_payload_b64": payload_b64
            }
        }]),
    );

    let requests = pending_broker_requests(&state_db(&state));
    let destinations = requests[..]
        .iter()
        .map(|request| request["destination"].as_str().expect("destination"))
        .collect::<Vec<_>>();
    assert!(destinations.contains(&fresh_subscriber));
    assert!(destinations.contains(&stale_subscriber));
    assert!(!destinations.contains(&unrelated_active));

    assert_eq!(destinations.len(), 2);

    std::fs::remove_file(db_path).expect("cleanup db");
}

#[tokio::test]
async fn reticulumd_inbound_direct_topic_preserves_subscriber_despite_stale_announce() {
    let envelope = r3akt_protocol::ProtocolEnvelope::new(
        r3akt_protocol::NodeId::new("peer-alpha"),
        r3akt_protocol::Destination::Topic(r3akt_protocol::Topic::new("direct")),
        r3akt_protocol::Topic::new("direct"),
        r3akt_protocol::Payload::TopicMessage(r3akt_protocol::TopicMessage {
            body: "phone to active phone".to_string(),
            content_type: "text/plain".to_string(),
            correlation_id: Some("direct-relay-active-1".to_string()),
            attachments: Vec::new(),
        }),
    );
    let payload_b64 = BASE64_STANDARD.encode(envelope.encode_msgpack().expect("msgpack"));
    let db_path = std::env::temp_dir().join(format!(
        "r3akt-reticulumd-inbound-direct-active-relay-{}.db",
        Uuid::new_v4()
    ));
    let mut store = RchSqliteStore::open(&db_path).expect("sqlite");
    let now = crate::unix_now_ms();
    let mut snapshot = r3akt_rch_core::RchCore::new().snapshot();
    snapshot.subscribers = vec![r3akt_rch_core::SubscriberRecord {
        subscriber_id: None,
        node_id: "peer-stale".to_string(),
        topic_id: "direct".to_string(),
        reject_tests: None,
        metadata: json!({ "source": "old_phone_hil" }),
        first_seen_ts_ms: now - r3akt_rch_core::RECENT_ANNOUNCE_WINDOW_MS - 10_000,
        last_seen_ts_ms: now - r3akt_rch_core::RECENT_ANNOUNCE_WINDOW_MS - 10_000,
    }];
    snapshot.identity_announces = vec![r3akt_rch_core::IdentityAnnounceRecord {
        destination_hash: "peer-stale".to_string(),
        announced_identity_hash: None,
        display_name: Some("stale phone".to_string()),
        source_interface: Some("reticulumd".to_string()),
        announce_capabilities: Vec::new(),
        client_type: "generic_lxmf".to_string(),
        first_seen_ts_ms: now - r3akt_rch_core::RECENT_ANNOUNCE_WINDOW_MS - 10_000,
        last_seen_ts_ms: now - r3akt_rch_core::RECENT_ANNOUNCE_WINDOW_MS - 10_000,
    }];
    store.save_snapshot(&snapshot).expect("save snapshot");
    drop(store);

    let state = crate::AppState::from_sqlite_path(&db_path)
        .expect("state")
        .with_test_reticulumd_source("local-destination");

    let mut state = state;

    state.enable_durable_consumer().expect("durable consumer");
    seed_client(&state, "peer-bravo", now);

    apply_daemon_messages(
        &state,
        json!([{
            "id": "lxmf-inbound-direct-active-relay-1",
            "destination": "local-destination",
            "fields": {
                "r3akt_payload_b64": payload_b64
            }
        }]),
    );
    let requests = pending_broker_requests(&state_db(&state));
    let params = &requests[0];
    assert_eq!(params["destination"], "peer-stale");
    assert_ne!(params["destination"], "peer-bravo");

    let destinations = requests
        .iter()
        .map(|request| request["destination"].as_str().expect("destination"))
        .collect::<Vec<_>>();
    // An explicit subscriber is relayed to even when its announce is stale.
    assert_eq!(destinations, ["peer-stale"]);

    std::fs::remove_file(db_path).expect("cleanup db");
}

#[tokio::test]
async fn reticulumd_inbound_direct_topic_relays_to_active_generic_lxmf_clients() {
    let envelope = r3akt_protocol::ProtocolEnvelope::new(
        r3akt_protocol::NodeId::new("peer-alpha"),
        r3akt_protocol::Destination::Topic(r3akt_protocol::Topic::new("direct")),
        r3akt_protocol::Topic::new("direct"),
        r3akt_protocol::Payload::TopicMessage(r3akt_protocol::TopicMessage {
            body: "phone to phone".to_string(),
            content_type: "text/plain".to_string(),
            correlation_id: Some("direct-relay-corr-1".to_string()),
            attachments: Vec::new(),
        }),
    );
    let payload_b64 = BASE64_STANDARD.encode(envelope.encode_msgpack().expect("msgpack"));
    let db_path = std::env::temp_dir().join(format!(
        "r3akt-reticulumd-inbound-direct-relay-{}.db",
        Uuid::new_v4()
    ));
    let state = crate::AppState::from_sqlite_path(&db_path)
        .expect("state")
        .with_test_reticulumd_source("local-destination");
    let mut state = state;
    state.enable_durable_consumer().expect("durable consumer");
    let now = crate::unix_now_ms();
    seed_named_client(&state, "peer-alpha", Some("Alpha_1"), now);
    seed_client(&state, "peer-bravo", now);
    seed_client(
        &state,
        "peer-stale",
        now - r3akt_rch_core::RECENT_RUNTIME_PRESENCE_WINDOW_MS - 1_000,
    );

    apply_daemon_messages(
        &state,
        json!([{
            "id": "lxmf-inbound-direct-relay-1",
            "destination": "local-destination",
            "fields": {
                "r3akt_payload_b64": payload_b64
            }
        }]),
    );
    let requests = pending_broker_requests(&state_db(&state));
    let params = &requests[0];
    assert_eq!(params["destination"], "peer-bravo");
    assert_eq!(params["content"], "Alpha_1 > phone to phone");

    let destinations = requests
        .iter()
        .map(|request| request["destination"].as_str().expect("destination"))
        .collect::<Vec<_>>();
    // Default direct recipients: active roster clients, excluding the sender
    // and clients outside the activity window.
    assert_eq!(destinations, ["peer-bravo"]);

    std::fs::remove_file(db_path).expect("cleanup db");
}

#[tokio::test]
async fn reticulumd_inbound_topic_message_relays_to_other_subscribers() {
    let envelope = r3akt_protocol::ProtocolEnvelope::new(
        r3akt_protocol::NodeId::new("a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1"),
        r3akt_protocol::Destination::Topic(r3akt_protocol::Topic::new("ops")),
        r3akt_protocol::Topic::new("ops"),
        r3akt_protocol::Payload::TopicMessage(r3akt_protocol::TopicMessage {
            body: "Relay this".to_string(),
            content_type: "text/plain".to_string(),
            correlation_id: Some("relay-corr-1".to_string()),
            attachments: Vec::new(),
        }),
    );
    let payload_b64 = BASE64_STANDARD.encode(envelope.encode_msgpack().expect("msgpack"));
    let db_path = std::env::temp_dir().join(format!(
        "r3akt-reticulumd-inbound-relay-{}.db",
        Uuid::new_v4()
    ));
    let state = crate::AppState::from_sqlite_path(&db_path)
        .expect("state")
        .with_api_key("secret")
        .with_test_reticulumd_source("local-destination");
    let mut state = state;
    state.enable_durable_consumer().expect("durable consumer");
    let app = crate::create_app_with_state(state.clone());
    let topic_response = app
        .clone()
        .oneshot(
            Request::builder()
                .header("X-API-Key", "secret")
                .method(Method::POST)
                .uri("/Topic")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "TopicID": "ops",
                        "TopicName": "Operations",
                        "TopicPath": "ops"
                    })
                    .to_string(),
                ))
                .expect("topic request"),
        )
        .await
        .expect("topic response");
    assert_eq!(topic_response.status(), StatusCode::OK);
    for destination in [
        "a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1",
        "c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3",
    ] {
        let subscriber = app
            .clone()
            .oneshot(
                Request::builder()
                    .header("X-API-Key", "secret")
                    .method(Method::POST)
                    .uri("/Subscriber/Add")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "Destination": destination,
                            "TopicID": "ops"
                        })
                        .to_string(),
                    ))
                    .expect("subscriber request"),
            )
            .await
            .expect("subscriber response");
        assert_eq!(subscriber.status(), StatusCode::OK);
    }
    let now = crate::unix_now_ms();
    crate::persist_identity_announce_records(
        &state,
        &[
            r3akt_rch_core::IdentityAnnounceRecord {
                destination_hash: "a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1".to_string(),
                announced_identity_hash: None,
                display_name: Some("peer alpha".to_string()),
                source_interface: Some("reticulumd".to_string()),
                announce_capabilities: Vec::new(),
                client_type: "generic_lxmf".to_string(),
                first_seen_ts_ms: now,
                last_seen_ts_ms: now,
            },
            r3akt_rch_core::IdentityAnnounceRecord {
                destination_hash: "c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3".to_string(),
                announced_identity_hash: None,
                display_name: Some("peer charlie".to_string()),
                source_interface: Some("reticulumd".to_string()),
                announce_capabilities: Vec::new(),
                client_type: "generic_lxmf".to_string(),
                first_seen_ts_ms: now,
                last_seen_ts_ms: now,
            },
        ],
    )
    .expect("persist fresh relay announce");

    apply_daemon_messages(
        &state,
        json!([{
            "id": "lxmf-inbound-relay-1",
            "destination": "local-destination",
            "fields": {
                "r3akt_payload_b64": payload_b64
            }
        }]),
    );
    let requests = pending_broker_requests(&state_db(&state));
    let params = &requests[0];
    assert_eq!(params["destination"], "c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3");
    assert_eq!(params["content"], "peer alpha > Relay this");
    assert!(params.get("method").is_none());
    let outbound_response = app
        .oneshot(
            Request::builder()
                .header("X-API-Key", "secret")
                .method(Method::GET)
                .uri("/Chat/Messages?direction=outbound")
                .body(Body::empty())
                .expect("outbound request"),
        )
        .await
        .expect("outbound response");
    assert_eq!(outbound_response.status(), StatusCode::OK);
    let outbound_body = outbound_response
        .into_body()
        .collect()
        .await
        .expect("outbound body")
        .to_bytes();
    let outbound: serde_json::Value =
        serde_json::from_slice(&outbound_body).expect("outbound json");
    assert_eq!(outbound[0]["Direction"], "outbound");
    assert_eq!(outbound[0]["Content"], "peer alpha > Relay this");
    std::fs::remove_file(db_path).expect("cleanup db");
}

#[tokio::test]
async fn reticulumd_inbound_worker_records_topic_envelope_event() {
    let envelope = r3akt_protocol::ProtocolEnvelope::new(
        r3akt_protocol::NodeId::new("peer-alpha"),
        r3akt_protocol::Destination::Topic(r3akt_protocol::Topic::new("ops")),
        r3akt_protocol::Topic::new("ops"),
        r3akt_protocol::Payload::TopicMessage(r3akt_protocol::TopicMessage {
            body: "Inbound from Rust transport".to_string(),
            content_type: "text/plain".to_string(),
            correlation_id: Some("corr-1".to_string()),
            attachments: Vec::new(),
        }),
    )
    .with_dedupe_key("dedupe-1");
    let payload_b64 = BASE64_STANDARD.encode(envelope.encode_msgpack().expect("msgpack"));
    let db_path =
        std::env::temp_dir().join(format!("r3akt-reticulumd-inbound-{}.db", Uuid::new_v4()));
    let state = crate::AppState::from_sqlite_path(&db_path)
        .expect("state")
        .with_api_key("secret")
        .with_test_reticulumd_source("local-destination");
    let mut state = state;
    state.enable_durable_consumer().expect("durable consumer");
    let app = crate::create_app_with_state(state.clone());

    apply_daemon_messages(
        &state,
        json!([{
            "id": "lxmf-inbound-1",
            "destination": "local-destination",
            "fields": {
                "r3akt_payload_b64": payload_b64
            }
        }]),
    );
    {
        let events = state.system_events.read().expect("events");
        let event = events
            .iter()
            .find(|event| event.event_type == "message_received")
            .expect("inbound event");
        assert_eq!(event.message, "Message received from peer-alp");
        assert_eq!(event.metadata["source"], "peer-alpha");
        assert_eq!(event.metadata["topic"], "ops");
        assert_eq!(event.metadata["dedupe_key"], "dedupe-1");
        assert_eq!(event.metadata["correlation_id"], "corr-1");
    }
    let chat_response = app
        .oneshot(
            Request::builder()
                .header("X-API-Key", "secret")
                .method(Method::GET)
                .uri("/Chat/Messages?direction=inbound")
                .body(Body::empty())
                .expect("request"),
        )
        .await
        .expect("chat response");
    assert_eq!(chat_response.status(), StatusCode::OK);
    let chat_body = chat_response
        .into_body()
        .collect()
        .await
        .expect("body")
        .to_bytes();
    let chat_payload: serde_json::Value = serde_json::from_slice(&chat_body).expect("json");
    assert_eq!(chat_payload[0]["Direction"], "inbound");
    assert_eq!(chat_payload[0]["State"], "received");
    assert_eq!(chat_payload[0]["Source"], "peer-alpha");
    assert_eq!(chat_payload[0]["TopicID"], "ops");
    assert_eq!(chat_payload[0]["Content"], "Inbound from Rust transport");
    let diagnostics = crate::runtime_diagnostics_payload(&state).expect("diagnostics");
    assert_eq!(diagnostics["reticulumd_inbound"]["received_total"], 1);
    assert_eq!(diagnostics["outbound_delivery"]["total"], 0);
    assert_eq!(
        diagnostics["metrics"]["counters"]["reticulumd_inbound_received_total"],
        1
    );
    let restored = crate::AppState::from_sqlite_path(&db_path)
        .expect("restored")
        .with_api_key("secret");
    let restored_events = restored.system_events.read().expect("restored events");
    assert!(
        restored_events
            .iter()
            .any(|event| event.event_type == "message_received")
    );
    std::fs::remove_file(db_path).expect("cleanup db");
}
