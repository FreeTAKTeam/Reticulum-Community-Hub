use super::{
    ChatEventInput, DateTime, LocationSnapshot, RchNorthboundClient, TakCotReceiver, TakCotSender,
    TakInboundCotEvent, TakInboundCotResult, TakInboundService, TakService, Utc, Value, json,
};
use sha2::{Digest, Sha256};
use std::collections::{HashSet, VecDeque};
#[cfg(test)]
mod tests;

const SEEN_CAPACITY: usize = 4096;

#[derive(Default)]
struct SeenEntries {
    keys: HashSet<String>,
    order: VecDeque<String>,
}

impl SeenEntries {
    fn contains(&self, key: &str) -> bool {
        self.keys.contains(key)
    }
    fn insert(&mut self, key: String) {
        if !self.keys.insert(key.clone()) {
            return;
        }
        self.order.push_back(key);
        if self.order.len() > SEEN_CAPACITY {
            if let Some(oldest) = self.order.pop_front() {
                self.keys.remove(&oldest);
            }
        }
    }
}

#[derive(Default)]
struct SnapshotProgress {
    digest: Option<[u8; 32]>,
    next: usize,
    remaining: usize,
}

#[derive(Default)]
pub(super) struct BridgeState {
    telemetry: SeenEntries,
    telemetry_progress: SnapshotProgress,
    chat: SeenEntries,
    cot: SeenEntries,
    pending_cot: VecDeque<(String, Value)>,
}

pub(super) fn bridge_rch_to_tak<S: TakCotSender>(
    client: &RchNorthboundClient,
    service: &mut TakService<S>,
    state: &mut BridgeState,
) -> Result<(), Box<dyn std::error::Error>> {
    let previous_failure = if service.status().queue.pending > 0 {
        service.flush_once()?.error
    } else {
        None
    };
    let telemetry = client.get_json("/Telemetry?since=0")?;
    let entries = telemetry["entries"]
        .as_array()
        .ok_or("RCH telemetry response must contain an entries array")?;
    let digest: [u8; 32] = Sha256::digest(serde_json::to_vec(entries)?).into();
    let progress = &mut state.telemetry_progress;
    if progress.digest != Some(digest) {
        progress.digest = Some(digest);
        progress.remaining = entries.len();
        if !entries.is_empty() {
            progress.next %= entries.len();
        }
    }
    // Keep a cursor over each bounded HTTP snapshot, including after the FIFO
    // history evicts its oldest keys. Reserve one queue slot for chat so a large
    // telemetry snapshot cannot monopolize every admission cycle.
    let queue = service.status().queue;
    let available = queue.capacity.saturating_sub(queue.pending);
    let budget = if queue.capacity == 1 {
        available
    } else {
        available.saturating_sub(1)
    };
    let mut admitted = 0;
    while progress.remaining > 0 && admitted < budget {
        let entry = &entries[progress.next];
        if let Some((snapshot, label, key)) = location_snapshot_from_entry(entry) {
            if !state.telemetry.contains(&key) {
                service.queue_location(&snapshot, Utc::now(), label.as_deref())?;
                state.telemetry.insert(key);
                admitted += 1;
            }
        }
        progress.next = (progress.next + 1) % entries.len();
        progress.remaining -= 1;
    }

    let messages = client.get_json("/Chat/Messages?limit=100")?;
    for message in messages.as_array().into_iter().flatten() {
        if message["Direction"].as_str() != Some("outbound") {
            continue;
        }
        let Some(input) = chat_input_from_message(message) else {
            continue;
        };
        let key = input
            .message_uuid
            .clone()
            .unwrap_or_else(|| format!("{}:{}", input.timestamp.timestamp(), input.content));
        if !state.chat.contains(&key) {
            service.queue_chat(&input)?;
            state.chat.insert(key);
        }
    }
    // At most one failed network flush per cycle; the existing service retains
    // admitted payloads until delivery succeeds and reports queue backpressure.
    if let Some(error) = previous_failure {
        return Err(error.into());
    }
    if let Some(error) = service.flush_once()?.error {
        return Err(error.into());
    }
    Ok(())
}

pub(super) fn bridge_tak_to_rch<R: TakCotReceiver>(
    client: &RchNorthboundClient,
    receiver: &mut TakInboundService<R>,
    state: &mut BridgeState,
) -> Result<(), Box<dyn std::error::Error>> {
    flush_pending_cot(client, state)?;
    let report = receiver.poll_once()?;
    if let Some(error) = report.error {
        return Err(error.into());
    }
    if let Some(TakInboundCotResult::Raw(raw)) = &report.result {
        eprintln!(
            "TAK inbound payload was not a valid CoT event; ignored {} bytes",
            raw.len()
        );
    }
    let Some(TakInboundCotResult::Parsed(event)) = report.result else {
        return Ok(());
    };
    let key = format!("{}:{}:{}", event.uid, event.time, event.stale);
    if !state.cot.contains(&key) {
        // Stop receiving when a pending POST fails. This keeps a single owned
        // event for retry rather than consuming and forgetting additional CoT.
        state
            .pending_cot
            .push_back((key, marker_payload_from_cot(&event)));
        flush_pending_cot(client, state)?;
    }
    Ok(())
}

fn flush_pending_cot(
    client: &RchNorthboundClient,
    state: &mut BridgeState,
) -> Result<(), Box<dyn std::error::Error>> {
    while let Some((key, payload)) = state.pending_cot.front() {
        let idempotency_key = format!("rch-tak-cot:{:x}", Sha256::digest(key.as_bytes()));
        client.post_json_idempotent("/api/markers", payload, &idempotency_key)?;
        state.cot.insert(key.clone());
        state.pending_cot.pop_front();
    }
    Ok(())
}

pub(super) fn location_snapshot_from_entry(
    entry: &Value,
) -> Option<(LocationSnapshot, Option<String>, String)> {
    let location = entry.get("telemetry")?.get("location")?;
    let timestamp = entry.get("timestamp")?.as_i64()?;
    let peer = entry.get("peer_destination")?.as_str()?.to_string();
    let label = entry
        .get("identity_label")
        .and_then(Value::as_str)
        .or_else(|| entry.get("display_name").and_then(Value::as_str))
        .map(ToOwned::to_owned);
    let key = format!("{peer}:{timestamp}");
    Some((
        LocationSnapshot {
            latitude: json_f64(location, "latitude")?,
            longitude: json_f64(location, "longitude")?,
            altitude: json_f64(location, "altitude").unwrap_or(0.0),
            speed: json_f64(location, "speed").unwrap_or(0.0),
            bearing: json_f64(location, "bearing").unwrap_or(0.0),
            accuracy: json_f64(location, "accuracy").unwrap_or(0.0),
            updated_at: DateTime::from_timestamp(timestamp, 0)?,
            peer_hash: Some(peer),
        },
        label,
        key,
    ))
}

fn chat_input_from_message(message: &Value) -> Option<ChatEventInput> {
    let content = message.get("Content")?.as_str()?.trim();
    if content.is_empty() {
        return None;
    }
    let timestamp = message
        .get("CreatedAt")
        .and_then(Value::as_str)
        .and_then(|value| DateTime::parse_from_rfc3339(value).ok())
        .map_or_else(Utc::now, |value| value.with_timezone(&Utc));
    Some(ChatEventInput {
        content: content.to_string(),
        sender_label: "RCH".to_string(),
        topic_id: message
            .get("TopicID")
            .and_then(Value::as_str)
            .map(ToOwned::to_owned),
        source_hash: None,
        timestamp,
        message_uuid: message
            .get("MessageID")
            .and_then(Value::as_str)
            .map(ToOwned::to_owned),
    })
}

pub(super) fn marker_payload_from_cot(event: &TakInboundCotEvent) -> Value {
    let symbol = marker_symbol_for_cot_type(event.event_type.as_str());
    json!({
        "type": symbol,
        "symbol": symbol,
        "name": event.uid,
        "category": "tak",
        "lat": event.point.lat,
        "lon": event.point.lon,
        "notes": format!(
            "TAK CoT type={} how={} hae={} ce={} le={}",
            event.event_type, event.how, event.point.hae, event.point.ce, event.point.le
        )
    })
}

fn marker_symbol_for_cot_type(event_type: &str) -> &'static str {
    if event_type.contains("-h-") || event_type.starts_with("a-h") {
        "hostile"
    } else if event_type.contains("-n-") || event_type.starts_with("a-n") {
        "neutral"
    } else if event_type.contains("-u-") || event_type.starts_with("a-u") {
        "unknown"
    } else if event_type.contains("-f-") || event_type.starts_with("a-f") {
        "friendly"
    } else {
        "marker"
    }
}

fn json_f64(value: &Value, key: &str) -> Option<f64> {
    match value.get(key)? {
        Value::Number(number) => number.as_f64(),
        Value::String(text) => text.parse::<f64>().ok(),
        _ => None,
    }
}
