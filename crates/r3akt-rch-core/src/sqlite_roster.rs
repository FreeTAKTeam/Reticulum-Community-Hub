use super::{ClientRecord, RchCoreError, RchSqliteStore, encode_msgpack, normalize_hash, params};
use rusqlite::{Transaction, TransactionBehavior};

impl RchSqliteStore {
    pub fn upsert_client(&mut self, record: &ClientRecord) -> Result<(), RchCoreError> {
        let transaction = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let key = remove_aliases(&transaction, &record.identity)?;
        transaction.execute(
            "INSERT INTO rch_clients (identity, payload) VALUES (?1, ?2)",
            params![key, encode_msgpack(record)?],
        )?;
        transaction.commit()?;
        Ok(())
    }

    pub fn delete_client(&mut self, identity: &str) -> Result<(), RchCoreError> {
        let transaction = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        remove_aliases(&transaction, identity)?;
        transaction.commit()?;
        Ok(())
    }
}

fn remove_aliases(transaction: &Transaction<'_>, identity: &str) -> Result<String, RchCoreError> {
    let key = normalize_hash(Some(identity))
        .ok_or_else(|| RchCoreError::InvalidPayload("client identity is required".to_string()))?;
    // Legacy stores used raw identity strings as keys. Match those with the same
    // Rust normalization as the live roster, including Unicode whitespace;
    // SQLite's default trim() only removes ASCII spaces. Read keys, not payloads.
    let aliases = {
        let mut statement = transaction.prepare("SELECT identity FROM rch_clients")?;
        let rows = statement.query_map([], |row| row.get::<_, String>(0))?;
        rows.collect::<Result<Vec<_>, _>>()?
    };
    for alias in aliases {
        if normalize_hash(Some(&alias)).as_deref() == Some(key.as_str()) {
            transaction.execute("DELETE FROM rch_clients WHERE identity = ?1", [alias])?;
        }
    }
    Ok(key)
}
