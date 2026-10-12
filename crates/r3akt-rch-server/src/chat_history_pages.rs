//! Additive paging boundary; legacy chat array responses remain unchanged.
use crate::*;
use r3akt_rch_core::{ChatConversationFilter, ChatCursor};

#[derive(Debug, Deserialize)]
pub(super) struct ChatHistoryQuery {
    scope: String,
    topic_id: Option<String>,
    peer: Option<String>,
    cursor: Option<String>,
    limit: Option<usize>,
}
pub(super) async fn list_chat_history(
    State(state): State<AppState>,
    Query(query): Query<ChatHistoryQuery>,
) -> Result<Json<Value>, ApiError> {
    let target =
        match query.scope.as_str() {
            "broadcast" => None,
            "topic" => Some(normalize_optional_text(query.topic_id).ok_or_else(|| {
                ApiError::BadRequest("topic_id is required for topic history".into())
            })?),
            "dm" => Some(normalize_optional_text(query.peer).ok_or_else(|| {
                ApiError::BadRequest("peer is required for direct history".into())
            })?),
            _ => {
                return Err(ApiError::BadRequest(
                    "scope must be broadcast, topic or dm".into(),
                ));
            }
        };
    let cursor = query
        .cursor
        .as_deref()
        .map(ChatCursor::parse)
        .transpose()
        .map_err(|error| ApiError::BadRequest(error.to_string()))?;
    let limit = query
        .limit
        .unwrap_or(100)
        .clamp(1, r3akt_rch_core::RECENT_MESSAGE_COUNT);
    let path = state.sqlite_path.clone().ok_or_else(|| {
        ApiError::ServiceUnavailable("Paged chat history requires durable SQLite state".into())
    })?;
    let page = tokio::task::spawn_blocking(move || {
        let store = RchSqliteStore::open_read_only(path.as_ref())
            .map_err(|error| ApiError::Internal(error.to_string()))?;
        store
            .chat_history_page(
                &ChatConversationFilter {
                    scope: &query.scope,
                    target: target.as_deref(),
                },
                cursor,
                limit,
            )
            .map_err(|error| ApiError::Internal(error.to_string()))
    })
    .await
    .map_err(|error| ApiError::Internal(error.to_string()))??;
    Ok(Json(json!({
        "Messages": page.messages.into_iter().map(OutboundMessageRecord::from).map(chat_message_payload).collect::<Vec<_>>(),
        "NextCursor": page.next_cursor.map(ChatCursor::encode)
    })))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[tokio::test]
    async fn paged_boundary_rejects_invalid_scope_cursor_and_non_durable_state() {
        let state = AppState::default();
        for query in [
            ChatHistoryQuery {
                scope: "bad".into(),
                topic_id: None,
                peer: None,
                cursor: None,
                limit: None,
            },
            ChatHistoryQuery {
                scope: "topic".into(),
                topic_id: None,
                peer: None,
                cursor: None,
                limit: None,
            },
            ChatHistoryQuery {
                scope: "broadcast".into(),
                topic_id: None,
                peer: None,
                cursor: Some("bad".into()),
                limit: None,
            },
        ] {
            assert!(matches!(
                list_chat_history(State(state.clone()), Query(query)).await,
                Err(ApiError::BadRequest(_))
            ));
        }
        assert!(matches!(
            list_chat_history(
                State(state),
                Query(ChatHistoryQuery {
                    scope: "broadcast".into(),
                    topic_id: None,
                    peer: None,
                    cursor: None,
                    limit: None
                })
            )
            .await,
            Err(ApiError::ServiceUnavailable(_))
        ));
    }
    #[tokio::test]
    async fn authenticated_http_pages_preserve_legacy_array_and_cursor_order() {
        use axum::{
            body::Body,
            http::{Request, StatusCode},
        };
        use http_body_util::BodyExt;
        use r3akt_rch_core::{DeliveryMode, MessageRecord};
        use tower::ServiceExt;
        let path = std::env::temp_dir().join(format!("rch-chat-history-{}.db", Uuid::new_v4()));
        let mut store = RchSqliteStore::open(&path).expect("store");
        for (id, mode, topic) in [
            ("one", DeliveryMode::Broadcast, None),
            ("two", DeliveryMode::Broadcast, None),
            ("topic", DeliveryMode::Fanout, Some("scope")),
        ] {
            store
                .upsert_message(&MessageRecord {
                    message_id: id.into(),
                    topic_id: topic.map(str::to_owned),
                    destination: None,
                    sender: "peer".into(),
                    content: id.into(),
                    delivery_mode: mode,
                    delivery_method: String::new(),
                    delivery_policy_reason: String::new(),
                    delivery_state: "received".into(),
                    delivery_metadata: json!({"direction":"inbound"}),
                    created_ts_ms: 1000,
                    attachments: vec![],
                })
                .expect("message");
        }
        drop(store);
        let app = create_app_with_state(
            AppState::from_sqlite_path(&path)
                .expect("state")
                .with_api_key("secret"),
        );
        let unauthorized = app
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/Chat/History?scope=broadcast")
                    .body(Body::empty())
                    .expect("request"),
            )
            .await
            .expect("response");
        assert_eq!(unauthorized.status(), StatusCode::UNAUTHORIZED);
        let request = |uri: &str| {
            Request::builder()
                .uri(uri)
                .header("X-API-Key", "secret")
                .body(Body::empty())
                .expect("request")
        };
        let response = app
            .clone()
            .oneshot(request("/Chat/History?scope=broadcast&limit=1"))
            .await
            .expect("response");
        assert_eq!(response.status(), StatusCode::OK);
        let payload: Value = serde_json::from_slice(
            &response
                .into_body()
                .collect()
                .await
                .expect("body")
                .to_bytes(),
        )
        .expect("json");
        assert_eq!(payload["Messages"][0]["MessageID"], "one");
        assert_eq!(payload["Messages"][0]["State"], "received");
        let cursor = payload["NextCursor"].as_str().expect("cursor");
        let response = app
            .clone()
            .oneshot(request(&format!(
                "/Chat/History?scope=broadcast&limit=1&cursor={cursor}"
            )))
            .await
            .expect("response");
        let payload: Value = serde_json::from_slice(
            &response
                .into_body()
                .collect()
                .await
                .expect("body")
                .to_bytes(),
        )
        .expect("json");
        assert_eq!(payload["Messages"][0]["MessageID"], "two");
        assert!(payload["NextCursor"].is_null());
        let response = app
            .clone()
            .oneshot(request("/Chat/History?scope=topic&topic_id=scope"))
            .await
            .expect("response");
        let payload: Value = serde_json::from_slice(
            &response
                .into_body()
                .collect()
                .await
                .expect("body")
                .to_bytes(),
        )
        .expect("json");
        assert_eq!(payload["Messages"].as_array().expect("rows").len(), 1);
        assert_eq!(payload["Messages"][0]["MessageID"], "topic");
        let response = app
            .oneshot(request("/Chat/Messages?limit=3"))
            .await
            .expect("response");
        let payload: Value = serde_json::from_slice(
            &response
                .into_body()
                .collect()
                .await
                .expect("body")
                .to_bytes(),
        )
        .expect("json");
        assert_eq!(payload.as_array().expect("legacy array").len(), 3);
        // The state owns its background worker; teardown closes it before the temporary DB expires.
    }
}
