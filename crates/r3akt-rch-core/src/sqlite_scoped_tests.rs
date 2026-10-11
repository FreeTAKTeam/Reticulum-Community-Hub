fn scoped_fixture() -> RchCore {
    let mut core = sqlite_snapshot_fixture_core(&command(
        "mission.message.send",
        json!({"content":"history","destination":"facefeed"}),
    ));
    core.set_authorization_required(false);
    // A real checklist aggregate is required for task and assignment response parity.
    core.handle_command(&command("checklist.create.offline",json!({"checklist_uid":"sqlite-checklist","mission_uid":"sqlite-mission","name":"Checklist"})));
    core.checklist_cells.insert(
        "sqlite-cell".into(),
        ChecklistCellRecord {
            cell_uid: "sqlite-cell".into(),
            task_uid: "sqlite-task".into(),
            column_uid: "sqlite-column".into(),
            value: Some("kept cell".into()),
            updated_ts_ms: utc_now_ms(),
            updated_by_team_member_rns_identity: None,
        },
    );
    core
}
fn scrub_dynamic(value: &mut Value) {
    match value {
        Value::Object(fields) => {
            for key in [
                "updated_at",
                "created_at",
                "accepted_at",
                "timestamp",
                "timestamp_ms",
                "created_ts_ms",
                "updated_ts_ms",
                "last_activity_ts",
                "created_ts",
                "last_activity_ts_ms",
                "last_seen_ts_ms",
                "event_id",
            ] {
                fields.remove(key);
            }
            for value in fields.values_mut() {
                scrub_dynamic(value);
            }
        }
        Value::Array(values) => {
            for value in values {
                scrub_dynamic(value);
            }
        }
        _ => {}
    }
}
#[test]
fn scoped_commands_match_domain_results_across_registry_families() {
    let base = scoped_fixture().snapshot();
    let cases = [
        (
            "mission.registry.mission.patch",
            json!({"mission_uid":"sqlite-mission","patch":{"mission_name":"Changed"}}),
        ),
        (
            "mission.registry.team.upsert",
            json!({"uid":"sqlite-team","team_name":"Changed"}),
        ),
        (
            "mission.registry.team_member.upsert",
            json!({"uid":"sqlite-member","rns_identity":"peer-sqlite","display_name":"Changed"}),
        ),
        (
            "mission.registry.asset.upsert",
            json!({"asset_uid":"sqlite-asset","name":"Changed"}),
        ),
        (
            "mission.registry.skill.upsert",
            json!({"skill_uid":"sqlite-skill","name":"Changed"}),
        ),
        (
            "mission.registry.team_member_skill.upsert",
            json!({"team_member_rns_identity":"peer-sqlite","skill_uid":"sqlite-skill","level":7}),
        ),
        (
            "mission.registry.task_skill_requirement.upsert",
            json!({"task_uid":"sqlite-task","skill_uid":"sqlite-skill","minimum_level":3}),
        ),
        (
            "mission.registry.assignment.upsert",
            json!({"assignment_uid":"sqlite-assignment","mission_uid":"sqlite-mission","task_uid":"sqlite-task","team_member_rns_identity":"peer-sqlite","assets":["sqlite-asset"]}),
        ),
        (
            "mission.registry.log_entry.upsert",
            json!({"entry_uid":"sqlite-log","mission_uid":"sqlite-mission","content":"Changed"}),
        ),
        (
            "mission.registry.mission_change.upsert",
            json!({"uid":"sqlite-change","mission_uid":"sqlite-mission","notes":"Changed"}),
        ),
        (
            "mission.registry.mission.get",
            json!({"mission_uid":"sqlite-mission","expand":"teams"}),
        ),
        (
            "mission.registry.rights.mission_access.assign",
            json!({"mission_uid":"sqlite-mission","subject_type":"team_member","subject_id":"sqlite-member"}),
        ),
        (
            "topic.patch",
            json!({"id":"mission-1","topic_name":"Changed"}),
        ),
        (
            "checklist.update",
            json!({"checklist_uid":"sqlite-checklist","patch":{"name":"Changed"}}),
        ),
        (
            "mission.registry.mission.get",
            json!({"mission_uid":"sqlite-mission","expand":"checklists"}),
        ),
        (
            "mission.registry.asset.delete",
            json!({"asset_uid":"sqlite-asset"}),
        ),
        (
            "mission.registry.team_member.delete",
            json!({"uid":"sqlite-member"}),
        ),
        ("mission.registry.team.delete", json!({"uid":"sqlite-team"})),
        (
            "mission.registry.assignment.delete",
            json!({"assignment_uid":"sqlite-assignment"}),
        ),
        (
            "mission.registry.asset.list",
            json!({"team_member_uid":"sqlite-member"}),
        ),
        (
            "mission.registry.team_member_skill.list",
            json!({"team_member_rns_identity":"peer-sqlite"}),
        ),
        (
            "mission.registry.task_skill_requirement.list",
            json!({"task_uid":"sqlite-task"}),
        ),
        ("mission.registry.rights.subjects.list", json!({})),
    ];
    for (kind, args) in cases {
        let db = std::env::temp_dir().join(format!("rch-scoped-{}.db", Uuid::new_v4()));
        let mut store = RchSqliteStore::open(&db).expect("store");
        store.save_snapshot(&base).expect("fixture");
        let request = command(kind, args);
        let checklist = kind.starts_with("checklist.");
        let mut full = RchCore::from_snapshot(base.clone()).expect("domain");
        let full_result = if checklist {
            full.handle_checklist_sync_command(&request)
        } else {
            full.handle_mission_sync_command(&request)
        };
        let mut unit = store.begin_scoped_command(&request, checklist).expect(kind);
        let scoped_result = if checklist {
            unit.core_mut().handle_checklist_sync_command(&request)
        } else {
            unit.core_mut().handle_mission_sync_command(&request)
        };
        let mut left = serde_json::to_value(full_result).expect("full result");
        let mut right = serde_json::to_value(scoped_result).expect("scoped result");
        scrub_dynamic(&mut left);
        scrub_dynamic(&mut right);
        assert_eq!(left, right, "{kind}");
        let delta = unit.commit_delta().expect("commit");
        assert!(delta.rows_read < 100, "{kind}: {} rows", delta.rows_read);
        assert_eq!(
            store.row_count("rch_messages").expect("history"),
            base.messages.len()
        );
        drop(store);
        std::fs::remove_file(db).expect("cleanup");
    }
}
#[test]
fn scoped_one_mission_ignores_same_actor_unrelated_rights_and_corrupt_history() {
    let mut core = scoped_fixture();
    core.set_authorization_required(true);
    core.assign_mission_access_role("sqlite-mission", "identity", "abcdef", "MISSION_OWNER")
        .expect("role");
    let db = std::env::temp_dir().join(format!("rch-scope-scale-{}.db", Uuid::new_v4()));
    let mut store = RchSqliteStore::open(&db).expect("store");
    store.save_snapshot(&core.snapshot()).expect("fixture");
    let request = command(
        "mission.registry.mission.patch",
        json!({"mission_uid":"sqlite-mission","patch":{"mission_name":"Changed"}}),
    );
    let mut first = store.begin_scoped_command(&request, false).expect("first");
    let results = first.core_mut().handle_mission_sync_command(&request);
    assert!(
        !results
            .iter()
            .any(|r| r.results_field().is_some_and(|v| v["status"] == "rejected"))
    );
    drop(first);
    let first = store
        .begin_scoped_command(&request, false)
        .expect("baseline")
        .commit_delta()
        .expect("commit");
    // Corruption outside this target is intentionally never decoded by its command.
    store
        .connection
        .execute_batch("BEGIN IMMEDIATE")
        .expect("begin");
    for index in 0..5000 {
        let uid = format!("unrelated-{index}");
        store
            .connection
            .execute(
                "INSERT INTO rch_missions(uid,payload) VALUES(?1,X'C1')",
                [&uid],
            )
            .expect("mission");
        store.connection.execute("INSERT INTO rch_mission_access_assignments(mission_uid,subject_type,subject_id,payload) VALUES(?1,'identity','abcdef',X'C1')",[&uid]).expect("grant");
        store.connection.execute("INSERT INTO rch_subject_operation_rights(subject_type,subject_id,operation,scope_type,scope_id,payload) VALUES('identity','abcdef','mission.registry.mission.patch','mission',?1,X'C1')",[&uid]).expect("right");
        store
            .connection
            .execute(
                "INSERT INTO rch_messages(message_id,payload) VALUES(?1,X'C1')",
                [&uid],
            )
            .expect("history");
    }
    store
        .connection
        .execute_batch("COMMIT")
        .expect("commit scale");
    let mut request = request;
    request.command_id.push_str("-second");
    let second = store
        .begin_scoped_command(&request, false)
        .expect("same actor bounded")
        .commit_delta()
        .expect("commit");
    assert_eq!(first.rows_read, second.rows_read);
    assert_eq!(first.payload_bytes_read, second.payload_bytes_read);
    let denied = store
        .connection
        .query_row(
            "EXPLAIN QUERY PLAN SELECT payload FROM rch_missions WHERE uid='sqlite-mission'",
            [],
            |row| row.get::<_, String>(3),
        )
        .expect("plan");
    assert!(denied.contains("SEARCH"));
    drop(store);
    std::fs::remove_file(db).expect("cleanup");
}
#[test]
fn scoped_overlap_keeps_staged_changes_and_rollback_is_atomic() {
    let db = std::env::temp_dir().join(format!("rch-scoped-overlap-{}.db", Uuid::new_v4()));
    let mut store = RchSqliteStore::open(&db).expect("store");
    store
        .save_snapshot(&scoped_fixture().snapshot())
        .expect("fixture");
    let first = command(
        "mission.registry.mission.patch",
        json!({"mission_uid":"sqlite-mission","patch":{"mission_name":"First"}}),
    );
    let second = command(
        "mission.registry.mission.get",
        json!({"mission_uid":"sqlite-mission"}),
    );
    {
        let mut unit = store.begin_scoped_command(&first, false).expect("begin");
        unit.core_mut().handle_mission_sync_command(&first);
        unit.prepare_source("abcdef").expect("source");
        unit.prepare_command(&second).expect("overlap");
        assert_eq!(unit.core_mut().missions()[0].mission_name, "First");
        // Drop the unit, including events, without publishing any staged effects.
    }
    assert_ne!(
        store
            .load_snapshot()
            .expect("snapshot")
            .expect("state")
            .missions[0]
            .mission_name,
        "First"
    );
    drop(store);
    std::fs::remove_file(db).expect("cleanup");
}
#[test]
fn recent_message_hydration_bounds_bytes_and_chat_keeps_evicted_history() {
    let db = std::env::temp_dir().join(format!("rch-message-history-{}.db", Uuid::new_v4()));
    let mut store = RchSqliteStore::open(&db).expect("store");
    let prototype = scoped_fixture().messages()[0].clone();
    let records = (0..800)
        .map(|index| {
            let mut message = prototype.clone();
            message.message_id = format!("message-{index}");
            message.created_ts_ms = i64::from(index);
            message.content = "x".repeat(128 * 1024);
            message.delivery_state = "delivered".into();
            message
        })
        .collect::<Vec<_>>();
    store.upsert_messages(&records).expect("history");
    let recent = store.recent_messages().expect("recent");
    assert!(recent.len() < RECENT_MESSAGE_COUNT);
    assert!(
        recent
            .iter()
            .map(MessageRecord::estimated_resident_bytes)
            .sum::<usize>()
            <= RECENT_MESSAGE_BYTES
    );
    let history = store
        .chat_history(&ChatHistoryFilter::default(), 800)
        .expect("all history");
    assert_eq!(history.len(), 800);
    assert_eq!(history[0].message_id, "message-799");
    assert_eq!(history[799].message_id, "message-0");
    assert_eq!(history[799].attachments, prototype.attachments);
    drop(store);
    std::fs::remove_file(db).expect("cleanup");
}

#[test]
fn scoped_staged_membership_loads_persisted_subject_denies() {
    let mut core = scoped_fixture();
    core.set_authorization_required(true);
    core.grant_operation_right("identity", "abcdef", "mission.write", "global", "")
        .expect("identity grant");
    core.revoke_operation_right(
        "team_member",
        "sqlite-member",
        "mission.write",
        "global",
        "",
    )
    .expect("member deny");
    let db = std::env::temp_dir().join(format!("rch-staged-rights-{}.db", Uuid::new_v4()));
    let mut store = RchSqliteStore::open(&db).expect("store");
    store.save_snapshot(&core.snapshot()).expect("fixture");
    let link = command(
        "mission.registry.team_member.client.link",
        json!({"team_member_uid":"sqlite-member","client_identity":"abcdef"}),
    );
    let patch = command(
        "mission.registry.mission.patch",
        json!({"mission_uid":"sqlite-mission","patch":{"mission_name":"Forbidden"}}),
    );
    let mut unit = store.begin_scoped_command(&link, false).expect("begin");
    unit.core_mut().handle_command(&link);
    unit.prepare_command(&patch).expect("staged authority");
    let responses = unit.core_mut().handle_mission_sync_command(&patch);
    assert!(
        responses
            .iter()
            .any(|r| r.results_field().is_some_and(|v| v["status"] == "rejected")),
        "{responses:?}"
    );
    drop(unit);
    drop(store);
    std::fs::remove_file(db).expect("cleanup");
}
#[test]
fn scoped_rem_modes_preserve_global_summary_across_staged_commands() {
    let mut core = RchCore::new();
    for identity in ["aaaa", "bbbb", "cccc"] {
        core.record_identity_announce(
            identity,
            None,
            None,
            Some("identity".into()),
            vec!["r3akt".into(), "EmergencyMessages".into()],
        )
        .expect("announce");
        core.set_identity_rem_mode(identity, "connected")
            .expect("mode");
    }
    let db = std::env::temp_dir().join(format!("rch-staged-modes-{}.db", Uuid::new_v4()));
    let mut store = RchSqliteStore::open(&db).expect("store");
    store.save_snapshot(&core.snapshot()).expect("fixture");
    let mut first = command("rem.registry.mode.set", json!({"mode":"autonomous"}));
    first.source.rns_identity = "aaaa".into();
    let mut unit = store.begin_scoped_command(&first, false).expect("begin");
    for (index, identity) in ["aaaa", "bbbb", "cccc"].into_iter().enumerate() {
        let mut request = first.clone();
        request.command_id = format!("mode-{index}");
        request.source.rns_identity = identity.into();
        unit.prepare_command(&request).expect("next mode");
        let responses = unit.core_mut().handle_mission_sync_command(&request);
        assert_eq!(
            responses[1].results_field().expect("result")["result"]["effective_connected_mode"],
            index < 2
        );
    }
    unit.commit().expect("commit");
    assert!(
        store
            .load_snapshot()
            .expect("state")
            .expect("snapshot")
            .identity_rem_modes
            .iter()
            .all(|r| r.mode == "autonomous")
    );
    drop(store);
    std::fs::remove_file(db).expect("cleanup");
}
#[test]
fn scoped_subscriber_destination_collision_is_rejected_without_overwrite() {
    let mut core = scoped_fixture();
    core.handle_command(&command(
        "SubscribeTopic",
        json!({"TopicID":"mission-1","Destination":"second"}),
    ));
    let db = std::env::temp_dir().join(format!("rch-subscription-collision-{}.db", Uuid::new_v4()));
    let mut store = RchSqliteStore::open(&db).expect("store");
    store.save_snapshot(&core.snapshot()).expect("fixture");
    let request = command(
        "topic.subscriber.patch",
        json!({"subscriber_id":"facefeed","destination":"second"}),
    );
    let mut unit = store.begin_scoped_command(&request, false).expect("begin");
    let responses = unit.core_mut().handle_mission_sync_command(&request);
    assert!(
        responses
            .iter()
            .any(|r| r.results_field().is_some_and(|v| v["status"] == "rejected")),
        "{responses:?}"
    );
    drop(unit);
    assert_eq!(
        store
            .load_snapshot()
            .expect("state")
            .expect("snapshot")
            .subscribers,
        core.snapshot().subscribers
    );
    drop(store);
    std::fs::remove_file(db).expect("cleanup");
}
#[test]
fn startup_cache_excludes_idle_rows_but_history_remains_available() {
    let db = std::env::temp_dir().join(format!("rch-cache-age-{}.db", Uuid::new_v4()));
    let mut store = RchSqliteStore::open(&db).expect("store");
    let record = scoped_fixture().messages()[0].clone();
    store.upsert_message(&record).expect("write");
    assert_eq!(store.recent_messages().expect("recent").len(), 1);
    store
        .connection
        .execute(
            "UPDATE rch_messages SET cache_activity_ts_ms=?1",
            [utc_now_ms() - RECENT_MESSAGE_IDLE_MS - 1],
        )
        .expect("age");
    assert!(store.recent_messages().expect("idle").is_empty());
    assert_eq!(
        store
            .chat_history(&ChatHistoryFilter::default(), 10)
            .expect("history")
            .len(),
        1
    );
    store.upsert_message(&record).expect("late delivery update");
    let snapshot = store.load_snapshot().expect("snapshot").expect("state");
    store
        .save_checklist_command_projection(&snapshot)
        .expect("compatibility projection");
    assert_eq!(
        store.recent_messages().expect("activity preserved").len(),
        1
    );
    store
        .save_snapshot(&snapshot)
        .expect("full compatibility snapshot");
    assert_eq!(store.recent_messages().expect("rehydrated").len(), 1);
    drop(store);
    std::fs::remove_file(db).expect("cleanup");
}

#[test]
fn scoped_concurrent_commands_preserve_both_field_updates() {
    let db = std::env::temp_dir().join(format!("rch-concurrent-scope-{}.db", Uuid::new_v4()));
    let mut store = RchSqliteStore::open(&db).expect("store");
    store
        .save_snapshot(&scoped_fixture().snapshot())
        .expect("fixture");
    drop(store);
    let barrier = std::sync::Arc::new(std::sync::Barrier::new(2));
    let handles = [
        json!({"mission_name":"Concurrent"}),
        json!({"description":"Preserved"}),
    ]
    .into_iter()
    .enumerate()
    .map(|(index, patch)| {
        let path = db.clone();
        let barrier = barrier.clone();
        std::thread::spawn(move || {
            let mut store = RchSqliteStore::open(&path).expect("writer");
            let mut request = command(
                "mission.registry.mission.patch",
                json!({"mission_uid":"sqlite-mission","patch":patch}),
            );
            request.command_id = format!("concurrent-{index}");
            barrier.wait();
            let mut unit = store
                .begin_scoped_command(&request, false)
                .expect("reservation");
            let result = unit.core_mut().handle_mission_sync_command(&request);
            assert!(
                !result
                    .iter()
                    .any(|r| r.results_field().is_some_and(|v| v["status"] == "rejected"))
            );
            unit.commit().expect("commit");
        })
    })
    .collect::<Vec<_>>();
    for handle in handles {
        handle.join().expect("writer");
    }
    let store = RchSqliteStore::open(&db).expect("store");
    let snapshot = store.load_snapshot().expect("snapshot").expect("state");
    assert_eq!(snapshot.missions[0].mission_name, "Concurrent");
    assert_eq!(
        serde_json::to_value(&snapshot.missions[0]).expect("mission")["description"],
        "Preserved"
    );
    drop(store);
    std::fs::remove_file(db).expect("cleanup");
}
#[test]
fn command_index_migration_rolls_back_columns_and_version_on_decode_failure() {
    let directory = std::env::temp_dir().join(format!("rch-index-migration-{}", Uuid::new_v4()));
    std::fs::create_dir(&directory).expect("dir");
    let db = directory.join("state.db");
    let mut store = RchSqliteStore::open(&db).expect("store");
    store
        .save_snapshot(&scoped_fixture().snapshot())
        .expect("fixture");
    store.connection.execute_batch("DROP INDEX idx_rch_clients_identity_normalized;ALTER TABLE rch_clients DROP COLUMN identity_normalized;DELETE FROM rch_schema_migrations WHERE version=6;UPDATE rch_settings SET setting_value='5' WHERE setting_key='schema_version';UPDATE rch_missions SET payload=X'C1';").expect("v5 fixture");
    drop(store);
    assert!(RchSqliteStore::open(&db).is_err());
    let connection = Connection::open(&db).expect("inspect");
    assert!(
        !sqlite_table_has_column(&connection, "rch_clients", "identity_normalized")
            .expect("columns")
    );
    assert_eq!(
        connection
            .query_row(
                "SELECT setting_value FROM rch_settings WHERE setting_key='schema_version'",
                [],
                |row| row.get::<_, String>(0)
            )
            .expect("version"),
        "5"
    );
    assert_eq!(
        connection
            .query_row(
                "SELECT COUNT(*) FROM rch_schema_migrations WHERE version=6",
                [],
                |row| row.get::<_, i64>(0)
            )
            .expect("migration"),
        0
    );
    drop(connection);
    std::fs::remove_dir_all(directory).expect("cleanup");
}
