use super::{
    DurableOutboundIntent, InboxEvent, NEXT_INBOX_EVENT_SQL, PENDING_BROKER_INTENT_SQL,
    RchSqliteStore, encode,
};
use rusqlite::{Connection, StatementStatus, params};

fn history(store: &RchSqliteStore, count: i64) {
    let tx = store.connection.unchecked_transaction().unwrap();
    tx.execute(
        "INSERT INTO rch_broker_checkpoint VALUES('consumer','journal',?1,?1,NULL,NULL,NULL)",
        [count],
    )
    .unwrap();
    for position in 1..=count {
        tx.execute(
            "INSERT INTO rch_broker_inbox VALUES('journal',?1,'inbound',0,'{}','fixture',?2,NULL)",
            params![
                position,
                if position % 2 == 0 {
                    "applied"
                } else {
                    "rejected"
                }
            ],
        )
        .unwrap();
        tx.execute("INSERT INTO rch_broker_dispatch(operation_id,message_id,payload,state) VALUES(?1,?1,'{}',?2)", params![position.to_string(), if position % 2 == 0 { "terminal" } else { "admitted" }]).unwrap();
    }
    tx.commit().unwrap();
}

fn empty_lookup_cost(store: &RchSqliteStore, sql: &str, inbox: bool) -> (i32, i32) {
    let mut statement = store.connection.prepare(sql).unwrap();
    {
        let mut rows = if inbox {
            statement.query(["consumer"]).unwrap()
        } else {
            statement.query([]).unwrap()
        };
        assert!(rows.next().unwrap().is_none());
    }
    (
        statement.get_status(StatementStatus::VmStep),
        statement.get_status(StatementStatus::FullscanStep),
    )
}

#[test]
fn empty_pending_lookups_do_not_walk_completed_history() {
    let mut costs = Vec::new();
    for count in [32, 10_000] {
        let store = RchSqliteStore::in_memory().unwrap();
        history(&store, count);
        assert!(store.next_inbox_event("consumer").unwrap().is_none());
        assert!(store.pending_broker_intent().unwrap().is_none());
        let inbox = empty_lookup_cost(&store, NEXT_INBOX_EVENT_SQL, true);
        let dispatch = empty_lookup_cost(&store, PENDING_BROKER_INTENT_SQL, false);
        eprintln!(
            "completed_rows={count} inbox(vm_steps,fullscan_steps)={inbox:?} dispatch={dispatch:?}"
        );
        costs.push((inbox, dispatch));
    }
    assert_eq!(costs[0], costs[1]);
    assert_eq!((costs[0].0.1, costs[0].1.1), (0, 0));
}

fn event(position: u64) -> InboxEvent {
    InboxEvent {
        version: 1,
        position,
        created_at: 0,
        event_type: "inbound".into(),
        payload: serde_json::json!({}),
    }
}

#[test]
fn unfinished_lookup_keeps_unknown_states_and_position_order() {
    let store = RchSqliteStore::in_memory().unwrap();
    history(&store, 2_392);
    for (position, status) in [
        (2_400_i64, "stored"),
        (2_399, "error"),
        (2_398, "upgrade_required"),
    ] {
        store.connection.execute("INSERT INTO rch_broker_inbox VALUES('journal',?1,'inbound',0,?2,'fixture',?3,NULL)", params![position, encode(&event(u64::try_from(position).unwrap())).unwrap(), status]).unwrap();
    }
    for position in [2_398, 2_399, 2_400] {
        assert_eq!(
            i64::try_from(
                store
                    .next_inbox_event("consumer")
                    .unwrap()
                    .unwrap()
                    .position
            )
            .unwrap(),
            position
        );
        store
            .connection
            .execute(
                "UPDATE rch_broker_inbox SET status='applied' WHERE position=?1",
                [position],
            )
            .unwrap();
    }
    assert!(store.next_inbox_event("consumer").unwrap().is_none());
}

#[test]
fn pending_dispatch_keeps_admission_order_and_state_changes() {
    let store = RchSqliteStore::in_memory().unwrap();
    history(&store, 330);
    for operation in ["z-first", "a-second"] {
        let intent = DurableOutboundIntent {
            operation_id: operation.into(),
            message: crate::MessageRecord {
                message_id: operation.into(),
                topic_id: None,
                destination: Some("peer".into()),
                sender: "rch".into(),
                content: "fixture".into(),
                delivery_mode: crate::DeliveryMode::Targeted,
                delivery_method: "durable_broker".into(),
                delivery_policy_reason: "reply".into(),
                delivery_state: "broker_pending".into(),
                delivery_metadata: serde_json::json!({}),
                created_ts_ms: 0,
                attachments: Vec::new(),
            },
            request: serde_json::json!({}),
        };
        store.connection.execute("INSERT INTO rch_broker_dispatch(operation_id,message_id,payload,state) VALUES(?1,?1,?2,'pending')", params![operation, encode(&intent).unwrap()]).unwrap();
    }
    for operation in ["z-first", "a-second"] {
        assert_eq!(
            store.pending_broker_intent().unwrap().unwrap().operation_id,
            operation
        );
        store
            .connection
            .execute(
                "UPDATE rch_broker_dispatch SET state='admitted' WHERE operation_id=?1",
                [operation],
            )
            .unwrap();
    }
    assert!(store.pending_broker_intent().unwrap().is_none());
}

#[test]
fn version_seven_upgrade_preserves_history_and_backs_up_before_indexing() {
    let dir = std::env::temp_dir().join(format!("rch-pending-migration-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir(&dir).unwrap();
    let path = dir.join("state.db");
    let store = RchSqliteStore::open(&path).unwrap();
    history(&store, 330);
    store.connection.execute_batch("DROP INDEX IF EXISTS rch_broker_inbox_unfinished; DROP INDEX IF EXISTS rch_broker_dispatch_pending_state; DELETE FROM rch_schema_migrations WHERE version=8; UPDATE rch_settings SET setting_value='7' WHERE setting_key='schema_version';").unwrap();
    drop(store);
    let store = RchSqliteStore::open(&path).unwrap();
    assert_eq!(store.schema_version().unwrap(), "8");
    assert_eq!(
        store
            .connection
            .query_row("SELECT COUNT(*) FROM rch_broker_inbox", [], |r| r
                .get::<_, i64>(0))
            .unwrap(),
        330
    );
    empty_lookup_cost(&store, NEXT_INBOX_EVENT_SQL, true);
    empty_lookup_cost(&store, PENDING_BROKER_INTENT_SQL, false);
    drop(store);
    let backup = Connection::open(format!("{}.pre-migration-v8.bak", path.display())).unwrap();
    assert_eq!(
        backup
            .query_row(
                "SELECT setting_value FROM rch_settings WHERE setting_key='schema_version'",
                [],
                |r| r.get::<_, String>(0)
            )
            .unwrap(),
        "7"
    );
    assert_eq!(
        backup
            .query_row("SELECT COUNT(*) FROM rch_broker_dispatch", [], |r| r
                .get::<_, i64>(0))
            .unwrap(),
        330
    );
    drop(backup);
    let reopened = RchSqliteStore::open(&path).unwrap();
    assert_eq!(
        reopened
            .connection
            .query_row(
                "SELECT COUNT(*) FROM rch_schema_migrations WHERE version=8",
                [],
                |r| r.get::<_, i64>(0)
            )
            .unwrap(),
        1
    );
    drop(reopened);
    std::fs::remove_dir_all(dir).unwrap();
}
