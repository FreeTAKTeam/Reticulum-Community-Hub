//! Marker replication between RCH and REM nodes.
//!
//! Replicas travel as the RCH marker API representation
//! ([`MarkerRecord::api_value`]) inside `mission.marker.*` events. Receivers
//! rebuild the record through the same validation as local creation and keep
//! the most recently updated copy, so every node converges on one record per
//! `object_destination_hash`.

use serde_json::Value;

use crate::marker::{self, MarkerError, MarkerRecord, Position};
use crate::time::unix_ms_from_iso8601;

/// Event types that carry a full marker replica.
pub const UPSERT_EVENTS: &[&str] = &[
    "mission.marker.created",
    "mission.marker.updated",
    "mission.marker.position.updated",
];

/// Event type that removes a replica.
pub const DELETE_EVENT: &str = "mission.marker.deleted";

fn text<'a>(value: &'a Value, key: &str) -> Option<&'a str> {
    value
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|text| !text.is_empty())
}

fn timestamp(value: &Value, key: &'static str) -> Result<i64, MarkerError> {
    text(value, key)
        .and_then(unix_ms_from_iso8601)
        .ok_or(MarkerError::Missing(key))
}

/// The validated identifier of a replicated marker payload.
///
/// # Errors
/// [`MarkerError::Missing`] or [`MarkerError::Identifier`].
pub fn replica_id(value: &Value) -> Result<String, MarkerError> {
    let raw = text(value, "object_destination_hash")
        .ok_or(MarkerError::Missing("object_destination_hash"))?;
    marker::object_destination_hash(raw)
}

/// Rebuilds a marker from its API representation with the same rules as
/// local creation: catalog type and symbol, valid coordinates and a 32-hex
/// identifier. `local_id` is the receiver's own storage key.
///
/// # Errors
/// The first [`MarkerError`] found.
pub fn from_api_value(value: &Value, local_id: String) -> Result<MarkerRecord, MarkerError> {
    let object_destination_hash = replica_id(value)?;
    let marker_type = marker::marker_type(text(value, "type").unwrap_or_default())?;
    let symbol = marker::marker_symbol(text(value, "symbol").unwrap_or_default())?;
    let position = value
        .get("position")
        .ok_or(MarkerError::Missing("position"))?;
    let coordinate = |key| {
        position
            .get(key)
            .and_then(Value::as_f64)
            .unwrap_or(f64::NAN)
    };
    let position = Position::new(coordinate("lat"), coordinate("lon"))?;
    Ok(MarkerRecord {
        local_id,
        object_destination_hash,
        origin_rch: text(value, "origin_rch").unwrap_or_default().to_string(),
        marker_type,
        name: text(value, "name")
            .and_then(marker::normalize_name)
            .unwrap_or_else(|| "Marker".to_string()),
        category: text(value, "category").map_or_else(|| symbol.clone(), str::to_string),
        symbol,
        lat: position.lat(),
        lon: position.lon(),
        notes: text(value, "notes").map(str::to_string),
        created_ts_ms: timestamp(value, "created_at")?,
        updated_ts_ms: timestamp(value, "updated_at")?,
    })
}

/// Last-writer-wins: the incoming replica replaces the stored one only when
/// it was updated later. Equal timestamps keep the stored copy.
#[must_use]
pub fn supersedes(incoming: &MarkerRecord, existing: Option<&MarkerRecord>) -> bool {
    existing.is_none_or(|existing| incoming.updated_ts_ms > existing.updated_ts_ms)
}
