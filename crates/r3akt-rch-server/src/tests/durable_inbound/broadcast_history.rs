use super::*;

async fn history(state: crate::AppState) -> Value {
    let response = crate::create_app_with_state(state)
        .oneshot(
            Request::builder()
                .uri("/Chat/Messages")
                .header("X-API-Key", "secret")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    serde_json::from_slice(&response.into_body().collect().await.unwrap().to_bytes()).unwrap()
}

#[tokio::test]
async fn ordinary_client_chat_repairs_legacy_history_without_retransmission() {
    let path = temp_db();
    let state = durable_inbound_test_state(&path, "hub-source");
    let columba = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    let ratspeak = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    let recipient = "cccccccccccccccccccccccccccccccc";
    for peer in [columba, ratspeak, recipient] {
        seed_client(&state, peer, crate::unix_now_ms());
    }
    for (source, content, fields) in [
        (
            columba,
            "Columba Pixel chat",
            json!({"172":{"app":"Columba"}}),
        ),
        (ratspeak, "Ratspeak Windows chat", json!({})),
    ] {
        apply_daemon_messages(
            &state,
            json!([{
                "id": format!("ordinary-{source}"), "source": source,
                "content": content, "fields": fields
            }]),
        );
    }
    let requests = pending_broker_requests(&path);
    assert_eq!(requests.len(), 4);
    for source in [columba, ratspeak] {
        let label = &source[..8];
        let relays = requests
            .iter()
            .filter(|r| r["content"].as_str().unwrap().starts_with(label))
            .collect::<Vec<_>>();
        assert_eq!(relays.len(), 2);
        assert!(relays.iter().all(|r| r["destination"] != source));
        assert!(relays.iter().any(|r| r["destination"] == recipient));
    }
    // These are the pre-fix persisted rows: no migration or rewritten delivery intent is needed.
    let store = RchSqliteStore::open(&path).unwrap();
    let records = store
        .chat_history(&r3akt_rch_core::ChatHistoryFilter::default(), 100)
        .unwrap();
    for message in records
        .iter()
        .filter(|m| m.delivery_metadata["direction"] == "inbound")
    {
        assert_eq!(message.delivery_mode, crate::DeliveryMode::Targeted);
        assert_eq!(message.topic_id.as_deref(), Some("direct"));
        assert!(message.destination.is_none());
    }
    drop(store);
    let before = history(state.clone()).await;
    let restarted = crate::AppState::from_sqlite_path(&path)
        .unwrap()
        .with_api_key("secret");
    let after = history(restarted.clone()).await;
    assert_eq!(before, after);
    // Exercise the non-SQLite presentation path against the same hydrated history.
    let mut resident = restarted;
    resident.sqlite_path = None;
    assert_eq!(history(resident).await, before);
    let broadcasts = before
        .as_array()
        .unwrap()
        .iter()
        .filter(|m| m["Scope"] == "broadcast")
        .collect::<Vec<_>>();
    assert_eq!(broadcasts.len(), 2);
    for (source, content) in [
        (columba, "Columba Pixel chat"),
        (ratspeak, "Ratspeak Windows chat"),
    ] {
        let row = broadcasts.iter().find(|m| m["Source"] == source).unwrap();
        assert_eq!(row["Content"], content);
        assert_eq!(row["Direction"], "inbound");
    }
    assert_eq!(pending_broker_requests(&path), requests);
    drop(state);
    std::fs::remove_file(path).unwrap();
}
