use super::{
    ApiError, AppState, ProtocolEnvelope, Value, json, record_system_event_best_effort,
    sha256_lower_hex, unix_now_ms,
};

pub(crate) fn recover_history(
    state: &AppState,
    source: &str,
    mut fetch_page: impl FnMut(
        Option<String>,
    ) -> Result<r3akt_transport_rns::LxmfMessageHistoryPage, ApiError>,
) -> Result<usize, ApiError> {
    let mut cursor = None;
    let mut recovered = 0_usize;
    for _ in 0..100 {
        let page = fetch_page(cursor.clone())?;
        for message in &page.messages {
            if !is_inbound_to_source(&message.direction, &message.destination, source) {
                continue;
            }
            let value = serde_json::to_value(message)
                .map_err(|error| ApiError::Internal(error.to_string()))?;
            if import_message(state, &value, source)? {
                recovered = recovered.saturating_add(1);
            }
        }
        let next_cursor = page.next_cursor;
        if next_cursor.is_none() || next_cursor == cursor {
            break;
        }
        cursor = next_cursor;
    }
    Ok(recovered)
}

pub(crate) fn import_message(
    state: &AppState,
    message: &Value,
    source: &str,
) -> Result<bool, ApiError> {
    let direction = message
        .get("direction")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let destination = message
        .get("destination")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if !is_inbound_to_source(direction, destination, source) {
        return Ok(false);
    }
    let Some(envelope) = decode_message_or_quarantine(state, message, source)? else {
        return Ok(false);
    };
    if super::reticulumd_inbound_was_already_processed(state, &envelope)? {
        return Ok(false);
    }
    super::process_reticulumd_inbound_envelope(state, &envelope)?;
    super::record_reticulumd_inbound_worker_received(state, &envelope);
    Ok(true)
}

fn is_inbound_to_source(direction: &str, destination: &str, source: &str) -> bool {
    (direction.eq_ignore_ascii_case("in") || direction.eq_ignore_ascii_case("inbound"))
        && destination.eq_ignore_ascii_case(source)
}

pub(crate) fn decode_event_or_quarantine(
    state: &AppState,
    event: &r3akt_transport_rns::ReticulumdEventRecord,
    source: &str,
) -> Result<Option<ProtocolEnvelope>, ApiError> {
    let quarantine_key = format!("event:{}", event.event_id);
    if quarantine_was_recorded(state, &quarantine_key)? {
        return Ok(None);
    }
    match r3akt_transport_rns::reticulumd_event_to_envelope(event, source) {
        Ok(envelope) => Ok(envelope),
        Err(error) => handle_decode_error(
            state,
            &quarantine_key,
            source,
            Some(event.event_id.as_str()),
            event_message_id(event),
            error.to_string().as_str(),
        ),
    }
}

pub(crate) fn decode_message_or_quarantine(
    state: &AppState,
    message: &Value,
    source: &str,
) -> Result<Option<ProtocolEnvelope>, ApiError> {
    let quarantine_key = message_quarantine_key(message, source);
    if quarantine_was_recorded(state, &quarantine_key)? {
        return Ok(None);
    }
    match r3akt_transport_rns::reticulumd_message_to_envelope(message, source) {
        Ok(envelope) => Ok(envelope),
        Err(error) => handle_decode_error(
            state,
            &quarantine_key,
            source,
            None,
            message_id(message),
            error.to_string().as_str(),
        ),
    }
}

fn handle_decode_error(
    state: &AppState,
    quarantine_key: &str,
    source: &str,
    event_id: Option<&str>,
    message_id: Option<&str>,
    error: &str,
) -> Result<Option<ProtocolEnvelope>, ApiError> {
    if !is_malformed_field_commands_error(error) {
        return Err(ApiError::Internal(error.to_string()));
    }
    quarantine_message(state, quarantine_key, source, event_id, message_id, error)?;
    Ok(None)
}

fn is_malformed_field_commands_error(error: &str) -> bool {
    error.contains("malformed LXMF FIELD_COMMANDS (0x09)")
}

fn event_message_id(event: &r3akt_transport_rns::ReticulumdEventRecord) -> Option<&str> {
    event
        .message_id
        .as_deref()
        .filter(|value| !value.trim().is_empty())
        .or_else(|| event.payload.get("message").and_then(message_id))
}

fn message_id(message: &Value) -> Option<&str> {
    ["id", "message_id", "messageId"].iter().find_map(|key| {
        message
            .get(*key)
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
    })
}

fn message_quarantine_key(message: &Value, source: &str) -> String {
    message_id(message).map_or_else(
        || {
            format!(
                "message:{source}:sha256:{}",
                sha256_lower_hex(message.to_string().as_bytes())
            )
        },
        |message_id| format!("message:{source}:{message_id}"),
    )
}

fn quarantine_was_recorded(state: &AppState, quarantine_key: &str) -> Result<bool, ApiError> {
    let events = state
        .system_events
        .read()
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    Ok(events.iter().any(|event| {
        event.event_type == "reticulumd_inbound_message_quarantined"
            && event.metadata.get("quarantine_key").and_then(Value::as_str) == Some(quarantine_key)
    }))
}

fn quarantine_message(
    state: &AppState,
    quarantine_key: &str,
    source: &str,
    event_id: Option<&str>,
    message_id: Option<&str>,
    error: &str,
) -> Result<(), ApiError> {
    if quarantine_was_recorded(state, quarantine_key)? {
        return Ok(());
    }
    record_system_event_best_effort(
        state,
        "reticulumd_inbound_message_quarantined",
        "Malformed LXMF inbound message quarantined",
        json!({
            "quarantine_key": quarantine_key,
            "source": source,
            "event_id": event_id,
            "message_id": message_id,
            "error": error,
        }),
    );
    if let Ok(mut stats) = state.reticulumd_inbound_worker_stats.write() {
        stats.quarantined_total = stats.quarantined_total.saturating_add(1);
        stats.error_total = stats.error_total.saturating_add(1);
        stats.last_poll_ts_ms = Some(unix_now_ms());
        stats.last_error = Some(format!("reticulumd inbound message quarantined: {error}"));
        stats.last_quarantine_error = Some(error.to_string());
    }
    Ok(())
}
