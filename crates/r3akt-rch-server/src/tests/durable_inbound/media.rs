use super::*;

#[tokio::test]
async fn reticulumd_inbound_worker_infers_direct_image_media_type_from_bytes() {
    let png_bytes = b"\x89PNG\r\n\x1a\npayload";
    let db_path = std::env::temp_dir().join(format!(
        "r3akt-reticulumd-direct-image-{}.db",
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
            "id": "lxmf-direct-image-1",
            "source": "peer-image",
            "destination": "local-destination",
            "content": "Direct inbound with image",
            "fields": {
                "TopicID": "ops",
                "image": {
                    "data": "iVBORw0KGgpwYXlsb2Fk"
                }
            }
        }]),
    );

    let chat_response = app
        .clone()
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
    assert_eq!(chat_payload[0]["Content"], "Direct inbound with image");
    assert_eq!(chat_payload[0]["Attachments"][0]["Category"], "image");
    assert_eq!(chat_payload[0]["Attachments"][0]["Size"], png_bytes.len());
    assert_eq!(chat_payload[0]["Attachments"][0]["MediaType"], "image/png");
    assert!(
        chat_payload[0]["Attachments"][0]["Name"]
            .as_str()
            .expect("attachment name")
            .ends_with(".png")
    );
    let file_id = chat_payload[0]["Attachments"][0]["FileID"]
        .as_u64()
        .expect("file id");

    let raw_response = app
        .oneshot(
            Request::builder()
                .header("X-API-Key", "secret")
                .method(Method::GET)
                .uri(format!("/Image/{file_id}/raw"))
                .body(Body::empty())
                .expect("raw request"),
        )
        .await
        .expect("raw response");
    assert_eq!(raw_response.status(), StatusCode::OK);
    assert_eq!(
        raw_response
            .headers()
            .get(axum::http::header::CONTENT_TYPE)
            .and_then(|value| value.to_str().ok()),
        Some("image/png")
    );
    let raw_body = raw_response
        .into_body()
        .collect()
        .await
        .expect("raw body")
        .to_bytes();
    assert_eq!(raw_body.as_ref(), png_bytes);

    let restored = crate::AppState::from_sqlite_path(&db_path)
        .expect("restored")
        .with_api_key("secret");
    let restored_attachments =
        crate::load_attachment_records(&restored, "image").expect("restored attachments");
    let attachment = restored_attachments
        .iter()
        .find(|record| record.file_id == file_id)
        .expect("restored attachment");
    assert_eq!(attachment.topic_id.as_deref(), Some("ops"));
    assert_eq!(attachment.media_type.as_deref(), Some("image/png"));
    // Durable attachments live in SQLite (`rch-db:<id>`); the stored name carries
    // the inferred extension.
    assert!(attachment.name.ends_with(".png"), "{}", attachment.name);
    std::fs::remove_file(db_path).expect("cleanup db");
}

#[tokio::test]
async fn reticulumd_inbound_worker_persists_direct_lxmf_attachment_fields() {
    let db_path = std::env::temp_dir().join(format!(
        "r3akt-reticulumd-direct-attachment-{}.db",
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
            "id": "lxmf-direct-attachment-1",
            "source": "peer-direct",
            "destination": "local-destination",
            "content": "Direct inbound with attachment",
            "fields": {
                "TopicID": "ops",
                "attachments": [{
                    "name": "direct.txt",
                    "data": "ZGlyZWN0LWZpbGU=",
                    "media_type": "text/plain"
                }]
            }
        }]),
    );
    let chat_response = app
        .clone()
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
    assert_eq!(chat_payload[0]["Content"], "Direct inbound with attachment");
    assert_eq!(chat_payload[0]["Source"], "peer-direct");
    assert_eq!(chat_payload[0]["TopicID"], "ops");
    assert_eq!(chat_payload[0]["Attachments"][0]["Name"], "direct.txt");
    assert_eq!(chat_payload[0]["Attachments"][0]["Category"], "file");
    assert_eq!(chat_payload[0]["Attachments"][0]["Size"], 11);
    let file_id = chat_payload[0]["Attachments"][0]["FileID"]
        .as_u64()
        .expect("file id");

    let raw_response = app
        .oneshot(
            Request::builder()
                .header("X-API-Key", "secret")
                .method(Method::GET)
                .uri(format!("/File/{file_id}/raw"))
                .body(Body::empty())
                .expect("raw request"),
        )
        .await
        .expect("raw response");
    assert_eq!(raw_response.status(), StatusCode::OK);
    let raw_body = raw_response
        .into_body()
        .collect()
        .await
        .expect("raw body")
        .to_bytes();
    assert_eq!(raw_body.as_ref(), b"direct-file");
    let restored = crate::AppState::from_sqlite_path(&db_path)
        .expect("restored")
        .with_api_key("secret");
    let restored_attachments =
        crate::load_attachment_records(&restored, "file").expect("restored attachments");
    if let Some(attachment) = restored_attachments
        .iter()
        .find(|record| record.file_id == file_id)
    {
        let _ = std::fs::remove_file(&attachment.path);
    }
    std::fs::remove_file(db_path).expect("cleanup db");
}

#[tokio::test]
async fn reticulumd_inbound_worker_persists_topic_file_attachments() {
    let envelope = r3akt_protocol::ProtocolEnvelope::new(
        r3akt_protocol::NodeId::new("peer-attachments"),
        r3akt_protocol::Destination::Topic(r3akt_protocol::Topic::new("ops")),
        r3akt_protocol::Topic::new("ops"),
        r3akt_protocol::Payload::TopicMessage(r3akt_protocol::TopicMessage {
            body: "Inbound with attachment".to_string(),
            content_type: "text/plain".to_string(),
            correlation_id: Some("attachment-corr-1".to_string()),
            attachments: vec![r3akt_protocol::TopicAttachment {
                name: "report.txt".to_string(),
                data: b"file-content".to_vec(),
                media_type: Some("text/plain".to_string()),
                category: "file".to_string(),
            }],
        }),
    );
    let payload_b64 = BASE64_STANDARD.encode(envelope.encode_msgpack().expect("msgpack"));
    let db_path = std::env::temp_dir().join(format!(
        "r3akt-reticulumd-inbound-attachment-{}.db",
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
            "id": "lxmf-inbound-attachment-1",
            "destination": "local-destination",
            "fields": {
                "r3akt_payload_b64": payload_b64
            }
        }]),
    );

    let chat_response = app
        .clone()
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
    assert_eq!(chat_payload[0]["Content"], "Inbound with attachment");
    assert_eq!(chat_payload[0]["Attachments"][0]["Name"], "report.txt");
    assert_eq!(chat_payload[0]["Attachments"][0]["Category"], "file");
    assert_eq!(chat_payload[0]["Attachments"][0]["Size"], 12);
    assert_eq!(chat_payload[0]["Attachments"][0]["MediaType"], "text/plain");
    let file_id = chat_payload[0]["Attachments"][0]["FileID"]
        .as_u64()
        .expect("file id");

    let raw_response = app
        .oneshot(
            Request::builder()
                .header("X-API-Key", "secret")
                .method(Method::GET)
                .uri(format!("/File/{file_id}/raw"))
                .body(Body::empty())
                .expect("raw request"),
        )
        .await
        .expect("raw response");
    assert_eq!(raw_response.status(), StatusCode::OK);
    let raw_body = raw_response
        .into_body()
        .collect()
        .await
        .expect("raw body")
        .to_bytes();
    assert_eq!(raw_body.as_ref(), b"file-content");

    let restored = crate::AppState::from_sqlite_path(&db_path)
        .expect("restored")
        .with_api_key("secret");
    let restored_attachments =
        crate::load_attachment_records(&restored, "file").expect("restored attachments");
    let attachment = restored_attachments
        .iter()
        .find(|record| record.file_id == file_id)
        .expect("restored attachment");
    assert_eq!(attachment.topic_id.as_deref(), Some("ops"));
    assert_eq!(attachment.media_type.as_deref(), Some("text/plain"));
    let _ = std::fs::remove_file(&attachment.path);
    std::fs::remove_file(db_path).expect("cleanup db");
}

#[tokio::test]
async fn telemetry_stream_receives_reticulumd_inbound_health_telemetry() {
    let envelope = r3akt_protocol::ProtocolEnvelope::new(
        r3akt_protocol::NodeId::new("peer-telemetry"),
        r3akt_protocol::Destination::Topic(r3akt_protocol::Topic::new("ops")),
        r3akt_protocol::Topic::new("ops"),
        r3akt_protocol::Payload::HealthTelemetry(r3akt_protocol::HealthTelemetry {
            status: r3akt_protocol::HealthStatus::Degraded,
            metrics: vec![r3akt_protocol::TelemetryMetric::new(
                "battery", 41.0, "percent",
            )],
            observed_at: chrono::DateTime::from_timestamp(1_714_000_222, 0).expect("timestamp"),
        }),
    );
    let payload_b64 = BASE64_STANDARD.encode(envelope.encode_msgpack().expect("msgpack"));
    let db_path = std::env::temp_dir().join(format!(
        "r3akt-reticulumd-telemetry-ws-{}.db",
        Uuid::new_v4()
    ));
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
    let (mut socket, _) = connect_async(format!("ws://{addr}/telemetry/stream"))
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
            json!({"type":"telemetry.subscribe","data":{"since":0,"follow":true}})
                .to_string()
                .into(),
        ))
        .await
        .expect("send subscribe");
    let snapshot_reply = socket
        .next()
        .await
        .expect("snapshot frame")
        .expect("snapshot reply");
    assert_eq!(
        serde_json::from_str::<serde_json::Value>(snapshot_reply.to_text().expect("snapshot text"))
            .expect("snapshot json")["type"],
        "telemetry.snapshot"
    );

    apply_daemon_messages(
        &state,
        json!([{
            "id": "lxmf-telemetry-ws-1",
            "destination": "local-destination",
            "fields": {
                "r3akt_payload_b64": payload_b64
            }
        }]),
    );
    let update_reply = tokio::time::timeout(Duration::from_secs(2), socket.next())
        .await
        .expect("update timeout")
        .expect("update frame")
        .expect("update reply");
    let update_payload: serde_json::Value =
        serde_json::from_str(update_reply.to_text().expect("update text")).expect("update json");
    assert_eq!(update_payload["type"], "telemetry.update");
    assert_eq!(
        update_payload["data"]["entry"]["peer_destination"],
        "peer-telemetry"
    );
    assert_eq!(update_payload["data"]["entry"]["timestamp"], 1_714_000_222);
    assert_eq!(
        update_payload["data"]["entry"]["telemetry"]["status"],
        "Degraded"
    );
    assert_eq!(
        update_payload["data"]["entry"]["telemetry"]["metrics"][0]["name"],
        "battery"
    );
    drop(socket);
    server.abort();
    std::fs::remove_file(db_path).expect("cleanup db");
}
