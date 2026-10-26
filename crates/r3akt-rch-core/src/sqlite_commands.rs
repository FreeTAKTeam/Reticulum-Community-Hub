mod broker_application;
mod broker_delivery;

use super::{
    FileAttachmentRecord, MessageRecord, RchCore, RchCoreError, RchCoreSnapshot, RchSqliteStore,
    SubscriberRecord, TelemetryRecord, Transaction, decode_msgpack, encode_msgpack,
    normalize_topic_id, params, save_checklist_delta_tables, save_registry_delta_tables,
    utc_now_ms,
};
use rusqlite::{OptionalExtension, TransactionBehavior};
use std::cell::Cell;

/// Owns the complete read, domain mutation and commit under one `SQLite` write reservation.
/// Dropping an uncommitted command rolls back; no projection should be published before commit.
pub struct RchCommandTransaction<'conn> {
    transaction: Transaction<'conn>,
    before: RchCoreSnapshot,
    core: RchCore,
    checklist: bool,
    inbox: Option<(String, String, i64)>,
    rejection: Option<String>,
    staged_outbound_intents: Cell<usize>,
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
            staged_outbound_intents: Cell::new(0),
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
    let records = {
        let mut statement = transaction.prepare(
            "SELECT payload FROM rch_file_attachments WHERE topic_id=?1 ORDER BY file_id",
        )?;
        let rows = statement.query_map([topic_id], |row| row.get::<_, Vec<u8>>(0))?;
        rows.map(|row| decode_msgpack::<FileAttachmentRecord>(&row?))
            .collect::<Result<Vec<_>, _>>()?
    };
    for mut record in records {
        if normalize_topic_id(record.topic_id.as_deref()).as_deref() == Some(topic_id) {
            record.topic_id = None;
            record.updated_ts_ms = utc_now_ms();
            transaction.execute(
                "UPDATE rch_file_attachments SET payload = ?1, topic_id=NULL WHERE file_id = ?2",
                params![encode_msgpack(&record)?, super::sqlite_u64(record.file_id)?],
            )?;
        }
    }
    Ok(())
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
            staged_outbound_intents: Cell::new(0),
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

impl RchCommandTransaction<'_> {
    /// Most recent visible inbound chat on `topic` from other senders, oldest first,
    /// read inside this unit of work for `/join` replay.
    pub fn recent_inbound_topic_messages(
        &self,
        topic: &str,
        exclude_sender: &str,
        limit: usize,
    ) -> Result<Vec<MessageRecord>, RchCoreError> {
        let limit = i64::try_from(limit).map_err(|e| RchCoreError::Encode(e.to_string()))?;
        let mut query = self.transaction.prepare(
            "SELECT payload FROM rch_messages WHERE topic_id=?1 AND chat_visible=1 \
             AND direction='inbound' AND sender<>?2 COLLATE NOCASE \
             ORDER BY created_ts_ms DESC,id DESC LIMIT ?3",
        )?;
        let rows = query.query_map(params![topic, exclude_sender, limit], |row| {
            row.get::<_, Vec<u8>>(0)
        })?;
        let mut messages = Vec::new();
        for row in rows {
            let message: MessageRecord = decode_msgpack(&row?)?;
            if !message.content.trim().is_empty() {
                messages.push(message);
            }
        }
        messages.reverse();
        Ok(messages)
    }
}
