use super::{ACTIVE_DELIVERY_COUNT_SQL, RchSqliteStore};
use rusqlite::{Connection, StatementStatus, params};

fn completed_history(store: &RchSqliteStore, count: usize) {
    let tx = store.connection.unchecked_transaction().unwrap();
    let payload = serde_json::json!({"fixture": "x".repeat(1024)}).to_string();
    for index in 0..count {
        let id = format!("completed-{index}");
        tx.execute(
            "INSERT INTO rch_broker_dispatch
                (operation_id,message_id,payload,state,receipt_status)
             VALUES(?1,?1,?2,'terminal','delivered')",
            params![id, payload],
        )
        .unwrap();
    }
    tx.commit().unwrap();
}

fn active_count_work(store: &RchSqliteStore) -> (usize, i32, i32) {
    let actual = store.message_history_counts().unwrap().1;
    let mut statement = store.connection.prepare(ACTIVE_DELIVERY_COUNT_SQL).unwrap();
    let measured: i64 = statement.query_row([], |row| row.get(0)).unwrap();
    assert_eq!(actual, usize::try_from(measured).unwrap());
    (
        actual,
        statement.get_status(StatementStatus::VmStep),
        statement.get_status(StatementStatus::FullscanStep),
    )
}

#[test]
fn active_delivery_count_does_not_walk_completed_history() {
    eprintln!("SQLite {}", rusqlite::version());
    let mut costs = Vec::new();
    for count in [32, 10_000] {
        let store = RchSqliteStore::in_memory().unwrap();
        completed_history(&store, count);
        let empty = active_count_work(&store);
        assert_eq!(empty.0, 0);
        eprintln!("completed_rows={count} active_count_vm_fullscan={empty:?}");
        costs.push(empty);
    }
    assert_eq!(costs[0], costs[1]);
    assert_eq!(costs[0].2, 0);
}

#[test]
fn active_delivery_count_preserves_pending_admitted_and_terminal_transitions() {
    let store = RchSqliteStore::in_memory().unwrap();
    completed_history(&store, 100);
    for (first, second, expected) in [
        ("terminal", "terminal", 0),
        ("pending", "terminal", 1),
        ("admitted", "terminal", 1),
        ("pending", "admitted", 2),
        ("terminal", "admitted", 1),
        ("unknown-future", "PENDING", 0),
        ("cancelled", "Admitted", 0),
    ] {
        for (id, state) in [("completed-0", first), ("completed-1", second)] {
            store
                .connection
                .execute(
                    "UPDATE rch_broker_dispatch SET state=?1 WHERE operation_id=?2",
                    params![state, id],
                )
                .unwrap();
        }
        assert_eq!(store.message_history_counts().unwrap(), (0, expected));
    }
}

#[test]
fn version_eight_upgrade_preserves_history_and_existing_pending_index() {
    let dir = std::env::temp_dir().join(format!("rch-active-count-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir(&dir).unwrap();
    let path = dir.join("state.db");
    let store = RchSqliteStore::open(&path).unwrap();
    completed_history(&store, 330);
    store
        .connection
        .execute_batch(
            "DROP INDEX IF EXISTS rch_broker_dispatch_active_state;
         DELETE FROM rch_schema_migrations WHERE version=9;
         UPDATE rch_settings SET setting_value='8' WHERE setting_key='schema_version';
         UPDATE rch_broker_dispatch SET state='pending' WHERE operation_id='completed-0';
         UPDATE rch_broker_dispatch SET state='admitted' WHERE operation_id='completed-1';",
        )
        .unwrap();
    let expected: Vec<(String, String, String)> = store
        .connection
        .prepare("SELECT operation_id,payload,state FROM rch_broker_dispatch ORDER BY operation_id")
        .unwrap()
        .query_map([], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)))
        .unwrap()
        .collect::<Result<_, _>>()
        .unwrap();
    drop(store);

    let store = RchSqliteStore::open(&path).unwrap();
    assert_eq!(store.schema_version().unwrap(), "9");
    assert_eq!(active_count_work(&store).0, 2);
    assert_eq!(active_count_work(&store).2, 0);
    assert_eq!(
        store
            .connection
            .query_row(
                "SELECT COUNT(*) FROM sqlite_master WHERE name='rch_broker_dispatch_pending_state'",
                [],
                |r| r.get::<_, i64>(0),
            )
            .unwrap(),
        1
    );
    let actual: Vec<(String, String, String)> = store
        .connection
        .prepare("SELECT operation_id,payload,state FROM rch_broker_dispatch ORDER BY operation_id")
        .unwrap()
        .query_map([], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)))
        .unwrap()
        .collect::<Result<_, _>>()
        .unwrap();
    assert_eq!(actual, expected);
    drop(store);

    let backup_path = format!("{}.pre-migration-v9.bak", path.display());
    let backup = Connection::open(&backup_path).unwrap();
    assert_eq!(
        backup
            .query_row(
                "SELECT setting_value FROM rch_settings WHERE setting_key='schema_version'",
                [],
                |r| r.get::<_, String>(0),
            )
            .unwrap(),
        "8"
    );
    assert_eq!(
        backup
            .query_row("SELECT COUNT(*) FROM rch_broker_dispatch", [], |r| r
                .get::<_, i64>(0))
            .unwrap(),
        330
    );
    assert_eq!(
        backup
            .query_row(
                "SELECT COUNT(*) FROM sqlite_master WHERE name='rch_broker_dispatch_active_state'",
                [],
                |r| r.get::<_, i64>(0),
            )
            .unwrap(),
        0
    );
    drop(backup);
    let backup_bytes = std::fs::read(&backup_path).unwrap();
    let reopened = RchSqliteStore::open(&path).unwrap();
    assert_eq!(
        reopened
            .connection
            .query_row(
                "SELECT COUNT(*) FROM rch_schema_migrations WHERE version=9",
                [],
                |r| r.get::<_, i64>(0),
            )
            .unwrap(),
        1
    );
    drop(reopened);
    assert_eq!(std::fs::read(backup_path).unwrap(), backup_bytes);
    std::fs::remove_dir_all(dir).unwrap();
}
