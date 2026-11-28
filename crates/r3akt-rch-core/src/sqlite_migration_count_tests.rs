#[test]
fn sqlite_store_records_ordered_migrations_and_safe_compaction_state() {
    let store = RchSqliteStore::in_memory().expect("sqlite");
    let migration_count: i64 = store
        .connection
        .query_row("SELECT COUNT(*) FROM rch_schema_migrations", [], |row| {
            row.get(0)
        })
        .expect("migration count");
    let stats = store.storage_stats().expect("storage stats");
    let report = store
        .compact_if_free_percent_exceeds(100.0, 100)
        .expect("no-op compaction");

    assert_eq!(migration_count, 11);

    let index_exists: bool = store
        .connection
        .query_row(
            "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = 'idx_rch_subscribers_topic_node')",
            [],
            |row| row.get(0),
        )
        .expect("subscriber topic index");
    assert!(index_exists);

    drop(store);
    assert!(stats.page_count > 0);
    assert!(!report.compacted);
    assert!(!report.requires_incremental_mode_conversion);
}
