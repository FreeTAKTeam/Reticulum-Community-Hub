use super::{
    FileAttachmentRecord, IdentityStateRecord, MarkerRecord, RchCoreError, RchSqliteStore,
    Transaction, ZoneRecord, decode_msgpack, encode_msgpack, params,
};
use rusqlite::{OptionalExtension, TransactionBehavior};

// Read/modify/write operations load the durable row under the same reservation
// as the update. A stale server projection cannot restore old fields or revive
// a record deleted by another connection.
impl RchSqliteStore {
    /// Announces may create an identity projection, but cannot overwrite a
    /// moderation decision committed through another connection.
    pub fn ensure_identity_states(
        &mut self,
        candidates: &[IdentityStateRecord],
    ) -> Result<Vec<IdentityStateRecord>, RchCoreError> {
        let transaction = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let mut records = Vec::with_capacity(candidates.len());
        for candidate in candidates {
            let existing = identity_state_row(&transaction, &candidate.identity)?;
            let record = if let Some(existing) = existing {
                existing
            } else {
                transaction.execute(
                    "INSERT INTO rch_identity_states (identity, payload) VALUES (?1, ?2)",
                    params![candidate.identity, encode_msgpack(candidate)?],
                )?;
                candidate.clone()
            };
            records.push(record);
        }
        transaction.commit()?;
        Ok(records)
    }

    pub fn patch_identity_state(
        &mut self,
        identity: &str,
        banned: Option<bool>,
        blackholed: Option<bool>,
        now_ms: i64,
    ) -> Result<IdentityStateRecord, RchCoreError> {
        let transaction = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let mut record =
            identity_state_row(&transaction, identity)?.unwrap_or_else(|| IdentityStateRecord {
                identity: identity.to_string(),
                is_banned: false,
                is_blackholed: false,
                updated_ts_ms: now_ms,
            });
        if let Some(value) = banned {
            record.is_banned = value;
        }
        if let Some(value) = blackholed {
            record.is_blackholed = value;
        }
        record.updated_ts_ms = now_ms;
        transaction.execute(
            "INSERT OR REPLACE INTO rch_identity_states (identity, payload) VALUES (?1, ?2)",
            params![identity, encode_msgpack(&record)?],
        )?;
        transaction.commit()?;
        Ok(record)
    }

    pub fn update_marker(
        &mut self,
        id: &str,
        update: impl FnOnce(&mut MarkerRecord),
    ) -> Result<Option<MarkerRecord>, RchCoreError> {
        let transaction = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let payload: Option<Vec<u8>> = transaction
            .query_row(
                "SELECT payload FROM rch_markers WHERE object_destination_hash = ?1",
                [id],
                |row| row.get(0),
            )
            .optional()?;
        let Some(payload) = payload else {
            return Ok(None);
        };
        let mut record: MarkerRecord = decode_msgpack(&payload)?;
        update(&mut record);
        transaction.execute(
            "UPDATE rch_markers SET payload = ?1 WHERE object_destination_hash = ?2",
            params![encode_msgpack(&record)?, id],
        )?;
        transaction.commit()?;
        Ok(Some(record))
    }

    pub fn update_zone(
        &mut self,
        id: &str,
        update: impl FnOnce(&mut ZoneRecord),
    ) -> Result<Option<ZoneRecord>, RchCoreError> {
        let transaction = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let payload: Option<Vec<u8>> = transaction
            .query_row(
                "SELECT payload FROM rch_zones WHERE zone_id = ?1",
                [id],
                |row| row.get(0),
            )
            .optional()?;
        let Some(payload) = payload else {
            return Ok(None);
        };
        let mut record: ZoneRecord = decode_msgpack(&payload)?;
        update(&mut record);
        transaction.execute(
            "UPDATE rch_zones SET payload = ?1 WHERE zone_id = ?2",
            params![encode_msgpack(&record)?, id],
        )?;
        transaction.commit()?;
        Ok(Some(record))
    }

    pub fn patch_file_attachment_topic(
        &mut self,
        id: u64,
        category: &str,
        topic: Option<String>,
        now_ms: i64,
    ) -> Result<Option<FileAttachmentRecord>, RchCoreError> {
        let transaction = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let Some(mut record) = attachment_row(&transaction, id, category)? else {
            return Ok(None);
        };
        record.topic_id = topic;
        record.updated_ts_ms = now_ms;
        transaction.execute(
            "UPDATE rch_file_attachments SET payload = ?1 WHERE file_id = ?2 AND category = ?3",
            params![encode_msgpack(&record)?, id, category],
        )?;
        transaction.commit()?;
        Ok(Some(record))
    }

    pub fn take_file_attachment(
        &mut self,
        id: u64,
        category: &str,
    ) -> Result<Option<FileAttachmentRecord>, RchCoreError> {
        let transaction = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let record = attachment_row(&transaction, id, category)?;
        if record.is_some() {
            transaction.execute(
                "DELETE FROM rch_file_attachments WHERE file_id = ?1 AND category = ?2",
                params![id, category],
            )?;
        }
        transaction.commit()?;
        Ok(record)
    }
}

fn identity_state_row(
    transaction: &Transaction<'_>,
    identity: &str,
) -> Result<Option<IdentityStateRecord>, RchCoreError> {
    let payload: Option<Vec<u8>> = transaction
        .query_row(
            "SELECT payload FROM rch_identity_states WHERE identity = ?1",
            [identity],
            |row| row.get(0),
        )
        .optional()?;
    payload.map(|payload| decode_msgpack(&payload)).transpose()
}

fn attachment_row(
    transaction: &Transaction<'_>,
    id: u64,
    category: &str,
) -> Result<Option<FileAttachmentRecord>, RchCoreError> {
    let payload: Option<Vec<u8>> = transaction
        .query_row(
            "SELECT payload FROM rch_file_attachments WHERE file_id = ?1 AND category = ?2",
            params![id, category],
            |row| row.get(0),
        )
        .optional()?;
    payload.map(|payload| decode_msgpack(&payload)).transpose()
}
