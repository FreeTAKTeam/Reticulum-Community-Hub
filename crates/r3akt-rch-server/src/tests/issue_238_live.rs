use super::*;
use r3akt_rch_bridge::{ReticulumdRpc, ReticulumdRpcClient};

#[tokio::test]
async fn live_issue_238_zmq_imports_announces_and_inbound_message_when_configured() {
    let required = [
        "R3AKT_LXMF_ZMQ_COMMAND_ENDPOINT",
        "R3AKT_LXMF_ZMQ_RESPONSE_ENDPOINT",
        "R3AKT_RETICULUMD_FIELD_COMMAND_RPC_ENDPOINT",
        "R3AKT_RETICULUMD_FIELD_COMMAND_SOURCE",
    ];
    let mut values = Vec::new();
    for name in required {
        match std::env::var(name) {
            Ok(value) if !value.trim().is_empty() => values.push(value),
            _ => {
                eprintln!("skipping live issue-238 imports: {name} is unset");
                return;
            }
        }
    }
    let db = std::env::temp_dir().join(format!("rch-issue-238-{}.db", Uuid::new_v4()));
    let identity_path = db.with_extension("identity");
    let mut state = crate::AppState::from_sqlite_path(&db)
        .expect("state")
        .with_lxmf_zmq_sdk_identity(
            values[0].clone(),
            values[1].clone(),
            None,
            &identity_path,
            "RCH issue-238 fixture",
        )
        .expect("SDK identity configuration");
    state
        .register_lxmf_zmq_service_identity()
        .expect("register service identity");
    let destination = state
        .reticulumd_source
        .as_ref()
        .expect("derived source")
        .as_str();
    let marker = format!("issue-238-inbound-{}", Uuid::new_v4());
    let envelope = r3akt_protocol::ProtocolEnvelope::new(
        r3akt_protocol::NodeId::new(values[3].clone()),
        r3akt_protocol::Destination::Topic(r3akt_protocol::Topic::new("ops")),
        r3akt_protocol::Topic::new("ops"),
        r3akt_protocol::Payload::TopicMessage(r3akt_protocol::TopicMessage {
            body: marker.clone(),
            content_type: "text/plain".to_string(),
            correlation_id: None,
            attachments: Vec::new(),
        }),
    );
    let payload = BASE64_STANDARD.encode(envelope.encode_msgpack().expect("RCH frame"));
    let mut sender = ReticulumdRpcClient::new(values[2].clone());
    let sent = sender
        .call(
            "send_message_v2",
            Some(json!({
                "id": marker, "source": values[3], "destination": destination,
                "title": "RCH", "content": marker, "method": "direct",
                "fields": {"r3akt_payload_b64": payload}
            })),
        )
        .expect("send peer message");
    assert!(sent.error.is_none(), "peer send rejected: {sent:?}");
    let mut cursor = None;
    let started = Instant::now();
    loop {
        let report = crate::process_lxmf_zmq_event_worker_tick(
            &state,
            &values[0],
            &values[1],
            destination,
            cursor,
        )
        .expect("real ZeroMQ event poll");
        cursor = report.next_cursor;
        let stats = state
            .reticulumd_inbound_worker_stats
            .read()
            .expect("stats")
            .clone();
        let imported = state
            .messages
            .read()
            .expect("messages")
            .iter()
            .any(|message| message.content == marker);
        if imported && stats.announces_imported_total > 0 {
            assert!(stats.received_total > 0);
            assert!(stats.events_imported_total >= 2);
            assert_eq!(stats.event_poll_errors_total, 0);
            println!(
                "issue_238_zmq_imports announces={} received={} events_imported={} marker={marker}",
                stats.announces_imported_total, stats.received_total, stats.events_imported_total
            );
            break;
        }
        assert!(
            started.elapsed() < Duration::from_secs(20),
            "missing announce/message import: imported={imported}, stats={stats:?}"
        );
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
    state
        .lxmf_zmq_data_plane
        .as_ref()
        .expect("plane")
        .shutdown()
        .expect("shutdown SDK");
    drop(state);
    std::fs::remove_file(identity_path).expect("remove fixture identity");
    std::fs::remove_file(db).expect("remove fixture database");
}
