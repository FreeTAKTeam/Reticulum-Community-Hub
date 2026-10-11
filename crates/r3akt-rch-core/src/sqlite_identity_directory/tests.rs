mod persistence;

use super::*;
use crate::{ClientRecord, RchCore};
use persistence::capture_production_plans;

fn state(identity: &str, moderated: bool) -> IdentityStateRecord {
    IdentityStateRecord {
        identity: identity.into(),
        is_banned: moderated,
        is_blackholed: false,
        updated_ts_ms: 0,
    }
}
fn announce(
    destination: &str,
    owner: &str,
    name: &str,
    source: &str,
    kind: &str,
    heard: i64,
) -> IdentityAnnounceRecord {
    IdentityAnnounceRecord {
        destination_hash: destination.into(),
        announced_identity_hash: Some(owner.into()),
        display_name: Some(name.into()),
        source_interface: Some(source.into()),
        announce_capabilities: vec![],
        client_type: kind.into(),
        first_seen_ts_ms: 0,
        last_seen_ts_ms: heard,
    }
}
fn query() -> IdentityDirectoryQuery {
    IdentityDirectoryQuery {
        limit: 50,
        ..Default::default()
    }
}

#[test]
fn preference_recency_aliases_and_raw_state_winner_are_independent() {
    let mut store = RchSqliteStore::in_memory().unwrap();
    store
        .upsert_identity_states(&[state(" OWNER ", true), state("owner", false)])
        .unwrap();
    store
        .upsert_identity_announces(&[
            announce("A", "owner", "Newer identity", "identity", "rem", 300),
            announce(
                "Z",
                " OWNER ",
                "Destination winner",
                " Destination ",
                "Generic_LXMF",
                100,
            ),
            announce(
                "ZZ",
                "owner",
                "Later destination",
                "destination",
                "rem",
                400,
            ),
        ])
        .unwrap();
    let page = store.load_identity_directory_page(&query(), &[]).unwrap();
    assert_eq!(page.total, 1);
    assert_eq!(page.entries[0].state.identity, "owner");
    assert_eq!(
        page.entries[0].announce.as_ref().unwrap().destination_hash,
        "Z"
    );
    assert_eq!(page.entries[0].last_heard_ts_ms, Some(400));
    let mut exact = query();
    exact.identity = Some(" zz ".into());
    assert_eq!(
        store
            .load_identity_directory_page(&exact, &[])
            .unwrap()
            .entries[0]
            .state
            .identity,
        "owner"
    );
    exact.identity = None;
    exact.search = Some("destination winner".into());
    assert_eq!(
        store
            .load_identity_directory_page(&exact, &[])
            .unwrap()
            .total,
        1
    );
    exact.search = Some("newer identity".into());
    assert_eq!(
        store
            .load_identity_directory_page(&exact, &[])
            .unwrap()
            .total,
        0
    );
}

#[test]
fn runtime_overlay_search_and_voice_exclusion_precede_count_and_page() {
    let mut store = RchSqliteStore::in_memory().unwrap();
    store
        .upsert_identity_states(&[
            state("voice", false),
            state("owner", false),
            state("other", false),
        ])
        .unwrap();
    let overlays = [IdentityDirectoryClientOverlay {
        identity: " Owner ".into(),
        display_name: Some("Custom name".into()),
        voice_destination: Some("VOICE".into()),
    }];
    let mut q = query();
    q.limit = 1;
    let page = store.load_identity_directory_page(&q, &overlays).unwrap();
    assert_eq!(page.total, 2);
    q.search = Some("custom".into());
    assert_eq!(
        store
            .load_identity_directory_page(&q, &overlays)
            .unwrap()
            .total,
        1
    );
    store
        .upsert_identity_announces(&[announce(
            "dst",
            "owner",
            "Actual",
            "destination",
            "generic_lxmf",
            1,
        )])
        .unwrap();
    assert_eq!(
        store
            .load_identity_directory_page(&q, &overlays)
            .unwrap()
            .total,
        0
    );
    q.search = None;
    assert_eq!(
        store
            .load_identity_directory_page(&q, &overlays)
            .unwrap()
            .total,
        3
    );
    store
        .connection
        .execute("DELETE FROM rch_identity_states WHERE identity='owner'", [])
        .unwrap();
    store
        .connection
        .execute("DELETE FROM rch_identity_announces", [])
        .unwrap();
    assert_eq!(
        store
            .load_identity_directory_page(&q, &overlays)
            .unwrap()
            .total,
        1
    );
}

#[test]
fn recent_preserves_joined_rem_moderated_and_member_linked_records() {
    let mut store = RchSqliteStore::in_memory().unwrap();
    store
        .upsert_identity_states(&[
            state("old", false),
            state("moderated", true),
            state("joined", false),
            state("rem", false),
            state("fresh", false),
        ])
        .unwrap();
    store
        .upsert_identity_announces(&[
            announce("r", "rem", "REM", "identity", "rem", 1),
            announce("f", "fresh", "Fresh", "identity", "generic_lxmf", 100),
        ])
        .unwrap();
    store
        .upsert_client(&ClientRecord {
            identity: "joined".into(),
            first_seen_ts_ms: 0,
            last_seen_ts_ms: 0,
            nickname: None,
            role: "member".into(),
            paused: false,
            text_only: false,
            last_chat_ts_ms: None,
        })
        .unwrap();
    let mut q = query();
    q.recent_cutoff_ms = Some(100);
    assert_eq!(
        store.load_identity_directory_page(&q, &[]).unwrap().total,
        4
    );
    q.client_type = Some("rem".into());
    assert_eq!(
        store.load_identity_directory_page(&q, &[]).unwrap().total,
        1
    );
    q.client_type = None;
    store.delete_client("joined").unwrap();
    assert_eq!(
        store.load_identity_directory_page(&q, &[]).unwrap().total,
        3
    );
    store
        .patch_identity_state("moderated", Some(false), None, 1)
        .unwrap();
    assert_eq!(
        store.load_identity_directory_page(&q, &[]).unwrap().total,
        2
    );
    q.recent_cutoff_ms = None;
    assert_eq!(
        store.load_identity_directory_page(&q, &[]).unwrap().total,
        5
    );
}

#[test]
fn snapshots_preserve_announces_and_transaction_rollback_keeps_directory_consistent() {
    let mut store = RchSqliteStore::in_memory().unwrap();
    let mut snapshot = RchCore::new().snapshot();
    snapshot.identity_states = vec![state("owner", false)];
    snapshot.identity_announces =
        vec![announce("d", "owner", "Original", "destination", "rem", 99)];
    snapshot.identity_rem_modes = vec![IdentityRemModeRecord {
        identity: "owner".into(),
        mode: "connected".into(),
        updated_ts_ms: 1,
    }];
    store.save_snapshot(&snapshot).unwrap();
    assert_eq!(
        store
            .load_identity_directory_page(&query(), &[])
            .unwrap()
            .entries[0]
            .rem_mode
            .as_ref()
            .unwrap()
            .mode,
        "connected"
    );
    snapshot.identity_announces.clear();
    snapshot.identity_states[0].is_banned = true;
    store
        .save_snapshot_preserving_identity_announces(&snapshot)
        .unwrap();
    let page = store.load_identity_directory_page(&query(), &[]).unwrap();
    assert!(page.entries[0].state.is_banned);
    assert_eq!(page.entries[0].last_heard_ts_ms, Some(99));
    store
        .connection
        .execute_batch("BEGIN; DELETE FROM rch_identity_states; ROLLBACK;")
        .unwrap();
    assert_eq!(
        store
            .load_identity_directory_page(&query(), &[])
            .unwrap()
            .total,
        1
    );
}

#[test]
fn large_history_decodes_only_selected_payloads_and_retains_all_records() {
    let mut store = RchSqliteStore::in_memory().unwrap();
    let states = (0..15_000)
        .map(|i| state(&format!("id{i:05}"), false))
        .collect::<Vec<_>>();
    store.upsert_identity_states(&states).unwrap();
    let announces = (0..100_000)
        .map(|i| {
            announce(
                &format!("dst{i:06}"),
                &format!("id{:05}", i % 15_000),
                "Name",
                "identity",
                "generic_lxmf",
                i,
            )
        })
        .collect::<Vec<_>>();
    store.upsert_identity_announces(&announces).unwrap();
    if let Some(path) = std::env::var_os("RCH_IDENTITY_DIRECTORY_FIXTURE_PATH") {
        store.backup_to(std::path::PathBuf::from(path)).unwrap();
    }
    let started = std::time::Instant::now();
    let valid_page = store.load_identity_directory_page(&query(), &[]).unwrap();
    eprintln!(
        "identity directory fixture: 15000 states, 100000 announces, {} selected, {} total, {} us",
        valid_page.entries.len(),
        valid_page.total,
        started.elapsed().as_micros()
    );
    let evidence = capture_production_plans(&store);
    if let Some(path) = std::env::var_os("RCH_IDENTITY_DIRECTORY_FIXTURE_PATH") {
        std::fs::write(
            std::path::PathBuf::from(path).with_extension("metrics.json"),
            serde_json::to_vec_pretty(&evidence).unwrap(),
        )
        .unwrap();
    }
    // Corrupt every unselected payload: any whole-history decode would fail.
    store
        .connection
        .execute(
            "UPDATE rch_identity_states SET payload=X'C1' WHERE identity>='id00050'",
            [],
        )
        .unwrap();
    store
        .connection
        .execute(
            "UPDATE rch_identity_announces SET payload=X'C1' WHERE directory_owner>='id00050'",
            [],
        )
        .unwrap();
    let page = store.load_identity_directory_page(&query(), &[]).unwrap();
    assert_eq!(page.total, 15_000);
    assert_eq!(page.entries.len(), 50);
    assert!(page.entries.iter().all(|e| e.announce.is_some()));
    for (table, count) in [
        ("rch_identity_states", 15_000),
        ("rch_identity_announces", 100_000),
    ] {
        assert_eq!(
            store
                .connection
                .query_row(&format!("SELECT COUNT(*) FROM {table}"), [], |r| r
                    .get::<_, i64>(0))
                .unwrap(),
            count
        );
    }
    for sql in [
        "SELECT destination_hash FROM rch_identity_announces WHERE directory_owner='id00001' ORDER BY directory_priority DESC,destination_hash ASC LIMIT 1",
        "SELECT MAX(last_seen_ts_ms) FROM rch_identity_announces WHERE directory_owner='id00001'",
        "SELECT * FROM rch_identity_directory ORDER BY last_heard_ts_ms DESC,identity ASC LIMIT 50",
    ] {
        let mut stmt = store
            .connection
            .prepare(&format!("EXPLAIN QUERY PLAN {sql}"))
            .unwrap();
        let plan = stmt
            .query_map([], |r| r.get::<_, String>(3))
            .unwrap()
            .collect::<Result<Vec<_>, _>>()
            .unwrap()
            .join("\n");
        assert!(plan.contains("INDEX"), "{plan}");
        assert!(!plan.contains("SCAN rch_identity_announces"), "{plan}");
        assert!(!plan.contains("TEMP B-TREE"), "{plan}");
    }
}
