use super::{MessageRecord, RchCommandTransaction, RchCoreError, params};
use rusqlite::OptionalExtension;

impl RchCommandTransaction<'_> {
    pub fn stage_operation_admission(
        &self,
        operation: &str,
        daemon_id: &str,
    ) -> Result<Option<MessageRecord>, RchCoreError> {
        let row:Option<(String,Option<String>)>=self.transaction.query_row("SELECT message_id,daemon_message_id FROM rch_broker_dispatch WHERE operation_id=?1",[operation],|r|Ok((r.get(0)?,r.get(1)?))).optional()?;
        let Some((parent, previous)) = row else {
            return Ok(None);
        };
        if previous.as_ref().is_some_and(|p| p != daemon_id) {
            return Err(RchCoreError::RecoveryRequired(
                "operation admission has conflicting message identifier".into(),
            ));
        }
        self.transaction.execute("UPDATE rch_broker_dispatch SET state=CASE WHEN state='pending' THEN 'admitted' ELSE state END,daemon_message_id=?1 WHERE operation_id=?2",params![daemon_id,operation])?;
        self.aggregate_broker_message(&parent).map(Some)
    }
    pub fn stage_broker_receipt(
        &self,
        daemon_id: &str,
        status: &str,
    ) -> Result<Option<MessageRecord>, RchCoreError> {
        let row:Option<(String,String,String)>=self.transaction.query_row("SELECT operation_id,message_id,receipt_status FROM rch_broker_dispatch WHERE daemon_message_id=?1",[daemon_id],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?))).optional()?;
        let Some((operation, parent, prior)) = row else {
            return Ok(None);
        };
        let raw_status = status;
        let normalized = status.trim().to_ascii_lowercase();
        let status = if normalized.starts_with("failed") {
            "failed"
        } else if normalized.starts_with("sent") {
            "sent"
        } else {
            normalized.as_str()
        };
        if !matches!(
            status,
            "queued"
                | "sending"
                | "sent"
                | "delivered"
                | "failed"
                | "cancelled"
                | "expired"
                | "rejected"
        ) {
            return Err(RchCoreError::InvalidPayload(
                "unsupported broker receipt state".into(),
            ));
        }
        let terminal = |s: &str| {
            matches!(
                s,
                "delivered" | "failed" | "cancelled" | "expired" | "rejected"
            )
        };
        if !(terminal(&prior) || prior == "sent" && matches!(status, "queued" | "sending")) {
            self.transaction.execute("UPDATE rch_broker_dispatch SET receipt_status=?1,state=CASE WHEN ?2 THEN 'terminal' ELSE state END WHERE operation_id=?3",params![status,terminal(status),operation])?;
        }
        let mut message = self.aggregate_broker_message(&parent)?;
        message.delivery_metadata["last_broker_receipt"] =
            serde_json::json!(raw_status.chars().take(512).collect::<String>());
        self.stage_message(&message)?;
        Ok(Some(message))
    }
    pub fn stage_broker_rejection(
        &self,
        operation: &str,
        reason: &str,
    ) -> Result<MessageRecord, RchCoreError> {
        let parent: String = self.transaction.query_row(
            "SELECT message_id FROM rch_broker_dispatch WHERE operation_id=?1",
            [operation],
            |r| r.get(0),
        )?;
        self.transaction.execute("UPDATE rch_broker_dispatch SET state='terminal',receipt_status='rejected' WHERE operation_id=?1 AND state='pending'",[operation])?;
        let mut message = self.aggregate_broker_message(&parent)?;
        message.delivery_metadata["broker_rejection"] =
            serde_json::json!(reason.chars().take(512).collect::<String>());
        self.stage_message(&message)?;
        Ok(message)
    }
    fn aggregate_broker_message(&self, parent: &str) -> Result<MessageRecord, RchCoreError> {
        let mut message = self.message(parent)?.ok_or_else(|| {
            RchCoreError::RecoveryRequired("durable intent lost its parent message".into())
        })?;
        let mut statement=self.transaction.prepare("SELECT daemon_message_id,receipt_status,payload FROM rch_broker_dispatch WHERE message_id=?1 ORDER BY operation_id LIMIT 257")?;
        let rows = statement
            .query_map([parent], |r| {
                Ok((
                    r.get::<_, Option<String>>(0)?,
                    r.get::<_, String>(1)?,
                    r.get::<_, String>(2)?,
                ))
            })?
            .collect::<Result<Vec<_>, _>>()?;
        if rows.len() > 256 {
            return Err(RchCoreError::StorageBackpressure(
                "outbound fanout exceeds durable recipient limit".into(),
            ));
        }
        let all_delivered = rows.iter().all(|(_, s, _)| s == "delivered");
        let all_terminal = rows.iter().all(|(_, s, _)| {
            matches!(
                s.as_str(),
                "delivered" | "failed" | "cancelled" | "expired" | "rejected"
            )
        });
        let admitted = rows.iter().filter(|(id, _, _)| id.is_some()).count();
        let state = if all_delivered {
            "delivered"
        } else if all_terminal {
            "failed"
        } else if rows.iter().any(|(_, s, _)| s == "sent") {
            "sent"
        } else if admitted > 0 {
            "sending"
        } else {
            "broker_pending"
        };
        message.delivery_state = state.into();
        let targets=rows.iter().map(|(id,status,payload)|{
            let intent:crate::DurableOutboundIntent=serde_json::from_str(payload).map_err(|e|RchCoreError::Decode(e.to_string()))?;
            Ok(serde_json::json!({"message_id":id,"destination":intent.request.get("destination"),"status":status}))
        }).collect::<Result<Vec<_>,RchCoreError>>()?;
        if rows.len() == 1 {
            message.delivery_metadata["reticulumd_message_id"] = serde_json::json!(rows[0].0);
        }
        message.delivery_metadata["reticulumd_receipt_targets"] = serde_json::json!(targets);
        message.delivery_metadata["reticulumd_dispatch_count"] = serde_json::json!(admitted);
        message.delivery_metadata["dispatch_status"] =
            serde_json::json!(if admitted < rows.len() {
                "broker_pending"
            } else {
                "accepted"
            });
        message.delivery_metadata["receipt_pending"] = serde_json::json!(!all_terminal);
        message.delivery_metadata["acked"] = serde_json::json!(all_delivered);
        message.delivery_metadata["retry_scheduled"] = serde_json::json!(false);
        self.stage_message(&message)?;
        Ok(message)
    }
}
