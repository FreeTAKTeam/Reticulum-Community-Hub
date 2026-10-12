use super::*;

#[test]
fn duplicate_plain_lxmf_join_command_is_processed_once() {
    let state = durable_inbound_test_state(&temp_db(), "hub-source");
    let source = "77b2539b72259af927e48c0f90721767";
    let topic = r3akt_protocol::Topic::new("direct");
    let envelope = r3akt_protocol::ProtocolEnvelope::new(
        r3akt_protocol::NodeId::new(source),
        r3akt_protocol::Destination::Topic(topic.clone()),
        topic,
        r3akt_protocol::Payload::TopicMessage(r3akt_protocol::TopicMessage {
            body: "/join".to_string(),
            content_type: "text/plain".to_string(),
            correlation_id: None,
            attachments: Vec::new(),
        }),
    )
    .with_dedupe_key("pixel-join-command-1");

    apply_envelope(&state, &envelope);
    apply_envelope(&state, &envelope);

    // The repeated daemon record is the same logical command: one reply only.
    let request = single(pending_broker_requests(&state_db(&state)));
    assert_eq!(request["content"], "joined");
    let messages = state.messages.read().expect("messages");
    assert_eq!(messages.len(), 1);
    assert_eq!(messages[0].content, "joined");
}

#[test]
fn list_messages_plain_lxmf_join_replies_joined() {
    let state = durable_inbound_test_state(&temp_db(), "hub-source");
    let source = "77b2539b72259af927e48c0f90721767";
    let imported = apply_daemon_messages(
        &state,
        json!([{
            "id": "pixel-backslash-join-1",
            "direction": "in",
            "source": source,
            "destination": "hub-source",
            "content": "\\join",
            "fields": {},
            "timestamp": 1_778_358_900,
            "title": ""
        }]),
    );

    assert_eq!(imported, 1);
    let request = single(pending_broker_requests(&state_db(&state)));
    let params = request.clone();
    assert_eq!(params["destination"], source);
    assert_eq!(params["content"], "joined");
    let messages = state.messages.read().expect("messages");
    assert_eq!(messages.len(), 1);
    assert_eq!(messages[0].content, "joined");
}

#[test]
fn list_messages_plain_lxmf_join_short_oi_replies_joined() {
    let state = durable_inbound_test_state(&temp_db(), "hub-source");
    let source = "77b2539b72259af927e48c0f90721767";
    let imported = apply_daemon_messages(
        &state,
        json!([{
            "id": "pixel-backslash-oi-1",
            "direction": "in",
            "source": source,
            "destination": "hub-source",
            "content": "\\oi",
            "fields": {},
            "timestamp": 1_778_379_382,
            "title": ""
        }]),
    );

    assert_eq!(imported, 1);
    let request = single(pending_broker_requests(&state_db(&state)));
    let params = request.clone();
    assert_eq!(params["destination"], source);
    assert_eq!(params["content"], "joined");
}

#[test]
fn list_messages_plain_lxmf_join_short_on_replies_joined() {
    let state = durable_inbound_test_state(&temp_db(), "hub-source");
    let source = "77b2539b72259af927e48c0f90721767";
    let imported = apply_daemon_messages(
        &state,
        json!([{
            "id": "pixel-backslash-on-1",
            "direction": "in",
            "source": source,
            "destination": "hub-source",
            "content": "\\on",
            "fields": {},
            "timestamp": 1_778_379_078,
            "title": ""
        }]),
    );

    assert_eq!(imported, 1);
    let request = single(pending_broker_requests(&state_db(&state)));
    let params = request.clone();
    assert_eq!(params["destination"], source);
    assert_eq!(params["content"], "joined");
}

#[test]
fn list_messages_plain_lxmf_join_typo_replies_joined() {
    let state = durable_inbound_test_state(&temp_db(), "hub-source");
    let source = "77b2539b72259af927e48c0f90721767";
    let imported = apply_daemon_messages(
        &state,
        json!([{
            "id": "pixel-backslash-ji-1",
            "direction": "in",
            "source": source,
            "destination": "hub-source",
            "content": "\\ji",
            "fields": {},
            "timestamp": 1_778_369_178,
            "title": ""
        }]),
    );

    assert_eq!(imported, 1);
    let request = single(pending_broker_requests(&state_db(&state)));
    let params = request.clone();
    assert_eq!(params["destination"], source);
    assert_eq!(params["content"], "joined");
}

#[test]
fn plain_lxmf_help_lists_roster_commands_and_legacy_escape() {
    let state = durable_inbound_test_state(&temp_db(), "hub-source");
    let source = "77b2539b72259af927e48c0f90721767";
    let topic = r3akt_protocol::Topic::new("direct");
    let envelope = r3akt_protocol::ProtocolEnvelope::new(
        r3akt_protocol::NodeId::new(source),
        r3akt_protocol::Destination::Topic(topic.clone()),
        topic,
        r3akt_protocol::Payload::TopicMessage(r3akt_protocol::TopicMessage {
            body: "\\help".to_string(),
            content_type: "text/plain".to_string(),
            correlation_id: None,
            attachments: Vec::new(),
        }),
    );

    apply_envelope(&state, &envelope);

    let request = single(pending_broker_requests(&state_db(&state)));
    let params = request.clone();
    assert_eq!(params["destination"], source);
    let content = params["content"].as_str().expect("help content");
    for expected in [
        "RCH commands:",
        "/join",
        "/leave",
        "/pause",
        "/resume",
        "/nick <name>",
        "/users",
        "/help",
        "\\join",
        "\\help",
    ] {
        assert!(
            content.contains(expected),
            "help reply missing {expected}: {content}"
        );
    }
}

#[test]
fn plain_lxmf_join_command_replies_joined_and_marks_source_joined() {
    let state = durable_inbound_test_state(&temp_db(), "hub-source");
    let source = "77b2539b72259af927e48c0f90721767";
    let topic = r3akt_protocol::Topic::new("direct");
    let envelope = r3akt_protocol::ProtocolEnvelope::new(
        r3akt_protocol::NodeId::new(source),
        r3akt_protocol::Destination::Topic(topic.clone()),
        topic,
        r3akt_protocol::Payload::TopicMessage(r3akt_protocol::TopicMessage {
            body: r"\\\join".to_string(),
            content_type: "text/plain".to_string(),
            correlation_id: None,
            attachments: Vec::new(),
        }),
    );

    apply_envelope(&state, &envelope);

    let request = single(pending_broker_requests(&state_db(&state)));
    let params = request.clone();
    assert_eq!(params["destination"], source);
    assert_eq!(params["title"], "RCH");
    assert_eq!(params["content"], "joined");
    assert_eq!(params["fields"], json!({}));

    assert!(state.clients.read().expect("clients").contains_key(source));
    let messages = state.messages.read().expect("messages");
    assert_eq!(messages.len(), 1);
    assert_eq!(messages[0].destination.as_deref(), Some(source));
    assert_eq!(messages[0].content, "joined");
    assert_eq!(messages[0].delivery_metadata["direction"], "outbound");
}

#[test]
fn plain_lxmf_roster_commands_update_member_state() {
    let state = durable_inbound_test_state(&temp_db(), "hub-source");
    let source = "77b2539b72259af927e48c0f90721767";
    for body in ["/join", "/nick Alpha_1", "/pause", "/resume"] {
        let topic = r3akt_protocol::Topic::new("direct");
        let envelope = r3akt_protocol::ProtocolEnvelope::new(
            r3akt_protocol::NodeId::new(source),
            r3akt_protocol::Destination::Topic(topic.clone()),
            topic,
            r3akt_protocol::Payload::TopicMessage(r3akt_protocol::TopicMessage {
                body: body.to_string(),
                content_type: "text/plain".to_string(),
                correlation_id: None,
                attachments: Vec::new(),
            }),
        );
        apply_envelope(&state, &envelope);
    }

    let requests = pending_broker_requests(&state_db(&state));
    let replies = requests
        .iter()
        .map(|request| request["content"].clone())
        .collect::<Vec<_>>();
    assert_eq!(
        replies,
        vec![
            json!("joined"),
            json!("nick set to Alpha_1"),
            json!("paused"),
            json!("resumed")
        ]
    );
    let client = state
        .clients
        .read()
        .expect("clients")
        .get(source)
        .cloned()
        .expect("client");
    assert_eq!(client.nickname.as_deref(), Some("Alpha_1"));
    assert!(!client.paused);
}

#[tokio::test]
async fn reticulumd_inbound_command_creates_topic() {
    let envelope = r3akt_protocol::ProtocolEnvelope::new(
        r3akt_protocol::NodeId::new("peer-create"),
        r3akt_protocol::Destination::Node(r3akt_protocol::NodeId::new("local-destination")),
        r3akt_protocol::Topic::new("control"),
        r3akt_protocol::Payload::Command(r3akt_protocol::Command {
            name: "CreateTopic".to_string(),
            args: json!({
                "TopicID": "field-ops",
                "TopicName": "Field Ops",
                "TopicPath": "field/ops",
                "TopicDescription": "Inbound-created topic"
            }),
            correlation_id: Some("cmd-create-topic".to_string()),
        }),
    );
    let payload_b64 = BASE64_STANDARD.encode(envelope.encode_msgpack().expect("msgpack"));
    let db_path = std::env::temp_dir().join(format!(
        "r3akt-reticulumd-create-topic-{}.db",
        Uuid::new_v4()
    ));
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
            "id": "lxmf-command-create-topic-1",
            "destination": "local-destination",
            "fields": {
                "r3akt_payload_b64": payload_b64
            }
        }]),
    );
    let topic_response = app
        .clone()
        .oneshot(
            Request::builder()
                .header("X-API-Key", "secret")
                .method(Method::GET)
                .uri("/Topic/field-ops")
                .body(Body::empty())
                .expect("topic request"),
        )
        .await
        .expect("topic response");
    assert_eq!(topic_response.status(), StatusCode::OK);
    let topic_body = topic_response
        .into_body()
        .collect()
        .await
        .expect("topic body")
        .to_bytes();
    let topic: serde_json::Value = serde_json::from_slice(&topic_body).expect("topic json");
    assert_eq!(topic["TopicID"], "field-ops");
    assert_eq!(topic["TopicName"], "Field Ops");
    assert_eq!(topic["TopicPath"], "field/ops");
    assert_eq!(topic["TopicDescription"], "Inbound-created topic");
    let client_response = app
        .oneshot(
            Request::builder()
                .header("X-API-Key", "secret")
                .method(Method::GET)
                .uri("/Client")
                .body(Body::empty())
                .expect("client request"),
        )
        .await
        .expect("client response");
    assert_eq!(client_response.status(), StatusCode::OK);
    let client_body = client_response
        .into_body()
        .collect()
        .await
        .expect("client body")
        .to_bytes();
    let clients: serde_json::Value = serde_json::from_slice(&client_body).expect("client json");
    assert_eq!(clients[0]["identity"], "peer-create");
    let restored = crate::AppState::from_sqlite_path(&db_path)
        .expect("restored")
        .with_api_key("secret");
    let topics = restored.topics.read().expect("topics");
    assert!(topics.contains_key("field-ops"));
    std::fs::remove_file(db_path).expect("cleanup db");
}

#[tokio::test]
async fn reticulumd_inbound_command_subscribes_source_to_topic() {
    let envelope = r3akt_protocol::ProtocolEnvelope::new(
        r3akt_protocol::NodeId::new("peer-bravo"),
        r3akt_protocol::Destination::Node(r3akt_protocol::NodeId::new("local-destination")),
        r3akt_protocol::Topic::new("control"),
        r3akt_protocol::Payload::Command(r3akt_protocol::Command {
            name: "SubscribeTopic".to_string(),
            args: json!({ "TopicID": "ops" }),
            correlation_id: Some("cmd-corr-1".to_string()),
        }),
    );
    let payload_b64 = BASE64_STANDARD.encode(envelope.encode_msgpack().expect("msgpack"));
    let db_path =
        std::env::temp_dir().join(format!("r3akt-reticulumd-command-{}.db", Uuid::new_v4()));
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
                    serde_json::to_vec(&json!({
                        "TopicID": "ops",
                        "TopicName": "Operations",
                        "TopicPath": "ops"
                    }))
                    .expect("topic json"),
                ))
                .expect("topic request"),
        )
        .await
        .expect("topic response");
    assert_eq!(topic_response.status(), StatusCode::OK);

    apply_daemon_messages(
        &state,
        json!([{
            "id": "lxmf-command-1",
            "destination": "local-destination",
            "fields": {
                "r3akt_payload_b64": payload_b64
            }
        }]),
    );
    let subscriber_response = app
        .clone()
        .oneshot(
            Request::builder()
                .header("X-API-Key", "secret")
                .method(Method::GET)
                .uri("/Subscriber")
                .body(Body::empty())
                .expect("subscriber request"),
        )
        .await
        .expect("subscriber response");
    assert_eq!(subscriber_response.status(), StatusCode::OK);
    let subscriber_body = subscriber_response
        .into_body()
        .collect()
        .await
        .expect("subscriber body")
        .to_bytes();
    let subscribers: serde_json::Value =
        serde_json::from_slice(&subscriber_body).expect("subscriber json");
    assert_eq!(subscribers[0]["Destination"], "peer-bravo");
    assert_eq!(subscribers[0]["TopicID"], "ops");
    let client_response = app
        .oneshot(
            Request::builder()
                .header("X-API-Key", "secret")
                .method(Method::GET)
                .uri("/Client")
                .body(Body::empty())
                .expect("client request"),
        )
        .await
        .expect("client response");
    assert_eq!(client_response.status(), StatusCode::OK);
    let client_body = client_response
        .into_body()
        .collect()
        .await
        .expect("client body")
        .to_bytes();
    let clients: serde_json::Value = serde_json::from_slice(&client_body).expect("client json");
    assert_eq!(clients[0]["identity"], "peer-bravo");
    let diagnostics = crate::runtime_diagnostics_payload(&state).expect("diagnostics");
    assert_eq!(diagnostics["reticulumd_inbound"]["received_total"], 1);
    std::fs::remove_file(db_path).expect("cleanup db");
}

#[tokio::test]
async fn reticulumd_inbound_mission_command_replies_and_fans_out_team_event() {
    let envelope = r3akt_protocol::ProtocolEnvelope::new(
        r3akt_protocol::NodeId::new("peer-mission-source"),
        r3akt_protocol::Destination::Node(r3akt_protocol::NodeId::new("local-destination")),
        r3akt_protocol::Topic::new("mission-alpha"),
        r3akt_protocol::Payload::Command(r3akt_protocol::Command {
            name: "mission.registry.log_entry.upsert".to_string(),
            args: json!({
                "entry_uid": "log-from-reticulumd",
                "mission_uid": "mission-inbound",
                "callsign": "Alpha",
                "content": "Inbound mission event"
            }),
            correlation_id: Some("cmd-mission-log".to_string()),
        }),
    )
    .with_dedupe_key("dedupe-mission-log");
    let payload_b64 = BASE64_STANDARD.encode(envelope.encode_msgpack().expect("msgpack"));
    let db_path = std::env::temp_dir().join(format!(
        "r3akt-reticulumd-mission-command-{}.db",
        Uuid::new_v4()
    ));
    let state = crate::AppState::from_sqlite_path(&db_path)
        .expect("state")
        .with_api_key("secret")
        .with_test_reticulumd_source("local-destination");
    let mut state = state;
    state.enable_durable_consumer().expect("durable consumer");
    let app = crate::create_app_with_state(state.clone());
    for (method, uri, body) in [
        (
            Method::POST,
            "/api/r3akt/missions",
            r#"{"uid":"mission-inbound","mission_name":"Inbound Mission"}"#,
        ),
        (
            Method::POST,
            "/api/r3akt/teams",
            r#"{"uid":"team-inbound","team_name":"Inbound Team"}"#,
        ),
        (
            Method::PUT,
            "/api/r3akt/teams/team-inbound/missions/mission-inbound",
            "{}",
        ),
        (
            Method::POST,
            "/api/r3akt/team-members",
            r#"{"uid":"member-inbound","team_uid":"team-inbound","rns_identity":"22222222222222222222222222222222","display_name":"Team Mate"}"#,
        ),
    ] {
        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .header("X-API-Key", "secret")
                    .method(method)
                    .uri(uri)
                    .header(axum::http::header::CONTENT_TYPE, "application/json")
                    .body(Body::from(body))
                    .expect("setup request"),
            )
            .await
            .expect("setup response");
        assert_eq!(response.status(), StatusCode::OK, "{uri}");
    }
    let now = crate::unix_now_ms();
    crate::persist_identity_announce_records(
        &state,
        &[r3akt_rch_core::IdentityAnnounceRecord {
            destination_hash: "peer-mission-source".to_string(),
            announced_identity_hash: None,
            display_name: Some("mission source".to_string()),
            source_interface: Some("reticulumd".to_string()),
            announce_capabilities: Vec::new(),
            client_type: "generic_lxmf".to_string(),
            first_seen_ts_ms: now,
            last_seen_ts_ms: now,
        }],
    )
    .expect("persist fresh mission source announce");

    apply_daemon_messages(
        &state,
        json!([{
            "id": "lxmf-command-mission-1",
            "destination": "local-destination",
            "fields": {
                "r3akt_payload_b64": payload_b64
            }
        }]),
    );
    let requests = pending_broker_requests(&state_db(&state));
    let direct_replies = requests
        .iter()
        .filter(|request| request["destination"] == "peer-mission-source")
        .collect::<Vec<_>>();
    assert_eq!(direct_replies.len(), 2);
    assert!(
        direct_replies
            .iter()
            .any(|request| { request["fields"]["10"]["status"] == "accepted" }),
        "{direct_replies:#?}"
    );
    let result_reply = direct_replies
        .iter()
        .find(|request| request["fields"]["10"]["status"] == "result")
        .expect("result reply");
    let result_params = result_reply;
    assert_eq!(
        result_params["fields"]["13"]["event_type"],
        "mission.registry.log_entry.upserted"
    );
    assert_eq!(
        result_params["fields"]["13"]["payload"]["mission_uid"],
        "mission-inbound"
    );

    let team_fanout = requests
        .iter()
        .find(|request| request["destination"] == "22222222222222222222222222222222")
        .expect("team fanout");
    let team_params = team_fanout;
    assert_eq!(
        team_params["content"],
        "r3akt mission event mission.registry.log_entry.upserted"
    );
    assert_eq!(
        team_params["fields"]["13"]["payload"]["entry_uid"],
        "log-from-reticulumd"
    );
    assert_eq!(
        team_params["fields"]["10"]["correlation_id"],
        "cmd-mission-log"
    );

    let restored = RchSqliteStore::open(&db_path)
        .expect("open restored")
        .load_snapshot()
        .expect("load restored")
        .expect("snapshot");
    assert!(
        restored
            .log_entries
            .iter()
            .any(|entry| entry.entry_uid == "log-from-reticulumd")
    );
    std::fs::remove_file(db_path).expect("cleanup db");
}

#[test]
fn list_messages_legacy_join_adds_source_replies_and_deduplicates() {
    let state = durable_inbound_test_state(&temp_db(), "hub-source");
    let source = "77b2539b72259af927e48c0f90721767";
    let result = json!({
        "messages": [{
            "id": "field-command-join-1",
            "direction": "in",
            "source": source,
            "destination": "hub-source",
            "content": "",
            "fields": {"9": [{"Command": "join"}]},
            "timestamp": 1_775_000_001,
            "title": ""
        }]
    });

    apply_daemon_messages(&state, result["messages"].clone());
    apply_daemon_messages(&state, result["messages"].clone());

    assert!(state.clients.read().expect("clients").contains_key(source));
    let messages = state.messages.read().expect("messages");
    assert_eq!(messages.len(), 1);
    assert_eq!(messages[0].content, "joined");
    drop(messages);

    let request = single(pending_broker_requests(&state_db(&state)));
    let params = request.clone();
    assert_eq!(params["destination"], source);
    assert_eq!(params["content"], "joined");
}

#[test]
fn list_messages_mission_style_join_still_dispatches() {
    let state = durable_inbound_test_state(&temp_db(), "hub-source");
    let source = "99b2539b72259af927e48c0f90721767";

    let imported = apply_daemon_messages(
        &state,
        json!([{
            "id": "field-command-mission-join-1",
            "direction": "in",
            "source": source,"direction":"in",
            "destination": "hub-source",
            "content": "",
            "fields": {"9": [{
                "command_id": "mission-join-1",
                "command_type": "mission.join",
                "args": {}
            }]},
            "timestamp": 1_775_000_003,
            "title": ""
        }]),
    );

    assert_eq!(imported, 1);
    assert!(state.clients.read().expect("clients").contains_key(source));
    let messages = state.messages.read().expect("messages");
    assert_eq!(messages.len(), 1);
    assert_eq!(messages[0].content, "joined");
    drop(messages);

    let request = single(pending_broker_requests(&state_db(&state)));
    let params = request.clone();
    assert_eq!(params["destination"], source);
    assert_eq!(params["content"], "joined");
}

#[test]
fn list_messages_numeric_legacy_leave_removes_source_and_replies() {
    let state = durable_inbound_test_state(&temp_db(), "hub-source");
    let source = "88b2539b72259af927e48c0f90721767";
    let now = crate::unix_now_ms();
    crate::with_core_store_write(&state, |store| {
        store.upsert_client(&r3akt_rch_core::ClientRecord {
            identity: source.to_string(),
            first_seen_ts_ms: now,
            last_seen_ts_ms: now,
            nickname: None,
            role: r3akt_rch_core::DEFAULT_ROSTER_ROLE.to_string(),
            paused: false,
            text_only: false,
            last_chat_ts_ms: None,
        })
    })
    .expect("seed roster");

    let imported = apply_daemon_messages(
        &state,
        json!([{
            "id": "field-command-leave-1",
            "direction": "in",
            "source": source,
            "destination": "hub-source",
            "content": "",
            "fields": {"9": [{"0": "leave"}]},
            "timestamp": 1_775_000_002,
            "title": ""
        }]),
    );

    assert_eq!(imported, 1);
    assert!(!state.clients.read().expect("clients").contains_key(source));
    let messages = state.messages.read().expect("messages");
    assert_eq!(messages.len(), 1);
    assert_eq!(messages[0].content, "left");
    drop(messages);

    let request = single(pending_broker_requests(&state_db(&state)));
    let params = request.clone();
    assert_eq!(params["destination"], source);
    assert_eq!(params["content"], "left");
}

#[tokio::test]
async fn reticulumd_inbound_team_peer_directory_returns_only_shared_team_rem_peers() {
    const YELLOW_TEAM_UID: &str = "d6b6e188b910d6bdd24d04b7a7ec5444";
    const BLUE_TEAM_UID: &str = "43341e5c822d99857fa6e8641f2ca9c0";
    const CALLER_IDENTITY: &str = "11111111111111111111111111111111";
    const CALLER_DESTINATION: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    const TEAMMATE_IDENTITY: &str = "22222222222222222222222222222222";
    const TEAMMATE_DESTINATION: &str = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    const OUTSIDER_IDENTITY: &str = "33333333333333333333333333333333";

    let setup_command = |command_type: &str, args: Value| {
        let command_id = format!("setup-{command_type}-{args}");
        r3akt_profile_rch::MissionCommandEnvelope {
            command_id,
            source: r3akt_profile_rch::RchSource::new("setup-source"),
            timestamp: "2026-07-16T12:00:00Z".to_string(),
            command_type: command_type.to_string(),
            args,
            correlation_id: None,
            topics: Vec::new(),
        }
    };
    let mut core = RchCore::new();
    for (uid, name) in [(YELLOW_TEAM_UID, "Yellow"), (BLUE_TEAM_UID, "Blue")] {
        core.handle_command(&setup_command(
            "mission.registry.team.upsert",
            json!({ "uid": uid, "team_name": name }),
        ));
    }
    for (uid, team_uid, identity) in [
        ("member-caller", YELLOW_TEAM_UID, CALLER_IDENTITY),
        ("member-teammate", YELLOW_TEAM_UID, TEAMMATE_IDENTITY),
        ("member-outsider", BLUE_TEAM_UID, OUTSIDER_IDENTITY),
    ] {
        core.handle_command(&setup_command(
            "mission.registry.team_member.upsert",
            json!({
                "uid": uid,
                "team_uid": team_uid,
                "rns_identity": identity,
                "display_name": uid,
            }),
        ));
    }
    let rem_capabilities = vec![
        "r3akt".to_string(),
        "EmergencyMessages".to_string(),
        "Telemetry".to_string(),
    ];
    for (identity, destination, display_name) in [
        (CALLER_IDENTITY, CALLER_DESTINATION, "Caller"),
        (TEAMMATE_IDENTITY, TEAMMATE_DESTINATION, "Teammate"),
    ] {
        core.record_identity_announce(
            destination,
            Some(identity.to_string()),
            Some(display_name.to_string()),
            Some("destination".to_string()),
            rem_capabilities.clone(),
        )
        .expect("REM destination announce");
    }
    core.record_identity_announce(
        OUTSIDER_IDENTITY,
        None,
        Some("Outsider".to_string()),
        Some("identity".to_string()),
        rem_capabilities,
    )
    .expect("outsider announce");

    let db_path = std::env::temp_dir().join(format!(
        "r3akt-reticulumd-team-peer-directory-{}.db",
        Uuid::new_v4()
    ));
    {
        let mut store = RchSqliteStore::open(&db_path).expect("store");
        store.save_snapshot(&core.snapshot()).expect("snapshot");
    }
    let state = crate::AppState::from_sqlite_path(&db_path)
        .expect("state")
        .with_test_reticulumd_source("local-destination");
    let mut state = state;
    state.enable_durable_consumer().expect("durable consumer");

    apply_daemon_messages(
        &state,
        json!([{
            "id": "lxmf-team-directory-1",
            "source": CALLER_DESTINATION,
            "destination": "local-destination",
            "fields": { crate::FIELD_COMMANDS.to_string(): [{
                "command_id": "hub-directory-123",
                "command_type": "rem.registry.team_peers.list",
                "source": { "rns_identity": CALLER_IDENTITY },
                "timestamp": "2026-07-16T12:00:00Z",
                "args": {}
            }] }
        }]),
    );

    let requests = pending_broker_requests(&state_db(&state));
    let replies = requests.iter().collect::<Vec<_>>();
    assert!(replies.iter().any(|params| {
        params["fields"]["10"]["status"] == "accepted"
            && params["fields"]["10"]["command_id"] == "hub-directory-123"
    }));
    let result = replies
        .iter()
        .find(|params| params["fields"]["10"]["status"] == "result")
        .expect("result reply");
    assert_eq!(result["fields"]["10"]["command_id"], "hub-directory-123");
    assert_eq!(result["fields"]["10"]["result"]["scope"], "shared_teams");
    assert_eq!(result["fields"]["10"]["result"]["schema_version"], 2);
    assert_eq!(
        result["fields"]["10"]["result"]["caller_memberships"][0]["team_uid"],
        YELLOW_TEAM_UID
    );
    assert_eq!(
        result["fields"]["10"]["result"]["members"][0]["team_uid"],
        YELLOW_TEAM_UID
    );
    let items = result["fields"]["10"]["result"]["items"]
        .as_array()
        .expect("items");
    assert_eq!(items.len(), 1, "result reply: {result:#?}");
    assert_eq!(items[0]["identity"], TEAMMATE_IDENTITY);
    assert_eq!(items[0]["destination_hash"], TEAMMATE_DESTINATION);

    std::fs::remove_file(db_path).expect("cleanup db");
}

#[test]
fn plain_lxmf_join_replays_recent_topic_chat_from_other_senders() {
    let state = durable_inbound_test_state(&temp_db(), "hub-source");
    let speaker = "4bede2a6ecab26f234aac9bb894a441a";
    let joiner = "77b2539b72259af927e48c0f90721767";
    apply_daemon_messages(
        &state,
        json!([
            {"id": "chat-1", "source": speaker, "content": "first update"},
            {"id": "chat-2", "source": speaker, "content": "second update"},
            {"id": "chat-3", "source": joiner, "content": "my own earlier note"},
        ]),
    );
    let before = pending_broker_requests(&state_db(&state)).len();

    apply_daemon_messages(
        &state,
        json!([{"id": "join-1", "source": joiner, "content": "/join"}]),
    );

    let replies = pending_broker_requests(&state_db(&state))
        .into_iter()
        .skip(before)
        .filter(|request| request["destination"] == joiner)
        .map(|request| request["content"].as_str().expect("content").to_string())
        .collect::<Vec<_>>();
    assert_eq!(
        replies,
        [
            "joined",
            "[replay:direct]\nfirst update",
            "[replay:direct]\nsecond update",
        ]
    );
}
