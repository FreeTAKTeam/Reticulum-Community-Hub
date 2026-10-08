use super::*;
use crate::{RchCore, Uuid};
use std::sync::{Arc, Barrier};

fn set(store: &mut RchSqliteStore, granted: bool) -> OperationRightMutation {
    store
        .set_operation_right("identity", "aabb", "mission.read", "global", "", granted)
        .expect("right mutation")
}

#[test]
fn normalization_matches_the_existing_domain_owner() {
    let mut store = RchSqliteStore::in_memory().expect("store");
    let mut core = RchCore::new();
    let cases = [
        (
            " IDENTITY ",
            " AaBb ",
            " mission.Read ",
            " GLOBAL ",
            "ignored",
        ),
        ("identity", "aabb", "mission.Read", "", "also ignored"),
        (
            " TEAM_MEMBER ",
            " Member-A ",
            " mission.Read ",
            " MISSION ",
            " Mission-A ",
        ),
        (
            "team_member",
            "member-a",
            "mission.Read",
            "mission",
            "Mission-A",
        ),
        (
            "team_member",
            "Member-A",
            "mission.read",
            "mission",
            "Mission-A",
        ),
        (
            "team_member",
            "Member-A",
            "mission.Read",
            "mission",
            "mission-a",
        ),
        ("team_member", "Member-A", "mission.Read", "mission", ""),
    ];
    for (index, (subject_type, id, operation, scope, scope_id)) in cases.into_iter().enumerate() {
        let expected = if index % 2 == 0 {
            core.grant_operation_right(subject_type, id, operation, scope, scope_id)
        } else {
            core.revoke_operation_right(subject_type, id, operation, scope, scope_id)
        }
        .expect("domain validation");
        let result = store
            .set_operation_right(subject_type, id, operation, scope, scope_id, index % 2 == 0)
            .expect("durable validation");
        let mut actual = result.record;
        // Independent stores intentionally generate distinct UUIDs.
        actual.grant_uid = expected.grant_uid.clone();
        assert_eq!(actual, expected);
        assert!(result.rows_read <= 1);
        assert_eq!(result.rows_written, 1);
    }
    assert_eq!(
        store
            .load_permission_read_snapshot()
            .expect("read")
            .subject_operation_rights
            .len(),
        6
    );
}

#[test]
fn no_op_does_not_execute_insert_update_or_delete() {
    let mut store = RchSqliteStore::in_memory().expect("store");
    let original = set(&mut store, true);
    store
        .connection
        .execute_batch(
            "CREATE TRIGGER no_insert BEFORE INSERT ON rch_subject_operation_rights
         BEGIN SELECT RAISE(ABORT, 'unexpected insert'); END;
         CREATE TRIGGER no_update BEFORE UPDATE ON rch_subject_operation_rights
         BEGIN SELECT RAISE(ABORT, 'unexpected update'); END;
         CREATE TRIGGER no_delete BEFORE DELETE ON rch_subject_operation_rights
         BEGIN SELECT RAISE(ABORT, 'unexpected delete'); END;",
        )
        .expect("guards");
    let changes = store.connection.total_changes();
    for _ in 0..10 {
        let result = set(&mut store, true);
        assert_eq!(result.record, original.record);
        assert_eq!(result.rows_read, 1);
        assert_eq!(result.rows_written, 0);
        assert!(result.decoded_payload_bytes > 0);
    }
    assert_eq!(store.connection.total_changes(), changes);
    assert!(
        store
            .set_operation_right("identity", "aabb", "mission.read", "global", "", false)
            .is_err()
    );
    assert_eq!(
        store
            .load_permission_read_snapshot()
            .expect("read")
            .subject_operation_rights,
        [original.record]
    );
}

#[test]
fn invalid_requests_and_failed_commit_do_not_publish_rows() {
    let mut store = RchSqliteStore::in_memory().expect("store");
    for (subject_type, id, operation, scope) in [
        ("unknown", "aabb", "read", "global"),
        ("identity", " ", "read", "global"),
        ("identity", "aabb", " ", "global"),
        ("identity", "aabb", "read", "unknown"),
    ] {
        assert!(matches!(
            store.set_operation_right(subject_type, id, operation, scope, "", true),
            Err(RchCoreError::InvalidPayload(_))
        ));
    }
    assert!(
        store
            .load_permission_read_snapshot()
            .expect("read")
            .subject_operation_rights
            .is_empty()
    );
    // The INSERT succeeds, then deferred referential validation rejects COMMIT.
    store
        .connection
        .execute_batch(
            "CREATE TABLE required_parent(id INTEGER PRIMARY KEY);
         CREATE TABLE deferred_child(id INTEGER REFERENCES required_parent(id)
             DEFERRABLE INITIALLY DEFERRED);
         CREATE TRIGGER fail_commit AFTER INSERT ON rch_subject_operation_rights
         BEGIN INSERT INTO deferred_child VALUES(42); END;",
        )
        .expect("commit fault");
    assert!(matches!(
        store.set_operation_right("identity", "aabb", "mission.read", "global", "", true),
        Err(RchCoreError::Sqlite(_))
    ));
    assert!(
        store
            .load_permission_read_snapshot()
            .expect("rolled back")
            .subject_operation_rights
            .is_empty()
    );
    let child_count: i64 = store
        .connection
        .query_row("SELECT COUNT(*) FROM deferred_child", [], |row| row.get(0))
        .expect("child count");
    assert_eq!(child_count, 0);
    store
        .connection
        .execute_batch("DROP TRIGGER fail_commit")
        .expect("repair");
    assert_eq!(set(&mut store, true).rows_written, 1);
}

#[test]
fn malformed_or_mismatched_target_fails_without_overwriting_it() {
    let mut store = RchSqliteStore::in_memory().expect("store");
    let mut wrong = set(&mut store, true).record;
    wrong.subject_id = "other-subject".into();
    for payload in [vec![0xc1], encode_msgpack(&wrong).expect("payload")] {
        store
            .connection
            .execute(
                "UPDATE rch_subject_operation_rights SET payload=?1",
                [&payload],
            )
            .expect("corrupt target");
        let changes = store.connection.total_changes();
        assert!(matches!(
            store.set_operation_right("identity", "aabb", "mission.read", "global", "", false),
            Err(RchCoreError::Decode(_))
        ));
        assert_eq!(store.connection.total_changes(), changes);
        let retained: Vec<u8> = store
            .connection
            .query_row(
                SELECT_RIGHT,
                params!["identity", "aabb", "mission.read", "global", ""],
                |row| row.get(0),
            )
            .expect("raw retained target");
        assert_eq!(retained, payload);
    }
}

#[test]
fn indexed_point_read_ignores_large_malformed_unrelated_history() {
    let mut store = RchSqliteStore::in_memory().expect("store");
    let before = set(&mut store, true);
    store.connection.execute_batch(
        "WITH RECURSIVE ids(id) AS (VALUES(1) UNION ALL SELECT id+1 FROM ids WHERE id<100000)
         INSERT INTO rch_identity_announces(destination_hash, payload, last_seen_ts_ms)
         SELECT 'history-'||id, X'C1', 0 FROM ids;
         INSERT INTO rch_topics(topic_id,payload) VALUES ('unrelated',X'C1');
         WITH RECURSIVE ids(id) AS (VALUES(1) UNION ALL SELECT id+1 FROM ids WHERE id<10000)
         INSERT INTO rch_subject_operation_rights(subject_type,subject_id,operation,scope_type,scope_id,payload)
         SELECT 'identity','unrelated-'||id,'mission.read','global','',X'C1' FROM ids;"
    ).expect("unrelated malformed records");
    let changes = store.connection.total_changes();
    let after = set(&mut store, false);
    assert_eq!(after.rows_read, 1);
    assert_eq!(after.rows_written, 1);
    assert_eq!(store.connection.total_changes() - changes, 1);
    assert_eq!(after.record.grant_uid, before.record.grant_uid);
    let noop = set(&mut store, false);
    assert_eq!(noop.decoded_payload_bytes, after.decoded_payload_bytes);
    assert_eq!(noop.rows_written, 0);
    let plan: String = store
        .connection
        .query_row(
            &format!("EXPLAIN QUERY PLAN {SELECT_RIGHT}"),
            params!["identity", "aabb", "mission.read", "global", ""],
            |row| row.get(3),
        )
        .expect("query plan");
    assert!(plan.contains("SEARCH rch_subject_operation_rights USING INDEX sqlite_autoindex_rch_subject_operation_rights_1"), "{plan}");
    assert!(!plan.contains("SCAN"), "{plan}");
}

#[test]
fn competing_connections_and_restart_preserve_one_uid() {
    let path = std::env::temp_dir().join(format!("rch-right-{}.sqlite", Uuid::new_v4()));
    drop(RchSqliteStore::open(&path).expect("initialize"));
    let ready = Arc::new(Barrier::new(3));
    let threads = (0..2)
        .map(|index| {
            let path = path.clone();
            let ready = ready.clone();
            std::thread::spawn(move || {
                let mut store = RchSqliteStore::open(path).expect("independent connection");
                ready.wait();
                (0..20)
                    .map(|iteration| {
                        set(&mut store, (iteration + index) % 2 == 0)
                            .record
                            .grant_uid
                    })
                    .collect::<Vec<_>>()
            })
        })
        .collect::<Vec<_>>();
    ready.wait();
    let ids = threads
        .into_iter()
        .flat_map(|thread| thread.join().expect("join"))
        .collect::<Vec<_>>();
    assert!(ids.iter().all(|id| id == &ids[0]));
    let mut reopened = RchSqliteStore::open(&path).expect("restart");
    assert_eq!(set(&mut reopened, false).record.grant_uid, ids[0]);
    assert_eq!(
        reopened
            .load_permission_read_snapshot()
            .expect("read")
            .subject_operation_rights
            .len(),
        1
    );
    drop(reopened);
    std::fs::remove_file(path).expect("cleanup");
}
