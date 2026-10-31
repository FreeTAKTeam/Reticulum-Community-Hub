//! Canonical marker lifecycle hooks shared by every SQLite writer.
use crate::{
    MarkerRecord,
    sensor::{AltitudeDatum, OriginPosition},
    sensor_store as sensors,
    sqlite::StoreError,
};
use rusqlite::Connection;
fn exists(connection: &Connection) -> Result<bool, StoreError> {
    Ok(connection.query_row("SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type='table' AND name='r3s_sensor_origins')",[],|r|r.get(0))?)
}
fn error(error: sensors::StoreError) -> StoreError {
    StoreError::Decode(match error {
        sensors::StoreError::Invalid(reason) => reason.into(),
        sensors::StoreError::Json(error) => error.to_string(),
        sensors::StoreError::Sqlite(error) => error.to_string(),
    })
}
/// # Errors
/// Rejects reuse of a deleted sensor-origin identity and malformed persisted state.
pub fn available(connection: &Connection, id: &str) -> Result<(), StoreError> {
    if exists(connection)?
        && sensors::get(connection, id)
            .map_err(error)?
            .is_some_and(|o| o.deleted_at_ms.is_some())
    {
        return Err(StoreError::Decode(
            "deleted sensor origin identity cannot be reused".into(),
        ));
    }
    Ok(())
}
/// # Errors
/// Propagates failed canonical position updates.
pub fn updated(connection: &Connection, marker: &MarkerRecord) -> Result<(), StoreError> {
    available(connection, &marker.object_destination_hash)?;
    if !exists(connection)? {
        return Ok(());
    }
    let Some(origin) = sensors::get(connection, &marker.object_destination_hash).map_err(error)?
    else {
        return Ok(());
    };
    sensors::mutate(connection, &origin.origin_id, &origin.writer_id, |saved| {
        let kind = match marker.category.as_str() {
            "uav" | "camera" | "fixed" | "vehicle" => marker.category.as_str(),
            _ => "mobile",
        };
        let changed = saved.label != marker.name || saved.origin_kind != kind;
        saved.label.clone_from(&marker.name);
        saved.origin_kind = kind.into();
        Ok(changed)
    })
    .map_err(error)?;
    if origin.position.as_ref().is_some_and(|p| {
        p.lat.to_bits() == marker.lat.to_bits() && p.lon.to_bits() == marker.lon.to_bits()
    }) {
        return Ok(());
    }
    let time =
        u64::try_from(marker.updated_ts_ms).map_err(|e| StoreError::Decode(e.to_string()))?;
    let position = OriginPosition {
        lat: marker.lat,
        lon: marker.lon,
        alt_m: None,
        altitude_datum: AltitudeDatum::Unknown,
        fix_at_ms: time,
        speed_mps: None,
        course_deg: None,
        accuracy_m: None,
    };
    let now = u64::try_from(chrono::Utc::now().timestamp_millis())
        .map_err(|e| StoreError::Decode(e.to_string()))?;
    sensors::upsert_position(
        connection,
        &origin.origin_id,
        &origin.writer_id,
        &position,
        now,
    )
    .map_err(error)?;
    Ok(())
}
/// # Errors
/// Propagates deletion/tombstone storage errors.
pub fn deleted(connection: &Connection, id: &str) -> Result<(), StoreError> {
    if !exists(connection)? {
        return Ok(());
    }
    if let Some(origin) = sensors::get(connection, id)
        .map_err(error)?
        .filter(|o| o.deleted_at_ms.is_none())
    {
        let now = u64::try_from(chrono::Utc::now().timestamp_millis())
            .map_err(|e| StoreError::Decode(e.to_string()))?;
        sensors::remove_origin(
            connection,
            id,
            &origin.writer_id,
            now.max(origin.latest_source_time().saturating_add(1)),
            now,
        )
        .map_err(error)?;
    }
    Ok(())
}
