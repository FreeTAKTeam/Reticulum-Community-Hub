//! Durable inbox/outbound application under the existing command transaction.
use super::{
    FileAttachmentRecord, MessageRecord, RchCommandTransaction, RchCore, RchCoreError,
    RchCoreSnapshot, RchSqliteStore, TelemetryRecord, Transaction, TransactionBehavior,
    decode_msgpack, encode_msgpack, normalize_topic_id, params,
};
use rusqlite::OptionalExtension;

impl RchSqliteStore {
    pub fn begin_outbound_application(
        &mut self,
    ) -> Result<RchCommandTransaction<'_>, RchCoreError> {
        self.enable_durable_inbox()?;
        let transaction =
            Transaction::new_unchecked(&self.connection, TransactionBehavior::Immediate)?;
        let core = RchCore::new();
        let before = core.snapshot();
        Ok(RchCommandTransaction {
            changes_before: transaction.total_changes(),
            started: std::time::Instant::now(),
            transaction,
            before,
            core,
            checklist: false,
            inbox: None,
            rejection: None,
            staged_outbound_intents: std::cell::Cell::new(0),
            domain_snapshot: false,
            rows_read: 0,
            payload_bytes_read: 0,
        })
    }
    pub fn begin_inbox_application(
        &mut self,
        consumer: &str,
        event: &super::super::InboxEvent,
        checklist: bool,
    ) -> Result<RchCommandTransaction<'_>, RchCoreError> {
        self.enable_durable_inbox()?;
        let transaction =
            Transaction::new_unchecked(&self.connection, TransactionBehavior::Immediate)?;
        // No announce/message history is decoded. Authorization and routing rows share this snapshot.
        let domain_snapshot = matches!(event.event_type.as_str(), "inbound" | "bootstrap_message");
        let core = RchCore::new();
        let before = core.snapshot();
        let mut unit = RchCommandTransaction {
            changes_before: transaction.total_changes(),
            started: std::time::Instant::now(),
            transaction,
            before,
            core,
            checklist,
            inbox: None,
            rejection: None,
            staged_outbound_intents: std::cell::Cell::new(0),
            domain_snapshot,
            rows_read: 0,
            payload_bytes_read: 0,
        };
        let (journal,position,payload,status):(String,i64,String,String)=unit.transaction.query_row("SELECT i.journal_id,i.position,i.payload,i.status FROM rch_broker_inbox i JOIN rch_broker_checkpoint c USING(journal_id) WHERE c.consumer_id=?1 AND i.status NOT IN ('applied','rejected') ORDER BY i.position LIMIT 1",[consumer],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?)))?;
        let saved: super::super::InboxEvent =
            serde_json::from_str(&payload).map_err(|e| RchCoreError::Decode(e.to_string()))?;
        if super::super::sqlite_u64(event.position)? != position
            || serde_json::to_string(event).map_err(|e| RchCoreError::Encode(e.to_string()))?
                != payload
            || status != "stored"
            || saved.position != event.position
        {
            return Err(RchCoreError::RecoveryRequired(
                "application did not match the oldest pending immutable event".into(),
            ));
        }
        unit.inbox = Some((consumer.into(), journal, position));
        Ok(unit)
    }
}
impl RchCommandTransaction<'_> {
    /// Roll back one failed envelope while preserving earlier envelopes in this inbox input.
    pub fn apply_inbox_envelope<T, E>(
        &mut self,
        apply: impl FnOnce(&mut Self) -> Result<T, E>,
    ) -> Result<Result<T, E>, RchCoreError> {
        let before = self.before.clone();
        let domain = self.core.snapshot();
        let rejection = self.rejection.clone();
        let outbound_intents = self.staged_outbound_intents.get();
        self.transaction
            .execute_batch("SAVEPOINT rch_inbox_envelope")?;
        let result = apply(self);
        if result.is_err() {
            self.transaction
                .execute_batch("ROLLBACK TO rch_inbox_envelope")?;
            self.before = before;
            self.restore_domain(domain)?;
            self.rejection = rejection;
            self.staged_outbound_intents.set(outbound_intents);
        }
        self.transaction
            .execute_batch("RELEASE rch_inbox_envelope")?;
        Ok(result)
    }

    pub fn staged_outbound_intent_count(&self) -> usize {
        self.staged_outbound_intents.get()
    }

    pub fn stage_client(
        &mut self,
        record: &super::super::ClientRecord,
    ) -> Result<(), RchCoreError> {
        self.core.clients.insert(
            super::super::normalize_hash(Some(&record.identity))
                .unwrap_or_else(|| record.identity.clone()),
            record.clone(),
        );
        Ok(())
    }
    pub fn stage_message(&self, record: &MessageRecord) -> Result<(), RchCoreError> {
        super::super::durable_inbox::admit_effect_bytes(
            &self.transaction,
            record.content.len().saturating_add(
                serde_json::to_vec(&record.delivery_metadata)
                    .map_err(|e| RchCoreError::Encode(e.to_string()))?
                    .len(),
            ),
        )?;
        super::super::sqlite_message_history::write_message(&self.transaction, record)?;
        Ok(())
    }
    pub fn stage_system_event(
        &self,
        record: &super::super::SystemEventRecord,
    ) -> Result<(), RchCoreError> {
        self.transaction.execute(
            "INSERT INTO rch_system_events(event_id,payload) VALUES(?1,?2)",
            params![record.event_id, encode_msgpack(record)?],
        )?;
        self.transaction.execute("DELETE FROM rch_system_events WHERE id NOT IN (SELECT id FROM rch_system_events ORDER BY id DESC LIMIT 200)",[])?;
        Ok(())
    }
    pub fn stage_outbound_intent(
        &self,
        intent: &super::super::durable_inbox::DurableOutboundIntent,
    ) -> Result<(), RchCoreError> {
        let operation_id = &intent.operation_id;
        if operation_id.is_empty() || operation_id.len() > 128 {
            return Err(RchCoreError::InvalidPayload(
                "invalid durable outbound operation identifier".into(),
            ));
        }
        let payload =
            serde_json::to_string(intent).map_err(|e| RchCoreError::Encode(e.to_string()))?;
        let prior: Option<String> = self
            .transaction
            .query_row(
                "SELECT payload FROM rch_broker_dispatch WHERE operation_id=?1",
                [operation_id],
                |r| r.get(0),
            )
            .optional()?;
        if let Some(prior) = prior {
            let prior: super::super::DurableOutboundIntent =
                serde_json::from_str(&prior).map_err(|e| RchCoreError::Decode(e.to_string()))?;
            if prior.request != intent.request
                || prior.message.message_id != intent.message.message_id
            {
                return Err(RchCoreError::RecoveryRequired(
                    "operation identifier has conflicting outbound content".into(),
                ));
            }
            return Ok(());
        }
        if self.inbox.is_some() && self.staged_outbound_intents.get() >= 256 {
            return Err(RchCoreError::InvalidPayload(
                "durable input exceeds 256 outbound intents".into(),
            ));
        }
        super::super::durable_inbox::admit_effect_bytes(&self.transaction, payload.len())?;
        let used: i64 = self.transaction.query_row(
            "SELECT outbox_bytes FROM rch_broker_profile WHERE singleton=1",
            [],
            |r| r.get(0),
        )?;
        if used.saturating_add(
            i64::try_from(payload.len()).map_err(|e| RchCoreError::Encode(e.to_string()))?,
        ) > 128 * 1024 * 1024
        {
            return Err(RchCoreError::StorageBackpressure(
                "durable outbound intent storage reached its bound".into(),
            ));
        }
        self.stage_message(&intent.message)?;
        self.transaction.execute("INSERT INTO rch_broker_dispatch(operation_id,message_id,payload,state,daemon_message_id) VALUES(?1,?2,?3,'pending',NULL)",params![operation_id,intent.message.message_id,payload])?;
        self.transaction.execute(
            "UPDATE rch_broker_profile SET outbox_bytes=outbox_bytes+?1 WHERE singleton=1",
            [i64::try_from(payload.len()).map_err(|e| RchCoreError::Encode(e.to_string()))?],
        )?;
        self.staged_outbound_intents
            .set(self.staged_outbound_intents.get().saturating_add(1));
        Ok(())
    }
    pub fn claim_logical_input(
        &self,
        source: &str,
        id: &str,
        payload: &serde_json::Value,
    ) -> Result<bool, RchCoreError> {
        let source = super::super::normalize_hash(Some(source))
            .unwrap_or_else(|| source.to_ascii_lowercase());
        let encoded =
            serde_json::to_vec(payload).map_err(|e| RchCoreError::Encode(e.to_string()))?;
        let fingerprint = super::super::durable_inbox::hex_digest(&encoded);
        let previous: Option<String> = self
            .transaction
            .query_row(
                "SELECT fingerprint FROM rch_broker_claims WHERE source=?1 AND logical_id=?2",
                params![source, id],
                |r| r.get(0),
            )
            .optional()?;
        if let Some(previous) = previous {
            if previous != fingerprint {
                return Err(RchCoreError::RecoveryRequired(
                    "logical input identifier conflicts with committed content".into(),
                ));
            }
            return Ok(false);
        }
        super::super::durable_inbox::admit_effect_bytes(&self.transaction, encoded.len())?;
        self.transaction.execute(
            "INSERT INTO rch_broker_claims VALUES(?1,?2,?3)",
            params![source, id, fingerprint],
        )?;
        Ok(true)
    }
    /// A supported malformed/rejected command retains original bytes and discards partial domain changes.
    pub fn reject(&mut self, reason: &str) -> Result<(), RchCoreError> {
        self.core = RchCore::from_snapshot(self.before.clone())?;
        self.rejection = Some(reason.chars().take(2048).collect());
        Ok(())
    }
    /// Mark one input failure without discarding independently accepted envelopes.
    pub fn diagnose_rejection(&mut self, reason: &str) {
        self.rejection = Some(reason.chars().take(2048).collect());
    }
    pub fn restore_domain(&mut self, checkpoint: RchCoreSnapshot) -> Result<(), RchCoreError> {
        self.core = RchCore::from_snapshot(checkpoint)?;
        Ok(())
    }
    pub fn message(&self, id: &str) -> Result<Option<MessageRecord>, RchCoreError> {
        let payload: Option<Vec<u8>> = self
            .transaction
            .query_row(
                "SELECT payload FROM rch_messages WHERE message_id=?1",
                [id],
                |r| r.get(0),
            )
            .optional()?;
        payload.as_deref().map(decode_msgpack).transpose()
    }
    pub fn receipt_message(&self, id: &str) -> Result<Option<MessageRecord>, RchCoreError> {
        let payload:Option<Vec<u8>>=self.transaction.query_row("SELECT m.payload FROM rch_broker_dispatch d JOIN rch_messages m ON m.message_id=d.message_id WHERE d.daemon_message_id=?1",[id],|r|r.get(0)).optional()?;
        payload.as_deref().map(decode_msgpack).transpose()
    }
    /// Latest persisted collector candidates in timestamp order. Fail explicitly
    /// rather than silently truncating a snapshot beyond the response bound.
    pub fn collector_telemetry_since(
        &self,
        since: i64,
    ) -> Result<Vec<TelemetryRecord>, RchCoreError> {
        let mut statement = self.transaction.prepare("SELECT payload FROM rch_telemetry_records WHERE timestamp_s >= ?1 ORDER BY timestamp_s DESC, id DESC LIMIT 1025")?;
        let mut rows = statement.query([since])?;
        let mut records = Vec::new();
        while let Some(row) = rows.next()? {
            let bytes: Vec<u8> = row.get(0)?;
            records.push(decode_msgpack(&bytes)?);
            if records.len() > 1024 {
                return Err(RchCoreError::InvalidPayload(
                    "collector snapshot exceeds 1024 candidates".into(),
                ));
            }
        }
        Ok(records)
    }
    pub fn stage_telemetry(
        &self,
        record: &TelemetryRecord,
    ) -> Result<TelemetryRecord, RchCoreError> {
        let existing:Option<Vec<u8>>=self.transaction.query_row("SELECT payload FROM rch_telemetry_records WHERE lower(peer_destination)=lower(?1) ORDER BY timestamp_s DESC,id DESC LIMIT 1",[&record.peer_destination],|r|r.get(0)).optional()?;
        if let Some(payload) = existing {
            let prior: TelemetryRecord = decode_msgpack(&payload)?;
            if prior.timestamp_s > record.timestamp_s {
                return Ok(prior);
            }
        }
        self.transaction.execute(
            "DELETE FROM rch_telemetry_records WHERE lower(peer_destination)=lower(?1)",
            [&record.peer_destination],
        )?;
        self.transaction.execute("INSERT INTO rch_telemetry_records(peer_destination,timestamp_s,payload) VALUES(?1,?2,?3)",params![record.peer_destination,record.timestamp_s,encode_msgpack(record)?])?;
        Ok(record.clone())
    }
    pub fn stage_attachment(
        &self,
        mut record: FileAttachmentRecord,
        bytes: &[u8],
    ) -> Result<FileAttachmentRecord, RchCoreError> {
        if bytes.len() > super::super::MAX_DURABLE_ATTACHMENT_BYTES {
            return Err(RchCoreError::InvalidPayload(
                "attachment exceeds durable byte limit".into(),
            ));
        }
        super::super::durable_inbox::admit_effect_bytes(&self.transaction, bytes.len())?;
        self.transaction.execute(
            "INSERT INTO rch_file_attachments(category,payload,topic_id) VALUES(?1,?2,?3)",
            params![
                record.category,
                encode_msgpack(&record)?,
                normalize_topic_id(record.topic_id.as_deref())
            ],
        )?;
        record.file_id = u64::try_from(self.transaction.last_insert_rowid())
            .map_err(|e| RchCoreError::Decode(e.to_string()))?;
        record.path = format!("rch-db:{}", record.file_id);
        self.transaction.execute(
            "UPDATE rch_file_attachments SET payload=?1 WHERE file_id=?2",
            params![
                encode_msgpack(&record)?,
                super::super::sqlite_u64(record.file_id)?
            ],
        )?;
        self.transaction.execute(
            "INSERT INTO rch_broker_attachment_bytes VALUES(?1,?2)",
            params![super::super::sqlite_u64(record.file_id)?, bytes],
        )?;
        Ok(record)
    }
}
