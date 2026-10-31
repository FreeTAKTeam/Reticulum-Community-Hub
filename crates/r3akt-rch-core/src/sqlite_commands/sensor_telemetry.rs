//! Authenticated R3S origins under the durable broker transaction.
use super::super::{Connection, MissionCommandEnvelope, Value};
use super::{RchCommandTransaction, RchCoreError, RchSqliteStore, params};
use r3akt_map_core::{sensor_store as sensors, sensor_wire::SensorEvent};
use rusqlite::OptionalExtension;
fn sensor_error(error: sensors::StoreError) -> RchCoreError {
    match error {
        sensors::StoreError::Invalid(reason) => RchCoreError::InvalidPayload(reason.into()),
        error => RchCoreError::Decode(error.to_string()),
    }
}
pub(crate) fn initialize(connection: &Connection) -> Result<(), RchCoreError> {
    sensors::ensure_schema(connection).map_err(sensor_error)?;
    connection.execute_batch("CREATE TABLE IF NOT EXISTS r3s_marker_writers(origin_id TEXT PRIMARY KEY,writer_id TEXT NOT NULL); CREATE TABLE IF NOT EXISTS r3s_relay_metadata(origin_id TEXT NOT NULL,destination TEXT NOT NULL,hash TEXT NOT NULL,PRIMARY KEY(origin_id,destination));")?;
    Ok(())
}
impl RchSqliteStore {
    pub fn sensor_origins(&self) -> Result<Vec<sensors::SensorOrigin>, RchCoreError> {
        sensors::list(&self.connection).map_err(sensor_error)
    }
}
impl RchCommandTransaction<'_> {
    pub fn sensor_origins(&self) -> Result<Vec<sensors::SensorOrigin>, RchCoreError> {
        sensors::list_including_deleted(&self.transaction).map_err(sensor_error)
    }
    pub fn sensor_writer_authorized(
        &mut self,
        source: &str,
        id: &str,
        team: Option<&str>,
    ) -> Result<bool, RchCoreError> {
        let command:MissionCommandEnvelope=serde_json::from_value(serde_json::json!({"command_id":"r3s-policy","source":{"rns_identity":source},"timestamp":"","command_type":"mission.marker.create","args":{"object_destination_hash":id,"team_uid":team}})).map_err(|e|RchCoreError::Decode(e.to_string()))?;
        self.prepare_command(&command)?;
        Ok(self
            .core
            .authorize_command_operation(&command, "mission.content.write"))
    }
    pub fn sensor_marker_write_allowed(
        &self,
        id: &str,
        source: &str,
    ) -> Result<bool, RchCoreError> {
        Ok(sensors::get(&self.transaction, id)
            .map_err(sensor_error)?
            .is_none_or(|o| o.writer_id == source && o.deleted_at_ms.is_none()))
    }
    pub fn stage_operator_sensor_manifest(
        &self,
        writer: &str,
        id: &str,
        manifest: &r3akt_map_core::sensor::SensorManifest,
        source_time: u64,
        now: u64,
    ) -> Result<(), RchCoreError> {
        sensors::upsert_manifest(&self.transaction, id, writer, manifest, source_time, now)
            .map_err(sensor_error)?;
        Ok(())
    }
    pub fn stage_operator_sensor(
        &mut self,
        writer: &str,
        id: &str,
        position: &r3akt_map_core::sensor::OriginPosition,
        sensor: &r3akt_map_core::sensor::SensorState,
        stale_at_ms: Option<u64>,
        now: u64,
    ) -> Result<(), RchCoreError> {
        let marker = self.sensor_parent_marker(id)?.ok_or_else(|| {
            RchCoreError::InvalidPayload("CoT sensor requires its canonical marker".into())
        })?;
        let existing: Option<String> = self
            .transaction
            .query_row(
                "SELECT writer_id FROM r3s_marker_writers WHERE origin_id=?1",
                [id],
                |r| r.get(0),
            )
            .optional()?;
        if existing.as_deref().is_some_and(|w| w != writer) {
            return Err(RchCoreError::InvalidPayload(
                "origin belongs to another writer".into(),
            ));
        }
        self.record_sensor_marker_writer(id, writer)?;
        sensors::bind_origin(
            &self.transaction,
            id,
            writer,
            if matches!(
                marker.category.as_str(),
                "uav" | "camera" | "fixed" | "vehicle"
            ) {
                &marker.category
            } else {
                "mobile"
            },
            &marker.name,
        )
        .map_err(sensor_error)?;
        sensors::upsert_position(&self.transaction, id, writer, position, now)
            .map_err(sensor_error)?;
        sensors::upsert_sensors(
            &self.transaction,
            id,
            writer,
            std::slice::from_ref(sensor),
            now,
        )
        .map_err(sensor_error)?;
        if let Some(expires_at_ms) = stale_at_ms {
            r3akt_map_core::sensor_expiry::store(
                &self.transaction,
                writer,
                &r3akt_map_core::sensor_expiry::SensorExpiry {
                    origin_id: id.into(),
                    sensor_id: sensor.sensor_id.clone(),
                    sample_at_ms: sensor.sample_at_ms,
                    expires_at_ms,
                },
            )
            .map_err(sensor_error)?;
        }
        let accepted = sensors::get(&self.transaction, id)
            .map_err(sensor_error)?
            .ok_or_else(|| RchCoreError::InvalidPayload("missing accepted origin".into()))?;
        let position = accepted
            .position
            .as_ref()
            .ok_or_else(|| RchCoreError::InvalidPayload("missing accepted fix".into()))?;
        let packed = r3akt_map_core::sensor_wire::encode_packed(
            sensor.sample_at_ms.max(position.fix_at_ms) / 1000,
            Some(position),
            std::slice::from_ref(sensor),
        )
        .map_err(|e| RchCoreError::InvalidPayload(e.into()))?;
        sensors::retain_packed(
            &self.transaction,
            id,
            writer,
            &packed,
            sensor.sample_at_ms,
            now,
        )
        .map_err(sensor_error)?;
        if !self
            .before
            .markers
            .iter()
            .any(|m| m.object_destination_hash == id)
        {
            self.before.markers.push(marker.clone());
        }
        let mut moved = marker;
        moved.move_to(
            r3akt_map_core::Position::new(position.lat, position.lon)?,
            i64::try_from(position.fix_at_ms)
                .map_err(|e| RchCoreError::InvalidPayload(e.to_string()))?,
        );
        self.core.markers.insert(id.into(), moved);
        Ok(())
    }
    pub fn sensor_parent_marker(
        &self,
        id: &str,
    ) -> Result<Option<r3akt_map_core::MarkerRecord>, RchCoreError> {
        self.core.markers.get(id).cloned().map_or_else(
            || {
                r3akt_map_core::sqlite::get(&self.transaction, id)
                    .map_err(|e| RchCoreError::Decode(e.to_string()))
            },
            |m| Ok(Some(m)),
        )
    }
    pub fn record_sensor_marker_writer(&self, id: &str, writer: &str) -> Result<(), RchCoreError> {
        self.transaction.execute(
            "INSERT OR IGNORE INTO r3s_marker_writers VALUES (?1,?2)",
            params![id, writer],
        )?;
        Ok(())
    }
    pub fn stage_sensor_frame(
        &mut self,
        source: &str,
        fields: &Value,
        now: u64,
    ) -> Result<Vec<String>, RchCoreError> {
        let frame = r3akt_map_core::sensor_frame::decode_json(fields, source)
            .map_err(|e| RchCoreError::InvalidPayload(e.into()))?;

        // Only a fresh authenticated creation can establish an independent writer.
        let events = fields
            .get("13")
            .map(|v| v.as_array().map_or_else(|| vec![v], |a| a.iter().collect()))
            .unwrap_or_default();
        for event in events {
            if event["event_type"] != "mission.marker.created" {
                continue;
            }
            let payload = &event["payload"];
            let id = r3akt_map_core::replica::replica_id(payload)?;
            if !self.sensor_writer_authorized(
                source,
                &id,
                fields.get("11").and_then(Value::as_str),
            )? {
                continue;
            }
            if sensors::get(&self.transaction, &id)
                .map_err(sensor_error)?
                .is_some_and(|o| o.deleted_at_ms.is_some())
            {
                continue;
            }
            let existing = r3akt_map_core::sqlite::get(&self.transaction, &id)
                .map_err(|e| RchCoreError::Decode(e.to_string()))?;
            if existing.is_none() {
                let marker = r3akt_map_core::replica::from_api_value(
                    payload,
                    uuid::Uuid::new_v4().simple().to_string(),
                )?;
                self.core.markers.insert(id.clone(), marker);
                self.record_sensor_marker_writer(&id, source)?;
            }
        }
        let mut authorized = std::collections::BTreeSet::new();
        for id in frame
            .events
            .iter()
            .map(SensorEvent::origin_id)
            .chain(frame.samples.iter().map(|s| s.origin_id.as_str()))
            .chain(frame.expiries.iter().map(|s| s.origin_id.as_str()))
        {
            if authorized.contains(id)
                || !self.sensor_writer_authorized(
                    source,
                    id,
                    fields.get("11").and_then(Value::as_str),
                )?
            {
                continue;
            }
            let (kind, label) = if id == source {
                ("device".to_string(), source.to_string())
            } else {
                let writer: Option<String> = self
                    .transaction
                    .query_row(
                        "SELECT writer_id FROM r3s_marker_writers WHERE origin_id=?1",
                        [id],
                        |r| r.get(0),
                    )
                    .optional()?;
                if writer.as_deref() != Some(source) {
                    continue;
                }
                let marker = self
                    .core
                    .markers
                    .get(id)
                    .cloned()
                    .or(r3akt_map_core::sqlite::get(&self.transaction, id)
                        .map_err(|e| RchCoreError::Decode(e.to_string()))?);
                let Some(marker) = marker else {
                    continue;
                };
                let kind = if matches!(
                    marker.category.as_str(),
                    "camera" | "fixed" | "uav" | "vehicle"
                ) {
                    marker.category
                } else {
                    "mobile".into()
                };
                (kind, marker.name)
            };
            sensors::bind_origin(&self.transaction, id, source, &kind, &label)
                .map_err(sensor_error)?;
            authorized.insert(id.to_string());
        }
        let mut changed = std::collections::BTreeSet::new();
        for event in &frame.events {
            let id = event.origin_id();
            if !authorized.contains(id) {
                continue;
            }
            let updated = match event {
                SensorEvent::OriginFix(e) => {
                    let updated =
                        sensors::upsert_position(&self.transaction, id, source, &e.position, now)
                            .map_err(sensor_error)?;
                    if updated {
                        if !self.core.markers.contains_key(id)
                            && let Some(marker) = r3akt_map_core::sqlite::get(&self.transaction, id)
                                .map_err(|e| RchCoreError::Decode(e.to_string()))?
                        {
                            self.before.markers.push(marker.clone());
                            self.core.markers.insert(id.into(), marker);
                        }
                        if let Some(marker) = self.core.markers.get_mut(id) {
                            marker.move_to(
                                r3akt_map_core::Position::new(e.position.lat, e.position.lon)?,
                                i64::try_from(e.position.fix_at_ms).map_err(|_| {
                                    RchCoreError::InvalidPayload("fix time overflow".into())
                                })?,
                            );
                        }
                    }
                    updated
                }
                SensorEvent::Manifest(e) => sensors::upsert_manifest(
                    &self.transaction,
                    id,
                    source,
                    &e.manifest,
                    e.updated_at_ms,
                    now,
                )
                .map_err(sensor_error)?,
                SensorEvent::SensorRemoved(e) => sensors::remove_sensor(
                    &self.transaction,
                    id,
                    source,
                    &e.sensor_id,
                    e.deleted_at_ms,
                    now,
                )
                .map_err(sensor_error)?,
                SensorEvent::OriginRemoved(e) => {
                    let changed =
                        sensors::remove_origin(&self.transaction, id, source, e.deleted_at_ms, now)
                            .map_err(sensor_error)?;
                    if changed {
                        if !self
                            .before
                            .markers
                            .iter()
                            .any(|m| m.object_destination_hash == id)
                            && let Some(marker) = r3akt_map_core::sqlite::get(&self.transaction, id)
                                .map_err(|e| RchCoreError::Decode(e.to_string()))?
                        {
                            self.before.markers.push(marker);
                        }
                        self.core.markers.remove(id);
                    }
                    changed
                }
            };
            if updated {
                changed.insert(id.to_string());
            }
        }
        for sample in &frame.samples {
            if !authorized.contains(&sample.origin_id) || sample.sensors.is_empty() {
                continue;
            }
            if sensors::upsert_sensors(
                &self.transaction,
                &sample.origin_id,
                source,
                &sample.sensors,
                now,
            )
            .map_err(sensor_error)?
            {
                changed.insert(sample.origin_id.clone());
            }
            let time = sample
                .sensors
                .iter()
                .map(|s| s.sample_at_ms)
                .max()
                .ok_or_else(|| RchCoreError::InvalidPayload("missing sensor time".into()))?;
            sensors::retain_packed(
                &self.transaction,
                &sample.origin_id,
                source,
                &sample.packed_telemeter,
                time,
                now,
            )
            .map_err(sensor_error)?;
        }
        for expiry in &frame.expiries {
            if authorized.contains(&expiry.origin_id)
                && r3akt_map_core::sensor_expiry::store(&self.transaction, source, expiry)
                    .map_err(sensor_error)?
            {
                changed.insert(expiry.origin_id.clone());
            }
        }
        Ok(changed.into_iter().collect())
    }
}
