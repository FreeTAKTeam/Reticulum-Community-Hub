use super::*;

fn legacy(path: &std::path::Path) -> rusqlite::Connection {
    let connection = rusqlite::Connection::open(path).unwrap();
    connection
        .execute_batch(crate::RCH_SQLITE_MIGRATION_SQL)
        .unwrap();
    connection
        .execute_batch(crate::RCH_SQLITE_MIGRATION_2_SQL)
        .unwrap();
    connection
        .execute_batch(crate::RCH_SQLITE_MIGRATION_3_SQL)
        .unwrap();
    connection
        .execute(
            "INSERT OR IGNORE INTO rch_schema_migrations VALUES(3,'fixture',0)",
            [],
        )
        .unwrap();
    connection
}

#[test]
fn migration_preserves_payloads_backs_up_and_read_only_queries_work() {
    let directory =
        std::env::temp_dir().join(format!("rch-directory-migration-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir(&directory).unwrap();
    let path = directory.join("state.db");
    let old = legacy(&path);
    let state = state(" Owner ", true);
    let announce = announce("DST", "owner", "Équipe Müller", "destination", "rem", 123);
    let state_payload = crate::encode_msgpack(&state).unwrap();
    let announce_payload = crate::encode_msgpack(&announce).unwrap();
    old.execute(
        "INSERT INTO rch_identity_states VALUES(?1,?2)",
        params![state.identity, state_payload],
    )
    .unwrap();
    old.execute(
        "INSERT INTO rch_identity_announces VALUES(?1,?2)",
        params![announce.destination_hash, announce_payload],
    )
    .unwrap();
    drop(old);
    let store = RchSqliteStore::open(&path).unwrap();
    assert_eq!(store.schema_version().unwrap(), "7");
    drop(store);
    let backup =
        rusqlite::Connection::open(format!("{}.pre-migration-v7.bak", path.display())).unwrap();
    assert_eq!(
        backup
            .query_row(
                "SELECT setting_value FROM rch_settings WHERE setting_key='schema_version'",
                [],
                |r| r.get::<_, String>(0)
            )
            .unwrap(),
        "6"
    );
    assert_eq!(
        backup
            .query_row("SELECT payload FROM rch_identity_announces", [], |r| r
                .get::<_, Vec<u8>>(0))
            .unwrap(),
        announce_payload
    );
    drop(backup);
    let reader = RchSqliteStore::open_read_only(&path).unwrap();
    let mut unicode_query = query();
    unicode_query.search = Some("ÉQUIPE MÜLLER".into());
    let page = reader
        .load_identity_directory_page(&unicode_query, &[])
        .unwrap();
    assert_eq!(page.total, 1);
    assert_eq!(page.entries[0].state, state);
    assert_eq!(page.entries[0].announce.as_ref(), Some(&announce));
    assert_eq!(
        reader
            .connection
            .query_row("PRAGMA query_only", [], |r| r.get::<_, i64>(0))
            .unwrap(),
        1
    );
    drop(reader);
    std::fs::remove_dir_all(directory).unwrap();
}

#[test]
fn failed_directory_migration_rolls_back_derived_schema_without_losing_history() {
    let directory =
        std::env::temp_dir().join(format!("rch-directory-rollback-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir(&directory).unwrap();
    let path = directory.join("state.db");
    let old = legacy(&path);
    old.execute("INSERT INTO rch_identity_states VALUES('bad',X'C1')", [])
        .unwrap();
    drop(old);
    assert!(RchSqliteStore::open(&path).is_err());
    let connection = rusqlite::Connection::open(&path).unwrap();
    assert!(!crate::sqlite_table_exists(&connection, "rch_identity_directory").unwrap());
    assert!(
        !crate::sqlite_table_has_column(&connection, "rch_identity_states", "directory_identity")
            .unwrap()
    );
    assert_eq!(
        connection
            .query_row("SELECT payload FROM rch_identity_states", [], |r| r
                .get::<_, Vec<u8>>(0))
            .unwrap(),
        [0xc1]
    );
    assert_eq!(
        connection
            .query_row(
                "SELECT setting_value FROM rch_settings WHERE setting_key='schema_version'",
                [],
                |r| r.get::<_, String>(0)
            )
            .unwrap(),
        "6"
    );
    assert!(std::path::Path::new(&format!("{}.pre-migration-v7.bak", path.display())).exists());
    drop(connection);
    std::fs::remove_dir_all(directory).unwrap();
}

#[test]
fn announce_owner_changes_refresh_old_and_new_directory_rows() {
    let mut store = RchSqliteStore::in_memory().unwrap();
    store
        .upsert_identity_states(&[state("a", false), state("b", false)])
        .unwrap();
    store
        .upsert_identity_announces(&[announce("d", "a", "A", "destination", "rem", 1)])
        .unwrap();
    store
        .upsert_identity_announces(&[announce("d", "b", "B", "destination", "generic_lxmf", 2)])
        .unwrap();
    let page = store.load_identity_directory_page(&query(), &[]).unwrap();
    assert!(page.entries[0].announce.is_none());
    assert_eq!(page.entries[0].last_heard_ts_ms, None);
    assert_eq!(
        page.entries[1]
            .announce
            .as_ref()
            .unwrap()
            .display_name
            .as_deref(),
        Some("B")
    );
    store
        .connection
        .execute("DELETE FROM rch_identity_announces", [])
        .unwrap();
    assert!(
        store
            .load_identity_directory_page(&query(), &[])
            .unwrap()
            .entries
            .iter()
            .all(|e| e.announce.is_none())
    );
}

#[test]
fn member_links_and_mode_command_deltas_keep_directory_in_sync() {
    let mut store = RchSqliteStore::in_memory().unwrap();
    let mut before = RchCore::new().snapshot();
    before.identity_states = vec![
        state("direct", false),
        state("payload", false),
        state("explicit", false),
        state("rem", false),
    ];
    before.identity_announces = vec![announce("r", "rem", "REM", "destination", "rem", 1)];
    store.save_snapshot(&before).unwrap();
    let member = crate::TeamMemberRecord {
        uid: "member".into(),
        team_uid: Some("team".into()),
        rns_identity: " DIRECT ".into(),
        display_name: "Member".into(),
        icon: None,
        role: None,
        callsign: None,
        freq: None,
        email: None,
        phone: None,
        modulation: None,
        availability: None,
        certifications: vec![],
        last_active: None,
        client_identities: vec![" PAYLOAD ".into()],
        created_ts_ms: 0,
        updated_ts_ms: 0,
    };
    let mut after = before.clone();
    after.team_members.push(member);
    after
        .team_member_client_links
        .push(crate::TeamMemberClientLinkRecord {
            team_member_uid: "member".into(),
            client_identity: " EXPLICIT ".into(),
        });
    after.identity_rem_modes.push(IdentityRemModeRecord {
        identity: " REM ".into(),
        mode: "connected".into(),
        updated_ts_ms: 1,
    });
    store.save_r3akt_command_delta(&before, &after).unwrap();
    let mut q = query();
    q.recent_cutoff_ms = Some(100);
    let page = store.load_identity_directory_page(&q, &[]).unwrap();
    assert_eq!(page.total, 4);
    assert_eq!(page.entries[3].rem_mode.as_ref().unwrap().mode, "connected");
    let mut deleted = after.clone();
    deleted.team_members.clear();
    deleted.team_member_client_links.clear();
    deleted.identity_rem_modes.clear();
    store.save_r3akt_command_delta(&after, &deleted).unwrap();
    let page = store.load_identity_directory_page(&q, &[]).unwrap();
    assert_eq!(page.total, 1);
    assert!(page.entries[0].rem_mode.is_none());
    assert_eq!(store.load_identity_announces().unwrap().len(), 1);
}

pub(super) fn capture_production_plans(store: &RchSqliteStore) -> serde_json::Value {
    let overlays = r#"[{"identity":"id00000","display_name":"Custom ignored","voice_destination":"id14999"},{"identity":"runtime-only","display_name":null,"voice_destination":"id14998"}]"#;
    let mut evidence = Vec::new();
    for (label, identity, cutoff, search, newest) in [
        ("all_with_overlays", None, None, None, false),
        ("recent_with_overlays", None, Some(90_000), None, true),
        ("search_with_overlays", None, None, Some("name"), false),
        (
            "advertised_destination_lookup",
            Some("dst000001"),
            None,
            None,
            false,
        ),
    ] {
        let mut plans = Vec::new();
        for (kind, sql) in [
            (
                "count",
                format!(
                    "{} SELECT COUNT(*) FROM filtered",
                    filter_sql(identity.is_some())
                ),
            ),
            ("page", page_sql(newest, identity.is_some())),
        ] {
            let mut statement = store
                .connection
                .prepare(&format!("EXPLAIN QUERY PLAN {sql}"))
                .unwrap();
            let bindings = if kind == "count" {
                vec![
                    SqlValue::Text(overlays.into()),
                    identity.map_or(SqlValue::Null, |v| SqlValue::Text(v.into())),
                    SqlValue::Null,
                    cutoff.map_or(SqlValue::Null, SqlValue::Integer),
                    search.map_or(SqlValue::Null, |v| SqlValue::Text(v.into())),
                ]
            } else {
                vec![
                    SqlValue::Text(overlays.into()),
                    identity.map_or(SqlValue::Null, |v| SqlValue::Text(v.into())),
                    SqlValue::Null,
                    cutoff.map_or(SqlValue::Null, SqlValue::Integer),
                    search.map_or(SqlValue::Null, |v| SqlValue::Text(v.into())),
                    SqlValue::Integer(50),
                    SqlValue::Integer(0),
                ]
            };
            let plan = statement
                .query_map(rusqlite::params_from_iter(bindings), |r| {
                    r.get::<_, String>(3)
                })
                .unwrap()
                .collect::<Result<Vec<_>, _>>()
                .unwrap()
                .join("\n");
            assert!(
                plan.contains("idx_rch_directory_announces")
                    || plan.contains("idx_rch_directory_heard"),
                "{label} {kind}: {plan}"
            );
            assert!(
                plan.contains("idx_rch_directory_member_clients"),
                "{label} {kind}: {plan}"
            );
            assert!(
                !plan.contains("SCAN a ") && !plan.contains("SCAN annotation "),
                "{label} {kind}: {plan}"
            );
            if identity.is_some() {
                assert!(plan.contains("SEARCH d USING INDEX sqlite_autoindex_rch_identity_directory_1 (identity=?)"), "exact lookup must probe directory key: {plan}");
            }
            if kind == "page" {
                assert!(
                    plan.contains("CO-ROUTINE d") || plan.contains("MATERIALIZE d"),
                    "page must be selected before payload joins: {plan}"
                );
                assert!(
                    plan.contains("SEARCH s USING INDEX")
                        && plan.contains("SEARCH a USING INDEX")
                        && plan.contains("SEARCH m USING INDEX"),
                    "payload joins must use selected keys: {plan}"
                );
            }
            plans.push(serde_json::json!({"kind":kind,"sql":sql,"plan":plan}));
        }
        let runtime_overlays = [
            IdentityDirectoryClientOverlay {
                identity: "id00000".into(),
                display_name: Some("Custom ignored".into()),
                voice_destination: Some("id14999".into()),
            },
            IdentityDirectoryClientOverlay {
                identity: "runtime-only".into(),
                display_name: None,
                voice_destination: Some("id14998".into()),
            },
        ];
        let query = IdentityDirectoryQuery {
            identity: identity.map(str::to_string),
            recent_cutoff_ms: cutoff,
            search: search.map(str::to_string),
            newest_first: newest,
            ..query()
        };
        let started = std::time::Instant::now();
        let page = store
            .load_identity_directory_page(&query, &runtime_overlays)
            .unwrap();
        evidence.push(serde_json::json!({"query":label,"total":page.total,"decoded_states":page.entries.len(),"decoded_announces":page.entries.iter().filter(|e|e.announce.is_some()).count(),"decoded_modes":page.entries.iter().filter(|e|e.rem_mode.is_some()).count(),"page_and_count_us":started.elapsed().as_micros(),"plans":plans}));
    }
    serde_json::json!({"identity_count":15_000,"announce_count":100_000,"scalar_count_and_substring_scans_allowed":true,"queries":evidence})
}

#[test]
fn retained_fixture_production_query_plans() {
    if let Some(path) = std::env::var_os("RCH_IDENTITY_DIRECTORY_FIXTURE_PATH") {
        let reader = RchSqliteStore::open_read_only(std::path::PathBuf::from(&path)).unwrap();
        let evidence = capture_production_plans(&reader);
        std::fs::write(
            std::path::PathBuf::from(path).with_extension("metrics.json"),
            serde_json::to_vec_pretty(&evidence).unwrap(),
        )
        .unwrap();
    }
}

#[test]
fn unicode_name_search_preserves_original_payload_and_annotation_precedence() {
    let mut store = RchSqliteStore::in_memory().unwrap();
    store
        .upsert_identity_states(&[state("owner", false)])
        .unwrap();
    let overlay = IdentityDirectoryClientOverlay {
        identity: "OWNER".into(),
        display_name: Some("ÉQUIPE Müller".into()),
        voice_destination: None,
    };
    let mut q = query();
    q.search = Some("équipe MÜLLER".into());
    assert_eq!(
        store
            .load_identity_directory_page(&q, std::slice::from_ref(&overlay))
            .unwrap()
            .total,
        1
    );
    let record = announce(
        "dst",
        "owner",
        "Über ÁLPHA",
        "destination",
        "generic_lxmf",
        123,
    );
    let bytes = crate::encode_msgpack(&record).unwrap();
    store
        .upsert_identity_announces(std::slice::from_ref(&record))
        .unwrap();
    assert_eq!(
        store
            .load_identity_directory_page(&q, std::slice::from_ref(&overlay))
            .unwrap()
            .total,
        0
    );
    q.search = Some("ÜBER álpha".into());
    let page = store
        .load_identity_directory_page(&q, std::slice::from_ref(&overlay))
        .unwrap();
    assert_eq!(page.total, 1);
    assert_eq!(page.entries[0].announce.as_ref(), Some(&record));
    assert_eq!(
        store
            .connection
            .query_row("SELECT payload FROM rch_identity_announces", [], |r| r
                .get::<_, Vec<u8>>(0))
            .unwrap(),
        bytes
    );
    let mut snapshot = RchCore::new().snapshot();
    snapshot.identity_states = vec![state("owner", false)];
    snapshot.identity_announces = vec![record.clone()];
    store.save_snapshot(&snapshot).unwrap();
    assert_eq!(
        store.load_identity_directory_page(&q, &[]).unwrap().entries[0]
            .announce
            .as_ref(),
        Some(&record)
    );
}
