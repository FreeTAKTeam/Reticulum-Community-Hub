//! RCH owns custody checkpoints and ordered business completion independently of daemon ACKs.
use super::{RchCoreError, RchSqliteStore};
use rusqlite::{OptionalExtension, TransactionBehavior, params};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};

fn inbox_version() -> u16 {
    1
}
pub const INBOX_MAX_BYTES: i64 = 256 * 1024 * 1024;
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InboxEvent {
    #[serde(default = "inbox_version")]
    pub version: u16,
    pub position: u64,
    pub created_at: i64,
    pub event_type: String,
    pub payload: Value,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InboxBatch {
    pub journal_id: String,
    pub consumer_id: String,
    pub start: u64,
    pub end: u64,
    pub receipt: String,
    pub events: Vec<InboxEvent>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InboxCheckpoint {
    pub consumer_id: String,
    pub journal_id: Option<String>,
    pub stored: u64,
    pub applied: u64,
}
fn integer(value: u64) -> Result<i64, RchCoreError> {
    i64::try_from(value).map_err(|e| RchCoreError::Decode(e.to_string()))
}
fn encode<T: Serialize>(value: &T) -> Result<String, RchCoreError> {
    serde_json::to_string(value).map_err(|e| RchCoreError::Encode(e.to_string()))
}
fn decode<T: serde::de::DeserializeOwned>(value: &str) -> Result<T, RchCoreError> {
    serde_json::from_str(value).map_err(|e| RchCoreError::Decode(e.to_string()))
}
fn recovery(message: &str) -> RchCoreError {
    RchCoreError::RecoveryRequired(message.into())
}

impl RchSqliteStore {
    pub(super) fn migrate_durable_inbox(&self) -> Result<(), RchCoreError> {
        let done: bool = self.connection.query_row(
            "SELECT EXISTS(SELECT 1 FROM rch_schema_migrations WHERE version=5)",
            [],
            |row| row.get(0),
        )?;
        if done {
            return Ok(());
        }
        self.backup_before_migration(5)?;
        let tx = self.connection.unchecked_transaction()?;
        tx.execute_batch("CREATE TABLE IF NOT EXISTS rch_broker_profile (singleton INTEGER PRIMARY KEY CHECK(singleton=1),min_writer INTEGER NOT NULL CHECK(min_writer=1),inbox_bytes INTEGER NOT NULL DEFAULT 0,outbox_bytes INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS rch_broker_checkpoint (consumer_id TEXT PRIMARY KEY,journal_id TEXT NOT NULL,stored INTEGER NOT NULL,applied INTEGER NOT NULL CHECK(applied<=stored),receipt TEXT,issued_start INTEGER,issued_end INTEGER);
            CREATE TABLE IF NOT EXISTS rch_broker_inbox (journal_id TEXT NOT NULL,position INTEGER NOT NULL,event_type TEXT NOT NULL,created_at INTEGER NOT NULL,payload TEXT NOT NULL,fingerprint TEXT NOT NULL,status TEXT NOT NULL,error TEXT,PRIMARY KEY(journal_id,position));
            CREATE TABLE IF NOT EXISTS rch_broker_claims (source TEXT NOT NULL,logical_id TEXT NOT NULL,fingerprint TEXT NOT NULL,PRIMARY KEY(source,logical_id));
            CREATE TABLE IF NOT EXISTS rch_broker_dispatch (operation_id TEXT PRIMARY KEY,message_id TEXT NOT NULL,payload TEXT NOT NULL,state TEXT NOT NULL,daemon_message_id TEXT,receipt_status TEXT NOT NULL DEFAULT 'queued');
            CREATE TABLE IF NOT EXISTS rch_broker_attachment_bytes (file_id INTEGER PRIMARY KEY REFERENCES rch_file_attachments(file_id) ON DELETE CASCADE,bytes BLOB NOT NULL);
            CREATE INDEX IF NOT EXISTS rch_broker_dispatch_message ON rch_broker_dispatch(message_id);
            CREATE INDEX IF NOT EXISTS rch_broker_dispatch_daemon ON rch_broker_dispatch(daemon_message_id);
            CREATE INDEX IF NOT EXISTS rch_broker_pending ON rch_broker_inbox(journal_id,status,position);")?;
        tx.execute(
            "INSERT OR IGNORE INTO rch_schema_migrations VALUES(5,'durable ZeroMQ inbox',?1)",
            [super::utc_now_ms()],
        )?;
        tx.execute("INSERT OR REPLACE INTO rch_settings(setting_key,setting_value) VALUES('schema_version','5')",[])?;
        tx.commit()?;
        Ok(())
    }
    pub fn enable_durable_inbox(&self) -> Result<(), RchCoreError> {
        let version: String = self
            .connection
            .query_row("SELECT sqlite_version()", [], |r| r.get(0))?;
        let components = version
            .split('.')
            .map(str::parse::<u32>)
            .collect::<Result<Vec<_>, _>>()
            .map_err(|e| RchCoreError::Decode(e.to_string()))?;
        if components.as_slice() < [3, 51, 3].as_slice() {
            return Err(recovery(
                "native SQLite does not support the required WAL durability profile",
            ));
        }
        let mode: String = self
            .connection
            .query_row("PRAGMA journal_mode=WAL", [], |r| r.get(0))?;
        if mode != "wal" {
            return Err(recovery("durable custody requires local disk WAL storage"));
        }
        self.connection.pragma_update(None, "synchronous", "FULL")?;
        self.connection
            .pragma_update(None, "wal_autocheckpoint", 64)?;
        let page_size: i64 = self
            .connection
            .query_row("PRAGMA page_size", [], |r| r.get(0))?;
        let page_limit = (512 * 1024 * 1024) / page_size;
        self.connection
            .pragma_update(None, "max_page_count", page_limit)?;
        let actual_limit: i64 = self
            .connection
            .query_row("PRAGMA max_page_count", [], |r| r.get(0))?;
        if actual_limit > page_limit {
            return Err(recovery(
                "existing database exceeds durable page budget; compact before cutover",
            ));
        }
        let synchronous: i64 = self
            .connection
            .query_row("PRAGMA synchronous", [], |r| r.get(0))?;
        if synchronous != 2 {
            return Err(recovery("FULL synchronous was not applied"));
        }
        let version: Option<i64> = self
            .connection
            .query_row(
                "SELECT min_writer FROM rch_broker_profile WHERE singleton=1",
                [],
                |r| r.get(0),
            )
            .optional()?;
        if version.is_some_and(|v| v != 1) {
            return Err(recovery("RCH database requires a newer durable writer"));
        }
        self.connection.execute(
            "INSERT OR IGNORE INTO rch_broker_profile(singleton,min_writer) VALUES(1,1)",
            [],
        )?;
        if let Some(path) = self.connection.path() {
            let size = match std::fs::metadata(format!("{path}-wal")) {
                Ok(m) => m.len(),
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => 0,
                Err(e) => return Err(RchCoreError::StorageBackpressure(e.to_string())),
            };
            if size > 64 * 1024 * 1024 {
                let timeout: i64 = self
                    .connection
                    .query_row("PRAGMA busy_timeout", [], |r| r.get(0))?;
                self.connection.pragma_update(None, "busy_timeout", 0)?;
                let checkpoint =
                    self.connection
                        .query_row("PRAGMA wal_checkpoint(TRUNCATE)", [], |r| {
                            r.get::<_, i64>(0)
                        });
                self.connection
                    .pragma_update(None, "busy_timeout", timeout)?;
                checkpoint?;
            }
        }
        Ok(())
    }
    pub fn inbox_checkpoint(&self, consumer: &str) -> Result<InboxCheckpoint, RchCoreError> {
        let checkpoint = self
            .connection
            .query_row(
                "SELECT journal_id,stored,applied FROM rch_broker_checkpoint WHERE consumer_id=?1",
                [consumer],
                |r| {
                    Ok((
                        r.get::<_, String>(0)?,
                        r.get::<_, i64>(1)?,
                        r.get::<_, i64>(2)?,
                    ))
                },
            )
            .optional()?;
        Ok(match checkpoint {
            Some((journal, s, a)) => InboxCheckpoint {
                consumer_id: consumer.into(),
                journal_id: Some(journal),
                stored: position(s)?,
                applied: position(a)?,
            },
            None => InboxCheckpoint {
                consumer_id: consumer.into(),
                journal_id: None,
                stored: 0,
                applied: 0,
            },
        })
    }
    /// Short custody transaction only: business work is deliberately outside this commit.
    pub fn store_inbox_batch(&mut self, batch: &InboxBatch) -> Result<(), RchCoreError> {
        self.enable_durable_inbox()?;
        if batch.consumer_id.is_empty()
            || batch.consumer_id.len() > 128
            || batch.journal_id.len() > 128
            || batch.receipt.len() > 256
            || batch.events.len() > 128
        {
            return Err(recovery("invalid broker batch identifiers or size"));
        }
        admit_effect_bytes(&self.connection, 12 * 1024 * 1024)?;
        let tx = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let other: bool = tx.query_row(
            "SELECT EXISTS(SELECT 1 FROM rch_broker_checkpoint WHERE consumer_id<>?1)",
            [&batch.consumer_id],
            |r| r.get(0),
        )?;
        if other {
            return Err(recovery(
                "this RCH database is bound to another durable consumer",
            ));
        }
        let previous: Option<(String, i64)> = tx
            .query_row(
                "SELECT journal_id,stored FROM rch_broker_checkpoint WHERE consumer_id=?1",
                [&batch.consumer_id],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .optional()?;
        let stored = previous.as_ref().map_or(0, |(_, s)| *s);
        if previous
            .as_ref()
            .is_some_and(|(journal, _)| journal != &batch.journal_id)
            || integer(batch.start)? > stored
            || batch.end < batch.start
        {
            return Err(recovery(
                "journal changed or issued range skips local custody",
            ));
        }
        let mut used: i64 = tx.query_row(
            "SELECT inbox_bytes FROM rch_broker_profile WHERE singleton=1",
            [],
            |r| r.get(0),
        )?;
        let mut last = batch.start;
        let mut incoming = 0i64;
        for event in &batch.events {
            if event.position <= last || event.position > batch.end {
                return Err(recovery("events do not follow the issued scanned range"));
            }
            last = event.position;
            let payload = encode(event)?;
            incoming = incoming.saturating_add(length(payload.len())?);
            if incoming > 12 * 1024 * 1024 {
                return Err(recovery("broker batch exceeded the negotiated byte bound"));
            }
            let fingerprint = hex_digest(payload.as_bytes());
            let existing: Option<String> = tx
                .query_row(
                    "SELECT fingerprint FROM rch_broker_inbox WHERE journal_id=?1 AND position=?2",
                    params![batch.journal_id, integer(event.position)?],
                    |r| r.get(0),
                )
                .optional()?;
            if let Some(existing) = existing {
                if existing != fingerprint {
                    return Err(recovery(
                        "same journal position contains different immutable content",
                    ));
                }
                continue;
            }

            if used.saturating_add(length(payload.len())? + 256) > INBOX_MAX_BYTES {
                return Err(RchCoreError::StorageBackpressure(
                    "RCH inbox capacity exhausted before custody".into(),
                ));
            }
            used = used.saturating_add(length(payload.len())? + 256);
            tx.execute(
                "INSERT INTO rch_broker_inbox VALUES(?1,?2,?3,?4,?5,?6,'stored',NULL)",
                params![
                    batch.journal_id,
                    integer(event.position)?,
                    event.event_type,
                    event.created_at,
                    payload,
                    fingerprint
                ],
            )?;
        }
        tx.execute(
            "UPDATE rch_broker_profile SET inbox_bytes=?1 WHERE singleton=1",
            [used],
        )?;
        tx.execute("INSERT INTO rch_broker_checkpoint VALUES(?1,?2,?3,0,?4,?5,?6) ON CONFLICT(consumer_id) DO UPDATE SET stored=MAX(stored,excluded.stored),receipt=excluded.receipt,issued_start=excluded.issued_start,issued_end=excluded.issued_end",params![batch.consumer_id,batch.journal_id,integer(batch.end)?,batch.receipt,integer(batch.start)?,integer(batch.end)?])?;
        let next:Option<i64>=tx.query_row("SELECT MIN(position) FROM rch_broker_inbox WHERE journal_id=?1 AND status NOT IN ('applied','rejected')",[&batch.journal_id],|r|r.get(0))?;
        let handled = next.map_or(integer(batch.end)?, |next| next - 1);
        tx.execute(
            "UPDATE rch_broker_checkpoint SET applied=MAX(applied,?1) WHERE consumer_id=?2",
            params![handled, batch.consumer_id],
        )?;
        tx.commit()?;
        Ok(())
    }
    pub fn next_inbox_event(&self, consumer: &str) -> Result<Option<InboxEvent>, RchCoreError> {
        let payload:Option<String>=self.connection.query_row("SELECT payload FROM rch_broker_inbox i JOIN rch_broker_checkpoint c USING(journal_id) WHERE c.consumer_id=?1 AND i.status NOT IN ('applied','rejected') ORDER BY i.position LIMIT 1",[consumer],|r|r.get(0)).optional()?;
        payload.as_deref().map(decode).transpose()
    }
}
pub(super) fn hex_digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DurableOutboundIntent {
    pub operation_id: String,
    pub message: super::MessageRecord,
    pub request: Value,
}
impl RchSqliteStore {
    pub fn inbox_ack_receipt(
        &self,
        consumer: &str,
    ) -> Result<Option<(String, u64, String)>, RchCoreError> {
        self.connection.query_row("SELECT journal_id,stored,receipt FROM rch_broker_checkpoint WHERE consumer_id=?1 AND receipt IS NOT NULL",[consumer],|r|Ok((r.get(0)?,u64::try_from(r.get::<_,i64>(1)?).map_err(|e|rusqlite::Error::FromSqlConversionFailure(1,rusqlite::types::Type::Integer,Box::new(e)))?,r.get(2)?))).optional().map_err(Into::into)
    }
    pub fn pending_broker_intent(&self) -> Result<Option<DurableOutboundIntent>, RchCoreError> {
        let payload:Option<String>=self.connection.query_row("SELECT payload FROM rch_broker_dispatch WHERE state='pending' ORDER BY rowid LIMIT 1",[],|r|r.get(0)).optional()?;
        payload.as_deref().map(decode).transpose()
    }
    pub fn record_broker_admission(
        &mut self,
        operation: &str,
        daemon_message: &str,
    ) -> Result<super::MessageRecord, RchCoreError> {
        let unit = self.begin_outbound_application()?;
        let record = unit
            .stage_operation_admission(operation, daemon_message)?
            .ok_or_else(|| recovery("unknown durable operation admission"))?;
        unit.commit()?;
        Ok(record)
    }

    pub fn broker_attachment_bytes(&self, file_id: u64) -> Result<Option<Vec<u8>>, RchCoreError> {
        self.connection
            .query_row(
                "SELECT bytes FROM rch_broker_attachment_bytes WHERE file_id=?1",
                [integer(file_id)?],
                |r| r.get(0),
            )
            .optional()
            .map_err(Into::into)
    }
}

/// `SQLite`'s OS lock is released on process death, including SIGKILL. This lock database is separate
/// from business WAL and carries no application data or long-lived business read snapshot.
pub struct RchConsumerLease {
    _connection: rusqlite::Connection,
}
impl RchConsumerLease {
    pub fn acquire(path: &std::path::Path) -> Result<Self, RchCoreError> {
        let mut lock_path = path.as_os_str().to_os_string();
        lock_path.push(".broker-owner.sqlite");
        let connection = rusqlite::Connection::open(std::path::PathBuf::from(lock_path))?;
        connection.busy_timeout(std::time::Duration::ZERO)?;
        connection
            .execute_batch("PRAGMA journal_mode=DELETE;BEGIN EXCLUSIVE;")
            .map_err(|e| {
                recovery(&format!(
                    "another RCH process owns this durable consumer: {e}"
                ))
            })?;
        Ok(Self {
            _connection: connection,
        })
    }
}
impl RchSqliteStore {
    pub fn durable_consumer_id(&mut self) -> Result<String, RchCoreError> {
        self.enable_durable_inbox()?;
        let tx = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let previous: Option<String> = tx
            .query_row(
                "SELECT setting_value FROM rch_settings WHERE setting_key='durable_consumer_id'",
                [],
                |r| r.get(0),
            )
            .optional()?;
        let id = previous.unwrap_or_else(|| format!("rch-{}", uuid::Uuid::new_v4().simple()));
        tx.execute(
            "INSERT OR IGNORE INTO rch_settings VALUES('durable_consumer_id',?1)",
            [&id],
        )?;
        tx.commit()?;
        Ok(id)
    }
}

/// Includes every table/index and the WAL, rather than bounding only pending inbox payloads.
/// Admitted custody is retained on overload; control commits reserve 64 MiB of physical headroom.
pub(super) fn admit_effect_bytes(
    connection: &rusqlite::Connection,
    bytes: usize,
) -> Result<(), RchCoreError> {
    const CAP: u64 = 1024 * 1024 * 1024;
    const HEADROOM: u64 = 64 * 1024 * 1024;
    let path = connection
        .path()
        .ok_or_else(|| recovery("durable storage has no local path"))?;
    if path.is_empty() {
        return Err(recovery("durable storage requires local disk"));
    }
    let file = std::fs::metadata(path)
        .map_err(|e| RchCoreError::StorageBackpressure(format!("durable storage metadata: {e}")))?
        .len();
    let wal = match std::fs::metadata(format!("{path}-wal")) {
        Ok(m) => m.len(),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => 0,
        Err(e) => {
            return Err(RchCoreError::StorageBackpressure(format!(
                "durable WAL metadata: {e}"
            )));
        }
    };
    let page_count: u64 = connection
        .query_row("PRAGMA page_count", [], |r| r.get::<_, i64>(0))
        .and_then(|n| {
            u64::try_from(n).map_err(|e| rusqlite::Error::ToSqlConversionFailure(Box::new(e)))
        })?;
    let page_size: u64 = connection
        .query_row("PRAGMA page_size", [], |r| r.get::<_, i64>(0))
        .and_then(|n| {
            u64::try_from(n).map_err(|e| rusqlite::Error::ToSqlConversionFailure(Box::new(e)))
        })?;
    if page_count
        .saturating_mul(page_size)
        .saturating_add((bytes as u64).saturating_mul(4))
        .saturating_add(65536)
        > 512 * 1024 * 1024 - HEADROOM / 2
    {
        return Err(RchCoreError::StorageBackpressure(
            "RCH page limit headroom reserved for completion".into(),
        ));
    }
    if file
        .saturating_add(wal)
        .saturating_add((bytes as u64).saturating_mul(4))
        .saturating_add(65536)
        > CAP - HEADROOM
    {
        return Err(RchCoreError::StorageBackpressure(
            "RCH database and WAL high-water mark reached; custody retained".into(),
        ));
    }
    Ok(())
}
impl RchSqliteStore {
    pub fn mark_inbox_upgrade_required(
        &self,
        consumer: &str,
        position: u64,
        reason: &str,
    ) -> Result<(), RchCoreError> {
        self.connection.execute("UPDATE rch_broker_inbox SET status='upgrade_required',error=?1 WHERE position=?2 AND journal_id=(SELECT journal_id FROM rch_broker_checkpoint WHERE consumer_id=?3) AND status NOT IN ('applied','rejected')",params![reason,integer(position)?,consumer])?;
        Ok(())
    }
    pub fn reject_broker_intent(
        &mut self,
        operation: &str,
        reason: &str,
    ) -> Result<super::MessageRecord, RchCoreError> {
        let unit = self.begin_outbound_application()?;
        let record = unit.stage_broker_rejection(operation, reason)?;
        unit.commit()?;
        Ok(record)
    }
}

impl RchSqliteStore {
    pub fn durable_broker_diagnostics(&self) -> Result<Value, RchCoreError> {
        let (inbox_bytes, outbox_bytes): (i64, i64) = self.connection.query_row(
            "SELECT inbox_bytes,outbox_bytes FROM rch_broker_profile",
            [],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )?;
        let counts:(i64,i64,i64,i64)=self.connection.query_row("SELECT COALESCE(SUM(status='stored'),0),COALESCE(SUM(status='applied'),0),COALESCE(SUM(status='rejected'),0),COALESCE(SUM(status='upgrade_required'),0) FROM rch_broker_inbox",[],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?)))?;
        let dispatch: i64 = self.connection.query_row(
            "SELECT COUNT(*) FROM rch_broker_dispatch WHERE state='pending'",
            [],
            |r| r.get(0),
        )?;
        let sqlite: String = self
            .connection
            .query_row("SELECT sqlite_version()", [], |r| r.get(0))?;
        Ok(
            serde_json::json!({"inbox_bytes":inbox_bytes,"outbox_bytes":outbox_bytes,"pending":counts.0,"applied":counts.1,"rejected":counts.2,"upgrade_required":counts.3,"pending_dispatch":dispatch,"sqlite_version":sqlite,"durability":"WAL/FULL","writer_version":1}),
        )
    }
}

fn length(value: usize) -> Result<i64, RchCoreError> {
    i64::try_from(value).map_err(|e| RchCoreError::Encode(e.to_string()))
}
fn position(value: i64) -> Result<u64, RchCoreError> {
    u64::try_from(value).map_err(|e| RchCoreError::Decode(e.to_string()))
}
