use super::{
    RchCoreError, SqlValue, Transaction, delete_payload_row, sql_key_string, upsert_payload_row,
};
use serde::Serialize;
use std::collections::{HashMap, HashSet};

/// Persist only actual changes under the caller's existing write transaction.
/// Comparing borrowed records avoids encoding and rewriting unrelated payloads.
pub(super) fn save_payload_delta<T, KeyFn, UpsertFn>(
    transaction: &Transaction<'_>,
    table: &str,
    before: &[T],
    after: &[T],
    key_columns: KeyFn,
    indexed_columns: UpsertFn,
) -> Result<(), RchCoreError>
where
    T: Serialize + PartialEq,
    KeyFn: Fn(&T) -> Vec<(&'static str, SqlValue)> + Copy,
    UpsertFn: Fn(&T) -> Vec<(&'static str, SqlValue)> + Copy,
{
    let before_keys = before
        .iter()
        .map(|record| {
            let columns = key_columns(record);
            (sql_key_string(&columns), (columns, record))
        })
        .collect::<HashMap<_, _>>();
    let after_key_set = after
        .iter()
        .map(|record| sql_key_string(&key_columns(record)))
        .collect::<HashSet<_>>();
    for (key, (columns, _)) in &before_keys {
        if !after_key_set.contains(key.as_str()) {
            delete_payload_row(transaction, table, columns.clone())?;
        }
    }
    for record in after {
        let key = sql_key_string(&key_columns(record));
        if before_keys
            .get(&key)
            .is_none_or(|(_, previous)| *previous != record)
        {
            upsert_payload_row(transaction, table, indexed_columns(record), record)?;
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use rusqlite::Connection;
    use serde::Deserialize;

    #[derive(Clone, PartialEq, Serialize, Deserialize)]
    struct Record {
        key: String,
        content: String,
    }

    fn columns(record: &Record) -> Vec<(&'static str, SqlValue)> {
        vec![("record_key", SqlValue::Text(record.key.clone()))]
    }

    fn connection() -> Connection {
        let connection = Connection::open_in_memory().expect("database");
        connection
            .execute_batch(
                "CREATE TABLE records (record_key TEXT PRIMARY KEY, payload BLOB NOT NULL)",
            )
            .expect("schema");
        connection
    }

    #[test]
    fn unchanged_history_is_neither_encoded_nor_rewritten() {
        let mut connection = connection();
        let records = (0..1000)
            .map(|index| Record {
                key: index.to_string(),
                content: "x".repeat(4096),
            })
            .collect::<Vec<_>>();
        let transaction = connection.transaction().expect("transaction");
        save_payload_delta(&transaction, "records", &[], &records, columns, columns).expect("seed");
        transaction.commit().expect("commit");
        let changes = connection.total_changes();
        // A persistence regression must fail before an unrelated row can be rewritten.
        connection
            .execute_batch(
                "CREATE TRIGGER reject_rewrite BEFORE INSERT ON records
             BEGIN SELECT RAISE(ABORT, 'unrelated row rewritten'); END;",
            )
            .expect("guard");
        let transaction = connection.transaction().expect("transaction");
        save_payload_delta(
            &transaction,
            "records",
            &records,
            &records,
            columns,
            columns,
        )
        .expect("no unchanged inserts");
        transaction.commit().expect("commit");
        assert_eq!(connection.total_changes(), changes);
    }

    #[test]
    fn changed_added_and_removed_rows_are_persisted_and_rollback_atomically() {
        let mut connection = connection();
        let before = vec![
            Record {
                key: "keep".into(),
                content: "unchanged".into(),
            },
            Record {
                key: "edit".into(),
                content: "old".into(),
            },
            Record {
                key: "delete".into(),
                content: "removed".into(),
            },
        ];
        let transaction = connection.transaction().expect("transaction");
        save_payload_delta(&transaction, "records", &[], &before, columns, columns).expect("seed");
        transaction.commit().expect("commit");
        let changes = connection.total_changes();
        let after = vec![
            before[0].clone(),
            Record {
                key: "edit".into(),
                content: "new".into(),
            },
            Record {
                key: "add".into(),
                content: "added".into(),
            },
        ];
        {
            let transaction = connection.transaction().expect("transaction");
            save_payload_delta(&transaction, "records", &before, &after, columns, columns)
                .expect("staged delta");
            // Drop rolls back changed, added and deleted rows together.
        }
        let payload: Vec<u8> = connection
            .query_row(
                "SELECT payload FROM records WHERE record_key='edit'",
                [],
                |row| row.get(0),
            )
            .expect("old row");
        assert_eq!(
            rmp_serde::from_slice::<Record>(&payload)
                .expect("decode")
                .content,
            "old"
        );
        let transaction = connection.transaction().expect("transaction");
        save_payload_delta(&transaction, "records", &before, &after, columns, columns)
            .expect("delta");
        transaction.commit().expect("commit");
        assert_eq!(connection.total_changes() - changes, 6); // Three attempted, then three committed.
        let keys = connection
            .prepare("SELECT record_key FROM records ORDER BY record_key")
            .expect("query")
            .query_map([], |row| row.get::<_, String>(0))
            .expect("rows")
            .collect::<Result<Vec<_>, _>>()
            .expect("keys");
        assert_eq!(keys, ["add", "edit", "keep"]);
        let payload: Vec<u8> = connection
            .query_row(
                "SELECT payload FROM records WHERE record_key='edit'",
                [],
                |row| row.get(0),
            )
            .expect("changed row");
        assert_eq!(
            rmp_serde::from_slice::<Record>(&payload)
                .expect("decode")
                .content,
            "new"
        );
    }
}
