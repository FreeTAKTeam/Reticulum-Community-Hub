#![allow(
    clippy::items_after_test_module,
    clippy::missing_errors_doc,
    clippy::needless_pass_by_value
)]

use std::collections::{HashMap, HashSet};
use std::future::Future;
use std::path::Path;
use std::pin::Pin;

use r3akt_protocol::{EnvelopeId, ProtocolEnvelope};
use rusqlite::{Connection, params};
use thiserror::Error;
use time::OffsetDateTime;

pub type StoreFuture<'a, T> = Pin<Box<dyn Future<Output = Result<T, StoreError>> + 'a>>;

#[derive(Debug, Error)]
pub enum StoreError {
    #[error("store operation failed: {0}")]
    Operation(String),
    #[error("sqlite operation failed: {0}")]
    Sqlite(#[from] rusqlite::Error),
    #[error("protocol operation failed: {0}")]
    Protocol(#[from] r3akt_protocol::ProtocolError),
}

pub trait DurableStore: Send {
    fn put_inbox(&mut self, envelope: ProtocolEnvelope) -> StoreFuture<'_, StoreWrite>;
    fn put_outbox(&mut self, envelope: ProtocolEnvelope) -> StoreFuture<'_, StoreWrite>;
    fn get_envelope<'a>(&'a self, key: &'a str) -> StoreFuture<'a, Option<ProtocolEnvelope>>;
    fn list_inbox(&self) -> StoreFuture<'_, Vec<ProtocolEnvelope>>;
    fn list_outbox(&self) -> StoreFuture<'_, Vec<ProtocolEnvelope>>;
    fn contains_dedupe_key<'a>(&'a self, key: &'a str) -> StoreFuture<'a, bool>;
    fn audit(&mut self, record: AuditRecord) -> StoreFuture<'_, ()>;
    fn retain_since(&mut self, cutoff: OffsetDateTime) -> StoreFuture<'_, RetentionReport>;
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct StoreWrite {
    pub duplicate: bool,
}

#[derive(Debug, Clone)]
pub struct AuditRecord {
    pub envelope_id: EnvelopeId,
    pub dedupe_key: String,
    pub action: AuditAction,
    pub recorded_at: OffsetDateTime,
    pub detail: Option<String>,
}

impl AuditRecord {
    #[must_use]
    pub fn new(envelope: &ProtocolEnvelope, action: AuditAction) -> Self {
        Self {
            envelope_id: envelope.id,
            dedupe_key: envelope.stable_dedupe_key(),
            action,
            recorded_at: OffsetDateTime::now_utc(),
            detail: None,
        }
    }

    #[must_use]
    pub fn with_detail(mut self, detail: impl Into<String>) -> Self {
        self.detail = Some(detail.into());
        self
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AuditAction {
    Received,
    PersistedInbound,
    Sent,
    Routed,
    DroppedDuplicate,
    Rejected,
    AckEmitted,
    Expired,
}

impl AuditAction {
    #[must_use]
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Received => "received",
            Self::PersistedInbound => "persisted_inbound",
            Self::Sent => "sent",
            Self::Routed => "routed",
            Self::DroppedDuplicate => "dropped_duplicate",
            Self::Rejected => "rejected",
            Self::AckEmitted => "ack_emitted",
            Self::Expired => "expired",
        }
    }
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct RetentionReport {
    pub removed_inbox: usize,
    pub removed_outbox: usize,
    pub removed_audit: usize,
}

#[derive(Debug, Default)]
pub struct MemoryStore {
    inbox: HashMap<String, ProtocolEnvelope>,
    outbox: HashMap<String, ProtocolEnvelope>,
    seen: HashSet<String>,
    audit: Vec<AuditRecord>,
}

impl MemoryStore {
    #[must_use]
    pub fn new() -> Self {
        Self::default()
    }

    #[must_use]
    pub fn audit_records(&self) -> &[AuditRecord] {
        &self.audit
    }

    #[must_use]
    pub fn inbox_len(&self) -> usize {
        self.inbox.len()
    }

    #[must_use]
    pub fn outbox_len(&self) -> usize {
        self.outbox.len()
    }
}

impl DurableStore for MemoryStore {
    fn put_inbox(&mut self, envelope: ProtocolEnvelope) -> StoreFuture<'_, StoreWrite> {
        Box::pin(async move {
            let key = envelope.stable_dedupe_key();
            let duplicate = !self.seen.insert(key.clone());
            if !duplicate {
                self.inbox.insert(key, envelope);
            }
            Ok(StoreWrite { duplicate })
        })
    }

    fn put_outbox(&mut self, envelope: ProtocolEnvelope) -> StoreFuture<'_, StoreWrite> {
        Box::pin(async move {
            let key = envelope.stable_dedupe_key();
            let duplicate = !self.seen.insert(key.clone());
            if !duplicate {
                self.outbox.insert(key, envelope);
            }
            Ok(StoreWrite { duplicate })
        })
    }

    fn contains_dedupe_key<'a>(&'a self, key: &'a str) -> StoreFuture<'a, bool> {
        Box::pin(async move { Ok(self.seen.contains(key)) })
    }

    fn get_envelope<'a>(&'a self, key: &'a str) -> StoreFuture<'a, Option<ProtocolEnvelope>> {
        Box::pin(async move {
            Ok(self
                .inbox
                .get(key)
                .or_else(|| self.outbox.get(key))
                .cloned())
        })
    }

    fn list_inbox(&self) -> StoreFuture<'_, Vec<ProtocolEnvelope>> {
        Box::pin(async move { Ok(self.inbox.values().cloned().collect()) })
    }

    fn list_outbox(&self) -> StoreFuture<'_, Vec<ProtocolEnvelope>> {
        Box::pin(async move { Ok(self.outbox.values().cloned().collect()) })
    }

    fn audit(&mut self, record: AuditRecord) -> StoreFuture<'_, ()> {
        Box::pin(async move {
            self.audit.push(record);
            Ok(())
        })
    }

    fn retain_since(&mut self, cutoff: OffsetDateTime) -> StoreFuture<'_, RetentionReport> {
        Box::pin(async move {
            let inbox_before = self.inbox.len();
            let outbox_before = self.outbox.len();
            let audit_before = self.audit.len();
            self.inbox
                .retain(|_, envelope| envelope.timestamp >= cutoff);
            self.outbox
                .retain(|_, envelope| envelope.timestamp >= cutoff);
            self.audit.retain(|record| record.recorded_at >= cutoff);
            Ok(RetentionReport {
                removed_inbox: inbox_before - self.inbox.len(),
                removed_outbox: outbox_before - self.outbox.len(),
                removed_audit: audit_before - self.audit.len(),
            })
        })
    }
}

#[derive(Debug)]
pub struct SqliteStore {
    connection: Connection,
}

impl SqliteStore {
    pub fn open(path: impl AsRef<Path>) -> Result<Self, StoreError> {
        let connection = Connection::open(path)?;
        Self::from_connection(connection)
    }

    pub fn in_memory() -> Result<Self, StoreError> {
        let connection = Connection::open_in_memory()?;
        Self::from_connection(connection)
    }

    pub fn from_connection(connection: Connection) -> Result<Self, StoreError> {
        let store = Self { connection };
        store.migrate()?;
        Ok(store)
    }

    fn migrate(&self) -> Result<(), StoreError> {
        self.connection.execute_batch(
            "
            CREATE TABLE IF NOT EXISTS envelopes (
                dedupe_key TEXT PRIMARY KEY,
                envelope_id TEXT NOT NULL,
                direction TEXT NOT NULL,
                topic TEXT NOT NULL,
                source TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                payload BLOB NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                envelope_id TEXT NOT NULL,
                dedupe_key TEXT NOT NULL,
                action TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                detail TEXT
            );
            ",
        )?;
        Ok(())
    }

    #[must_use]
    pub fn envelope_count(&self, direction: &str) -> usize {
        self.connection
            .query_row(
                "SELECT COUNT(*) FROM envelopes WHERE direction = ?1",
                [direction],
                |row| row.get::<_, i64>(0),
            )
            .map_or(0, |count| usize::try_from(count).unwrap_or(0))
    }

    fn put_envelope(
        &mut self,
        envelope: ProtocolEnvelope,
        direction: &'static str,
    ) -> Result<StoreWrite, StoreError> {
        let key = envelope.stable_dedupe_key();
        let bytes = envelope.encode_msgpack()?;
        let changed = self.connection.execute(
            "INSERT OR IGNORE INTO envelopes
             (dedupe_key, envelope_id, direction, topic, source, timestamp, payload)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            params![
                key,
                envelope.id.to_string(),
                direction,
                envelope.topic.as_str(),
                envelope.source.as_str(),
                envelope.timestamp.to_string(),
                bytes
            ],
        )?;
        Ok(StoreWrite {
            duplicate: changed == 0,
        })
    }

    fn list_direction(&self, direction: &str) -> Result<Vec<ProtocolEnvelope>, StoreError> {
        let mut statement = self.connection.prepare(
            "SELECT payload FROM envelopes WHERE direction = ?1 ORDER BY timestamp, envelope_id",
        )?;
        let rows = statement.query_map([direction], |row| row.get::<_, Vec<u8>>(0))?;
        let mut envelopes = Vec::new();
        for row in rows {
            let bytes = row?;
            envelopes.push(ProtocolEnvelope::decode_msgpack(&bytes)?);
        }
        Ok(envelopes)
    }
}

impl DurableStore for SqliteStore {
    fn put_inbox(&mut self, envelope: ProtocolEnvelope) -> StoreFuture<'_, StoreWrite> {
        Box::pin(async move { self.put_envelope(envelope, "inbox") })
    }

    fn put_outbox(&mut self, envelope: ProtocolEnvelope) -> StoreFuture<'_, StoreWrite> {
        Box::pin(async move { self.put_envelope(envelope, "outbox") })
    }

    fn contains_dedupe_key<'a>(&'a self, key: &'a str) -> StoreFuture<'a, bool> {
        Box::pin(async move {
            let count = self.connection.query_row(
                "SELECT COUNT(*) FROM envelopes WHERE dedupe_key = ?1",
                [key],
                |row| row.get::<_, i64>(0),
            )?;
            Ok(count > 0)
        })
    }

    fn get_envelope<'a>(&'a self, key: &'a str) -> StoreFuture<'a, Option<ProtocolEnvelope>> {
        Box::pin(async move {
            let mut statement = self
                .connection
                .prepare("SELECT payload FROM envelopes WHERE dedupe_key = ?1")?;
            let mut rows = statement.query([key])?;
            let Some(row) = rows.next()? else {
                return Ok(None);
            };
            let bytes: Vec<u8> = row.get(0)?;
            Ok(Some(ProtocolEnvelope::decode_msgpack(&bytes)?))
        })
    }

    fn list_inbox(&self) -> StoreFuture<'_, Vec<ProtocolEnvelope>> {
        Box::pin(async move { self.list_direction("inbox") })
    }

    fn list_outbox(&self) -> StoreFuture<'_, Vec<ProtocolEnvelope>> {
        Box::pin(async move { self.list_direction("outbox") })
    }

    fn audit(&mut self, record: AuditRecord) -> StoreFuture<'_, ()> {
        Box::pin(async move {
            self.connection.execute(
                "INSERT INTO audit_records
                 (envelope_id, dedupe_key, action, recorded_at, detail)
                 VALUES (?1, ?2, ?3, ?4, ?5)",
                params![
                    record.envelope_id.to_string(),
                    record.dedupe_key,
                    record.action.as_str(),
                    record.recorded_at.to_string(),
                    record.detail
                ],
            )?;
            Ok(())
        })
    }

    fn retain_since(&mut self, cutoff: OffsetDateTime) -> StoreFuture<'_, RetentionReport> {
        Box::pin(async move {
            let cutoff = cutoff.to_string();
            let removed_inbox = self.connection.execute(
                "DELETE FROM envelopes WHERE direction = 'inbox' AND timestamp < ?1",
                [&cutoff],
            )?;
            let removed_outbox = self.connection.execute(
                "DELETE FROM envelopes WHERE direction = 'outbox' AND timestamp < ?1",
                [&cutoff],
            )?;
            let removed_audit = self.connection.execute(
                "DELETE FROM audit_records WHERE recorded_at < ?1",
                [&cutoff],
            )?;
            Ok(RetentionReport {
                removed_inbox,
                removed_outbox,
                removed_audit,
            })
        })
    }
}

#[cfg(test)]
mod tests {
    use r3akt_protocol::{Destination, HealthStatus, Heartbeat, NodeId, Payload, Topic};

    use super::*;

    fn heartbeat(sequence: u64) -> ProtocolEnvelope {
        ProtocolEnvelope::new(
            NodeId::new("alpha"),
            Destination::Topic(Topic::new("health")),
            Topic::new("health"),
            Payload::Heartbeat(Heartbeat {
                status: HealthStatus::Nominal,
                sequence,
            }),
        )
        .with_dedupe_key(format!("alpha:heartbeat:{sequence}"))
    }

    #[test]
    fn memory_store_dedupes_by_stable_key() {
        let mut store = MemoryStore::new();
        let envelope = heartbeat(1);
        crate::test_block_on(store.put_inbox(envelope.clone())).expect("first insert");
        let duplicate = crate::test_block_on(store.put_inbox(envelope))
            .expect("second insert")
            .duplicate;

        assert!(duplicate);
        assert_eq!(store.inbox_len(), 1);
    }

    #[test]
    fn sqlite_store_persists_msgpack_envelopes() {
        let mut store = SqliteStore::in_memory().expect("sqlite store");
        let envelope = heartbeat(2);
        let key = envelope.stable_dedupe_key();

        crate::test_block_on(store.put_inbox(envelope.clone())).expect("insert");

        assert_eq!(store.envelope_count("inbox"), 1);
        assert_eq!(
            crate::test_block_on(store.get_envelope(&key)).expect("get"),
            Some(envelope.clone())
        );
        assert_eq!(
            crate::test_block_on(store.list_inbox()).expect("list"),
            vec![envelope]
        );
    }
}

#[cfg(test)]
pub fn test_block_on<F>(future: F) -> F::Output
where
    F: Future,
{
    use std::task::{Context, Poll, Waker};

    let mut context = Context::from_waker(Waker::noop());
    let mut future = Box::pin(future);

    loop {
        match Pin::new(&mut future).poll(&mut context) {
            Poll::Ready(output) => return output,
            Poll::Pending => std::thread::yield_now(),
        }
    }
}
