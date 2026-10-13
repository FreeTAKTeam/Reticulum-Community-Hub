//! Point markers: independently identified map objects.
//!
//! `object_destination_hash` is the authoritative external identifier. The
//! serialized record layout is the stored RCH layout and must not change
//! without an explicit migration.

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use uuid::Uuid;

use crate::symbols;
use crate::time::iso8601_from_unix_ms;

/// A persisted point marker.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MarkerRecord {
    pub local_id: String,
    pub object_destination_hash: String,
    pub origin_rch: String,
    pub marker_type: String,
    pub symbol: String,
    pub name: String,
    pub category: String,
    pub lat: f64,
    pub lon: f64,
    pub notes: Option<String>,
    pub created_ts_ms: i64,
    pub updated_ts_ms: i64,
}

/// Validation failures. Display strings are part of the RCH API contract.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum MarkerError {
    #[error("{0} is required")]
    Missing(&'static str),
    #[error("Unsupported marker type")]
    UnsupportedType,
    #[error("Unsupported marker symbol")]
    UnsupportedSymbol,
    #[error("lat must be between -90 and 90")]
    Latitude,
    #[error("lon must be between -180 and 180")]
    Longitude,
}

/// A validated WGS 84 position.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Position {
    lat: f64,
    lon: f64,
}

impl Position {
    /// Rejects non-finite or out-of-range coordinates.
    ///
    /// # Errors
    /// [`MarkerError::Latitude`] or [`MarkerError::Longitude`].
    pub fn new(lat: f64, lon: f64) -> Result<Self, MarkerError> {
        if !(-90.0..=90.0).contains(&lat) {
            return Err(MarkerError::Latitude);
        }
        if !(-180.0..=180.0).contains(&lon) {
            return Err(MarkerError::Longitude);
        }
        Ok(Self { lat, lon })
    }

    #[must_use]
    pub fn lat(self) -> f64 {
        self.lat
    }

    #[must_use]
    pub fn lon(self) -> f64 {
        self.lon
    }
}

/// Validated creation fields; identifiers and timestamps are minted by
/// [`MarkerRecord::create`].
#[derive(Debug, Clone, PartialEq)]
pub struct MarkerDraft {
    pub marker_type: String,
    pub symbol: String,
    pub name: String,
    pub category: String,
    pub position: Position,
    pub notes: Option<String>,
    pub origin_rch: String,
}

/// Normalizes a required marker type to a supported catalog symbol.
///
/// # Errors
/// [`MarkerError::Missing`] when nothing usable remains, otherwise
/// [`MarkerError::UnsupportedType`] for keys outside the catalog.
pub fn marker_type(raw: &str) -> Result<String, MarkerError> {
    let value = symbols::normalize(raw).ok_or(MarkerError::Missing("marker_type"))?;
    supported_type(value)
}

/// Normalizes a required symbol to a supported catalog symbol.
///
/// # Errors
/// [`MarkerError::Missing`] when nothing usable remains, otherwise
/// [`MarkerError::UnsupportedSymbol`].
pub fn marker_symbol(raw: &str) -> Result<String, MarkerError> {
    let value = symbols::normalize(raw).ok_or(MarkerError::Missing("symbol"))?;
    supported_symbol(value)
}

/// Accepts an already normalized type key only when it is in the catalog.
///
/// # Errors
/// [`MarkerError::UnsupportedType`].
pub fn supported_type(value: String) -> Result<String, MarkerError> {
    if symbols::is_supported(&value) {
        Ok(value)
    } else {
        Err(MarkerError::UnsupportedType)
    }
}

/// Accepts an already normalized symbol key only when it is in the catalog.
///
/// # Errors
/// [`MarkerError::UnsupportedSymbol`].
pub fn supported_symbol(value: String) -> Result<String, MarkerError> {
    if symbols::is_supported(&value) {
        Ok(value)
    } else {
        Err(MarkerError::UnsupportedSymbol)
    }
}

/// Trims a marker name; `None` when it is blank.
#[must_use]
pub fn normalize_name(raw: &str) -> Option<String> {
    let name = raw.trim();
    (!name.is_empty()).then(|| name.to_string())
}

impl MarkerRecord {
    /// Creates a marker with a fresh `object_destination_hash`.
    #[must_use]
    pub fn create(draft: MarkerDraft, local_id: String, now_ms: i64) -> Self {
        Self {
            local_id,
            object_destination_hash: Uuid::new_v4().simple().to_string(),
            origin_rch: draft.origin_rch,
            marker_type: draft.marker_type,
            symbol: draft.symbol,
            name: draft.name,
            category: draft.category,
            lat: draft.position.lat,
            lon: draft.position.lon,
            notes: draft.notes,
            created_ts_ms: now_ms,
            updated_ts_ms: now_ms,
        }
    }

    /// Moves the marker.
    pub fn move_to(&mut self, position: Position, now_ms: i64) {
        self.lat = position.lat;
        self.lon = position.lon;
        self.updated_ts_ms = now_ms;
    }

    /// Renames the marker with an already validated name.
    pub fn rename(&mut self, name: String, now_ms: i64) {
        self.name = name;
        self.updated_ts_ms = now_ms;
    }

    /// The RCH marker API representation (`/api/markers`, mission events).
    #[must_use]
    pub fn api_value(&self) -> Value {
        let updated_at = iso8601_from_unix_ms(self.updated_ts_ms);
        json!({
            "object_destination_hash": self.object_destination_hash,
            "origin_rch": self.origin_rch,
            "type": self.marker_type,
            "name": self.name,
            "category": self.category,
            "symbol": self.symbol,
            "notes": self.notes,
            "position": { "lat": self.lat, "lon": self.lon },
            "time": updated_at,
            "stale_at": updated_at,
            "created_at": iso8601_from_unix_ms(self.created_ts_ms),
            "updated_at": updated_at,
        })
    }
}
