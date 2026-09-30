use super::{
    FileAttachmentRecord, MessageRecord, RchCore, RchCoreError, RchCoreSnapshot, RchSqliteStore,
    SubscriberRecord, TelemetryRecord, Transaction, decode_msgpack, encode_msgpack,
    message_queue_projection, normalize_topic_id, params, save_checklist_delta_tables,
    save_registry_delta_tables, utc_now_ms,
};
use rusqlite::{OptionalExtension, TransactionBehavior};

/// Owns the complete read, domain mutation and commit under one `SQLite` write reservation.
/// Dropping an uncommitted command rolls back; no projection should be published before commit.
pub struct RchCommandTransaction<'conn> {
    transaction: Transaction<'conn>,
    before: RchCoreSnapshot,
    core: RchCore,
    checklist: bool,
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
            let projection = message_queue_projection(record);
            transaction.execute(
                "DELETE FROM rch_messages WHERE message_id = ?1",
                [record.message_id.as_str()],
            )?;
            transaction.execute("INSERT INTO rch_messages (message_id, payload, delivery_state, dispatch_status,
                next_attempt_at_ts_ms, attempts, priority, batch_id, created_ts_ms) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)",
                params![record.message_id, encode_msgpack(record)?, projection.delivery_state, projection.dispatch_status,
                    projection.next_attempt_at_ts_ms, projection.attempts, projection.priority, projection.batch_id, projection.created_ts_ms])?;
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
            transaction,
            before,
            core,
            checklist,
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
        let after = self.core.snapshot();
        if self.checklist {
            save_checklist_delta_tables(&self.transaction, &self.before, &after)?;
        } else {
            save_registry_delta_tables(&self.transaction, &self.before, &after)?;
        }
        self.transaction.commit()?;
        Ok(after)
    }
}

pub(super) fn detach_topic_attachments(
    transaction: &Transaction<'_>,
    topic_id: &str,
) -> Result<(), RchCoreError> {
    let records = {
        let mut statement =
            transaction.prepare("SELECT payload FROM rch_file_attachments ORDER BY file_id")?;
        let rows = statement.query_map([], |row| row.get::<_, Vec<u8>>(0))?;
        rows.map(|row| decode_msgpack::<FileAttachmentRecord>(&row?))
            .collect::<Result<Vec<_>, _>>()?
    };
    for mut record in records {
        if normalize_topic_id(record.topic_id.as_deref()).as_deref() == Some(topic_id) {
            record.topic_id = None;
            record.updated_ts_ms = utc_now_ms();
            transaction.execute(
                "UPDATE rch_file_attachments SET payload = ?1 WHERE file_id = ?2",
                params![encode_msgpack(&record)?, record.file_id],
            )?;
        }
    }
    Ok(())
}
