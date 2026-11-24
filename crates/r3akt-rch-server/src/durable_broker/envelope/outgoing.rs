use super::{
    ApiError, CoreMessageRecord, DeliveryMode, DurableOutboundIntent, InboxEvent,
    OutboundMessageRecord, ProtocolEnvelope, RchCommandTransaction, Value, json, sha256_lower_hex,
    storage,
};

pub(crate) fn outgoing(
    unit: &RchCommandTransaction<'_>,
    _event: &InboxEvent,
    destination: &str,
    content: &str,
    fields: Value,
    created: i64,
) -> Result<OutboundMessageRecord, ApiError> {
    let mut fields = fields;
    let sensor_policy = fields
        .as_object_mut()
        .and_then(|f| f.remove("_r3s_relay_policy"));
    let index = unit.staged_outbound_intent_count();
    let operation = sha256_lower_hex(
        format!(
            "{}:{index}:{destination}",
            unit.inbox_event_key().map_err(storage)?
        )
        .as_bytes(),
    );
    let record = OutboundMessageRecord {
        message_id: operation.clone(),
        topic_id: None,
        destination: Some(destination.into()),
        sender: "r3akt-rch-server".into(),
        content: content.into(),
        delivery_mode: DeliveryMode::Targeted,
        delivery_method: "durable_broker".into(),
        delivery_policy_reason: "inbox_application".into(),
        delivery_state: "broker_pending".into(),
        delivery_metadata: json!({"direction":"outbound","lxmf_fields":fields,"r3s_policy":sensor_policy}),
        created_ts_ms: created,
        attachments: Vec::new(),
    };
    unit.stage_outbound_intent(&DurableOutboundIntent {operation_id:operation.clone(),message:CoreMessageRecord::from(record.clone()),request:json!({"identity":"","operation_id":operation,"destination":destination,"title":"RCH","content":content,"fields":fields,"options":{"method":"direct","try_propagation_on_fail":true}})}).map_err(|error| match error {
        r3akt_rch_core::RchCoreError::InvalidPayload(reason) => ApiError::BadRequest(reason),
        error => storage(error),
    })?;
    Ok(record)
}

/// One plain-text reply to the envelope's sender (`/help`, `/time`).
pub(crate) fn reply_text(
    unit: &RchCommandTransaction<'_>,
    event: &InboxEvent,
    envelope: &ProtocolEnvelope,
    text: &str,
    published: &mut Vec<OutboundMessageRecord>,
) -> Result<(), ApiError> {
    let created = envelope.timestamp.timestamp_millis();
    let source = envelope.source.as_str();
    published.push(outgoing(unit, event, source, text, json!({}), created)?);
    Ok(())
}

/// REM stores events only from the `log_entry.upsert` command, never from the upserted
/// result event, so log entries are relayed in the REST fanout command shape.
pub(crate) fn rem_log_relay(
    unit: &mut RchCommandTransaction<'_>,
    envelope: &ProtocolEnvelope,
    event: Option<&Value>,
) -> Option<Value> {
    let event = event?;
    if !matches!(
        event["event_type"].as_str(),
        Some("mission.registry.log_entry.upserted" | "mission.log_entry.upserted")
    ) {
        return None;
    }
    let mut log = event["payload"].as_object()?.clone();
    if !log.get("callsign").is_some_and(Value::is_string) {
        let name = super::super::chat_presentation::relay_sender_label(
            unit.core_mut(),
            None,
            envelope.source.as_str(),
        );
        log.insert("callsign".into(), json!(name));
    }
    crate::rem_log_entry_command_fields(
        &log,
        "",
        &envelope.id.to_string(),
        envelope.source.as_str(),
    )
}
