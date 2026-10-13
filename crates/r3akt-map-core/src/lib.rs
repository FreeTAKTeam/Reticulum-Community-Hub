//! Shared R3AKT map objects and telemetry.
//!
//! This crate holds the canonical implementation of RCH point markers and the
//! Telemeter telemetry contract so that RCH (server) and REM (mobile) consume
//! one implementation instead of parallel copies. It deliberately excludes
//! HTTP routing, server state, UI, Android/JNI and BLE concerns; those stay in
//! each application's adapters.
//!
//! - [`marker`]: the marker record, validation, creation/update rules and the
//!   RCH marker API representation.
//! - [`symbols`]: the backend-owned symbol catalog, aliases and normalization.
//! - [`idempotency`]: idempotent marker creation keys and payload fingerprints.
//! - [`telemetry`]: checked decoding and normalization of LXMF `FIELD_TELEMETRY`
//!   Telemeter payloads (the verified RCH #258 receive contract).
//! - `sqlite` (feature `sqlite`): marker persistence compatible with the RCH
//!   database layout.
//!
//! Positions of users (telemetry) and independently identified map objects
//! (markers) are separate models and are never conflated.

pub mod bytes;
pub mod idempotency;
pub mod marker;
pub mod msgpack;
#[cfg(feature = "sqlite")]
pub mod sqlite;
pub mod symbols;
pub mod telemetry;
pub mod time;

pub use marker::{MarkerDraft, MarkerError, MarkerRecord, Position};
pub use symbols::{MarkerSymbol, SymbolSet};
