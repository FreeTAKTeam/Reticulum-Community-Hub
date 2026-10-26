use super::{
    ApiError, AppState, CoreSubscriberRecord, HashMap, SubscriberPayload, SubscriberRecord, Uuid,
    json, persist_subscriber_row, replace_subscriber_row, sha256_lower_hex, unix_now_ms,
};

fn legacy_id(destination: &str, topic: &str) -> String {
    sha256_lower_hex(format!("{}:{destination}:{topic}", destination.len()).as_bytes())
}

pub(super) fn get(
    records: &HashMap<String, SubscriberRecord>,
    id: &str,
) -> Result<SubscriberRecord, ApiError> {
    if let Some(record) = records.get(id) {
        return Ok(record.clone());
    }
    // Preserve unambiguous destination IDs used by older persisted subscriptions.
    let mut aliases = records.values().filter(|record| {
        record.destination == id
            && record.subscriber_id == legacy_id(&record.destination, &record.topic_id)
    });
    match (aliases.next(), aliases.next()) {
        (Some(record), None) => Ok(record.clone()),
        (Some(_), Some(_)) => Err(ApiError::Conflict(
            "Destination has multiple subscriptions; use SubscriberID".into(),
        )),
        _ => Err(ApiError::NotFound(format!("Subscriber not found: {id}"))),
    }
}

pub(super) fn create(
    state: &AppState,
    payload: SubscriberPayload,
    prefer_destination_id: bool,
) -> Result<SubscriberRecord, ApiError> {
    let destination = payload
        .destination
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| ApiError::BadRequest("Subscriber destination is required".into()))?;
    let topic_id = payload.topic_id.unwrap_or_default();
    let mut records = state
        .subscribers
        .write()
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    let subscriber_id = payload
        .subscriber_id
        .filter(|value| !value.trim().is_empty())
        .or_else(|| {
            records
                .values()
                .find(|record| record.destination == destination && record.topic_id == topic_id)
                .map(|record| record.subscriber_id.clone())
        })
        .unwrap_or_else(|| {
            if prefer_destination_id && !records.contains_key(&destination) {
                destination.clone()
            } else {
                Uuid::new_v4().simple().to_string()
            }
        });
    let record = SubscriberRecord {
        subscriber_id,
        destination,
        topic_id,
        reject_tests: payload.reject_tests,
        metadata: payload.metadata.unwrap_or_else(|| json!({})),
    };
    save(state, &mut records, record)
}

pub(super) fn save(
    state: &AppState,
    records: &mut HashMap<String, SubscriberRecord>,
    record: SubscriberRecord,
) -> Result<SubscriberRecord, ApiError> {
    if let Some(previous) = records.get(&record.subscriber_id) {
        replace_subscriber_row(state, previous, &record)?;
    } else {
        persist_subscriber_row(state, &record)?;
    }
    // SQLite owns one row per destination/topic pair, including explicit ID replacements.
    records.retain(|_, previous| {
        previous.destination != record.destination || previous.topic_id != record.topic_id
    });
    records.insert(record.subscriber_id.clone(), record.clone());
    Ok(record)
}

impl From<CoreSubscriberRecord> for SubscriberRecord {
    fn from(subscriber: CoreSubscriberRecord) -> Self {
        // Old payloads have no HTTP ID; derive one from both persisted keys.
        let subscriber_id = subscriber
            .subscriber_id
            .unwrap_or_else(|| legacy_id(&subscriber.node_id, &subscriber.topic_id));
        Self {
            subscriber_id,
            destination: subscriber.node_id,
            topic_id: subscriber.topic_id,
            reject_tests: subscriber.reject_tests,
            metadata: subscriber.metadata,
        }
    }
}

impl From<SubscriberRecord> for CoreSubscriberRecord {
    fn from(subscriber: SubscriberRecord) -> Self {
        let now_ms = unix_now_ms();
        Self {
            subscriber_id: Some(subscriber.subscriber_id),
            node_id: subscriber.destination,
            topic_id: subscriber.topic_id,
            first_seen_ts_ms: now_ms,
            last_seen_ts_ms: now_ms,
            reject_tests: subscriber.reject_tests,
            metadata: subscriber.metadata,
        }
    }
}

#[cfg(test)]
mod tests;
