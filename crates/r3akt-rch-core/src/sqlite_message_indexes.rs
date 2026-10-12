//! Atomic message identity migration and durable ordering preservation.
use super::{RchCoreError, RchSqliteStore};

impl RchSqliteStore {
    pub(super) fn migrate_message_indexes(&self) -> Result<(), RchCoreError> {
        if self.message_indexes_applied()? {
            return Ok(());
        }
        self.backup_before_migration(7)?;
        let transaction = rusqlite::Transaction::new_unchecked(
            &self.connection,
            rusqlite::TransactionBehavior::Immediate,
        )?;
        let applied: bool = transaction.query_row(
            "SELECT EXISTS(SELECT 1 FROM rch_schema_migrations WHERE version=7)",
            [],
            |row| row.get(0),
        )?;
        if applied {
            transaction.commit()?;
            return Ok(());
        }
        let duplicate: Option<String> = {
            use rusqlite::OptionalExtension;
            transaction.query_row("SELECT message_id FROM rch_messages GROUP BY message_id COLLATE NOCASE HAVING COUNT(*)>1 LIMIT 1", [], |row| row.get(0)).optional()?
        };
        if let Some(id) = duplicate {
            // Never silently discard payloads while duplicate reconciliation policy is pending.
            return Err(RchCoreError::InvalidPayload(format!(
                "schema 7 duplicate message identity {id}; message rows preserved and schema 7 not applied"
            )));
        }
        transaction.execute_batch("CREATE UNIQUE INDEX idx_rch_messages_identity ON rch_messages(message_id COLLATE NOCASE);")?;
        super::sqlite_chat_pages::migrate_chat_scope(&transaction)?;
        transaction.execute("INSERT INTO rch_schema_migrations VALUES(7,'message identity and conversation history indexes',?1)", [super::utc_now_ms()])?;
        transaction.execute(
            "INSERT OR REPLACE INTO rch_settings VALUES('schema_version','7')",
            [],
        )?;
        transaction.commit()?;
        Ok(())
    }
    fn message_indexes_applied(&self) -> Result<bool, RchCoreError> {
        self.connection
            .query_row(
                "SELECT EXISTS(SELECT 1 FROM rch_schema_migrations WHERE version=7)",
                [],
                |row| row.get(0),
            )
            .map_err(Into::into)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{ChatConversationFilter, DeliveryMode, MessageRecord};
    use serde_json::json;
    fn message(id: &str) -> MessageRecord {
        MessageRecord {
            message_id: id.into(),
            topic_id: None,
            destination: None,
            sender: "peer".into(),
            content: "sample".into(),
            delivery_mode: DeliveryMode::Broadcast,
            delivery_method: String::new(),
            delivery_policy_reason: String::new(),
            delivery_state: "received".into(),
            delivery_metadata: json!({"direction":"inbound"}),
            created_ts_ms: crate::utc_now_ms(),
            attachments: vec![],
        }
    }
    fn plans(store: &RchSqliteStore, sql: &str, values: &[&dyn rusqlite::ToSql]) -> Vec<String> {
        store
            .connection
            .prepare(&format!("EXPLAIN QUERY PLAN {sql}"))
            .expect("plan")
            .query_map(values, |row| row.get(3))
            .expect("rows")
            .collect::<Result<Vec<_>, _>>()
            .expect("plans")
    }
    #[test]
    fn identity_upsert_preserves_row_order_and_uses_nocase_unique_key() {
        let mut store = RchSqliteStore::in_memory().expect("store");
        let mut first = message("AaBb");
        let mut second = message("other");
        second.created_ts_ms = first.created_ts_ms;
        store.upsert_message(&first).expect("first");
        store.upsert_message(&second).expect("second");
        let id: i64 = store
            .connection
            .query_row(
                "SELECT id FROM rch_messages WHERE message_id='AaBb'",
                [],
                |row| row.get(0),
            )
            .expect("id");
        first.message_id = "aAbB".into();
        first.content = "updated".into();
        first.delivery_state = "delivered".into();
        store.upsert_message(&first).expect("upsert");
        let stored = store
            .message_by_id("AABB")
            .expect("lookup")
            .expect("message");
        assert_eq!(stored, first);
        assert_eq!(
            store
                .connection
                .query_row(
                    "SELECT id FROM rch_messages WHERE message_id=?1 COLLATE NOCASE",
                    ["AABB"],
                    |row| row.get::<_, i64>(0)
                )
                .expect("id"),
            id
        );
        assert_eq!(store.row_count("rch_messages").expect("count"), 2);
        let plan = plans(
            &store,
            "SELECT payload FROM rch_messages WHERE message_id=?1 COLLATE NOCASE",
            &[&"AABB"],
        );
        assert!(
            plan.iter()
                .any(|line| line.contains("SEARCH") && line.contains("idx_rch_messages_identity")),
            "{plan:?}"
        );
        let page = store
            .chat_history_page(
                &ChatConversationFilter {
                    scope: "broadcast",
                    target: None,
                },
                None,
                1,
            )
            .expect("page");
        assert_eq!(page.messages[0].message_id, "aAbB");
        let cursor = page.next_cursor.expect("cursor");
        first.content = "second update".into();
        store.upsert_message(&first).expect("update");
        let older = store
            .chat_history_page(
                &ChatConversationFilter {
                    scope: "broadcast",
                    target: None,
                },
                Some(cursor),
                1,
            )
            .expect("older");
        assert_eq!(older.messages[0].message_id, "other");
        assert!(older.next_cursor.is_none());
    }
    #[test]
    fn conversation_pages_use_keyed_scope_peer_indexes_and_include_both_directions() {
        let mut store = RchSqliteStore::in_memory().expect("store");
        for (id, source, destination, direction) in [
            ("inbound", "peer", "hub", "inbound"),
            ("outbound", "hub", "peer", "outbound"),
            ("self", "peer", "peer", "inbound"),
            ("unrelated", "other", "other", "inbound"),
            ("other-inbound", "other", "peer", "inbound"),
            ("other-outbound", "peer", "other", "outbound"),
        ] {
            let mut record = message(id);
            record.delivery_mode = DeliveryMode::Targeted;
            record.destination = Some(destination.into());
            record.delivery_metadata = json!({"direction":direction,"source":source});
            store.upsert_message(&record).expect("insert");
        }
        let page = store
            .chat_history_page(
                &ChatConversationFilter {
                    scope: "dm",
                    target: Some("peer"),
                },
                None,
                20,
            )
            .expect("dm");
        assert_eq!(page.messages.len(), 3);
        let plan = plans(
            &store,
            &crate::sqlite_chat_pages::page_sql("dm").expect("sql"),
            &[&"dm", &"peer", &i64::MAX, &0_i64, &21_i64],
        );
        for index in [
            "idx_rch_messages_source_history",
            "idx_rch_messages_destination_history",
        ] {
            assert!(
                plan.iter()
                    .any(|line| line.contains("SEARCH") && line.contains(index)),
                "{plan:?}"
            );
        }
        for scope in ["topic", "broadcast"] {
            let plan = plans(
                &store,
                &crate::sqlite_chat_pages::page_sql(scope).expect("sql"),
                &[&scope, &"topic", &i64::MAX, &0_i64, &21_i64],
            );
            assert!(
                plan.iter()
                    .any(|line| line.contains("SEARCH") && line.contains("history")),
                "{plan:?}"
            );
        }
    }
    #[test]
    fn topic_detachment_streams_matching_rows_and_ignores_other_payloads() {
        let mut store = RchSqliteStore::in_memory().expect("store");
        let unrelated = vec![0xc1];
        store.connection.execute("INSERT INTO rch_file_attachments(file_id,category,topic_id,payload) VALUES(5000,'file','other',?1)", [&unrelated]).expect("unrelated");
        for id in 1..=600 {
            store
                .upsert_file_attachment(&crate::FileAttachmentRecord {
                    file_id: id,
                    name: format!("{id}.txt"),
                    path: format!("{id}"),
                    category: "file".into(),
                    size: 20,
                    media_type: None,
                    topic_id: Some("target".into()),
                    created_ts_ms: 1,
                    updated_ts_ms: 1,
                })
                .expect("attachment");
        }
        let plan = plans(
            &store,
            "SELECT file_id,payload FROM rch_file_attachments WHERE topic_id=?1 AND file_id>?2 ORDER BY file_id LIMIT 256",
            &[&"target", &0_i64],
        );
        assert!(
            plan.iter().any(|line| line.contains("SEARCH")
                && line.contains("idx_rch_file_attachments_topic_id")),
            "{plan:?}"
        );
        let transaction = store.connection.transaction().expect("tx");
        crate::sqlite_commands::detach_topic_attachments(&transaction, "target").expect("detach");
        transaction.commit().expect("commit");
        assert_eq!(
            store
                .connection
                .query_row(
                    "SELECT COUNT(*) FROM rch_file_attachments WHERE topic_id IS NULL",
                    [],
                    |row| row.get::<_, i64>(0)
                )
                .expect("count"),
            600
        );
        let payload: Vec<u8> = store
            .connection
            .query_row(
                "SELECT payload FROM rch_file_attachments WHERE file_id=5000",
                [],
                |row| row.get(0),
            )
            .expect("other");
        assert_eq!(payload, unrelated);
        assert_eq!(
            store
                .load_file_attachment(1, "file")
                .expect("record")
                .expect("record")
                .topic_id,
            None
        );
    }
    #[test]
    fn populated_schema7_migration_preserves_payload_and_rolls_back_on_duplicates() {
        let directory =
            std::env::temp_dir().join(format!("rch-message-indexes-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir(&directory).expect("dir");
        let path = directory.join("state.db");
        let mut store = RchSqliteStore::open(&path).expect("store");
        let record = message("ABCD");
        store.upsert_message(&record).expect("message");
        let bytes: Vec<u8> = store
            .connection
            .query_row("SELECT payload FROM rch_messages", [], |row| row.get(0))
            .expect("bytes");
        store.connection.execute_batch("DROP INDEX idx_rch_messages_identity;DELETE FROM rch_schema_migrations WHERE version=7;UPDATE rch_settings SET setting_value='6' WHERE setting_key='schema_version';").expect("v6");
        store
            .connection
            .execute(
                "INSERT INTO rch_messages(message_id,payload) VALUES('abcd',?1)",
                [&bytes],
            )
            .expect("duplicate");
        drop(store);
        assert!(RchSqliteStore::open(&path).is_err());
        let connection = rusqlite::Connection::open(&path).expect("db");
        assert_eq!(
            connection
                .query_row("SELECT COUNT(*) FROM rch_messages", [], |row| row
                    .get::<_, i64>(0))
                .expect("count"),
            2
        );
        assert_eq!(
            connection
                .query_row(
                    "SELECT COUNT(*) FROM rch_schema_migrations WHERE version=7",
                    [],
                    |row| row.get::<_, i64>(0)
                )
                .expect("migration"),
            0
        );
        connection
            .execute("DELETE FROM rch_messages WHERE message_id='abcd'", [])
            .expect("reconcile fixture");
        drop(connection);
        let store = RchSqliteStore::open(&path).expect("migrate");
        let retained: Vec<u8> = store
            .connection
            .query_row("SELECT payload FROM rch_messages", [], |row| row.get(0))
            .expect("payload");
        assert_eq!(retained, bytes);
        assert_eq!(store.schema_version().expect("version"), "7");
        drop(store);
        assert_eq!(
            RchSqliteStore::open(&path)
                .expect("restart")
                .schema_version()
                .expect("version"),
            "7"
        );
        assert!(directory.join("state.db.pre-migration-v7.bak").exists());
        std::fs::remove_dir_all(directory).expect("cleanup");
    }
    #[test]
    fn malformed_migration_payload_rolls_back_index_and_version() {
        let store = RchSqliteStore::in_memory().expect("store");
        store.connection.execute_batch("DROP INDEX idx_rch_messages_identity;DELETE FROM rch_schema_migrations WHERE version=7;UPDATE rch_settings SET setting_value='6' WHERE setting_key='schema_version';INSERT INTO rch_messages(message_id,payload) VALUES('bad',X'C1');").expect("v6");
        assert!(store.migrate_message_indexes().is_err());
        assert_eq!(
            store
                .connection
                .query_row(
                    "SELECT COUNT(*) FROM sqlite_master WHERE name='idx_rch_messages_identity'",
                    [],
                    |row| row.get::<_, i64>(0)
                )
                .expect("index"),
            0
        );
        assert_eq!(store.schema_version().expect("version"), "6");
        let bytes: Vec<u8> = store
            .connection
            .query_row("SELECT payload FROM rch_messages", [], |row| row.get(0))
            .expect("raw");
        assert_eq!(bytes, [0xc1]);
    }
    #[test]
    fn fresh_and_upgraded_databases_have_identical_message_indexes() {
        let fresh = RchSqliteStore::in_memory().expect("fresh");
        let upgraded = RchSqliteStore::in_memory().expect("upgraded");
        upgraded.connection.execute_batch("DROP INDEX idx_rch_messages_identity;DROP INDEX idx_rch_messages_scope_history;DROP INDEX idx_rch_messages_topic_history;DROP INDEX idx_rch_messages_source_history;DROP INDEX idx_rch_messages_destination_history;ALTER TABLE rch_messages DROP COLUMN scope;ALTER TABLE rch_messages DROP COLUMN chat_source;DELETE FROM rch_schema_migrations WHERE version=7;UPDATE rch_settings SET setting_value='6' WHERE setting_key='schema_version';").expect("schema6 fixture");
        upgraded.migrate_message_indexes().expect("upgrade");
        let indexes = |store: &RchSqliteStore| {
            store.connection.prepare("SELECT name,sql FROM sqlite_master WHERE type='index' AND tbl_name='rch_messages' ORDER BY name").expect("statement").query_map([], |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))).expect("rows").collect::<Result<Vec<_>, _>>().expect("indexes")
        };
        assert_eq!(indexes(&fresh), indexes(&upgraded));
    }
}
