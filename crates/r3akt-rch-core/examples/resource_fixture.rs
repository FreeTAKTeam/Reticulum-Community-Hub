//! Create a fresh typed RCH history fixture without decoding a full snapshot.
use r3akt_rch_core::{
    ChatAttachmentRecord, DeliveryMode, IdentityAnnounceRecord, MessageRecord, RchSqliteStore,
};
use rusqlite::{Connection, params};
use serde_json::json;
use std::path::PathBuf;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    if args.len() != 3 {
        return Err("usage: resource_fixture <new-db> <announces> <messages>".into());
    }
    let path = PathBuf::from(&args[0]);
    if path.exists() {
        return Err("fixture output must be a new database".into());
    }
    let announces = args[1].parse::<usize>()?;
    let messages = args[2].parse::<usize>()?;
    let now = i64::try_from(
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)?
            .as_millis(),
    )?;
    let mut store = RchSqliteStore::open(&path)?;
    for start in (0..announces).step_by(1000) {
        let records = (start..announces.min(start + 1000))
            .map(|index| {
                Ok::<_, std::num::TryFromIntError>(IdentityAnnounceRecord {
                    destination_hash: format!("{index:032x}"),
                    announced_identity_hash: Some(format!("{:032x}", index + announces)),
                    display_name: Some(format!("Resource fixture peer {index}")),
                    source_interface: Some("resource-fixture".into()),
                    announce_capabilities: vec!["lxmf".into()],
                    client_type: "lxmf".into(),
                    first_seen_ts_ms: now - 86_400_000,
                    last_seen_ts_ms: now - i64::try_from(announces - index)? * 1000,
                })
            })
            .collect::<Result<Vec<_>, _>>()?;
        store.upsert_identity_announces(&records)?;
    }
    drop(store);
    let mut connection = Connection::open(&path)?;
    let transaction = connection.transaction()?;
    for index in 0..messages {
        let record = MessageRecord {
            message_id: format!("{:064x}", index + 1),
            topic_id: Some("resource-history".into()),
            destination: Some(format!("{:032x}", index % 100 + 1)),
            sender: "resource-fixture".into(),
            content: format!("history-{index:08}:{}", "x".repeat(4096)),
            delivery_mode: DeliveryMode::Targeted,
            delivery_method: "direct".into(),
            delivery_policy_reason: "sdk_owned".into(),
            delivery_state: "delivered".into(),
            delivery_metadata: json!({"direction":if index % 2 == 0 {"inbound"} else {"outbound"},
                "dispatch_status":"accepted", "acked":true}),
            created_ts_ms: now - i64::try_from(messages - index)? * 1000,
            attachments: if index % 10 == 0 {
                vec![ChatAttachmentRecord {
                    file_id: u64::try_from(index + 1)?,
                    category: "file".into(),
                    name: format!("history-{index}.txt"),
                    size: 4096,
                    media_type: Some("text/plain".into()),
                }]
            } else {
                Vec::new()
            },
        };
        let payload = rmp_serde::to_vec_named(&record)?;
        let restored: MessageRecord = rmp_serde::from_slice(&payload)?;
        if restored != record {
            return Err(format!("message round trip failed at {index}").into());
        }
        transaction.execute(
            "INSERT INTO rch_messages (message_id,payload,delivery_state,dispatch_status,created_ts_ms)
             VALUES (?1,?2,'delivered','accepted',?3)",
            params![record.message_id, payload, record.created_ts_ms],
        )?;
    }
    transaction.commit()?;
    connection.execute_batch("PRAGMA wal_checkpoint(TRUNCATE)")?;
    println!(
        "{}",
        json!({"database":path,"announces":announces,"messages":messages,
        "typed_message_round_trips":messages,"payload_content_bytes":4096,"created_at_ms":now})
    );
    Ok(())
}
