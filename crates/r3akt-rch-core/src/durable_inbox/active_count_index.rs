use super::{RchCoreError, RchSqliteStore, TransactionBehavior};

impl RchSqliteStore {
    pub(crate) fn migrate_broker_active_count_index(&self) -> Result<(), RchCoreError> {
        let applied: bool = self.connection.query_row(
            "SELECT EXISTS(SELECT 1 FROM rch_schema_migrations WHERE version=9)",
            [],
            |row| row.get(0),
        )?;
        if applied {
            return Ok(());
        }
        self.backup_before_migration(9)?;
        let tx =
            rusqlite::Transaction::new_unchecked(&self.connection, TransactionBehavior::Immediate)?;
        let applied: bool = tx.query_row(
            "SELECT EXISTS(SELECT 1 FROM rch_schema_migrations WHERE version=9)",
            [],
            |row| row.get(0),
        )?;
        if !applied {
            tx.execute_batch(
                "CREATE INDEX rch_broker_dispatch_active_state ON rch_broker_dispatch(state)
                    WHERE state IN ('pending','admitted');",
            )?;
            tx.execute(
                "INSERT INTO rch_schema_migrations VALUES(9,'active broker delivery count',?1)",
                [crate::utc_now_ms()],
            )?;
            tx.execute(
                "INSERT OR REPLACE INTO rch_settings VALUES('schema_version','9')",
                [],
            )?;
        }
        tx.commit()?;
        Ok(())
    }
}
