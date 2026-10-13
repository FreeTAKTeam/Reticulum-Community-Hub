//! Idempotent marker creation.
//!
//! A client key is bound to the validated, normalized creation fields, so a
//! replay with the same payload returns the original marker and reuse with a
//! different payload is a conflict.

use serde_json::json;
use sha2::{Digest, Sha256};

use crate::marker::MarkerRecord;

/// Key validation failures. Display strings are part of the RCH API contract.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum IdempotencyError {
    #[error("Idempotency-Key must contain 1 to 128 visible ASCII characters")]
    InvalidKey,
}

/// Accepts 1 to 128 visible ASCII characters.
///
/// # Errors
/// [`IdempotencyError::InvalidKey`].
pub fn validate_key(value: &str) -> Result<(), IdempotencyError> {
    if value.is_empty() || value.len() > 128 || !value.bytes().all(|byte| byte.is_ascii_graphic()) {
        return Err(IdempotencyError::InvalidKey);
    }
    Ok(())
}

/// Durable command-result ID for a creation key; the key itself is not stored.
#[must_use]
pub fn command_id(key: &str) -> String {
    format!("rch/http/marker/{}", digest(key.as_bytes()))
}

/// Fingerprint of the creation fields a key is bound to. Newly minted
/// identifiers, timestamps and authentication material are excluded.
#[must_use]
pub fn creation_fingerprint(marker: &MarkerRecord) -> String {
    let payload = json!({"marker_type": marker.marker_type, "symbol": marker.symbol,
        "name": marker.name, "category": marker.category, "lat": marker.lat,
        "lon": marker.lon, "notes": marker.notes});
    digest(payload.to_string().as_bytes())
}

/// Whether two markers carry the same creation fields, so a repeated create
/// for an existing identifier is a replay rather than a conflict.
#[must_use]
pub fn same_creation(existing: &MarkerRecord, candidate: &MarkerRecord) -> bool {
    creation_fingerprint(existing) == creation_fingerprint(candidate)
}

fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
