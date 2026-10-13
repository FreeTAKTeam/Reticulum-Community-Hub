//! `SQLite` persistence compatible with the RCH database layout.

use r3akt_map_core::sqlite::{self, MarkerCreation};
use r3akt_map_core::{MarkerDraft, MarkerRecord, Position, idempotency};
use rusqlite::Connection;

fn temp_db() -> std::path::PathBuf {
    std::env::temp_dir().join(format!("r3akt-map-core-{}.db", uuid::Uuid::new_v4()))
}

fn record(name: &str) -> MarkerRecord {
    MarkerRecord::create(
        MarkerDraft {
            marker_type: "marker".into(),
            symbol: "fire".into(),
            name: name.into(),
            category: "fire".into(),
            position: Position::new(1.5, 2.5).unwrap(),
            notes: None,
            origin_rch: "origin".into(),
        },
        format!("local-{name}"),
        1_000,
    )
}

#[test]
fn schema_is_created_migrated_and_idempotent() {
    let connection = Connection::open_in_memory().unwrap();
    // A pre-projection table without local_id, as in older RCH databases.
    connection
        .execute_batch(
            "CREATE TABLE rch_markers (object_destination_hash TEXT PRIMARY KEY, payload BLOB NOT NULL);",
        )
        .unwrap();
    sqlite::ensure_schema(&connection).unwrap();
    sqlite::ensure_schema(&connection).unwrap();
    let columns: Vec<String> = connection
        .prepare("SELECT name FROM pragma_table_info('rch_markers')")
        .unwrap()
        .query_map([], |row| row.get(0))
        .unwrap()
        .collect::<Result<_, _>>()
        .unwrap();
    assert_eq!(columns, ["object_destination_hash", "payload", "local_id"]);
    let index: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE name = 'idx_rch_markers_local_id'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(index, 1);
}

#[test]
fn crud_survives_restart() {
    let path = temp_db();
    let alpha = record("alpha");
    let bravo = record("bravo");
    {
        let mut connection = Connection::open(&path).unwrap();
        sqlite::ensure_schema(&connection).unwrap();
        sqlite::insert(&connection, &alpha).unwrap();
        assert!(
            sqlite::insert(&connection, &alpha).is_err(),
            "identifier is unique"
        );
        sqlite::upsert(&connection, &bravo).unwrap();
        let moved = sqlite::update(&mut connection, &alpha.object_destination_hash, |m| {
            m.move_to(Position::new(-3.0, 4.0).unwrap(), 2_000);
            m.rename("alpha 2".into(), 2_000);
        })
        .unwrap()
        .unwrap();
        assert_eq!(
            (moved.lat, moved.lon, moved.updated_ts_ms),
            (-3.0, 4.0, 2_000)
        );
        assert!(
            sqlite::update(&mut connection, "missing", |_| {})
                .unwrap()
                .is_none()
        );
    }
    let connection = Connection::open(&path).unwrap();
    let mut all = sqlite::load_all(&connection).unwrap();
    all.sort_by(|a, b| a.local_id.cmp(&b.local_id));
    assert_eq!(all.len(), 2);
    assert_eq!(all[0].name, "alpha 2");
    assert_eq!(all[1], bravo);
    sqlite::delete(&connection, &bravo.object_destination_hash).unwrap();
    sqlite::delete(&connection, "missing").unwrap();
    assert!(
        sqlite::get(&connection, &bravo.object_destination_hash)
            .unwrap()
            .is_none()
    );
    std::fs::remove_file(path).unwrap();
}

#[test]
fn idempotent_creation_replays_and_detects_conflicts() {
    let mut connection = Connection::open_in_memory().unwrap();
    sqlite::ensure_schema(&connection).unwrap();
    let first = record("alpha");
    let command = idempotency::command_id("key-1");
    let fingerprint = idempotency::creation_fingerprint(&first);
    assert_eq!(
        sqlite::create_once(&mut connection, &first, &command, &fingerprint).unwrap(),
        MarkerCreation::Created(first.clone())
    );
    // A retry mints new identifiers but carries the same fields.
    let retry = record("alpha");
    assert_eq!(
        sqlite::create_once(&mut connection, &retry, &command, &fingerprint).unwrap(),
        MarkerCreation::Replayed(first.clone())
    );
    let changed = record("bravo");
    let changed_fingerprint = idempotency::creation_fingerprint(&changed);
    assert_eq!(
        sqlite::create_once(&mut connection, &changed, &command, &changed_fingerprint).unwrap(),
        MarkerCreation::KeyConflict
    );
    assert_eq!(sqlite::load_all(&connection).unwrap(), vec![first]);
}

#[test]
fn stored_layout_is_named_messagepack() {
    let connection = Connection::open_in_memory().unwrap();
    sqlite::ensure_schema(&connection).unwrap();
    let marker = record("alpha");
    sqlite::insert(&connection, &marker).unwrap();
    let payload: Vec<u8> = connection
        .query_row("SELECT payload FROM rch_markers", [], |row| row.get(0))
        .unwrap();
    assert_eq!(payload, rmp_serde::to_vec_named(&marker).unwrap());
    let fields: serde_json::Value = rmp_serde::from_slice(&payload).unwrap();
    let keys: Vec<_> = fields.as_object().unwrap().keys().cloned().collect();
    let mut expected = vec![
        "local_id",
        "object_destination_hash",
        "origin_rch",
        "marker_type",
        "symbol",
        "name",
        "category",
        "lat",
        "lon",
        "notes",
        "created_ts_ms",
        "updated_ts_ms",
    ];
    let mut actual: Vec<&str> = keys.iter().map(String::as_str).collect();
    expected.sort_unstable();
    actual.sort_unstable();
    assert_eq!(actual, expected);
}

#[test]
fn malformed_rows_are_errors_not_panics() {
    let connection = Connection::open_in_memory().unwrap();
    sqlite::ensure_schema(&connection).unwrap();
    connection
        .execute(
            "INSERT INTO rch_markers (object_destination_hash, payload) VALUES ('bad', X'C1FF00')",
            [],
        )
        .unwrap();
    assert!(sqlite::get(&connection, "bad").is_err());
    assert!(sqlite::load_all(&connection).is_err());
}
