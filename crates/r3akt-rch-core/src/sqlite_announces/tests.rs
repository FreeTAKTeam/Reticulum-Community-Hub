use super::*;
use crate::{
    RCH_SQLITE_MIGRATION_2_SQL, RCH_SQLITE_MIGRATION_3_SQL, RCH_SQLITE_MIGRATION_SQL, RchCore,
};

fn record(destination: &str, timestamp: i64) -> IdentityAnnounceRecord {
    IdentityAnnounceRecord {
        destination_hash: destination.to_string(),
        announced_identity_hash: None,
        display_name: Some("Preserved peer".to_string()),
        source_interface: None,
        announce_capabilities: vec!["lxmf".to_string()],
        client_type: "generic_lxmf".to_string(),
        first_seen_ts_ms: -123,
        last_seen_ts_ms: timestamp,
    }
}

fn legacy(path: &std::path::Path) -> Connection {
    let connection = Connection::open(path).expect("legacy DB");
    connection
        .execute_batch(RCH_SQLITE_MIGRATION_SQL)
        .expect("v1");
    connection
        .execute_batch(RCH_SQLITE_MIGRATION_2_SQL)
        .expect("v2");
    connection
        .execute_batch(RCH_SQLITE_MIGRATION_3_SQL)
        .expect("v3");
    connection
        .execute(
            "INSERT OR IGNORE INTO rch_schema_migrations VALUES (3, 'fixture', 0)",
            [],
        )
        .expect("version");
    connection
        .execute(
            "UPDATE rch_settings SET setting_value='3' WHERE setting_key='schema_version'",
            [],
        )
        .expect("setting");
    connection
}

#[test]
fn legacy_migration_preserves_payload_bytes_and_normalizes_both_identity_keys() {
    let path = std::env::temp_dir().join(format!(
        "rch-announce-migration-{}.db",
        uuid::Uuid::new_v4()
    ));
    let old = legacy(&path);
    let mut announce = record("\u{2003}MiXeD\u{2003}", 1_000);
    announce.announced_identity_hash = Some(" Alias ".to_string());
    let payload = encode_msgpack(&announce).expect("payload");
    old.execute(
        "INSERT INTO rch_identity_announces VALUES (?1, ?2)",
        params![announce.destination_hash, payload],
    )
    .expect("old writer");
    drop(old);
    let store = RchSqliteStore::open(&path).expect("migration");
    assert_eq!(store.schema_version().expect("version"), "4");
    assert!(store.has_identity_announce(" MIXED ").expect("destination"));
    assert!(
        store
            .has_identity_announce("\u{2003}ALIAS\u{2003}")
            .expect("alias")
    );
    assert!(!store.has_identity_announce("missing").expect("absent"));
    assert!(!store.has_identity_announce(" ").expect("empty"));
    let bytes: Vec<u8> = store
        .connection
        .query_row("SELECT payload FROM rch_identity_announces", [], |row| {
            row.get(0)
        })
        .expect("bytes");
    assert_eq!(bytes, payload);
    assert!(std::path::Path::new(&format!("{}.pre-migration-v4.bak", path.display())).exists());
    drop(store);
    let store = RchSqliteStore::open(&path).expect("reopen");
    assert_eq!(
        store
            .identity_announce_summary(1_000)
            .expect("summary")
            .fresh,
        1
    );
    drop(store);
    std::fs::remove_file(format!("{}.pre-migration-v4.bak", path.display()))
        .expect("backup cleanup");
    std::fs::remove_file(path).expect("cleanup");
}

#[test]
fn malformed_legacy_payload_rolls_back_columns_indexes_version_and_bytes() {
    let path =
        std::env::temp_dir().join(format!("rch-announce-rollback-{}.db", uuid::Uuid::new_v4()));
    let old = legacy(&path);
    let valid = encode_msgpack(&record("a", 10)).expect("payload");
    old.execute(
        "INSERT INTO rch_identity_announces VALUES ('a', ?1)",
        [&valid],
    )
    .expect("valid row");
    old.execute("INSERT INTO rch_identity_announces VALUES ('z', X'C1')", [])
        .expect("bad row");
    drop(old);
    assert!(RchSqliteStore::open(&path).is_err());
    let old = Connection::open(&path).expect("original remains readable");
    let version: String = old
        .query_row(
            "SELECT setting_value FROM rch_settings WHERE setting_key='schema_version'",
            [],
            |row| row.get(0),
        )
        .expect("version");
    assert_eq!(version, "3");
    let columns: usize = old
        .query_row(
            "SELECT COUNT(*) FROM pragma_table_info('rch_identity_announces')",
            [],
            |row| row.get(0),
        )
        .expect("columns");
    assert_eq!(columns, 2);
    let projections: usize = old.query_row("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'idx_rch_announces_%' OR name LIKE 'rch_announces_require_%'", [], |row| row.get(0)).expect("indexes");
    assert_eq!(projections, 0);
    let migrations: usize = old
        .query_row(
            "SELECT COUNT(*) FROM rch_schema_migrations WHERE version=4",
            [],
            |row| row.get(0),
        )
        .expect("version4");
    assert_eq!(migrations, 0);
    let bytes: Vec<u8> = old
        .query_row(
            "SELECT payload FROM rch_identity_announces WHERE destination_hash='a'",
            [],
            |row| row.get(0),
        )
        .expect("bytes");
    assert_eq!(bytes, valid);
    let bad: Vec<u8> = old
        .query_row(
            "SELECT payload FROM rch_identity_announces WHERE destination_hash='z'",
            [],
            |row| row.get(0),
        )
        .expect("bad bytes");
    assert_eq!(bad, [0xc1]);
    drop(old);
    std::fs::remove_file(format!("{}.pre-migration-v4.bak", path.display()))
        .expect("backup cleanup");
    std::fs::remove_file(path).expect("cleanup");
}

#[test]
fn both_write_paths_update_summary_and_older_payload_only_writers_are_rejected() {
    let mut store = RchSqliteStore::in_memory().expect("store");
    let mut announce = record("a", 999);
    store
        .upsert_identity_announces(&[announce.clone()])
        .expect("row write");
    assert_eq!(
        store.identity_announce_summary(1_000).expect("stale").fresh,
        0
    );
    announce.last_seen_ts_ms = 1_000;
    announce.announced_identity_hash = Some(" Alias ".to_string());
    let mut snapshot = RchCore::new().snapshot();
    snapshot.identity_announces = vec![announce.clone()];
    store.save_snapshot(&snapshot).expect("snapshot write");
    assert!(
        store
            .has_identity_announce("alias")
            .expect("snapshot alias")
    );
    assert_eq!(
        store
            .identity_announce_summary(1_000)
            .expect("boundary")
            .fresh,
        1
    );
    for sql in [
        "INSERT INTO rch_identity_announces (destination_hash,payload) VALUES ('b',?1)",
        "INSERT OR REPLACE INTO rch_identity_announces (destination_hash,payload) VALUES ('a',?1)",
    ] {
        assert!(
            store
                .connection
                .execute(sql, [encode_msgpack(&announce).expect("payload")])
                .is_err()
        );
    }
    {
        let transaction = store
            .connection
            .transaction()
            .expect("old snapshot transaction");
        transaction
            .execute("DELETE FROM rch_identity_announces", [])
            .expect("old snapshot clear");
        assert!(
            transaction
                .execute(
                    "INSERT INTO rch_identity_announces (destination_hash,payload) VALUES ('b',?1)",
                    [encode_msgpack(&announce).expect("payload")],
                )
                .is_err()
        );
        transaction.rollback().expect("old snapshot rollback");
    }
    assert_eq!(
        store.load_identity_announces().expect("history"),
        [announce.clone()]
    );
    announce.last_seen_ts_ms = 1_001;
    announce.announced_identity_hash = None;
    store
        .upsert_identity_announces(&[announce])
        .expect("replacement");
    assert!(
        !store
            .has_identity_announce("alias")
            .expect("old alias removed")
    );
}

#[test]
fn bounded_summary_matches_legacy_ordering_and_uses_covering_indexes() {
    let mut store = RchSqliteStore::in_memory().expect("store");
    assert_eq!(
        store.identity_announce_summary(1_000).expect("empty").total,
        0
    );
    let mut records = (0..10_000)
        .map(|index| record(&format!("{index:08}"), index % 2_000))
        .collect::<Vec<_>>();
    store.upsert_identity_announces(&records).expect("history");
    records.sort_by(|left, right| {
        right
            .last_seen_ts_ms
            .cmp(&left.last_seen_ts_ms)
            .then_with(|| left.destination_hash.cmp(&right.destination_hash))
    });
    let summary = store.identity_announce_summary(1_000).expect("summary");
    assert_eq!(summary.total, 10_000);
    assert_eq!(
        summary.fresh,
        records
            .iter()
            .filter(|record| record.last_seen_ts_ms >= 1_000)
            .count()
    );
    assert_eq!(summary.recent, records[..10]);
    let oldest = records
        .iter()
        .filter(|record| record.last_seen_ts_ms < 1_000)
        .min_by_key(|record| record.last_seen_ts_ms)
        .expect("oldest");
    assert_eq!(
        summary.oldest_stale,
        Some((oldest.destination_hash.clone(), oldest.last_seen_ts_ms))
    );
    for sql in [
        "SELECT payload FROM rch_identity_announces ORDER BY last_seen_ts_ms DESC, destination_hash ASC LIMIT 10",
        "SELECT COUNT(*) FROM rch_identity_announces WHERE last_seen_ts_ms >= 1000",
        "SELECT destination_hash,last_seen_ts_ms FROM rch_identity_announces WHERE last_seen_ts_ms = (SELECT MIN(last_seen_ts_ms) FROM rch_identity_announces WHERE last_seen_ts_ms < 1000) ORDER BY destination_hash ASC LIMIT 1",
    ] {
        let mut statement = store
            .connection
            .prepare(&format!("EXPLAIN QUERY PLAN {sql}"))
            .expect("query plan");
        let plan = statement
            .query_map([], |row| row.get::<_, String>(3))
            .expect("rows")
            .collect::<Result<Vec<_>, _>>()
            .expect("plan")
            .join(" ");
        assert!(plan.contains("idx_rch_announces_recent"), "{plan}");
        assert!(!plan.contains("TEMP B-TREE"), "{plan}");
    }
}

#[test]
fn duplicate_snapshot_keys_fail_without_replacing_the_committed_history() {
    let mut store = RchSqliteStore::in_memory().expect("store");
    let original = record("original", 10);
    store
        .upsert_identity_announces(&[original.clone()])
        .expect("original");
    let mut snapshot = RchCore::new().snapshot();
    snapshot.identity_announces = vec![record("duplicate", 20), record("duplicate", 30)];
    assert!(store.save_snapshot(&snapshot).is_err());
    assert_eq!(
        store.load_identity_announces().expect("rollback"),
        [original]
    );
    assert!(
        store
            .has_identity_announce("original")
            .expect("original projection")
    );
    assert!(
        !store
            .has_identity_announce("duplicate")
            .expect("rolled back projection")
    );
}

#[test]
fn batch_membership_counts_missing_duplicates_without_decoding_history() {
    let mut store = RchSqliteStore::in_memory().expect("store");
    let mut announce = record(" MiXeD ", 10);
    announce.announced_identity_hash = Some(" ALIAS ".to_string());
    store.upsert_identity_announces(&[announce]).expect("write");
    let destinations = ["mixed", "alias", "missing", "missing", " "].map(str::to_string);
    assert_eq!(
        store
            .missing_identity_announce_count(&destinations)
            .expect("membership"),
        3
    );
    assert_eq!(
        store.missing_identity_announce_count(&[]).expect("empty"),
        0
    );
}

#[test]
fn identity_matches_preserve_raw_order_and_deduplicate_destination_and_alias_matches() {
    let mut store = RchSqliteStore::in_memory().expect("store");
    let mut first = record("\u{2003}TARGET\u{2003}", 30);
    first.announced_identity_hash = Some(" Shared ".to_string());
    let mut second = record("A", 20);
    second.announced_identity_hash = Some("shared".to_string());
    let mut third = record("shared", 10);
    third.announced_identity_hash = Some("SHARED".to_string());
    store
        .upsert_identity_announces(&[first, second, third])
        .expect("records");
    let all = store.load_identity_announces().expect("reference");
    let keys = [" SHARED ", "target", "SHARED", "missing", " "].map(str::to_string);
    assert_eq!(
        store
            .load_identity_announces_for_identities(&keys)
            .expect("matches"),
        all
    );
    assert!(
        store
            .load_identity_announces_for_identities(&[])
            .expect("empty")
            .is_empty()
    );
    store.connection.execute(
        "INSERT INTO rch_identity_announces (destination_hash,payload,last_seen_ts_ms,normalized_destination_hash) VALUES ('unrelated',X'C1',0,'unrelated')", [],
    ).expect("corrupt unrelated fixture");
    assert_eq!(
        store
            .load_identity_announces_for_identities(&keys)
            .expect("isolated matches"),
        all
    );
    assert!(
        store
            .load_identity_announces_for_identities(&["unrelated".to_string()])
            .is_err()
    );
    let bytes: Vec<u8> = store
        .connection
        .query_row(
            "SELECT payload FROM rch_identity_announces WHERE destination_hash='unrelated'",
            [],
            |row| row.get(0),
        )
        .expect("unrelated bytes");
    assert_eq!(bytes, [0xc1]);
}

#[test]
fn indexed_freshness_matches_normalized_aliases_and_inclusive_timestamp_boundaries() {
    let mut store = RchSqliteStore::in_memory().expect("store");
    let mut announce = record(" MiXeD ", -10);
    announce.announced_identity_hash = Some("\u{2003}ALIAS\u{2003}".to_string());
    store
        .upsert_identity_announces(&[announce])
        .expect("record");
    for identity in ["mixed", " MIXED ", "alias", "\u{2003}ALIAS\u{2003}"] {
        assert!(
            store
                .has_identity_announce_since_for_any(&[identity], -10)
                .expect("boundary")
        );
        assert!(
            !store
                .has_identity_announce_since_for_any(&[identity], -9)
                .expect("stale")
        );
    }
    assert!(
        store
            .has_identity_announce_since_for_any(&["missing", "alias"], i64::MIN)
            .expect("any")
    );
    assert!(
        !store
            .has_identity_announce_since_for_any(&["alias"], i64::MAX)
            .expect("future")
    );
    assert!(
        !store
            .has_identity_announce_since_for_any(&[" ", "missing"], -10)
            .expect("absent")
    );
    assert!(
        !store
            .has_identity_announce_since_for_any(&[], -10)
            .expect("empty")
    );
    for sql in [
        "SELECT destination_hash,payload FROM rch_identity_announces WHERE normalized_destination_hash='mixed' UNION ALL SELECT destination_hash,payload FROM rch_identity_announces WHERE normalized_announced_identity_hash='mixed'",
        "SELECT EXISTS(SELECT 1 FROM rch_identity_announces WHERE normalized_destination_hash='mixed' AND last_seen_ts_ms>=-10 UNION ALL SELECT 1 FROM rch_identity_announces WHERE normalized_announced_identity_hash='mixed' AND last_seen_ts_ms>=-10)",
    ] {
        let mut statement = store
            .connection
            .prepare(&format!("EXPLAIN QUERY PLAN {sql}"))
            .expect("plan");
        let plan = statement
            .query_map([], |row| row.get::<_, String>(3))
            .expect("rows")
            .collect::<Result<Vec<_>, _>>()
            .expect("plan")
            .join(" ");
        assert!(
            plan.contains("SEARCH rch_identity_announces USING"),
            "{plan}"
        );
        assert!(plan.contains("idx_rch_announces_destination"), "{plan}");
        assert!(plan.contains("idx_rch_announces_identity"), "{plan}");
        assert!(!plan.contains("SCAN rch_identity_announces"), "{plan}");
    }
}
