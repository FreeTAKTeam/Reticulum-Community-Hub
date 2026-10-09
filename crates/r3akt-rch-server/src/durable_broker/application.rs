use super::envelope::apply_envelope;
use super::{
    ApiError, AppState, ClientRecord, MarkerRecord, OutboundMessageRecord, SubscriberRecord,
    TopicRecord, Value, ZoneRecord, bound_presentation, broadcast_message_event,
    broadcast_system_event, broadcast_telemetry_event, ensure_kill_switch_persistence_unlocked,
    json, normalize_identity_key, open, storage,
};
pub(super) fn apply(state: &AppState, consumer: &str) -> Result<bool, ApiError> {
    let _quiescence = state
        .broker_work_gate
        .read()
        .map_err(|e| ApiError::Internal(e.to_string()))?;
    ensure_kill_switch_persistence_unlocked(state)?;
    let mut store = open(state)?;
    let Some(event) = store.next_inbox_event(consumer).map_err(storage)? else {
        return Ok(false);
    };
    if event.version != 1
        || !matches!(
            event.event_type.as_str(),
            "inbound" | "bootstrap_message" | "receipt" | "outbound"
        )
    {
        store
            .mark_inbox_upgrade_required(consumer, event.position, "unknown required event type")
            .map_err(storage)?;
        return Err(ApiError::ServiceUnavailable(format!(
            "upgrade required at inbox position {}",
            event.position
        )));
    }
    // Same lock order as HTTP writers: projections precede the SQLite write reservation.
    let mut markers = state
        .markers
        .write()
        .map_err(|e| ApiError::Internal(e.to_string()))?;
    let mut zones = state
        .zones
        .write()
        .map_err(|e| ApiError::Internal(e.to_string()))?;
    let mut clients = state
        .clients
        .write()
        .map_err(|e| ApiError::Internal(e.to_string()))?;
    let mut topics = state
        .topics
        .write()
        .map_err(|e| ApiError::Internal(e.to_string()))?;
    let mut subscribers = state
        .subscribers
        .write()
        .map_err(|e| ApiError::Internal(e.to_string()))?;
    let mut messages = state
        .messages
        .write()
        .map_err(|e| ApiError::Internal(e.to_string()))?;
    let mut system_events = state
        .system_events
        .write()
        .map_err(|e| ApiError::Internal(e.to_string()))?;
    let mut telemetry_records = state
        .telemetry_records
        .write()
        .map_err(|e| ApiError::Internal(e.to_string()))?;
    let mut unit = store
        .begin_inbox_application(consumer, &event, false)
        .map_err(storage)?;
    let mut published = Vec::new();
    let mut telemetry = Vec::new();
    let mut system_event_count = 1_usize;
    match event.event_type.as_str() {
        "outbound" => {
            if let (Some(operation), Some(id)) = (
                event.payload.get("operation_id").and_then(Value::as_str),
                event.payload.pointer("/message/id").and_then(Value::as_str),
            ) {
                if let Some(message) = unit
                    .stage_operation_admission(operation, id)
                    .map_err(storage)?
                {
                    published.push(OutboundMessageRecord::from(message));
                }
            } else {
                unit.reject("malformed supported outbound admission event")
                    .map_err(storage)?;
            }
        }
        "receipt" => {
            if let (Some(id), Some(status)) = (
                event.payload.get("message_id").and_then(Value::as_str),
                event.payload.get("status").and_then(Value::as_str),
            ) {
                match unit.stage_broker_receipt(id, status) {
                    Ok(Some(message)) => published.push(message.into()),
                    Ok(None) => {}
                    Err(r3akt_rch_core::RchCoreError::InvalidPayload(reason)) => {
                        unit.reject(&reason).map_err(storage)?;
                    }
                    Err(error) => return Err(storage(error)),
                }
            } else {
                unit.reject("malformed supported receipt event")
                    .map_err(storage)?;
            }
        }
        "inbound" | "bootstrap_message" => {
            let message = event.payload.get("message").unwrap_or(&Value::Null);
            let source = state.reticulumd_source.as_deref().ok_or_else(|| {
                ApiError::ServiceUnavailable("RCH service destination required".into())
            })?;
            match r3akt_transport_rns::reticulumd_message_to_payloads(message, source) {
                Err(error) => unit
                    .reject(&format!("malformed supported inbound: {error}"))
                    .map_err(storage)?,
                Ok(decoded) => {
                    if !decoded.command_diagnostics.is_empty() {
                        system_event_count += 1;
                        let diagnostic = decoded.command_diagnostics.join("; ");
                        if decoded.envelopes.is_empty() {
                            unit.reject(&diagnostic).map_err(storage)?;
                        }
                        unit.stage_system_event(&r3akt_rch_core::SystemEventRecord {
                            event_id: format!("broker:{}:commands", unit.inbox_event_key().map_err(storage)?),
                            event_type: "lxmf_command_diagnostic".into(),
                            message: diagnostic,
                            timestamp_ms: event.created_at.saturating_mul(1000),
                            metadata: json!({"position":event.position,"valid_payloads":decoded.envelopes.len()}),
                        }).map_err(storage)?;
                    }
                    if let Some(first) = decoded.envelopes.first() {
                        let logical = format!(
                            "lxmf:{}",
                            message
                                .get("id")
                                .and_then(Value::as_str)
                                .unwrap_or(&first.id.to_string())
                        );
                        let immutable = json!({"source":normalize_identity_key(first.source.as_str()),"destination":message.get("destination"),"title":message.get("title"),"content":message.get("content"),"timestamp":message.get("timestamp"),"fields":message.get("fields")});
                        if unit
                            .claim_logical_input(first.source.as_str(), &logical, &immutable)
                            .map_err(storage)?
                        {
                            for envelope in &decoded.envelopes {
                                if event.event_type != "bootstrap_message"
                                    && matches!(&envelope.payload, super::Payload::Command(command) if command.name == "telemetry.collect")
                                {
                                    system_event_count += 1;
                                }
                                apply_envelope(
                                    &mut unit,
                                    &event,
                                    envelope,
                                    event.event_type == "bootstrap_message",
                                    &mut published,
                                    &mut telemetry,
                                    state.outbound_identity_allowlist.as_deref(),
                                )?;
                            }
                        }
                    }
                }
            }
        }
        other => {
            return Err(ApiError::ServiceUnavailable(format!(
                "upgrade required: ordered inbox paused at {} for event {other}",
                event.position
            )));
        }
    }
    let system_event = r3akt_rch_core::SystemEventRecord {
        event_id: format!("broker:{}", unit.inbox_event_key().map_err(storage)?),
        event_type: "durable_broker_handled".into(),
        message: event.event_type.clone(),
        timestamp_ms: event.created_at.saturating_mul(1000),
        metadata: json!({"position":event.position}),
    };
    unit.stage_system_event(&system_event).map_err(storage)?;
    let after = unit.commit().map_err(storage)?;
    if matches!(event.event_type.as_str(), "inbound" | "bootstrap_message") {
        *markers = after
            .markers
            .into_iter()
            .map(|r| (r.object_destination_hash.clone(), MarkerRecord::from(r)))
            .collect();
        *zones = after
            .zones
            .into_iter()
            .map(|r| (r.zone_id.clone(), ZoneRecord::from(r)))
            .collect();
        *clients = after
            .clients
            .into_iter()
            .map(|r| {
                (
                    normalize_identity_key(&r.identity).unwrap_or_else(|| r.identity.clone()),
                    ClientRecord::from(r),
                )
            })
            .collect();
        *topics = after
            .topics
            .into_iter()
            .map(|r| (r.topic_id.clone(), TopicRecord::from(r)))
            .collect();
        *subscribers = after
            .subscribers
            .into_iter()
            .map(|r| {
                let r = SubscriberRecord::from(r);
                (r.subscriber_id.clone(), r)
            })
            .collect();
    }
    for record in &published {
        if let Some(existing) = messages
            .iter_mut()
            .find(|m| m.message_id == record.message_id)
        {
            *existing = record.clone();
        } else {
            messages.push(record.clone());
        }
    }
    bound_presentation(&mut messages);
    // Read only the bounded number of diagnostics staged by this input, rather
    // than decoding the presentation history on every ordinary upload/message.
    let committed_events = store
        .list_system_events_page(system_event_count.min(200), 0)
        .map_err(storage)?;
    let new_events = committed_events
        .iter()
        .filter(|event| {
            !system_events
                .iter()
                .any(|old| old.event_id == event.event_id)
        })
        .cloned()
        .collect::<Vec<_>>();
    for event in new_events.iter().rev() {
        system_events.push(event.clone());
    }
    if system_events.len() > 200 {
        let excess = system_events.len() - 200;
        system_events.drain(..excess);
    }
    for record in &telemetry {
        telemetry_records.retain(|old| {
            !old.peer_destination
                .eq_ignore_ascii_case(&record.peer_destination)
        });
        telemetry_records.push(record.clone());
    }
    drop(telemetry_records);
    drop(system_events);
    drop(messages);
    drop(subscribers);
    drop(topics);
    drop(clients);
    drop(zones);
    drop(markers);
    for event in new_events.into_iter().rev() {
        broadcast_system_event(state, &event);
    }
    for record in telemetry {
        broadcast_telemetry_event(state, &record);
    }
    for record in published {
        broadcast_message_event(state, &record);
    }
    Ok(true)
}
