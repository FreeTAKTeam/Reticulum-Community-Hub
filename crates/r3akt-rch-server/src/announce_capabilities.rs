//! Optional announce capability metadata is untrusted, including embedded `MessagePack`.
//!
//! Announce app data belongs to whichever application announced the
//! destination, so most of it is not capability metadata (#349). Capability
//! documents are UTF-8 text or a `MessagePack` string, binary, array or map.
//! App data that starts with any other `MessagePack` marker (a one-byte
//! scalar such as a fixint, a fixed-width number, nil/bool, an extension or
//! the never-used `0xc1`) cannot be one of those documents and is classified
//! as opaque without parsing it. Its trailing bytes are never accepted as
//! `MessagePack`. A recognised document that fails validation (truncated,
//! trailing data, oversized, too deep, too many items) is still a rejection.
//!
//! The daemon re-serves the same latest announce per peer on every restart
//! and reconciliation, so outcomes are memoised per payload digest in a
//! bounded cache. Diagnostics separate decode calls, cache hits, distinct
//! payloads and opaque data, without recording payloads or peers.
use super::{Value, normalize_capability_value};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::sync::{
    LazyLock, Mutex, PoisonError,
    atomic::{AtomicU64, Ordering},
};
use std::time::Instant;

mod msgpack;
#[cfg(test)]
mod tests;

const MAX_APP_DATA_BYTES: usize = 16 * 1024;
const MAX_DEPTH: usize = 32;
const MAX_ITEMS: usize = 4096;
const LOG_INTERVAL_SECONDS: u64 = 60;
/// Distinct payload outcomes kept; the cache restarts empty when full.
const MAX_CACHED_OUTCOMES: usize = 4096;
static LOG_START: LazyLock<Instant> = LazyLock::new(Instant::now);
static DECODER: LazyLock<Decoder> = LazyLock::new(Decoder::default);

#[derive(Default)]
struct Rejections {
    total: AtomicU64,
    next_log_second: AtomicU64,
}

impl Rejections {
    fn record_at(&self, now_seconds: u64) -> Option<u64> {
        let total = self.total.fetch_add(1, Ordering::Relaxed).saturating_add(1);
        // Monotonic time, independent of the lifetime count. Only one concurrent
        // caller can claim a log window, including the first rejection at time zero.
        let next = self.next_log_second.load(Ordering::Relaxed);
        (now_seconds >= next
            && self
                .next_log_second
                .compare_exchange(
                    next,
                    now_seconds.saturating_add(LOG_INTERVAL_SECONDS),
                    Ordering::Relaxed,
                    Ordering::Relaxed,
                )
                .is_ok())
        .then_some(total)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, thiserror::Error)]
enum DecodeError {
    #[error("app data exceeds byte limit")]
    TooLarge,
    #[error("invalid app-data hex")]
    Hex,
    #[error("malformed or truncated MessagePack")]
    Malformed,
    #[error("MessagePack nesting exceeds limit")]
    Depth,
    #[error("MessagePack item count exceeds limit")]
    Items,
    #[error("unsupported capability value")]
    Value,
    /// Not an error: the app data cannot be a capability document.
    #[error("app data is not a capability document")]
    Opaque,
}

/// The classification of one app-data payload.
#[derive(Clone, Debug, PartialEq, Eq)]
enum Outcome {
    /// A capability document or empty app data; possibly no capabilities.
    Decoded(Vec<String>),
    /// App data of another application; it cannot hold capabilities.
    Opaque,
    /// A capability document that failed validation.
    Rejected(DecodeError),
}

#[derive(Default)]
struct Decoder {
    calls: AtomicU64,
    cache_hits: AtomicU64,
    opaque_total: AtomicU64,
    opaque_distinct: AtomicU64,
    /// Failed decode calls, including repeats served from the cache.
    rejections: Rejections,
    /// Failed payloads seen for the first time since the cache was empty.
    rejected_distinct: AtomicU64,
    cache_resets: AtomicU64,
    cache: Mutex<HashMap<[u8; 32], Outcome>>,
}

impl Decoder {
    fn decode_hex(&self, raw_hex: &str) -> Vec<String> {
        self.calls.fetch_add(1, Ordering::Relaxed);
        let (outcome, fresh) = self.outcome(raw_hex);
        match outcome {
            Outcome::Decoded(capabilities) => capabilities,
            Outcome::Opaque => {
                self.opaque_total.fetch_add(1, Ordering::Relaxed);
                if fresh {
                    self.opaque_distinct.fetch_add(1, Ordering::Relaxed);
                }
                Vec::new()
            }
            Outcome::Rejected(error) => {
                // Count one failed decode call, never individual optional
                // slots or unique peers/attacks. The announce is still ingested.
                let logged = self.rejections.record_at(LOG_START.elapsed().as_secs());
                if fresh {
                    self.rejected_distinct.fetch_add(1, Ordering::Relaxed);
                }
                if let Some(count) = logged {
                    eprintln!(
                        "announce capability decoding failed: {error}; rejected_total={count} rejected_distinct_total={} opaque_total={}",
                        self.rejected_distinct.load(Ordering::Relaxed),
                        self.opaque_total.load(Ordering::Relaxed),
                    );
                }
                Vec::new()
            }
        }
    }

    /// The payload's outcome and whether it was computed rather than cached.
    fn outcome(&self, raw_hex: &str) -> (Outcome, bool) {
        // Never hash or allocate from unbounded encoded input.
        if raw_hex.len() > MAX_APP_DATA_BYTES * 2 {
            return (Outcome::Rejected(DecodeError::TooLarge), true);
        }
        let key: [u8; 32] = Sha256::digest(raw_hex.trim().as_bytes()).into();
        // The cache only memoises pure results, so a poisoned lock is safe to reuse.
        if let Some(outcome) = self
            .cache
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .get(&key)
        {
            self.cache_hits.fetch_add(1, Ordering::Relaxed);
            return (outcome.clone(), false);
        }
        let outcome = classify_hex(raw_hex);
        let mut cache = self.cache.lock().unwrap_or_else(PoisonError::into_inner);
        if cache.len() >= MAX_CACHED_OUTCOMES {
            cache.clear();
            self.cache_resets.fetch_add(1, Ordering::Relaxed);
        }
        let fresh = cache.insert(key, outcome.clone()).is_none();
        (outcome, fresh)
    }

    fn diagnostics(&self) -> Value {
        serde_json::json!({
            "decode_calls_total": self.calls.load(Ordering::Relaxed),
            "cache_hits_total": self.cache_hits.load(Ordering::Relaxed),
            "cache_entries": self.cache.lock().unwrap_or_else(PoisonError::into_inner).len(),
            "cache_max_entries": MAX_CACHED_OUTCOMES,
            "cache_resets_total": self.cache_resets.load(Ordering::Relaxed),
            "rejected_total": self.rejections.total.load(Ordering::Relaxed),
            "rejected_total_scope": "failed_app_data_decode_calls",
            "rejected_distinct_total": self.rejected_distinct.load(Ordering::Relaxed),
            "rejected_distinct_total_scope": "distinct_failed_app_data_payloads_per_cache_window",
            "opaque_total": self.opaque_total.load(Ordering::Relaxed),
            "opaque_total_scope": "decode_calls_with_non_capability_app_data",
            "opaque_distinct_total": self.opaque_distinct.load(Ordering::Relaxed),
            "log_interval_seconds": LOG_INTERVAL_SECONDS,
            "max_app_data_bytes": MAX_APP_DATA_BYTES,
            "max_depth": MAX_DEPTH,
            "max_items": MAX_ITEMS,
        })
    }
}

pub(super) fn diagnostics() -> Value {
    DECODER.diagnostics()
}

pub(super) fn decode_hex(raw_hex: &str) -> Vec<String> {
    DECODER.decode_hex(raw_hex)
}

fn classify_hex(raw_hex: &str) -> Outcome {
    match decode_hex_result(raw_hex) {
        Ok(capabilities) => Outcome::Decoded(capabilities),
        Err(DecodeError::Opaque) => Outcome::Opaque,
        Err(error) => Outcome::Rejected(error),
    }
}

fn decode_hex_result(raw_hex: &str) -> Result<Vec<String>, DecodeError> {
    // Count surrounding whitespace too: never allocate from unbounded encoded input.
    if raw_hex.len() > MAX_APP_DATA_BYTES * 2 {
        return Err(DecodeError::TooLarge);
    }
    let text = raw_hex.trim();
    if text.is_empty() {
        return Ok(Vec::new());
    }
    if !text.len().is_multiple_of(2) {
        return Err(DecodeError::Hex);
    }
    let mut bytes = Vec::with_capacity(text.len() / 2);
    for pair in text.as_bytes().as_chunks::<2>().0 {
        let high = hex_digit(pair[0]).ok_or(DecodeError::Hex)?;
        let low = hex_digit(pair[1]).ok_or(DecodeError::Hex)?;
        bytes.push((high << 4) | low);
    }
    decode(&bytes)
}

fn hex_digit(byte: u8) -> Option<u8> {
    match byte {
        b'0'..=b'9' => Some(byte - b'0'),
        b'a'..=b'f' => Some(byte - b'a' + 10),
        b'A'..=b'F' => Some(byte - b'A' + 10),
        _ => None,
    }
}

fn decode(bytes: &[u8]) -> Result<Vec<String>, DecodeError> {
    if bytes.len() > MAX_APP_DATA_BYTES {
        return Err(DecodeError::TooLarge);
    }
    if let Ok(text) = std::str::from_utf8(bytes) {
        let capabilities = normalize_capability_value(&Value::String(text.to_owned()));
        if !capabilities.is_empty() {
            return Ok(capabilities);
        }
    }
    if bytes.is_empty() {
        return Ok(Vec::new());
    }
    if !is_document_marker(bytes[0]) {
        return Err(DecodeError::Opaque);
    }
    // This validates the complete document before collecting any array slices.
    if let Some(slots) = msgpack::array_items(bytes)? {
        for slot in slots.into_iter().skip(2) {
            match decode_slot(slot) {
                Ok(capabilities) if !capabilities.is_empty() => return Ok(capabilities),
                // Other clients may put opaque non-capability bytes in these
                // slots. Failed capability probes are expected, not rejections.
                Ok(_) | Err(_) => {}
            }
        }
        return Ok(Vec::new());
    }
    let value = decode_value(bytes)?;
    Ok(normalize_capability_value(&value))
}

/// `MessagePack` markers that can start a capability document: map, array,
/// string or binary. Every other marker starts some other application's data.
fn is_document_marker(marker: u8) -> bool {
    matches!(marker, 0x80..=0xbf | 0xc4..=0xc6 | 0xd9..=0xdf)
}

fn decode_value(bytes: &[u8]) -> Result<Value, DecodeError> {
    // Embedded documents need their own budgets; outer slots are already checked
    // by array_items and can be deserialized directly in decode_slot.
    msgpack::validate(bytes)?;
    rmp_serde::from_slice(bytes).map_err(|_| DecodeError::Value)
}

fn decode_slot(slot: &[u8]) -> Result<Vec<String>, DecodeError> {
    if let Some((bytes, binary)) = msgpack::byte_payload(slot)? {
        match decode_value(bytes) {
            Ok(value) => {
                let caps = normalize_capability_value(&value);
                if !caps.is_empty() {
                    return Ok(caps);
                }
            }
            Err(error) if binary => return Err(error),
            // Ordinary string capabilities need not contain an embedded document.
            Err(_) => {}
        }
    }
    let value: Value = rmp_serde::from_slice(slot).map_err(|_| DecodeError::Value)?;
    let caps = normalize_capability_value(&value);
    if !caps.is_empty() {
        return Ok(caps);
    }
    if let Value::Array(items) = value {
        let bytes = items
            .iter()
            .map(|item| item.as_u64().and_then(|v| u8::try_from(v).ok()))
            .collect::<Option<Vec<u8>>>();
        if let Some(bytes) = bytes {
            return decode_value(&bytes).map(|value| normalize_capability_value(&value));
        }
    }
    Ok(Vec::new())
}
