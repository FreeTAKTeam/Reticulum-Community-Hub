//! Marker mission commands. Marker rules (validation, identifiers, replay)
//! live in `r3akt-map-core`; this adapter maps command args onto them.

use serde_json::{Value, json};
use uuid::Uuid;

use super::{
    EventEnvelope, MarkerRecord, MissionCommandEnvelope, RchCore, RchCoreError, normalize_hash,
    optional_text, required_f64, required_text, utc_now_ms,
};

impl RchCore {
    pub(super) fn apply_marker_command(
        &mut self,
        command: &MissionCommandEnvelope,
    ) -> Result<Option<EventEnvelope>, RchCoreError> {
        match command.command_type.as_str() {
            "mission.marker.list" => Ok(Some(Self::event(
                "mission.marker.listed",
                command,
                json!({ "markers": self.marker_values() }),
            ))),
            "mission.marker.create" => {
                let marker = self.create_marker_from_args(command, &command.args)?;
                Ok(Some(Self::event(
                    "mission.marker.created",
                    command,
                    Self::marker_value(&marker),
                )))
            }
            "mission.marker.position.patch" => {
                let marker = self.patch_marker_position_from_args(&command.args)?;
                Ok(Some(Self::event(
                    "mission.marker.position.updated",
                    command,
                    Self::marker_value(&marker),
                )))
            }
            "mission.marker.patch" => {
                let marker = self.patch_marker_from_args(&command.args)?;
                Ok(Some(Self::event(
                    "mission.marker.updated",
                    command,
                    Self::marker_value(&marker),
                )))
            }
            "mission.marker.delete" => {
                let marker = self.delete_marker_from_args(&command.args)?;
                Ok(Some(Self::event(
                    "mission.marker.deleted",
                    command,
                    Self::marker_value(&marker),
                )))
            }
            other => Err(RchCoreError::UnsupportedCommand(other.to_string())),
        }
    }

    fn create_marker_from_args(
        &mut self,
        command: &MissionCommandEnvelope,
        args: &Value,
    ) -> Result<MarkerRecord, RchCoreError> {
        use r3akt_map_core::{marker, symbols};
        let position =
            r3akt_map_core::Position::new(required_f64(args, "lat")?, required_f64(args, "lon")?)?;
        // Mission commands default absent or unusable type/symbol to `marker`
        // and normalize the category, unlike the HTTP route.
        let normalized_or_marker = |keys: &[&str]| {
            symbols::normalize(&optional_text(args, keys).unwrap_or_else(|| "marker".to_string()))
                .unwrap_or_else(|| "marker".to_string())
        };
        let marker_type = marker::supported_type(normalized_or_marker(&["marker_type", "type"]))?;
        let symbol = marker::supported_symbol(normalized_or_marker(&["symbol"]))?;
        let category = symbols::normalize(
            &optional_text(args, &["category"]).unwrap_or_else(|| "marker".to_string()),
        )
        .unwrap_or_else(|| symbol.clone());
        let draft = r3akt_map_core::MarkerDraft {
            marker_type,
            symbol,
            name: optional_text(args, &["name"]).unwrap_or_else(|| "Marker".to_string()),
            category,
            position,
            notes: optional_text(args, &["notes"]),
            origin_rch: normalize_hash(Some(&command.source.rns_identity)).unwrap_or_default(),
        };
        let local_id = Uuid::new_v4().simple().to_string();
        // A client-supplied identifier keeps one canonical ID across REM and
        // RCH replicas; repeating the same create is a replay, not a duplicate.
        let Some(raw_id) = optional_text(args, &["object_destination_hash"]) else {
            let marker = MarkerRecord::create(draft, local_id, utc_now_ms());
            self.markers
                .insert(marker.object_destination_hash.clone(), marker.clone());
            return Ok(marker);
        };
        let id = marker::object_destination_hash(&raw_id)?;
        let marker = MarkerRecord::create_with_id(draft, id.clone(), local_id, utc_now_ms());
        if let Some(existing) = self.markers.get(&id) {
            return if r3akt_map_core::idempotency::same_creation(existing, &marker) {
                Ok(existing.clone())
            } else {
                Err(RchCoreError::InvalidPayload(
                    "object_destination_hash already identifies a different marker".to_string(),
                ))
            };
        }
        self.markers.insert(id, marker.clone());
        Ok(marker)
    }

    fn patch_marker_position_from_args(
        &mut self,
        args: &Value,
    ) -> Result<MarkerRecord, RchCoreError> {
        let marker_hash = required_text(args, &["object_destination_hash"])?;
        let marker_hash = normalize_hash(Some(&marker_hash)).ok_or_else(|| {
            RchCoreError::InvalidPayload("object_destination_hash is required".to_string())
        })?;
        let position =
            r3akt_map_core::Position::new(required_f64(args, "lat")?, required_f64(args, "lon")?)?;
        let marker = self
            .markers
            .get_mut(&marker_hash)
            .ok_or(RchCoreError::TopicNotFound)?;
        marker.move_to(position, utc_now_ms());
        Ok(marker.clone())
    }

    fn patch_marker_from_args(&mut self, args: &Value) -> Result<MarkerRecord, RchCoreError> {
        let marker_hash = required_text(args, &["object_destination_hash"])?;
        let marker_hash = normalize_hash(Some(&marker_hash)).ok_or_else(|| {
            RchCoreError::InvalidPayload("object_destination_hash is required".to_string())
        })?;
        let name =
            match optional_text(args, &["name"]) {
                Some(name) => Some(r3akt_map_core::marker::normalize_name(&name).ok_or_else(
                    || RchCoreError::InvalidPayload("Marker name is required".to_string()),
                )?),
                None => None,
            };
        let marker = self
            .markers
            .get_mut(&marker_hash)
            .ok_or(RchCoreError::TopicNotFound)?;
        let now = utc_now_ms();
        match name {
            Some(name) => marker.rename(name, now),
            None => marker.updated_ts_ms = now,
        }
        Ok(marker.clone())
    }

    fn delete_marker_from_args(&mut self, args: &Value) -> Result<MarkerRecord, RchCoreError> {
        let marker_hash = required_text(args, &["object_destination_hash"])?;
        let marker_hash = normalize_hash(Some(&marker_hash)).ok_or_else(|| {
            RchCoreError::InvalidPayload("object_destination_hash is required".to_string())
        })?;
        self.markers
            .remove(&marker_hash)
            .ok_or(RchCoreError::TopicNotFound)
    }
}

#[cfg(test)]
mod tests {
    use r3akt_profile_rch::RchSource;
    use serde_json::{Value, json};

    use super::super::MissionSyncResponse;
    use super::{MissionCommandEnvelope, RchCore};

    const CLIENT_ID: &str = "0123456789abcdef0123456789abcdef";

    fn create(args: &Value) -> Vec<MissionSyncResponse> {
        let mut core = RchCore::new();
        core.handle_mission_sync_command(&marker_command(args))
    }

    fn marker_command(args: &Value) -> MissionCommandEnvelope {
        MissionCommandEnvelope {
            command_id: format!("cmd-marker-{args}"),
            source: RchSource {
                rns_identity: "ABCDEF".to_string(),
                display_name: None,
            },
            timestamp: "2026-10-13T12:00:00Z".to_string(),
            command_type: "mission.marker.create".to_string(),
            args: args.clone(),
            correlation_id: None,
            topics: Vec::new(),
        }
    }

    fn fire(id: &str, lat: f64) -> Value {
        json!({
            "object_destination_hash": id,
            "marker_type": "fire",
            "symbol": "fire",
            "category": "incident",
            "name": "Ridge",
            "lat": lat,
            "lon": -1.25,
        })
    }

    fn result(responses: &[MissionSyncResponse]) -> Value {
        responses
            .last()
            .and_then(MissionSyncResponse::results_field)
            .cloned()
            .expect("result")
    }

    #[test]
    fn client_supplied_identifier_is_kept_and_replay_is_idempotent() {
        let mut core = RchCore::new();
        let first = core.handle_mission_sync_command(&marker_command(&fire(
            &CLIENT_ID.to_ascii_uppercase(),
            44.5,
        )));
        assert_eq!(
            result(&first)["result"]["object_destination_hash"],
            CLIENT_ID
        );
        assert_eq!(result(&first)["result"]["symbol"], "fire");

        let mut replay = marker_command(&fire(CLIENT_ID, 44.5));
        replay.command_id = "cmd-marker-replay".to_string();
        let replayed = core.handle_mission_sync_command(&replay);
        assert_eq!(
            result(&replayed)["result"]["object_destination_hash"],
            CLIENT_ID
        );
        assert_eq!(core.markers.len(), 1);

        let mut conflict = marker_command(&fire(CLIENT_ID, 10.0));
        conflict.command_id = "cmd-marker-conflict".to_string();
        let rejected = result(&core.handle_mission_sync_command(&conflict));
        assert_eq!(rejected["status"], "rejected");
        assert_eq!(
            rejected["reason"],
            "invalid command payload: object_destination_hash already identifies a different marker"
        );
        assert!((core.markers[CLIENT_ID].lat - 44.5).abs() < f64::EPSILON);
    }

    #[test]
    fn invalid_client_identifier_is_rejected_and_absent_one_is_minted() {
        let rejected = result(&create(&fire("not-a-hash", 1.0)));
        assert_eq!(rejected["status"], "rejected");
        assert_eq!(
            rejected["reason"],
            "invalid command payload: object_destination_hash must be 32 hexadecimal characters"
        );

        let mut args = fire(CLIENT_ID, 1.0);
        args.as_object_mut()
            .expect("object")
            .remove("object_destination_hash");
        let minted = result(&create(&args))["result"]["object_destination_hash"]
            .as_str()
            .expect("minted id")
            .to_string();
        assert_ne!(minted, CLIENT_ID);
        assert!(r3akt_map_core::marker::object_destination_hash(&minted).is_ok());
    }
}
