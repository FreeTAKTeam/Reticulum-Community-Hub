use super::{RchCoreError, RchSqliteStore, TransactionBehavior, Value};

/// Trigger-maintained inbox status counts (#242): diagnostics read four rows
/// instead of summing an inbox that only grows with retained custody history.
impl RchSqliteStore {
    pub(crate) fn migrate_broker_inbox_status_counts(&self) -> Result<(), RchCoreError> {
        let applied: bool = self.connection.query_row(
            "SELECT EXISTS(SELECT 1 FROM rch_schema_migrations WHERE version=10)",
            [],
            |row| row.get(0),
        )?;
        if applied {
            return Ok(());
        }
        self.backup_before_migration(10)?;
        let tx =
            rusqlite::Transaction::new_unchecked(&self.connection, TransactionBehavior::Immediate)?;
        let applied: bool = tx.query_row(
            "SELECT EXISTS(SELECT 1 FROM rch_schema_migrations WHERE version=10)",
            [],
            |row| row.get(0),
        )?;
        if !applied {
            tx.execute_batch(
                "CREATE TABLE rch_broker_inbox_status_counts (
                    status TEXT PRIMARY KEY, rows INTEGER NOT NULL);
                 INSERT INTO rch_broker_inbox_status_counts(status,rows)
                    SELECT status,COUNT(*) FROM rch_broker_inbox GROUP BY status;
                 CREATE TRIGGER rch_broker_inbox_count_insert AFTER INSERT ON rch_broker_inbox BEGIN
                    INSERT INTO rch_broker_inbox_status_counts VALUES(NEW.status,1)
                    ON CONFLICT(status) DO UPDATE SET rows=rows+1;
                 END;
                 CREATE TRIGGER rch_broker_inbox_count_update AFTER UPDATE OF status ON rch_broker_inbox
                 WHEN OLD.status IS NOT NEW.status BEGIN
                    UPDATE rch_broker_inbox_status_counts SET rows=rows-1 WHERE status=OLD.status;
                    INSERT INTO rch_broker_inbox_status_counts VALUES(NEW.status,1)
                    ON CONFLICT(status) DO UPDATE SET rows=rows+1;
                 END;
                 CREATE TRIGGER rch_broker_inbox_count_delete AFTER DELETE ON rch_broker_inbox BEGIN
                    UPDATE rch_broker_inbox_status_counts SET rows=rows-1 WHERE status=OLD.status;
                 END;",
            )?;
            tx.execute(
                "INSERT INTO rch_schema_migrations VALUES(10,'broker inbox status counts',?1)",
                [crate::utc_now_ms()],
            )?;
            tx.execute(
                "INSERT OR REPLACE INTO rch_settings VALUES('schema_version','10')",
                [],
            )?;
        }
        tx.commit()?;
        Ok(())
    }
}

impl RchSqliteStore {
    pub fn durable_broker_diagnostics(&self) -> Result<Value, RchCoreError> {
        let (inbox_bytes, outbox_bytes): (i64, i64) = self.connection.query_row(
            "SELECT inbox_bytes,outbox_bytes FROM rch_broker_profile",
            [],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )?;
        let count = |status: &str| -> Result<i64, RchCoreError> {
            Ok(self.connection.query_row(
                "SELECT COALESCE((SELECT rows FROM rch_broker_inbox_status_counts WHERE status=?1),0)",
                [status],
                |r| r.get(0),
            )?)
        };
        let counts = (
            count("stored")?,
            count("applied")?,
            count("rejected")?,
            count("upgrade_required")?,
        );
        let dispatch: i64 = self.connection.query_row(
            "SELECT COUNT(*) FROM rch_broker_dispatch WHERE state='pending'",
            [],
            |r| r.get(0),
        )?;
        let sqlite: String = self
            .connection
            .query_row("SELECT sqlite_version()", [], |r| r.get(0))?;
        Ok(
            serde_json::json!({"inbox_bytes":inbox_bytes,"outbox_bytes":outbox_bytes,"pending":counts.0,"applied":counts.1,"rejected":counts.2,"upgrade_required":counts.3,"pending_dispatch":dispatch,"sqlite_version":sqlite,"durability":"WAL/FULL","writer_version":1}),
        )
    }
}

#[cfg(test)]
mod tests {
    use crate::RchSqliteStore;

    #[test]
    fn status_counts_track_inbox_writes_and_backfill_legacy_rows() {
        let dir = std::env::temp_dir().join(format!("rch-inbox-counts-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&dir).expect("dir");
        let path = dir.join("rch.db");
        let store = RchSqliteStore::open(&path).expect("open");
        let insert = |position: i64, status: &str| {
            store
                .connection
                .execute(
                    "INSERT INTO rch_broker_inbox VALUES('j',?1,'e',0,'',?1,?2,NULL)",
                    rusqlite::params![position, status],
                )
                .expect("insert");
        };
        insert(1, "stored");
        insert(2, "stored");
        insert(3, "applied");
        store
            .connection
            .execute(
                "UPDATE rch_broker_inbox SET status='rejected' WHERE position=1",
                [],
            )
            .expect("reject");
        store
            .connection
            .execute("DELETE FROM rch_broker_inbox WHERE position=3", [])
            .expect("delete");
        let check = |store: &RchSqliteStore| {
            let count = |status: &str| -> i64 {
                store
                    .connection
                    .query_row(
                        "SELECT COALESCE((SELECT rows FROM rch_broker_inbox_status_counts WHERE status=?1),0)",
                        [status],
                        |r| r.get(0),
                    )
                    .expect("count")
            };
            let sql: (i64, i64, i64) = store
                .connection
                .query_row(
                    "SELECT COALESCE(SUM(status='stored'),0),COALESCE(SUM(status='applied'),0),COALESCE(SUM(status='rejected'),0) FROM rch_broker_inbox",
                    [],
                    |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
                )
                .expect("sum");
            assert_eq!((count("stored"), count("applied"), count("rejected")), sql);
        };
        check(&store);
        // A pre-v10 database is backfilled from its existing rows.
        store
            .connection
            .execute_batch(
                "DROP TRIGGER rch_broker_inbox_count_insert; DROP TRIGGER rch_broker_inbox_count_update;
                 DROP TRIGGER rch_broker_inbox_count_delete; DROP TABLE rch_broker_inbox_status_counts;
                 DELETE FROM rch_schema_migrations WHERE version=10;
                 INSERT INTO rch_broker_inbox VALUES('j',9,'e',0,'','9','applied',NULL);",
            )
            .expect("legacy");
        drop(store);
        check(&RchSqliteStore::open(&path).expect("reopen"));
        std::fs::remove_dir_all(dir).expect("cleanup");
    }
}
