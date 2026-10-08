use super::{
    RchCoreError, RchSqliteStore, SubjectOperationRight, decode_msgpack, encode_msgpack,
    operation_rights::{operation_right_key, operation_right_record},
    params,
};
use rusqlite::{OptionalExtension, TransactionBehavior};
use std::time::{Duration, Instant};

const SELECT_RIGHT: &str = "SELECT payload FROM rch_subject_operation_rights
    WHERE subject_type = ?1 AND subject_id = ?2 AND operation = ?3
    AND scope_type = ?4 AND scope_id = ?5";

/// Accounting for one committed keyed mutation. Payload bytes exclude decoded
/// string allocations, `SQLite` pages, statement preparation and allocator overhead.
#[derive(Debug)]
pub struct OperationRightMutation {
    pub record: SubjectOperationRight,
    pub rows_read: u64,
    pub rows_written: u64,
    pub decoded_payload_bytes: u64,
    pub elapsed: Duration,
}

impl RchSqliteStore {
    /// Update one normalized right under a write reservation, preserving its UID.
    /// No aggregate snapshot or unrelated payload is read or written.
    pub fn set_operation_right(
        &mut self,
        subject_type: &str,
        subject_id: &str,
        operation: &str,
        scope_type: &str,
        scope_id: &str,
        granted: bool,
    ) -> Result<OperationRightMutation, RchCoreError> {
        let started = Instant::now();
        let key = operation_right_key(subject_type, subject_id, operation, scope_type, scope_id)?;
        let transaction = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let payload: Option<Vec<u8>> = transaction
            .query_row(
                SELECT_RIGHT,
                params![key.0, key.1, key.2, key.3, key.4],
                |row| row.get(0),
            )
            .optional()?;
        let rows_read = u64::from(payload.is_some());
        let decoded_payload_bytes = payload
            .as_ref()
            .map_or(0, |payload| payload.len().try_into().unwrap_or(u64::MAX));
        let previous: Option<SubjectOperationRight> = payload
            .as_ref()
            .map(|payload| decode_msgpack(payload))
            .transpose()?;
        if let Some(record) = &previous {
            if (
                &record.subject_type,
                &record.subject_id,
                &record.operation,
                &record.scope_type,
                &record.scope_id,
            ) != (&key.0, &key.1, &key.2, &key.3, &key.4)
            {
                return Err(RchCoreError::Decode(
                    "operation-right payload does not match its durable key".to_string(),
                ));
            }
        }
        let record = operation_right_record(&key, previous.as_ref(), granted);
        let rows_written = if previous.as_ref() == Some(&record) {
            0
        } else {
            transaction
                .execute(
                    "INSERT INTO rch_subject_operation_rights
                 (subject_type, subject_id, operation, scope_type, scope_id, payload)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6)
                 ON CONFLICT(subject_type, subject_id, operation, scope_type, scope_id)
                 DO UPDATE SET payload = excluded.payload",
                    params![key.0, key.1, key.2, key.3, key.4, encode_msgpack(&record)?],
                )?
                .try_into()
                .unwrap_or(u64::MAX)
        };
        transaction.commit()?;
        Ok(OperationRightMutation {
            record,
            rows_read,
            rows_written,
            decoded_payload_bytes,
            elapsed: started.elapsed(),
        })
    }
}

#[cfg(test)]
mod tests;
