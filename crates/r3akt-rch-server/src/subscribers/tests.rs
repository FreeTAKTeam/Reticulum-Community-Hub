use crate::*;
use axum::http::{Method, Request};
use http_body_util::BodyExt;
use tower::ServiceExt;

async fn request(state: &AppState, method: Method, path: &str, body: Value) -> Value {
    let response = create_app_with_state(state.clone())
        .oneshot(
            Request::builder()
                .method(method)
                .uri(path)
                .header("X-API-Key", "subscriber-test")
                .header("Content-Type", "application/json")
                .body(Body::from(body.to_string()))
                .expect("request"),
        )
        .await
        .expect("response");
    assert_eq!(response.status(), StatusCode::OK);
    let bytes = response
        .into_body()
        .collect()
        .await
        .expect("body")
        .to_bytes();
    serde_json::from_slice(&bytes).expect("JSON")
}

fn state(path: &FsPath) -> AppState {
    AppState::from_sqlite_path(path)
        .expect("state")
        .with_api_key("subscriber-test")
}

#[tokio::test]
async fn subscription_ids_and_topic_recipients_survive_restart() {
    let directory = std::env::temp_dir().join(format!("rch-subscriptions-{}", Uuid::new_v4()));
    std::fs::create_dir(&directory).expect("directory");
    let path = directory.join("state.db");
    let initial = state(&path);
    let mut created = Vec::new();
    for topic in ["ops", "alerts"] {
        request(
            &initial,
            Method::POST,
            "/Topic",
            json!({"TopicID":topic,"TopicName":topic,"TopicPath":topic}),
        )
        .await;
        created.push(
            request(
                &initial,
                Method::POST,
                "/Topic/Subscribe",
                json!({"TopicID":topic,"Destination":"peer"}),
            )
            .await,
        );
    }
    assert_ne!(created[0]["SubscriberID"], created[1]["SubscriberID"]);
    assert_eq!(
        request(
            &initial,
            Method::POST,
            "/Topic/Subscribe",
            json!({"TopicID":"ops","Destination":"peer"}),
        )
        .await,
        created[0]
    );
    assert_eq!(initial.subscribers.read().unwrap().len(), 2);
    drop(initial);
    let restarted = state(&path);
    for record in &created {
        let id = record["SubscriberID"].as_str().expect("id");
        assert_eq!(
            request(
                &restarted,
                Method::GET,
                &format!("/Subscriber/{id}"),
                Value::Null
            )
            .await,
            *record
        );
        assert_eq!(
            topic_subscriber_destinations(&restarted, record["TopicID"].as_str().unwrap()).unwrap(),
            ["peer"]
        );
    }
    let id = created[0]["SubscriberID"].as_str().unwrap();
    request(
        &restarted,
        Method::PATCH,
        "/Subscriber",
        json!({"SubscriberID":id,"Metadata":{"role":"updated"}}),
    )
    .await;
    drop(restarted);
    let restarted = state(&path);
    let updated = request(
        &restarted,
        Method::GET,
        &format!("/Subscriber/{id}"),
        Value::Null,
    )
    .await;
    assert_eq!(updated["Metadata"], json!({"role":"updated"}));
    request(
        &restarted,
        Method::DELETE,
        &format!("/Subscriber?id={id}"),
        Value::Null,
    )
    .await;
    drop(restarted);
    let restarted = state(&path);
    assert!(
        topic_subscriber_destinations(&restarted, "ops")
            .unwrap()
            .is_empty()
    );
    assert_eq!(
        topic_subscriber_destinations(&restarted, "alerts").unwrap(),
        ["peer"]
    );
    drop(restarted);
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[test]
fn legacy_subscriptions_have_distinct_repeatable_ids_without_rewriting_payloads() {
    let directory =
        std::env::temp_dir().join(format!("rch-legacy-subscriptions-{}", Uuid::new_v4()));
    std::fs::create_dir(&directory).expect("directory");
    let path = directory.join("state.db");
    let mut store = RchSqliteStore::open(&path).expect("store");
    for topic in ["ops", "alerts"] {
        let legacy = json!({"node_id":"peer","topic_id":topic,"first_seen_ts_ms":1,"last_seen_ts_ms":1,"reject_tests":null,"metadata":{}});
        let bytes = rmp_serde::to_vec_named(&legacy).unwrap();
        let record: CoreSubscriberRecord = rmp_serde::from_slice(&bytes).unwrap();
        assert_eq!(record.subscriber_id, None);
        store.upsert_subscriber(&record).unwrap();
    }
    let original = store.load_snapshot().unwrap().unwrap().subscribers;
    let first = state(&path);
    let ids = first
        .subscribers
        .read()
        .unwrap()
        .keys()
        .cloned()
        .collect::<HashSet<_>>();
    assert_eq!(ids.len(), 2);
    let second = state(&path);
    assert_eq!(
        second
            .subscribers
            .read()
            .unwrap()
            .keys()
            .cloned()
            .collect::<HashSet<_>>(),
        ids
    );
    assert_eq!(
        store.load_snapshot().unwrap().unwrap().subscribers,
        original
    );
    drop((first, second, store));
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[tokio::test]
async fn add_and_explicit_replacements_match_storage_before_and_after_restart() {
    let directory = std::env::temp_dir().join(format!("rch-subscriber-upserts-{}", Uuid::new_v4()));
    std::fs::create_dir(&directory).unwrap();
    let path = directory.join("state.db");
    let initial = state(&path);
    let first = request(
        &initial,
        Method::POST,
        "/Subscriber/Add",
        json!({"Destination":"peer","TopicID":"ops"}),
    )
    .await;
    let second = request(
        &initial,
        Method::POST,
        "/Subscriber/Add",
        json!({"Destination":"peer","TopicID":"alerts"}),
    )
    .await;
    assert_ne!(first["SubscriberID"], second["SubscriberID"]);
    let repeated = request(
        &initial,
        Method::POST,
        "/Subscriber/Add",
        json!({"Destination":"peer","TopicID":"ops","Metadata":{"updated":true}}),
    )
    .await;
    assert_eq!(repeated["SubscriberID"], first["SubscriberID"]);
    assert_eq!(initial.subscribers.read().unwrap().len(), 2);
    request(
        &initial,
        Method::POST,
        "/Subscriber",
        json!({"SubscriberID":"explicit","Destination":"peer","TopicID":"ops"}),
    )
    .await;
    assert_eq!(initial.subscribers.read().unwrap().len(), 2);
    assert!(
        !initial
            .subscribers
            .read()
            .unwrap()
            .contains_key(first["SubscriberID"].as_str().unwrap())
    );
    request(
        &initial,
        Method::POST,
        "/Subscriber",
        json!({"SubscriberID":"explicit","Destination":"other","TopicID":"new"}),
    )
    .await;
    assert!(
        topic_subscriber_destinations(&initial, "ops")
            .unwrap()
            .is_empty()
    );
    let restarted = state(&path);
    assert_eq!(
        *initial.subscribers.read().unwrap(),
        *restarted.subscribers.read().unwrap()
    );
    // Moving onto an occupied destination/topic replaces that pair in both stores.
    request(
        &restarted,
        Method::PATCH,
        "/Subscriber",
        json!({"SubscriberID":"explicit","Destination":"peer","TopicID":"alerts"}),
    )
    .await;
    assert_eq!(restarted.subscribers.read().unwrap().len(), 1);
    let final_state = state(&path);
    assert_eq!(
        *restarted.subscribers.read().unwrap(),
        *final_state.subscribers.read().unwrap()
    );
    drop((initial, restarted, final_state));
    std::fs::remove_dir_all(directory).unwrap();
}

#[test]
fn legacy_destination_alias_requires_an_unambiguous_subscription() {
    let record = |topic: &str| {
        SubscriberRecord::from(CoreSubscriberRecord {
            subscriber_id: None,
            node_id: "peer".into(),
            topic_id: topic.into(),
            first_seen_ts_ms: 0,
            last_seen_ts_ms: 0,
            reject_tests: None,
            metadata: json!({}),
        })
    };
    let first = record("ops");
    let mut records = HashMap::from([(first.subscriber_id.clone(), first.clone())]);
    assert_eq!(super::get(&records, "peer").unwrap(), first);
    let second = record("alerts");
    records.insert(second.subscriber_id.clone(), second);
    assert!(matches!(
        super::get(&records, "peer"),
        Err(ApiError::Conflict(_))
    ));
    assert_eq!(super::get(&records, &first.subscriber_id).unwrap(), first);
}
