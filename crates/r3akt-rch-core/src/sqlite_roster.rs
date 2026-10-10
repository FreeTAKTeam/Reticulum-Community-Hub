use super::{ClientRecord, RchCoreError, RchSqliteStore, normalize_hash};
use rusqlite::{Transaction, TransactionBehavior};

impl RchSqliteStore {
    pub fn upsert_client(&mut self, record: &ClientRecord) -> Result<(), RchCoreError> {
        let transaction = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let key = remove_aliases(&transaction, &record.identity)?;
        super::upsert_payload_row(
            &transaction,
            "rch_clients",
            vec![("identity", super::sql_text(key))],
            record,
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
    // Legacy external writers may omit the derived key. Inspect only their IDs,
    // preserving alias cleanup without hydrating any unrelated payload.
    let aliases = {
        let mut statement =
            transaction.prepare("SELECT identity FROM rch_clients WHERE identity_normalized=?1 OR identity_normalized IS NULL")?;
        let rows = statement.query_map([&key], |row| row.get::<_, String>(0))?;
        rows.collect::<Result<Vec<_>, _>>()?
    };
    for alias in aliases {
        if normalize_hash(Some(&alias)).as_deref() == Some(key.as_str()) {
            transaction.execute("DELETE FROM rch_clients WHERE identity = ?1", [alias])?;
        }
    }
    Ok(key)
}
