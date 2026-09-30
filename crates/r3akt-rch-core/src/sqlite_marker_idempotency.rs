use super::{
    CommandResultEnvelope, CommandResultStatus, MarkerRecord, RchCoreError, RchSqliteStore,
    decode_msgpack, encode_msgpack, params,
};
use rusqlite::{OptionalExtension, TransactionBehavior};

pub enum MarkerCreation {
    Created(MarkerRecord),
    Replayed(MarkerRecord),
    KeyConflict,
}

impl RchSqliteStore {
    /// Commit the marker and its replay result in the existing durable command
    /// result table. Read only this key under the write reservation; never load
    /// an unbounded command history into the server's request cache.
    pub fn create_marker_once(
        &mut self,
        marker: &MarkerRecord,
        command_id: &str,
        fingerprint: &str,
    ) -> Result<MarkerCreation, RchCoreError> {
        let transaction = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let cached: Option<Vec<u8>> = transaction
            .query_row(
                "SELECT payload FROM rch_command_results WHERE command_id = ?1",
                [command_id],
                |row| row.get(0),
            )
            .optional()?;
        if let Some(payload) = cached {
            let result: CommandResultEnvelope = decode_msgpack(&payload)?;
            if result.correlation_id.as_deref() != Some(fingerprint) {
                return Ok(MarkerCreation::KeyConflict);
            }
            if result.status != CommandResultStatus::Accepted {
                return Err(RchCoreError::Decode(
                    "marker replay result is not an accepted command".to_string(),
                ));
            }
            let original = serde_json::from_value(result.result)
                .map_err(|error| RchCoreError::Decode(format!("marker replay result: {error}")))?;
            return Ok(MarkerCreation::Replayed(original));
        }
        transaction.execute(
            "INSERT INTO rch_markers (object_destination_hash, payload) VALUES (?1, ?2)",
            params![marker.object_destination_hash, encode_msgpack(marker)?],
        )?;
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
                .map_err(|error| RchCoreError::Encode(format!("marker replay result: {error}")))?,
        };
        transaction.execute(
            "INSERT INTO rch_command_results (command_id, payload) VALUES (?1, ?2)",
            params![command_id, encode_msgpack(&result)?],
        )?;
        transaction.commit()?;
        Ok(MarkerCreation::Created(marker.clone()))
    }
}
