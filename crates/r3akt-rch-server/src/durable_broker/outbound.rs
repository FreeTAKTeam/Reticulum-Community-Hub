use super::{
    ApiError, AppState, CoreMessageRecord, DurableOutboundIntent, OutboundMessageRecord,
    RchCommandTransaction, Value, broadcast_message_event, broker,
    ensure_kill_switch_persistence_unlocked, json, merge_delivery_metadata, open,
    outbound_destination_text_only, outbound_destinations, outbound_identity_allowed,
    outbound_lxmf_content, outbound_lxmf_fields, outbound_lxmf_title, plane,
    record_system_event_best_effort, sha256_lower_hex, storage,
};
#[cfg(test)]
pub(super) fn dispatch(state: &AppState) -> Result<bool, ApiError> {
    let _quiescence = state
        .broker_work_gate
        .read()
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    ensure_kill_switch_persistence_unlocked(state)?;
    let mut store = open(state)?;
    dispatch_with_store(state, &mut store)
}

pub(super) fn dispatch_with_store(
    state: &AppState,
    store: &mut r3akt_rch_core::RchSqliteStore,
) -> Result<bool, ApiError> {
    ensure_kill_switch_persistence_unlocked(state)?;
    let Some(intent) = store.pending_broker_intent().map_err(storage)? else {
        return Ok(false);
    };
    let destination = intent
        .request
        .get("destination")
        .and_then(Value::as_str)
        .ok_or_else(|| ApiError::Internal("intent lacks destination".into()))?
        .to_string();
    if !outbound_identity_allowed(state, &destination, &destination) {
        reject_dispatch(
            state,
            store,
            &intent.operation_id,
            "current destination authorization rejected this intent",
        )?;
        return Ok(true);
    }
    if !super::sensor_telemetry::dispatch_allowed(
        store,
        &destination,
        intent.request.get("fields").unwrap_or(&Value::Null),
        intent
            .message
            .delivery_metadata
            .get("r3s_policy")
            .unwrap_or(&Value::Null),
        state.outbound_identity_allowlist.as_deref(),
    )? {
        reject_dispatch(
            state,
            store,
            &intent.operation_id,
            "sensor source, team or snapshot is no longer current",
        )?;
        return Ok(true);
    }
    let plane = plane(state)?;
    let receipt = plane
        .broker_reconcile(broker::ReconcileRequest {
            identity: String::new(),
            operation_id: intent.operation_id.clone(),
        })
        .map_err(|e| ApiError::ServiceUnavailable(e.to_string()))?;
    let receipt = match receipt {
        Some(receipt) => receipt,
        None => match plane.broker_admit(
            serde_json::from_value(intent.request)
                .map_err(|e| ApiError::Internal(e.to_string()))?,
        ) {
            Ok(receipt) => receipt,
            Err(r3akt_transport_rns::TransportError::Sdk { code, message, .. })
                if code.starts_with("SDK_VALIDATION_")
                    || matches!(
                        code.as_str(),
                        "SDK_SECURITY_SOURCE_FORBIDDEN"
                            | "SDK_SECURITY_IDENTITY_FORBIDDEN"
                            | "SDK_BROKER_OPERATION_CONFLICT"
                    ) =>
            {
                reject_dispatch(
                    state,
                    store,
                    &intent.operation_id,
                    &format!("{code}: {message}"),
                )?;
                return Ok(true);
            }
            Err(error) => return Err(ApiError::ServiceUnavailable(error.to_string())),
        },
    };
    let mut messages = state
        .messages
        .write()
        .map_err(|e| ApiError::Internal(e.to_string()))?;
    let record = OutboundMessageRecord::from(
        store
            .record_broker_admission(&receipt.operation_id, &receipt.message_id)
            .map_err(storage)?,
    );
    if let Some(existing) = messages
        .iter_mut()
        .find(|m| m.message_id == record.message_id)
    {
        *existing = record.clone();
    } else {
        messages.push(record.clone());
    }
    super::super::message_residency::bound(state, &mut messages, &[&record.message_id])?;
    drop(messages);
    broadcast_message_event(state, &record);
    Ok(true)
}

/// Python RCH accepts a northbound send that has no authorized recipients and
/// records it as failed with `drop_reason: no_recipients`; keep that contract.
fn record_without_recipients(
    state: &AppState,
    mut message: OutboundMessageRecord,
) -> Result<OutboundMessageRecord, ApiError> {
    message.delivery_method = "durable_broker".into();
    message.delivery_state = "failed".into();
    merge_delivery_metadata(
        &mut message.delivery_metadata,
        json!({"dispatch_status":"failed","drop_reason":"no_recipients","acked":false,"fanout_count":0,"targeted_recipient_count":0,"receipt_pending":false,"retry_scheduled":false}),
    );
    let mut messages = state
        .messages
        .write()
        .map_err(|e| ApiError::Internal(e.to_string()))?;
    let mut store = open(state)?;
    let unit = store.begin_outbound_application().map_err(storage)?;
    unit.stage_message(&CoreMessageRecord::from(message.clone()))
        .map_err(storage)?;
    unit.commit().map_err(storage)?;
    messages.push(message.clone());
    super::super::message_residency::bound(state, &mut messages, &[&message.message_id])?;
    drop(messages);
    broadcast_message_event(state, &message);
    record_message_sent(state, &message);
    record_system_event_best_effort(
        state,
        "message_failed",
        "Message failed",
        json!({
            "message_id": message.message_id,
            "topic_id": message.topic_id,
            "destination": message.destination,
            "drop_reason": "no_recipients",
        }),
    );
    Ok(message)
}

/// Northbound and inbound-generated replies share the same persisted operation admission owner.
pub(crate) fn queue_northbound(
    state: &AppState,
    mut message: OutboundMessageRecord,
) -> Result<OutboundMessageRecord, ApiError> {
    let _quiescence = state
        .broker_work_gate
        .read()
        .map_err(|e| ApiError::Internal(e.to_string()))?;
    ensure_kill_switch_persistence_unlocked(state)?;
    let destinations = outbound_destinations(state, &message)?;
    if destinations.is_empty() {
        return record_without_recipients(state, message);
    }
    let destinations = destinations
        .into_iter()
        .map(|destination| {
            let text_only = outbound_destination_text_only(state, &destination);
            (destination, text_only)
        })
        .collect::<Vec<_>>();
    let mut messages = state
        .messages
        .write()
        .map_err(|e| ApiError::Internal(e.to_string()))?;
    let mut store = open(state)?;
    let unit = store.begin_outbound_application().map_err(storage)?;
    message = stage_business_message(&unit, message, destinations)?;
    unit.commit().map_err(storage)?;
    messages.push(message.clone());
    super::super::message_residency::bound(state, &mut messages, &[&message.message_id])?;
    drop(messages);
    broadcast_message_event(state, &message);
    record_message_sent(state, &message);
    Ok(message)
}

/// Python RCH logs `message_sent` for every recorded outbound message.
fn record_message_sent(state: &AppState, message: &OutboundMessageRecord) {
    record_system_event_best_effort(
        state,
        "message_sent",
        "Message sent from hub",
        json!({
            "message_id": message.message_id,
            "topic_id": message.topic_id,
            "destination": message.destination,
            "delivery_method": message.delivery_method,
            "delivery_state": message.delivery_state,
        }),
    );
}

pub(super) fn stage_business_message(
    unit: &RchCommandTransaction<'_>,
    mut message: OutboundMessageRecord,
    destinations: Vec<(String, bool)>,
) -> Result<OutboundMessageRecord, ApiError> {
    if destinations.is_empty() {
        return Err(ApiError::BadRequest(
            "no authorized delivery recipients".into(),
        ));
    }
    let fields = outbound_lxmf_fields(
        &message,
        message
            .delivery_metadata
            .get("lxmf_fields")
            .cloned()
            .unwrap_or_else(|| json!({})),
    );
    let title = outbound_lxmf_title(&message);
    let content = outbound_lxmf_content(&message);
    let bytes = fields
        .to_string()
        .len()
        .saturating_add(title.len())
        .saturating_add(content.len())
        .saturating_add(4096);
    if destinations
        .len()
        .saturating_add(unit.staged_outbound_intent_count())
        > 256
        || bytes.saturating_mul(destinations.len()) > 32 * 1024 * 1024
    {
        return Err(ApiError::BadRequest(
            "durable northbound fanout count/byte limit exceeded before admission".into(),
        ));
    }
    let title = title.to_owned();
    let content = content.to_owned();
    message.delivery_method = "durable_broker".into();
    message.delivery_state = "broker_pending".into();
    merge_delivery_metadata(
        &mut message.delivery_metadata,
        json!({"dispatch_status":"broker_pending","receipt_pending":!destinations.is_empty(),"retry_scheduled":false,"reticulumd_dispatch_count":0,"acked":false}),
    );
    unit.stage_message(&CoreMessageRecord::from(message.clone()))
        .map_err(storage)?;
    for (destination, text_only) in destinations {
        let operation =
            sha256_lower_hex(format!("northbound:{}:{destination}", message.message_id).as_bytes());
        let mut fields = fields.clone();
        if text_only && let Some(fields) = fields.as_object_mut() {
            for key in ["5", "0x05", "attachments", "FIELD_ATTACHMENTS"] {
                fields.remove(key);
            }
        }
        let intent = DurableOutboundIntent {
            operation_id: operation.clone(),
            message: CoreMessageRecord::from(message.clone()),
            request: json!({"identity":"","operation_id":operation,"destination":destination,"title":title,"content":content,"fields":fields,"options":{"method":"direct","try_propagation_on_fail":true}}),
        };
        unit.stage_outbound_intent(&intent)
            .map_err(|error| match error {
                r3akt_rch_core::RchCoreError::InvalidPayload(reason) => {
                    ApiError::BadRequest(reason)
                }
                error => storage(error),
            })?;
    }
    Ok(message)
}

fn reject_dispatch(
    state: &AppState,
    store: &mut r3akt_rch_core::RchSqliteStore,
    operation: &str,
    reason: &str,
) -> Result<(), ApiError> {
    let mut messages = state
        .messages
        .write()
        .map_err(|e| ApiError::Internal(e.to_string()))?;
    let record = OutboundMessageRecord::from(
        store
            .reject_broker_intent(operation, reason)
            .map_err(storage)?,
    );
    if let Some(existing) = messages
        .iter_mut()
        .find(|m| m.message_id == record.message_id)
    {
        *existing = record.clone();
    } else {
        messages.push(record.clone());
    }
    super::super::message_residency::bound(state, &mut messages, &[&record.message_id])?;
    drop(messages);
    broadcast_message_event(state, &record);
    Ok(())
}
