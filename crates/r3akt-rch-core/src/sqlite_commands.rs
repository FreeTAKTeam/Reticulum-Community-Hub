mod broker_delivery;

use super::{
    FileAttachmentRecord, MessageRecord, RchCore, RchCoreError, RchCoreSnapshot, RchSqliteStore,
    SubscriberRecord, TelemetryRecord, Transaction, decode_msgpack, encode_msgpack,
    normalize_topic_id, params, save_checklist_delta_tables, save_registry_delta_tables,
    utc_now_ms,
};
use rusqlite::{OptionalExtension, TransactionBehavior};

/// Owns the complete read, domain mutation and commit under one `SQLite` write reservation.
/// Dropping an uncommitted command rolls back; no projection should be published before commit.
pub struct RchCommandTransaction<'conn> {
    transaction: Transaction<'conn>,
    before: RchCoreSnapshot,
    core: RchCore,
    checklist: bool,
    inbox: Option<(String, String, i64)>,
    rejection: Option<String>,
    domain_snapshot: bool,
    rows_read: usize,
    payload_bytes_read: usize,
    started: std::time::Instant,
    changes_before: u64,
}

impl RchSqliteStore {
    pub(super) fn consistent_read<T>(
        &self,
        read: impl FnOnce(&Self) -> Result<T, RchCoreError>,
    ) -> Result<T, RchCoreError> {
        let transaction = self.connection.unchecked_transaction()?;
        let result = read(self)?;
        transaction.commit()?;
        Ok(result)
    }
    pub fn upsert_messages(&mut self, records: &[MessageRecord]) -> Result<(), RchCoreError> {
        let transaction = self.connection.transaction()?;
        for record in records {
            super::sqlite_message_history::write_message(&transaction, record)?;
        }
        transaction.commit()?;
        Ok(())
    }

    pub fn begin_r3akt_command(&mut self) -> Result<RchCommandTransaction<'_>, RchCoreError> {
        self.begin_command(false)
    }

    pub fn begin_checklist_command(&mut self) -> Result<RchCommandTransaction<'_>, RchCoreError> {
        self.begin_command(true)
    }

    fn begin_command(
        &mut self,
        checklist: bool,
    ) -> Result<RchCommandTransaction<'_>, RchCoreError> {
        // The public mutable borrow prevents callers nesting transactions. The shared
        // connection constructor lets the existing read helpers execute within this reservation.
        let transaction =
            Transaction::new_unchecked(&self.connection, TransactionBehavior::Immediate)?;
        let before = if checklist {
            self.load_checklist_command_snapshot_rows()?
        } else {
            self.load_r3akt_read_snapshot_rows()?
        };
        let core = RchCore::from_snapshot(before.clone())?;
        Ok(RchCommandTransaction {
            changes_before: transaction.total_changes(),
            started: std::time::Instant::now(),
            transaction,
            before,
            core,
            checklist,
            inbox: None,
            rejection: None,
            domain_snapshot: true,
            rows_read: 0,
            payload_bytes_read: 0,
        })
    }

    /// Preserve timestamp ordering even when independent server states share this database.
    pub fn upsert_latest_telemetry_record(
        &mut self,
        record: &TelemetryRecord,
    ) -> Result<TelemetryRecord, RchCoreError> {
        let transaction = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let existing: Option<Vec<u8>> = transaction.query_row(
            "SELECT payload FROM rch_telemetry_records WHERE lower(peer_destination) = lower(?1)
             ORDER BY timestamp_s DESC, id DESC LIMIT 1", [record.peer_destination.as_str()], |row| row.get(0),
        ).optional()?;
        if let Some(payload) = existing {
            let existing: TelemetryRecord = decode_msgpack(&payload)?;
            if existing.timestamp_s > record.timestamp_s {
                return Ok(existing);
            }
        }
        transaction.execute(
            "DELETE FROM rch_telemetry_records WHERE lower(peer_destination) = lower(?1)",
            [record.peer_destination.as_str()],
        )?;
        transaction.execute("INSERT INTO rch_telemetry_records (peer_destination, timestamp_s, payload) VALUES (?1, ?2, ?3)",
            params![record.peer_destination, record.timestamp_s, encode_msgpack(record)?])?;
        transaction.commit()?;
        Ok(record.clone())
    }

    pub fn replace_subscriber(
        &mut self,
        previous: &SubscriberRecord,
        next: &SubscriberRecord,
    ) -> Result<(), RchCoreError> {
        let transaction = self.connection.transaction()?;
        transaction.execute(
            "DELETE FROM rch_subscribers WHERE node_id = ?1 AND topic_id = ?2",
            params![previous.node_id, previous.topic_id],
        )?;
        transaction.execute("INSERT OR REPLACE INTO rch_subscribers (node_id, topic_id, payload) VALUES (?1, ?2, ?3)",
            params![next.node_id, next.topic_id, encode_msgpack(next)?])?;
        transaction.commit()?;
        Ok(())
    }
}

impl RchCommandTransaction<'_> {
    pub fn core_mut(&mut self) -> &mut RchCore {
        &mut self.core
    }

    pub fn commit(self) -> Result<RchCoreSnapshot, RchCoreError> {
        self.commit_delta().map(|delta| delta.after)
    }

    pub fn commit_delta(self) -> Result<CommandDelta, RchCoreError> {
        let after = self.core.snapshot();
        if !self.domain_snapshot {
        } else if self.checklist {
            save_checklist_delta_tables(&self.transaction, &self.before, &after)?;
        } else {
            save_registry_delta_tables(&self.transaction, &self.before, &after)?;
            super::save_payload_delta(
                &self.transaction,
                "rch_identity_states",
                &self.before.identity_states,
                &after.identity_states,
                |r| vec![("identity", super::sql_text(&r.identity))],
                |r| vec![("identity", super::sql_text(&r.identity))],
            )?;
            for record in &after.identity_announces {
                if !self.before.identity_announces.contains(record) {
                    super::sqlite_announces::write_identity_announce(
                        &self.transaction,
                        record,
                        true,
                    )?;
                }
            }
            if self.before.authorization_required != after.authorization_required {
                self.transaction.execute(
                    "INSERT OR REPLACE INTO rch_settings VALUES('authorization_required',?1)",
                    [if after.authorization_required {
                        "true"
                    } else {
                        "false"
                    }],
                )?;
            }
            for record in &after.messages {
                if !self.before.messages.contains(record) {
                    super::sqlite_message_history::write_message(&self.transaction, record)?;
                }
            }
            for previous in &self.before.topics {
                if !after
                    .topics
                    .iter()
                    .any(|record| record.topic_id == previous.topic_id)
                {
                    detach_topic_attachments(&self.transaction, &previous.topic_id)?;
                }
            }
            if self.inbox.is_some() {
                super::save_checklist_delta_tables_with_common(
                    &self.transaction,
                    &self.before,
                    &after,
                    false,
                )?;
            }
        }
        if let Some((consumer, journal, position)) = self.inbox.as_ref() {
            if let Some(reason) = self.rejection.as_ref() {
                self.transaction.execute("UPDATE rch_broker_inbox SET status='rejected',error=?3 WHERE journal_id=?1 AND position=?2",params![journal,position,reason])?;
            } else {
                self.transaction.execute("UPDATE rch_broker_profile SET inbox_bytes=inbox_bytes-(SELECT length(payload) FROM rch_broker_inbox WHERE journal_id=?1 AND position=?2) WHERE singleton=1",params![journal,position])?;
                self.transaction.execute("UPDATE rch_broker_inbox SET status='applied',payload='' WHERE journal_id=?1 AND position=?2",params![journal,position])?;
            }
            let next:Option<i64>=self.transaction.query_row("SELECT MIN(position) FROM rch_broker_inbox WHERE journal_id=?1 AND status NOT IN ('applied','rejected')",[journal],|row|row.get(0))?;
            let stored: i64 = self.transaction.query_row(
                "SELECT stored FROM rch_broker_checkpoint WHERE consumer_id=?1",
                [consumer],
                |row| row.get(0),
            )?;
            let applied = next.map_or(stored, |next| next - 1);
            self.transaction.execute(
                "UPDATE rch_broker_checkpoint SET applied=?1 WHERE consumer_id=?2",
                params![applied, consumer],
            )?;
        }
        let rows_written = self
            .transaction
            .total_changes()
            .saturating_sub(self.changes_before);
        self.transaction.commit()?;
        let duration_us = u64::try_from(self.started.elapsed().as_micros()).unwrap_or(u64::MAX);
        Ok(CommandDelta {
            before: self.before,
            after,
            rows_read: self.rows_read,
            payload_bytes_read: self.payload_bytes_read,
            rows_written,
            duration_us,
        })
    }
}

pub(super) fn detach_topic_attachments(
    transaction: &Transaction<'_>,
    topic_id: &str,
) -> Result<(), RchCoreError> {
    let mut after = -1_i64;
    loop {
        let records = {
            let mut statement = transaction.prepare(
                "SELECT file_id,payload FROM rch_file_attachments WHERE topic_id=?1 AND file_id>?2 ORDER BY file_id LIMIT 256",
            )?;
            let rows = statement.query_map(params![topic_id, after], |row| {
                Ok((row.get::<_, i64>(0)?, row.get::<_, Vec<u8>>(1)?))
            })?;
            rows.collect::<Result<Vec<_>, _>>()?
        };
        if records.is_empty() {
            break;
        }
        for (id, payload) in records {
            let mut record: FileAttachmentRecord = decode_msgpack(&payload)?;
            record.topic_id = None;
            record.updated_ts_ms = utc_now_ms();
            transaction.execute(
                "UPDATE rch_file_attachments SET payload=?1,topic_id=NULL WHERE file_id=?2",
                params![encode_msgpack(&record)?, id],
            )?;
            after = id;
        }
    }
    Ok(())
}

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
            domain_snapshot: false,
            rows_read: 0,
            payload_bytes_read: 0,
        })
    }
    pub fn begin_inbox_application(
        &mut self,
        consumer: &str,
        event: &super::InboxEvent,
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
            domain_snapshot,
            rows_read: 0,
            payload_bytes_read: 0,
        };
        let (journal,position,payload,status):(String,i64,String,String)=unit.transaction.query_row("SELECT i.journal_id,i.position,i.payload,i.status FROM rch_broker_inbox i JOIN rch_broker_checkpoint c USING(journal_id) WHERE c.consumer_id=?1 AND i.status NOT IN ('applied','rejected') ORDER BY i.position LIMIT 1",[consumer],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?)))?;
        let saved: super::InboxEvent =
            serde_json::from_str(&payload).map_err(|e| RchCoreError::Decode(e.to_string()))?;
        if super::sqlite_u64(event.position)? != position
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
    pub fn stage_client(&mut self, record: &super::ClientRecord) -> Result<(), RchCoreError> {
        self.core.clients.insert(
            super::normalize_hash(Some(&record.identity))
                .unwrap_or_else(|| record.identity.clone()),
            record.clone(),
        );
        Ok(())
    }
    pub fn stage_message(&self, record: &MessageRecord) -> Result<(), RchCoreError> {
        super::durable_inbox::admit_effect_bytes(
            &self.transaction,
            record.content.len().saturating_add(
                serde_json::to_vec(&record.delivery_metadata)
                    .map_err(|e| RchCoreError::Encode(e.to_string()))?
                    .len(),
            ),
        )?;
        super::sqlite_message_history::write_message(&self.transaction, record)?;
        Ok(())
    }
    pub fn stage_system_event(
        &self,
        record: &super::SystemEventRecord,
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
        intent: &super::durable_inbox::DurableOutboundIntent,
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
            let prior: super::DurableOutboundIntent =
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
        super::durable_inbox::admit_effect_bytes(&self.transaction, payload.len())?;
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
        Ok(())
    }
    pub fn claim_logical_input(
        &self,
        source: &str,
        id: &str,
        payload: &serde_json::Value,
    ) -> Result<bool, RchCoreError> {
        let source =
            super::normalize_hash(Some(source)).unwrap_or_else(|| source.to_ascii_lowercase());
        let encoded =
            serde_json::to_vec(payload).map_err(|e| RchCoreError::Encode(e.to_string()))?;
        let fingerprint = super::durable_inbox::hex_digest(&encoded);
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
        super::durable_inbox::admit_effect_bytes(&self.transaction, encoded.len())?;
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
                "SELECT payload FROM rch_messages WHERE message_id=?1 COLLATE NOCASE",
                [id],
                |r| r.get(0),
            )
            .optional()?;
        payload.as_deref().map(decode_msgpack).transpose()
    }
    pub fn receipt_message(&self, id: &str) -> Result<Option<MessageRecord>, RchCoreError> {
        let payload:Option<Vec<u8>>=self.transaction.query_row("SELECT m.payload FROM rch_broker_dispatch d JOIN rch_messages m ON m.message_id=d.message_id COLLATE NOCASE WHERE d.daemon_message_id=?1",[id],|r|r.get(0)).optional()?;
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
        if bytes.len() > super::MAX_DURABLE_ATTACHMENT_BYTES {
            return Err(RchCoreError::InvalidPayload(
                "attachment exceeds durable byte limit".into(),
            ));
        }
        super::durable_inbox::admit_effect_bytes(&self.transaction, bytes.len())?;
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
            params![encode_msgpack(&record)?, super::sqlite_u64(record.file_id)?],
        )?;
        self.transaction.execute(
            "INSERT INTO rch_broker_attachment_bytes VALUES(?1,?2)",
            params![super::sqlite_u64(record.file_id)?, bytes],
        )?;
        Ok(record)
    }
}

impl RchCommandTransaction<'_> {
    pub fn inbox_event_key(&self) -> Result<String, RchCoreError> {
        self.inbox
            .as_ref()
            .map(|(_, journal, position)| format!("{journal}:{position}"))
            .ok_or_else(|| RchCoreError::RecoveryRequired("not an inbox unit of work".into()))
    }
}

/// Only the loaded command read set participates in this committed delta.
pub struct CommandDelta {
    pub before: RchCoreSnapshot,
    pub after: RchCoreSnapshot,
    pub rows_read: usize,
    pub payload_bytes_read: usize,
    pub rows_written: u64,
    pub duration_us: u64,
}
impl RchSqliteStore {
    pub fn begin_scoped_command(
        &mut self,
        command: &super::MissionCommandEnvelope,
        checklist: bool,
    ) -> Result<RchCommandTransaction<'_>, RchCoreError> {
        let transaction =
            Transaction::new_unchecked(&self.connection, TransactionBehavior::Immediate)?;
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
            domain_snapshot: true,
            rows_read: 0,
            payload_bytes_read: 0,
        };
        unit.prepare_command(command)?;
        Ok(unit)
    }
}
impl RchCommandTransaction<'_> {
    pub fn prepare_command(
        &mut self,
        command: &super::MissionCommandEnvelope,
    ) -> Result<(), RchCoreError> {
        let mut read = super::sqlite_command_reads::ReadSet::new(&self.transaction);
        let inactive_modes = self
            .core
            .identity_rem_modes()
            .into_iter()
            .filter(|record| record.mode.trim() != "connected")
            .map(|record| record.identity)
            .collect::<Vec<_>>();
        read.command(command, &inactive_modes)?;
        self.rows_read += read.rows;
        self.payload_bytes_read += read.bytes;
        super::sqlite_command_reads::extend(
            &mut self.before,
            &mut self.core,
            read.snapshot,
            read.authorization,
        )?;
        // Resolve access against staged domain state: earlier envelopes may have
        // changed the caller's member identity or the target's mission scope.
        let mut authority = super::sqlite_command_reads::ReadSet::new(&self.transaction);
        authority.authorization(command, &self.core)?;
        self.rows_read += authority.rows;
        self.payload_bytes_read += authority.bytes;
        super::sqlite_command_reads::extend(
            &mut self.before,
            &mut self.core,
            authority.snapshot,
            None,
        )
    }
    pub fn prepare_recipients(
        &mut self,
        mission: Option<&str>,
        team: Option<&str>,
    ) -> Result<(), RchCoreError> {
        let mut read = super::sqlite_command_reads::ReadSet::new(&self.transaction);
        read.recipients(mission, team)?;
        self.rows_read += read.rows;
        self.payload_bytes_read += read.bytes;
        super::sqlite_command_reads::extend(
            &mut self.before,
            &mut self.core,
            read.snapshot,
            read.authorization,
        )
    }
    pub fn prepare_collector(&mut self, topic: Option<&str>) -> Result<(), RchCoreError> {
        let mut read = super::sqlite_command_reads::ReadSet::new(&self.transaction);
        read.collector(topic)?;
        self.rows_read += read.rows;
        self.payload_bytes_read += read.bytes;
        super::sqlite_command_reads::extend(
            &mut self.before,
            &mut self.core,
            read.snapshot,
            read.authorization,
        )
    }
    pub fn prepare_source(&mut self, source: &str) -> Result<(), RchCoreError> {
        let mut read = super::sqlite_command_reads::ReadSet::new(&self.transaction);
        read.source(source)?;
        self.rows_read += read.rows;
        self.payload_bytes_read += read.bytes;
        super::sqlite_command_reads::extend(
            &mut self.before,
            &mut self.core,
            read.snapshot,
            read.authorization,
        )
    }
    pub fn take_generated_messages(&mut self) -> Vec<MessageRecord> {
        std::mem::take(&mut self.core.messages)
    }
    pub fn prepare_routing(&mut self, source: &str, topic: &str) -> Result<(), RchCoreError> {
        let mut read = super::sqlite_command_reads::ReadSet::new(&self.transaction);
        read.routing(source, topic)?;
        self.rows_read += read.rows;
        self.payload_bytes_read += read.bytes;
        super::sqlite_command_reads::extend(
            &mut self.before,
            &mut self.core,
            read.snapshot,
            read.authorization,
        )
    }
}

impl RchCommandTransaction<'_> {
    pub fn row_count(&self, table: &str) -> Result<usize, RchCoreError> {
        if !super::RCH_SQLITE_DATA_TABLES.contains(&table) {
            return Err(RchCoreError::InvalidPayload("unsupported table".into()));
        }
        self.transaction
            .query_row(&format!("SELECT COUNT(*) FROM {table}"), [], |row| {
                super::sqlite_read_usize(row, 0)
            })
            .map_err(Into::into)
    }
}
