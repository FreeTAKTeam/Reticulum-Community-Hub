use super::{
    ApiError, AppState, Instant, Ordering, RchSqliteStore, Value,
    ensure_kill_switch_persistence_unlocked, json, r3akt_core_error, record_sqlite_latency,
};
use r3akt_rch_core::{OperationRightMutation, RchCoreError, SubjectOperationRight};
use std::sync::atomic::AtomicU64;

/// Fixed accounting slots; no registry of subjects or operations grows with traffic.
#[derive(Debug, Default)]
pub(super) struct Metrics {
    committed: AtomicU64,
    rows_read: AtomicU64,
    rows_written: AtomicU64,
    payload_bytes: AtomicU64,
    max_payload_bytes: AtomicU64,
    total_us: AtomicU64,
    max_us: AtomicU64,
}

impl Metrics {
    fn record(&self, mutation: &OperationRightMutation) {
        let elapsed_us = mutation.elapsed.as_micros().try_into().unwrap_or(u64::MAX);
        self.committed.fetch_add(1, Ordering::Relaxed);
        self.rows_read
            .fetch_add(mutation.rows_read, Ordering::Relaxed);
        self.rows_written
            .fetch_add(mutation.rows_written, Ordering::Relaxed);
        self.payload_bytes
            .fetch_add(mutation.decoded_payload_bytes, Ordering::Relaxed);
        self.max_payload_bytes
            .fetch_max(mutation.decoded_payload_bytes, Ordering::Relaxed);
        self.total_us.fetch_add(elapsed_us, Ordering::Relaxed);
        self.max_us.fetch_max(elapsed_us, Ordering::Relaxed);
    }

    pub(super) fn snapshot(&self) -> Value {
        json!({
            "committed": self.committed.load(Ordering::Relaxed),
            "matching_rows_read": self.rows_read.load(Ordering::Relaxed),
            "changed_rows_written": self.rows_written.load(Ordering::Relaxed),
            "decoded_payload_bytes": self.payload_bytes.load(Ordering::Relaxed),
            "max_decoded_payload_bytes": self.max_payload_bytes.load(Ordering::Relaxed),
            "total_us": self.total_us.load(Ordering::Relaxed),
            "max_us": self.max_us.load(Ordering::Relaxed),
            "accounting_scope": "committed keyed operation-right transactions; matched payload rows and bytes only; excludes SQLite pages, decoded allocations, connection setup and allocator overhead",
        })
    }
}

pub(super) fn set(
    state: &AppState,
    subject_type: &str,
    subject_id: &str,
    operation: &str,
    scope_type: &str,
    scope_id: &str,
    granted: bool,
) -> Result<SubjectOperationRight, ApiError> {
    ensure_kill_switch_persistence_unlocked(state)?;
    let path = state
        .sqlite_path
        .as_ref()
        .ok_or_else(|| ApiError::ServiceUnavailable("R3AKT HTTP writes unavailable".to_string()))?;
    let started = Instant::now();
    let mut store = RchSqliteStore::open(path.as_ref())
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    let result = store.set_operation_right(
        subject_type,
        subject_id,
        operation,
        scope_type,
        scope_id,
        granted,
    );
    record_sqlite_latency(state, started.elapsed());
    let mutation = result.map_err(|error| match error {
        RchCoreError::Encode(_) | RchCoreError::Decode(_) | RchCoreError::Sqlite(_) => {
            ApiError::Internal(error.to_string())
        }
        _ => r3akt_core_error(error),
    })?;
    state.runtime_metrics.operation_rights.record(&mutation);
    Ok(mutation.record)
}
