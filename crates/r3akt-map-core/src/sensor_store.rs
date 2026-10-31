//! Shared bounded sensor persistence; callers establish authenticated writer authority.

use crate::sensor::{self, OriginPosition, SensorManifest, SensorState};
use rusqlite::{Connection, OptionalExtension, Transaction, TransactionBehavior, params};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

pub const MAX_ORIGINS: i64 = 4096;
const MAX_TOMBSTONES: usize = 128;

#[derive(Debug, thiserror::Error)]
pub enum StoreError {
    #[error(transparent)]
    Sqlite(#[from] rusqlite::Error),
    #[error(transparent)]
    Json(#[from] serde_json::Error),
    #[error("{0}")]
    Invalid(&'static str),
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SensorOrigin {
    pub origin_id: String,
    pub writer_id: String,
    pub origin_kind: String,
    pub label: String,
    pub position: Option<OriginPosition>,
    pub sensors: BTreeMap<String, SensorState>,
    #[serde(default)]
    pub sensor_expiry_ms: BTreeMap<String, u64>,
    pub manifests: BTreeMap<String, SensorManifest>,
    pub manifest_times: BTreeMap<String, u64>,
    pub sensor_tombstones: BTreeMap<String, u64>,
    pub deleted_at_ms: Option<u64>,
    #[serde(default)]
    pub packed_telemeter: Option<Vec<u8>>,
    #[serde(default)]
    pub packed_at_ms: u64,
}

impl SensorOrigin {
    #[must_use]
    pub fn latest_source_time(&self) -> u64 {
        self.sensors
            .values()
            .map(|s| s.sample_at_ms)
            .chain(self.position.iter().map(|p| p.fix_at_ms))
            .chain(self.manifest_times.values().copied())
            .chain(self.sensor_tombstones.values().copied())
            .max()
            .unwrap_or(0)
    }
    /// # Errors
    /// Returns a diagnostic if stored sensor geometry is invalid.
    pub fn projection(&self, now_ms: u64, ttl_ms: u64) -> Result<serde_json::Value, StoreError> {
        let mut sensors = Vec::new();
        for state in self.sensors.values() {
            let geometry = crate::sensor_geometry::project(
                &self.origin_id,
                self.position.as_ref(),
                state,
                !matches!(self.origin_kind.as_str(), "fixed" | "camera"),
                now_ms,
                ttl_ms.min(
                    self.sensor_expiry_ms
                        .get(&state.sensor_id)
                        .map_or(u64::MAX, |expiry| expiry.saturating_sub(state.sample_at_ms)),
                ),
            )
            .map_err(StoreError::Invalid)?;
            sensors.push(serde_json::json!({"state":state,"manifest":self.manifests.get(&state.sensor_id),"display":geometry,"sourceExpiresAtMs":self.sensor_expiry_ms.get(&state.sensor_id)}));
        }
        Ok(
            serde_json::json!({"originId":self.origin_id,"writerId":self.writer_id,
            "originKind":self.origin_kind,"label":self.label,"position":self.position,"sensors":sensors}),
        )
    }
}

/// # Errors
/// Propagates SQLite schema errors.
pub fn ensure_schema(connection: &Connection) -> Result<(), StoreError> {
    connection.execute_batch(
        "CREATE TABLE IF NOT EXISTS r3s_sensor_origins (
        origin_id TEXT PRIMARY KEY, writer_id TEXT NOT NULL, json TEXT NOT NULL);",
    )?;
    Ok(())
}

/// # Errors
/// Propagates SQLite and stored-record decoding errors.
pub fn get(connection: &Connection, id: &str) -> Result<Option<SensorOrigin>, StoreError> {
    let raw: Option<String> = connection
        .query_row(
            "SELECT json FROM r3s_sensor_origins WHERE origin_id=?1",
            [id],
            |row| row.get(0),
        )
        .optional()?;
    raw.map(|raw| serde_json::from_str(&raw).map_err(StoreError::from))
        .transpose()
}

/// # Errors
/// Propagates SQLite and stored-record decoding errors.
pub fn list(connection: &Connection) -> Result<Vec<SensorOrigin>, StoreError> {
    Ok(list_including_deleted(connection)?
        .into_iter()
        .filter(|o| o.deleted_at_ms.is_none())
        .collect())
}
/// Includes permanent origin tombstones for authenticated collector/control delivery.
/// # Errors
/// Propagates SQLite and stored-record decoding errors.
pub fn list_including_deleted(connection: &Connection) -> Result<Vec<SensorOrigin>, StoreError> {
    let mut statement =
        connection.prepare("SELECT json FROM r3s_sensor_origins ORDER BY origin_id LIMIT ?1")?;
    let rows = statement.query_map([MAX_ORIGINS], |row| row.get::<_, String>(0))?;
    let mut result = Vec::new();
    for row in rows {
        let record: SensorOrigin = serde_json::from_str(&row?)?;
        result.push(record);
    }
    Ok(result)
}

fn save(connection: &Connection, origin: &SensorOrigin) -> Result<(), StoreError> {
    connection.execute(
        "INSERT INTO r3s_sensor_origins(origin_id,writer_id,json) VALUES (?1,?2,?3)
        ON CONFLICT(origin_id) DO UPDATE SET json=excluded.json",
        params![
            origin.origin_id,
            origin.writer_id,
            serde_json::to_string(origin)?
        ],
    )?;
    Ok(())
}

/// Only call after local creation, authenticated remote creation or explicit mission authorization.
/// # Errors
/// Rejects invalid, conflicting, tombstoned or excessive origin bindings.
pub fn bind_origin(
    connection: &Connection,
    id: &str,
    writer: &str,
    kind: &str,
    label: &str,
) -> Result<(), StoreError> {
    if crate::marker::object_destination_hash(id).as_deref() != Ok(id)
        || crate::marker::object_destination_hash(writer).as_deref() != Ok(writer)
        || !matches!(
            kind,
            "device" | "uav" | "camera" | "fixed" | "mobile" | "vehicle"
        )
        || label.len() > 256
    {
        return Err(StoreError::Invalid("invalid origin binding"));
    }
    let transaction = if connection.is_autocommit() {
        Some(Transaction::new_unchecked(
            connection,
            TransactionBehavior::Immediate,
        )?)
    } else {
        None
    };
    let tx = transaction.as_deref().unwrap_or(connection);
    if let Some(existing) = get(tx, id)? {
        if existing.writer_id != writer || existing.deleted_at_ms.is_some() {
            return Err(StoreError::Invalid("origin writer binding denied"));
        }
    } else {
        let count: i64 =
            tx.query_row("SELECT count(*) FROM r3s_sensor_origins", [], |r| r.get(0))?;
        if count >= MAX_ORIGINS {
            return Err(StoreError::Invalid("sensor origin limit reached"));
        }
        save(
            tx,
            &SensorOrigin {
                origin_id: id.into(),
                writer_id: writer.into(),
                origin_kind: kind.into(),
                label: label.into(),
                position: None,
                sensors: BTreeMap::new(),
                sensor_expiry_ms: BTreeMap::new(),
                manifests: BTreeMap::new(),
                manifest_times: BTreeMap::new(),
                sensor_tombstones: BTreeMap::new(),
                deleted_at_ms: None,
                packed_telemeter: None,
                packed_at_ms: 0,
            },
        )?;
    }
    if let Some(transaction) = transaction {
        transaction.commit()?;
    }
    Ok(())
}

pub(super) fn mutate(
    connection: &Connection,
    id: &str,
    writer: &str,
    update: impl FnOnce(&mut SensorOrigin) -> Result<bool, StoreError>,
) -> Result<bool, StoreError> {
    let transaction = if connection.is_autocommit() {
        Some(Transaction::new_unchecked(
            connection,
            TransactionBehavior::Immediate,
        )?)
    } else {
        None
    };
    let tx = transaction.as_deref().unwrap_or(connection);
    let mut origin = get(tx, id)?.ok_or(StoreError::Invalid(
        "origin has no authenticated writer binding",
    ))?;
    if origin.writer_id != writer {
        return Err(StoreError::Invalid("origin writer binding denied"));
    }
    if origin.deleted_at_ms.is_some() {
        return Ok(false);
    }
    let changed = update(&mut origin)?;
    if changed {
        save(tx, &origin)?;
    }
    if let Some(transaction) = transaction {
        transaction.commit()?;
    }
    Ok(changed)
}

/// # Errors
/// Rejects unbound writers, invalid fixes and equal-time conflicts.
pub fn upsert_position(
    connection: &Connection,
    id: &str,
    writer: &str,
    position: &OriginPosition,
    now_ms: u64,
) -> Result<bool, StoreError> {
    position.validate().map_err(StoreError::Invalid)?;
    sensor::source_time(position.fix_at_ms, now_ms).map_err(StoreError::Invalid)?;
    mutate(connection, id, writer, |origin| {
        if let Some(old) = &origin.position {
            if old.fix_at_ms > position.fix_at_ms {
                return Ok(false);
            }
            if old.fix_at_ms == position.fix_at_ms {
                return if old == position {
                    Ok(false)
                } else {
                    Err(StoreError::Invalid("conflicting equal-time origin fix"))
                };
            }
        }
        origin.position = Some(position.clone());
        Ok(true)
    })
}

/// Snapshot omission never deletes another sensor.
/// # Errors
/// Rejects unbound writers, invalid samples, equal-time conflicts or capacity overflow.
pub fn upsert_sensors(
    connection: &Connection,
    id: &str,
    writer: &str,
    sensors: &[SensorState],
    now_ms: u64,
) -> Result<bool, StoreError> {
    crate::sensor_wire::encode_value(sensors).map_err(StoreError::Invalid)?;
    for state in sensors {
        sensor::source_time(state.sample_at_ms, now_ms).map_err(StoreError::Invalid)?;
    }
    mutate(connection, id, writer, |origin| {
        let mut changed = false;
        for state in sensors {
            if origin
                .sensor_tombstones
                .get(&state.sensor_id)
                .is_some_and(|t| *t >= state.sample_at_ms)
            {
                continue;
            }
            if let Some(old) = origin.sensors.get(&state.sensor_id) {
                if old.sample_at_ms > state.sample_at_ms {
                    continue;
                }
                if old.sample_at_ms == state.sample_at_ms {
                    if old != state {
                        return Err(StoreError::Invalid("conflicting equal-time sensor sample"));
                    }
                    continue;
                }
            }
            if !origin.sensors.contains_key(&state.sensor_id)
                && origin.sensors.len() >= sensor::MAX_SENSORS
            {
                return Err(StoreError::Invalid("sensor limit reached"));
            }
            origin.sensor_expiry_ms.remove(&state.sensor_id);
            origin
                .sensors
                .insert(state.sensor_id.clone(), state.clone());
            changed = true;
        }
        Ok(changed)
    })
}

/// # Errors
/// Rejects unbound writers, invalid metadata, equal-time conflicts or capacity overflow.
pub fn upsert_manifest(
    connection: &Connection,
    id: &str,
    writer: &str,
    manifest: &SensorManifest,
    updated_at_ms: u64,
    now_ms: u64,
) -> Result<bool, StoreError> {
    manifest.validate().map_err(StoreError::Invalid)?;
    sensor::source_time(updated_at_ms, now_ms).map_err(StoreError::Invalid)?;
    mutate(connection, id, writer, |origin| {
        if origin
            .sensor_tombstones
            .get(&manifest.sensor_id)
            .is_some_and(|t| *t >= updated_at_ms)
        {
            return Ok(false);
        }
        if let Some(old) = origin.manifest_times.get(&manifest.sensor_id) {
            if *old > updated_at_ms {
                return Ok(false);
            }
            if *old == updated_at_ms {
                return if origin.manifests.get(&manifest.sensor_id) == Some(manifest) {
                    Ok(false)
                } else {
                    Err(StoreError::Invalid(
                        "conflicting equal-time sensor manifest",
                    ))
                };
            }
        }
        if !origin.manifests.contains_key(&manifest.sensor_id)
            && origin.manifests.len() >= sensor::MAX_SENSORS
        {
            return Err(StoreError::Invalid("sensor manifest limit reached"));
        }
        origin
            .manifests
            .insert(manifest.sensor_id.clone(), manifest.clone());
        origin
            .manifest_times
            .insert(manifest.sensor_id.clone(), updated_at_ms);
        Ok(true)
    })
}

/// # Errors
/// Rejects unbound writers, invalid times or tombstone capacity overflow.
pub fn remove_sensor(
    connection: &Connection,
    id: &str,
    writer: &str,
    sensor_id: &str,
    deleted_at_ms: u64,
    now_ms: u64,
) -> Result<bool, StoreError> {
    sensor::sensor_id(sensor_id).map_err(StoreError::Invalid)?;
    sensor::source_time(deleted_at_ms, now_ms).map_err(StoreError::Invalid)?;
    mutate(connection, id, writer, |origin| {
        let latest = origin
            .sensors
            .get(sensor_id)
            .map_or(0, |s| s.sample_at_ms)
            .max(*origin.manifest_times.get(sensor_id).unwrap_or(&0))
            .max(*origin.sensor_tombstones.get(sensor_id).unwrap_or(&0));
        if latest >= deleted_at_ms {
            return Ok(false);
        }
        if !origin.sensor_tombstones.contains_key(sensor_id)
            && origin.sensor_tombstones.len() >= MAX_TOMBSTONES
        {
            return Err(StoreError::Invalid("sensor tombstone limit reached"));
        }
        origin.packed_telemeter = None;
        origin.sensor_expiry_ms.remove(sensor_id);
        origin.sensors.remove(sensor_id);
        origin.manifests.remove(sensor_id);
        origin.manifest_times.remove(sensor_id);
        origin
            .sensor_tombstones
            .insert(sensor_id.into(), deleted_at_ms);
        Ok(true)
    })
}

/// # Errors
/// Rejects unbound writers or invalid deletion timestamps.
pub fn remove_origin(
    connection: &Connection,
    id: &str,
    writer: &str,
    deleted_at_ms: u64,
    now_ms: u64,
) -> Result<bool, StoreError> {
    sensor::source_time(deleted_at_ms, now_ms).map_err(StoreError::Invalid)?;
    mutate(connection, id, writer, |origin| {
        if origin.latest_source_time() >= deleted_at_ms {
            return Ok(false);
        }
        origin.deleted_at_ms = Some(deleted_at_ms);
        origin.sensor_expiry_ms.clear();
        origin.sensors.clear();
        origin.manifests.clear();
        origin.position = None;
        origin.packed_telemeter = None;
        Ok(true)
    })
}

/// Retains the original checked sensor bytes for lossless collector forwarding.
/// # Errors
/// Rejects unbound writers, invalid times and malformed standard telemetry.
pub fn retain_packed(
    connection: &Connection,
    id: &str,
    writer: &str,
    packed: &[u8],
    sample_at_ms: u64,
    now_ms: u64,
) -> Result<bool, StoreError> {
    sensor::source_time(sample_at_ms, now_ms).map_err(StoreError::Invalid)?;
    crate::telemetry::decode_field(&serde_json::json!(packed)).map_err(StoreError::Invalid)?;
    let sensors = crate::sensor_wire::decode_packed(packed)
        .map_err(StoreError::Invalid)?
        .ok_or(StoreError::Invalid("missing sensor geometry"))?;
    mutate(connection, id, writer, |origin| {
        if sensors.iter().any(|s| {
            origin
                .sensor_tombstones
                .get(&s.sensor_id)
                .is_some_and(|time| *time >= s.sample_at_ms)
        }) {
            return Ok(false);
        }
        let snapshot_time = sample_at_ms.max(origin.position.as_ref().map_or(0, |p| p.fix_at_ms));
        if origin.packed_at_ms >= snapshot_time {
            return Ok(false);
        }
        if let Some(position) = &origin.position {
            crate::sensor_wire::validate_position_against_packed(position, packed)
                .map_err(StoreError::Invalid)?;
        }
        origin.packed_telemeter = Some(packed.to_vec());
        origin.packed_at_ms = snapshot_time;
        Ok(true)
    })
}
