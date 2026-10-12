//! Compare indexed writes against an immutable baseline using identical typed fixtures.
use r3akt_rch_core::{DeliveryMode, MessageRecord, RchSqliteStore};
use rusqlite::Connection;
use serde_json::json;
use std::{path::PathBuf, time::Instant};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    if args.len() == 2 && args[0] == "migrate" {
        let path = PathBuf::from(&args[1]);
        if !path.is_file() {
            return Err("migration input must be an existing database".into());
        }
        let started = Instant::now();
        let store = RchSqliteStore::open(&path)?;
        println!(
            "{}",
            json!({"database":path,"schema":store.schema_version()?,"elapsed_ms":started.elapsed().as_millis()})
        );
        return Ok(());
    }
    if args.len() != 3 {
        return Err("usage: message_index_probe <new-db> <history-count> <update-count>".into());
    }
    let path = PathBuf::from(&args[0]);
    if path.exists() {
        return Err("probe output must be a new database".into());
    }
    let count = args[1].parse::<usize>()?;
    let updates = args[2].parse::<usize>()?;
    if count == 0 {
        return Err("history-count must be positive".into());
    }
    let mut store = RchSqliteStore::open(&path)?;
    let observer = Connection::open(&path)?;
    let seed = Instant::now();
    for start in (0..count).step_by(1000) {
        let records = (start..count.min(start + 1000))
            .map(|index| {
                Ok::<_, std::num::TryFromIntError>(MessageRecord {
                    message_id: format!("{:064x}", index + 1),
                    topic_id: Some(format!("topic-{}", index % 10)),
                    destination: None,
                    sender: "fixture-peer".into(),
                    content: "x".repeat(4096),
                    delivery_mode: DeliveryMode::Fanout,
                    delivery_method: "direct".into(),
                    delivery_policy_reason: "sdk_owned".into(),
                    delivery_state: "queued".into(),
                    delivery_metadata: json!({"direction":"outbound"}),
                    created_ts_ms: 1_800_000_000_000 + i64::try_from(index)?,
                    attachments: vec![],
                })
            })
            .collect::<Result<Vec<_>, _>>()?;
        store.upsert_messages(&records)?;
    }
    let seed_ms = seed.elapsed().as_millis();
    observer.execute_batch("PRAGMA wal_checkpoint(TRUNCATE)")?;
    let before = std::fs::metadata(&path)?.len();
    // The observer holds no reader transaction: use the production auto-checkpoint behavior.
    let started = Instant::now();
    let mut max_wal = 0;
    for index in 0..updates {
        let id = format!("{:064x}", index % count + 1);
        let mut record = store.message_by_id(&id)?.ok_or("missing probe message")?;
        record.delivery_state = if index % 2 == 0 {
            "delivered"
        } else {
            "queued"
        }
        .into();
        store.upsert_message(&record)?;
        max_wal = max_wal.max(std::fs::metadata(format!("{}-wal", path.display()))?.len());
    }
    let update_ms = started.elapsed().as_millis();
    observer.execute_batch("PRAGMA wal_checkpoint(TRUNCATE)")?;
    let after = std::fs::metadata(&path)?.len();
    let pages: i64 = observer.query_row("PRAGMA page_count", [], |row| row.get(0))?;
    let free: i64 = observer.query_row("PRAGMA freelist_count", [], |row| row.get(0))?;
    println!(
        "{}",
        json!({"database":path,"schema":store.schema_version()?,"messages":count,"updates":updates,"content_bytes":4096,"seed_ms":seed_ms,"update_ms":update_ms,"db_before_bytes":before,"db_after_bytes":after,"max_wal_bytes":max_wal,"pages":pages,"free_pages":free})
    );
    Ok(())
}
