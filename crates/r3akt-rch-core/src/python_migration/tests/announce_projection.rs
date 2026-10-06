use super::*;

#[test]
fn migrates_python_identity_and_topic_tables_into_rust_snapshot() {
    let legacy_path = std::env::temp_dir().join(format!(
        "r3akt-python-migration-legacy-{}.sqlite3",
        Uuid::new_v4()
    ));
    let target_path = std::env::temp_dir().join(format!(
        "r3akt-python-migration-target-{}.sqlite3",
        Uuid::new_v4()
    ));
    create_minimal_legacy_database(&legacy_path);

    let report = migrate_python_database(&legacy_path, &target_path).expect("migration");

    assert_eq!(report.rows["topics"], 1);
    assert_eq!(report.rows["clients"], 1);
    assert_eq!(report.rows["identity_announces"], 1);
    let store = RchSqliteStore::open(&target_path).expect("target store");
    let snapshot = store
        .load_snapshot()
        .expect("load snapshot")
        .expect("snapshot");
    assert_eq!(snapshot.topics[0].topic_id, "ops");
    assert_eq!(snapshot.topics[0].topic_name, "Ops");
    assert_eq!(
        snapshot.clients[0].identity,
        "11112222333344445555666677778888"
    );
    assert_eq!(
        snapshot.identity_announces[0].destination_hash,
        "aaaabbbbccccddddeeeeffff00001111"
    );
    let summary = store
        .identity_announce_summary(0)
        .expect("announce summary");
    assert_eq!(summary.total, 1);
    assert_eq!(summary.fresh, 1);
    assert_eq!(summary.recent, snapshot.identity_announces);
    assert!(
        store
            .has_identity_announce("AAAABBBBCCCCDDDDEEEEFFFF00001111")
            .expect("normalized announce lookup")
    );
    assert!(snapshot.identity_states[0].is_banned);

    let _ = std::fs::remove_file(legacy_path);
    let _ = std::fs::remove_file(target_path);
}
