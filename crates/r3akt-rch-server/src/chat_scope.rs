#[cfg(test)]
use super::DeliveryMode;
use super::OutboundMessageRecord;

pub(super) fn message_scope(message: &OutboundMessageRecord) -> &'static str {
    r3akt_rch_core::chat_message_scope(
        &message.delivery_mode,
        &message.delivery_metadata,
        message.destination.as_deref(),
        message.topic_id.as_deref(),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn only_verified_group_history_overrides_delivery_mode() {
        let mut message = OutboundMessageRecord {
            message_id: "old-inbound".into(),
            topic_id: Some("direct".into()),
            destination: None,
            sender: "original-peer".into(),
            content: "hello".into(),
            delivery_mode: DeliveryMode::Targeted,
            delivery_method: "reticulumd_inbound".into(),
            delivery_policy_reason: "durable_broker".into(),
            delivery_state: "received".into(),
            delivery_metadata: json!({"direction":"inbound","reticulumd_inbound":true}),
            created_ts_ms: 0,
            attachments: vec![],
        };
        assert_eq!(message_scope(&message), "broadcast");
        message.topic_id = Some("ops".into());
        assert_eq!(message_scope(&message), "topic");
        message.destination = Some("private-peer".into());
        assert_eq!(message_scope(&message), "dm");
        message.destination = None;
        message.delivery_metadata = json!({"direction":"outbound"});
        assert_eq!(message_scope(&message), "dm");
        message.delivery_metadata = json!({"direction":"inbound"});
        assert_eq!(message_scope(&message), "dm");
        message.topic_id = None;
        message.delivery_metadata = json!({"direction":"inbound","reticulumd_inbound":true});
        assert_eq!(message_scope(&message), "dm");
        message.delivery_mode = DeliveryMode::Fanout;
        assert_eq!(message_scope(&message), "topic");
        message.delivery_mode = DeliveryMode::Broadcast;
        assert_eq!(message_scope(&message), "broadcast");
    }
}
