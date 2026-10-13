//! Inbound behavior exercised through the production durable inbox: daemon
//! records are committed to the local inbox and applied by the ordered worker,
//! exactly as `durable_broker::intake` and `apply` do at runtime.

use super::*;
use std::path::PathBuf;

fn temp_db() -> PathBuf {
    std::env::temp_dir().join(format!("r3akt-durable-inbound-{}.db", Uuid::new_v4()))
}

fn state_db(state: &crate::AppState) -> PathBuf {
    state
        .sqlite_path
        .as_deref()
        .map(PathBuf::from)
        .expect("durable inbound tests use SQLite")
}

/// Applies daemon message records; fills the fields every daemon record carries.
fn apply_daemon_messages(state: &crate::AppState, messages: Value) -> usize {
    let local = state
        .reticulumd_source
        .as_deref()
        .cloned()
        .expect("service destination");
    let messages = messages
        .as_array()
        .expect("message records")
        .iter()
        .map(|message| {
            let mut message = message.clone();
            let record = message.as_object_mut().expect("message record");
            record.entry("direction").or_insert_with(|| json!("in"));
            record.entry("destination").or_insert_with(|| json!(local));
            if !record.contains_key("source") {
                // A daemon always reports the verified sender; for embedded
                // R3AKT envelopes that is the envelope's own source.
                let embedded = record["fields"]["r3akt_payload_b64"]
                    .as_str()
                    .expect("record without source needs an embedded envelope");
                let bytes = BASE64_STANDARD.decode(embedded).expect("envelope base64");
                let envelope = r3akt_protocol::ProtocolEnvelope::decode_msgpack(&bytes)
                    .expect("embedded envelope");
                record.insert("source".to_string(), json!(envelope.source.to_string()));
            }
            message
        })
        .collect::<Vec<_>>();
    crate::durable_broker::apply_inbound_messages_for_test(state, &messages)
        .expect("apply durable inbound")
}

fn apply_envelope(state: &crate::AppState, envelope: &r3akt_protocol::ProtocolEnvelope) -> usize {
    let payload = BASE64_STANDARD.encode(envelope.encode_msgpack().expect("msgpack"));
    apply_daemon_messages(
        state,
        json!([{
            "id": envelope.id.to_string(),
            "source": envelope.source.to_string(),
            "fields": { "r3akt_payload_b64": payload }
        }]),
    )
}

/// Roster state lives in `SQLite`; the durable worker reads it from there.
fn seed_client(state: &crate::AppState, identity: &str, last_seen_ts_ms: i64) {
    seed_named_client(state, identity, None, last_seen_ts_ms);
}

fn seed_named_client(
    state: &crate::AppState,
    identity: &str,
    nickname: Option<&str>,
    last_seen_ts_ms: i64,
) {
    crate::with_core_store_write(state, |store| {
        store.upsert_client(&r3akt_rch_core::ClientRecord {
            identity: identity.to_string(),
            first_seen_ts_ms: last_seen_ts_ms,
            last_seen_ts_ms,
            nickname: nickname.map(str::to_string),
            role: r3akt_rch_core::DEFAULT_ROSTER_ROLE.to_string(),
            paused: false,
            text_only: false,
            last_chat_ts_ms: None,
        })
    })
    .expect("seed roster client");
}

fn single(mut requests: Vec<Value>) -> Value {
    assert_eq!(requests.len(), 1, "{requests:?}");
    requests.remove(0)
}

mod chat;
mod commands;
mod media;
