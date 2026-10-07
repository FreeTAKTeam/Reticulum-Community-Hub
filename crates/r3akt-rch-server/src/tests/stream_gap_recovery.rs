use crate::{AppState, reticulumd_inbound};
use r3akt_transport_rns::LxmfMessageHistoryPage;
use serde_json::{Value, json};

fn history_message(id: &str, fields: Value) -> Value {
    json!({
        "id": id,
        "source": "peer-history",
        "destination": "hub-source",
        "title": "",
        "content": format!("history {id}"),
        "timestamp": 1_775_000_001,
        "direction": "in",
        "fields": fields,
        "receipt_status": "delivered",
    })
}

fn history_pages() -> [LxmfMessageHistoryPage; 2] {
    let mut messages = (0..32)
        .map(|index| history_message(&format!("good-{index}"), json!({})))
        .collect::<Vec<_>>();
    messages.push(history_message(
        "poison",
        json!({"9": [{"not_a_selector": "join"}]}),
    ));
    messages.push(history_message("after-poison", json!({})));
    let mut foreign = history_message("other-identity", json!({}));
    foreign["destination"] = json!("another-identity");
    messages.push(foreign);
    [
        serde_json::from_value(json!({
            "messages": messages,
            "next_cursor": "history-page-2",
        }))
        .expect("first history page"),
        serde_json::from_value(json!({
            "messages": [history_message("last-page", json!({}))],
            "next_cursor": null,
        }))
        .expect("second history page"),
    ]
}

#[test]
fn stream_gap_recovery_quarantines_poison_and_does_not_recount_history() {
    let state = AppState::default();
    let pages = history_pages();
    let mut failures = 0;
    let mut recovered = 0;
    for _ in 0..128 {
        let mut requested = Vec::new();
        let result = reticulumd_inbound::recover_history(&state, "hub-source", |cursor| {
            let page = if cursor.is_none() { 0 } else { 1 };
            requested.push(cursor);
            Ok(pages[page].clone())
        });
        match result {
            Ok(count) => {
                recovered += count;
                assert_eq!(requested, vec![None, Some("history-page-2".to_string())]);
            }
            Err(_) => failures += 1,
        }
    }
    let stats = state.reticulumd_inbound_worker_stats.read().expect("stats");
    eprintln!(
        "recovery failures={failures}; received_total={}; recovered={recovered}",
        stats.received_total
    );
    assert_eq!(
        failures, 0,
        "malformed history must not abort stream recovery"
    );
    assert_eq!(recovered, 34);
    assert_eq!(stats.received_total, 34);
    assert_eq!(stats.quarantined_total, 1);
    assert!(
        stats
            .last_quarantine_error
            .as_deref()
            .is_some_and(|error| error.contains("poison"))
    );
    let messages = state.messages.read().expect("messages");
    assert_eq!(
        messages
            .iter()
            .filter(|message| message.delivery_state == "received")
            .count(),
        34
    );
    assert!(
        messages
            .iter()
            .all(|message| !message.content.contains("other-identity"))
    );
}

#[test]
fn stream_gap_recovery_preserves_page_fetch_errors() {
    let state = AppState::default();
    let error = reticulumd_inbound::recover_history(&state, "hub-source", |_| {
        Err(crate::ApiError::Internal(
            "history storage unavailable".to_string(),
        ))
    })
    .expect_err("storage error must remain actionable");
    assert!(error.to_string().contains("history storage unavailable"));
    let stats = state.reticulumd_inbound_worker_stats.read().expect("stats");
    assert_eq!(stats.received_total, 0);
    assert_eq!(stats.quarantined_total, 0);
}

#[test]
fn stream_gap_recovery_preserves_quarantine_and_deduplication_after_restart() {
    let path = std::env::temp_dir().join(format!("rch-gap-{}.db", uuid::Uuid::new_v4()));
    let pages = history_pages();
    {
        let state = AppState::from_sqlite_path(&path).expect("state");
        let count = reticulumd_inbound::recover_history(&state, "hub-source", |cursor| {
            Ok(pages[usize::from(cursor.is_some())].clone())
        })
        .expect("initial recovery");
        assert_eq!(count, 34);
    }
    let state = AppState::from_sqlite_path(&path).expect("restored state");
    let count = reticulumd_inbound::recover_history(&state, "hub-source", |cursor| {
        Ok(pages[usize::from(cursor.is_some())].clone())
    })
    .expect("recovery after restart");
    assert_eq!(count, 0);
    assert_eq!(
        state
            .reticulumd_inbound_worker_stats
            .read()
            .expect("stats")
            .received_total,
        0
    );
    assert_eq!(
        state
            .system_events
            .read()
            .expect("events")
            .iter()
            .filter(|event| event.event_type == "reticulumd_inbound_message_quarantined")
            .count(),
        1
    );
    drop(state);
    std::fs::remove_file(path).expect("cleanup database");
}
