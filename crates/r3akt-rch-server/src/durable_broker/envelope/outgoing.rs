use super::{
    ApiError, CoreMessageRecord, DeliveryMode, DurableOutboundIntent, InboxEvent,
    OutboundMessageRecord, RchCommandTransaction, Value, json, sha256_lower_hex, storage,
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
