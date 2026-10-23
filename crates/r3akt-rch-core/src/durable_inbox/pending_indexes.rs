use super::{RchCoreError, RchSqliteStore, TransactionBehavior};

impl RchSqliteStore {
    pub(crate) fn migrate_broker_pending_indexes(&self) -> Result<(), RchCoreError> {
        let applied: bool = self.connection.query_row(
            "SELECT EXISTS(SELECT 1 FROM rch_schema_migrations WHERE version=8)",
            [],
            |row| row.get(0),
        )?;
        if applied {
            return Ok(());
        }
        self.backup_before_migration(8)?;
        let tx =
            rusqlite::Transaction::new_unchecked(&self.connection, TransactionBehavior::Immediate)?;
        let applied: bool = tx.query_row(
            "SELECT EXISTS(SELECT 1 FROM rch_schema_migrations WHERE version=8)",
            [],
            |row| row.get(0),
        )?;
        if !applied {
            tx.execute_batch(
                "CREATE INDEX rch_broker_dispatch_pending_state ON rch_broker_dispatch(state)
                    WHERE state='pending';
                 CREATE INDEX rch_broker_inbox_unfinished ON rch_broker_inbox(journal_id,position)
                    WHERE status NOT IN ('applied','rejected');",
            )?;
            tx.execute(
                "INSERT INTO rch_schema_migrations VALUES(8,'pending-only broker lookups',?1)",
                [crate::utc_now_ms()],
            )?;
            tx.execute(
                "INSERT OR REPLACE INTO rch_settings VALUES('schema_version','8')",
                [],
            )?;
        }
        tx.commit()?;
        Ok(())
    }
}
