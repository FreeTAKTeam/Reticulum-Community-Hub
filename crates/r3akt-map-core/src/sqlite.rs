//! Marker persistence compatible with the RCH `SQLite` layout.
//!
//! Rows live in `rch_markers` (named `MessagePack` payload plus an indexed
//! `local_id`), and idempotent creations record an accepted
//! `CommandResultEnvelope` in `rch_command_results`. RCH creates these tables
//! through its own migration chain; standalone consumers call
//! [`ensure_schema`], which produces the same layout.

use r3akt_profile_rch::{CommandResultEnvelope, CommandResultStatus};
use rusqlite::{Connection, OptionalExtension, TransactionBehavior, params};
use serde::Serialize;
use serde::de::DeserializeOwned;

use crate::marker::MarkerRecord;

/// Persistence failures.
#[derive(Debug, thiserror::Error)]
pub enum StoreError {
    #[error(transparent)]
    Sqlite(#[from] rusqlite::Error),
    #[error("{0}")]
    Encode(String),
    #[error("{0}")]
    Decode(String),
}

/// Outcome of an idempotent creation.
#[derive(Debug, Clone, PartialEq)]
pub enum MarkerCreation {
    Created(MarkerRecord),
    /// The key was already used with the same fields; the original marker.
    Replayed(MarkerRecord),
    /// The key was already used with different fields.
    KeyConflict,
}

/// Creates the marker and command-result tables if absent.
///
/// # Errors
/// `SQLite` failures.
pub fn ensure_schema(connection: &Connection) -> Result<(), StoreError> {
    connection.execute_batch(
        "CREATE TABLE IF NOT EXISTS rch_markers (
            object_destination_hash TEXT PRIMARY KEY,
            payload BLOB NOT NULL
        );
        CREATE TABLE IF NOT EXISTS rch_command_results (
            command_id TEXT PRIMARY KEY,
            payload BLOB NOT NULL
        );",
    )?;
    let has_local_id = connection
        .prepare("SELECT 1 FROM pragma_table_info('rch_markers') WHERE name = 'local_id'")?
        .exists([])?;
    if !has_local_id {
        connection.execute("ALTER TABLE rch_markers ADD COLUMN local_id TEXT", [])?;
    }
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_rch_markers_local_id ON rch_markers(local_id)",
        [],
    )?;
    Ok(())
}

/// Inserts or replaces a marker row.
///
/// # Errors
/// `SQLite` or encoding failures.
pub fn upsert(connection: &Connection, marker: &MarkerRecord) -> Result<(), StoreError> {
    connection.execute(
        "INSERT OR REPLACE INTO rch_markers (object_destination_hash, payload, local_id)
         VALUES (?1, ?2, ?3)",
        params![
            marker.object_destination_hash,
            encode(marker)?,
            marker.local_id
        ],
    )?;
    Ok(())
}

/// Inserts a new marker row; fails if the identifier exists.
///
/// # Errors
/// `SQLite` (including uniqueness) or encoding failures.
pub fn insert(connection: &Connection, marker: &MarkerRecord) -> Result<(), StoreError> {
    connection.execute(
        "INSERT INTO rch_markers (object_destination_hash, payload, local_id) VALUES (?1, ?2, ?3)",
        params![
            marker.object_destination_hash,
            encode(marker)?,
            marker.local_id
        ],
    )?;
    Ok(())
}

/// Deletes a marker row; absent rows are not an error.
///
/// # Errors
/// `SQLite` failures.
pub fn delete(connection: &Connection, object_destination_hash: &str) -> Result<(), StoreError> {
    connection.execute(
        "DELETE FROM rch_markers WHERE object_destination_hash = ?1",
        params![object_destination_hash],
    )?;
    Ok(())
}

/// Loads one marker.
///
/// # Errors
/// `SQLite` or decoding failures.
pub fn get(
    connection: &Connection,
    object_destination_hash: &str,
) -> Result<Option<MarkerRecord>, StoreError> {
    connection
        .query_row(
            "SELECT payload FROM rch_markers WHERE object_destination_hash = ?1",
            [object_destination_hash],
            |row| row.get::<_, Vec<u8>>(0),
        )
        .optional()?
        .as_deref()
        .map(decode)
        .transpose()
}

/// Loads every marker, ordered by identifier.
///
/// # Errors
/// `SQLite` or decoding failures.
pub fn load_all(connection: &Connection) -> Result<Vec<MarkerRecord>, StoreError> {
    let mut statement =
        connection.prepare("SELECT payload FROM rch_markers ORDER BY object_destination_hash")?;
    let rows = statement.query_map([], |row| row.get::<_, Vec<u8>>(0))?;
    rows.map(|row| decode(&row?)).collect()
}

/// Applies `update` to a stored marker atomically; `None` when absent.
///
/// # Errors
/// `SQLite` or codec failures; the row is unchanged on error.
pub fn update(
    connection: &mut Connection,
    object_destination_hash: &str,
    update: impl FnOnce(&mut MarkerRecord),
) -> Result<Option<MarkerRecord>, StoreError> {
    let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
    let Some(mut record) = get(&transaction, object_destination_hash)? else {
        return Ok(None);
    };
    update(&mut record);
    transaction.execute(
        "UPDATE rch_markers SET payload = ?1, local_id = ?3 WHERE object_destination_hash = ?2",
        params![encode(&record)?, object_destination_hash, record.local_id],
    )?;
    transaction.commit()?;
    Ok(Some(record))
}

/// Inserts `marker` once per `command_id`, binding the key to `fingerprint`.
/// Reads only this key under the write reservation.
///
/// # Errors
/// `SQLite` or codec failures, or a stored result that is not an accepted
/// marker creation.
pub fn create_once(
    connection: &mut Connection,
    marker: &MarkerRecord,
    command_id: &str,
    fingerprint: &str,
) -> Result<MarkerCreation, StoreError> {
    let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
    let cached: Option<Vec<u8>> = transaction
        .query_row(
            "SELECT payload FROM rch_command_results WHERE command_id = ?1",
            [command_id],
            |row| row.get(0),
        )
        .optional()?;
    if let Some(payload) = cached {
        let result: CommandResultEnvelope = decode(&payload)?;
        if result.correlation_id.as_deref() != Some(fingerprint) {
            return Ok(MarkerCreation::KeyConflict);
        }
        if result.status != CommandResultStatus::Accepted {
            return Err(StoreError::Decode(
                "marker replay result is not an accepted command".to_string(),
            ));
        }
        let original = serde_json::from_value(result.result)
            .map_err(|error| StoreError::Decode(format!("marker replay result: {error}")))?;
        return Ok(MarkerCreation::Replayed(original));
    }
    insert(&transaction, marker)?;
    let result = CommandResultEnvelope {
        command_id: command_id.to_string(),
        status: CommandResultStatus::Accepted,
        detail: None,
        reason_code: None,
        reason: None,
        required_capabilities: Vec::new(),
        accepted_at: None,
        by_identity: None,
        correlation_id: Some(fingerprint.to_string()),
        result: serde_json::to_value(marker)
            .map_err(|error| StoreError::Encode(format!("marker replay result: {error}")))?,
    };
    transaction.execute(
        "INSERT INTO rch_command_results (command_id, payload) VALUES (?1, ?2)",
        params![command_id, encode(&result)?],
    )?;
    transaction.commit()?;
    Ok(MarkerCreation::Created(marker.clone()))
}

fn encode<T: Serialize>(value: &T) -> Result<Vec<u8>, StoreError> {
    rmp_serde::to_vec_named(value).map_err(|error| StoreError::Encode(error.to_string()))
}

fn decode<T: DeserializeOwned>(bytes: &[u8]) -> Result<T, StoreError> {
    rmp_serde::from_slice(bytes).map_err(|error| StoreError::Decode(error.to_string()))
}
