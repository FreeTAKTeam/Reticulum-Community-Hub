use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SubscriberRecord {
    pub node_id: String,
    pub topic_id: String,
    pub first_seen_ts_ms: i64,
    pub last_seen_ts_ms: i64,
    #[serde(default)]
    pub reject_tests: Option<i64>,
    pub metadata: Value,
    /// Northbound ID; mesh subscription commands retain destination addressing.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub subscriber_id: Option<String>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn legacy_compact_messagepack_preserves_field_order() {
        let old = (
            "peer",
            "ops",
            1_i64,
            2_i64,
            Some(1_i64),
            serde_json::json!({"role":"field"}),
        );
        let bytes = rmp_serde::to_vec(&old).unwrap();
        let decoded: SubscriberRecord = rmp_serde::from_slice(&bytes).unwrap();
        assert_eq!(decoded.node_id, "peer");
        assert_eq!(decoded.topic_id, "ops");
        assert_eq!(decoded.metadata, old.5);
        assert_eq!(decoded.subscriber_id, None);
        let mut current = decoded;
        current.subscriber_id = Some("subscription-id".into());
        let bytes = rmp_serde::to_vec(&current).unwrap();
        assert_eq!(
            rmp_serde::from_slice::<SubscriberRecord>(&bytes).unwrap(),
            current
        );
    }
}
