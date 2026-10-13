//! Southbound marker notifications for REM clients.
//!
//! Mission marker link changes go out as reduced REM commands. Marker
//! changes made through the RCH API go out as `mission.marker.*` events whose
//! payload is the shared marker API representation, the same `FIELD_EVENT`
//! shape RCH relays for team-scoped REM marker commands, so REM applies every
//! replica through `r3akt_map_core::replica`.

use r3akt_profile_rch::FIELD_EVENT;
use serde_json::{Value, json};

use super::{
    ApiError, AppState, MarkerRecord, OUTBOUND_RETRY_MAX_ATTEMPTS, REM_COMMAND_PLACEHOLDER_BODY,
    command_fanout_recipients_for_state, compact_rem_command_id, compact_rem_identifier_string,
    iso8601_from_unix_ms, record_outbound_message_with_metadata, rem_command_transport_fields,
    rem_marker_telemetry_command_fields, unix_now_ms,
};

fn not_attempted(reason: &str) -> Value {
    json!({
        "attempted": false,
        "reason": reason,
        "recipient_count": 0,
        "sent": 0,
        "failed": 0,
    })
}

fn rch_source_identity(state: &AppState) -> &str {
    state
        .reticulumd_source
        .as_ref()
        .map_or("r3akt-rch-server", |value| value.as_str())
}

/// Queues `fields` for every REM-capable recipient. `metadata` is extended
/// with the delivery policy and the fields themselves.
fn send_to_rem_recipients(
    state: &AppState,
    fields: &Value,
    mut metadata: Value,
    reliable: bool,
) -> Result<Value, ApiError> {
    let recipients = command_fanout_recipients_for_state(state)?;
    if recipients.is_empty() {
        return Ok(not_attempted("no_rem_or_generic_recipients"));
    }
    if let Some(object) = metadata.as_object_mut() {
        object.insert("delivery_receipt_required".into(), json!(reliable));
        let attempts = if reliable {
            OUTBOUND_RETRY_MAX_ATTEMPTS
        } else {
            1
        };
        object.insert("max_attempts".into(), json!(attempts));
        object.insert("lxmf_fields".into(), fields.clone());
    }
    let (mut sent, mut failed, mut skipped) = (0usize, 0usize, 0usize);
    let mut errors = Vec::new();
    for recipient in recipients {
        if !recipient.is_rem_capable {
            skipped += 1;
            continue;
        }
        match record_outbound_message_with_metadata(
            state,
            REM_COMMAND_PLACEHOLDER_BODY,
            None,
            Some(recipient.identity),
            Vec::new(),
            false,
            metadata.clone(),
        ) {
            Ok(_) => sent += 1,
            Err(error) => {
                failed += 1;
                errors.push(error.to_string());
            }
        }
    }
    Ok(json!({
        "attempted": true,
        "recipient_count": sent + failed,
        "sent": sent,
        "failed": failed,
        "skipped": skipped,
        "errors": errors,
    }))
}

pub(super) fn fanout_mission_marker_link_to_recipients(
    state: &AppState,
    event_type: &str,
    mission_uid: &str,
    marker_id: &str,
    _mission: &Value,
) -> Result<Value, ApiError> {
    let command_type = match event_type {
        "mission.registry.mission.marker.linked" => "mission.registry.mission.marker.link",
        "mission.registry.mission.marker.unlinked" => "mission.registry.mission.marker.unlink",
        _ => return Ok(not_attempted("mission_marker_event_not_deliverable")),
    };
    let fields = rem_mission_marker_link_command_fields(
        command_type,
        mission_uid,
        marker_id,
        rch_source_identity(state),
    );
    send_to_rem_recipients(
        state,
        &fields,
        json!({
            "fanout_kind": "mission_marker_link",
            "fanout_channel": "rem_marker_link_command",
            "source_event_type": event_type,
            "mission_uid": mission_uid,
            "marker_id": marker_id,
        }),
        true,
    )
}

pub(super) fn rem_mission_marker_link_command_fields(
    command_type: &str,
    mission_uid: &str,
    marker_id: &str,
    source_identity: &str,
) -> Value {
    let command_token = format!("{mission_uid}-{marker_id}");
    let args = json!({
        "mission_uid": compact_rem_identifier_string(mission_uid),
        "marker_id": compact_rem_identifier_string(marker_id),
    });
    let envelope = json!({
        "command_id": compact_rem_command_id(command_type, &command_token),
        "correlation_id": command_token,
        "command_type": command_type,
        "source": {
            "rns_identity": compact_rem_identifier_string(source_identity),
            "display_name": "RCH",
        },
        "timestamp": iso8601_from_unix_ms(unix_now_ms()),
        "topics": [],
        "args": args,
    });
    rem_command_transport_fields(envelope)
}

/// Maps RCH marker activity (`marker.created`, ...) to the replicated event.
fn mission_marker_event_type(activity: &str) -> Option<&'static str> {
    match activity {
        "marker.created" => Some("mission.marker.created"),
        "marker.updated" => Some("mission.marker.updated"),
        "marker.deleted" => Some("mission.marker.deleted"),
        _ => None,
    }
}

/// The `FIELD_EVENT` envelope REM receives for a marker replica.
pub(super) fn rem_marker_event_fields(
    event_type: &str,
    marker: &MarkerRecord,
    source_identity: &str,
) -> Value {
    json!({
        FIELD_EVENT.to_string(): {
            "event_type": event_type,
            "payload": marker.api_value(),
            "source": { "rns_identity": source_identity },
        }
    })
}

/// Fields for one marker activity, or `None` when it is not replicated.
fn marker_activity_fields(activity: &str, marker: &MarkerRecord, source: &str) -> Option<Value> {
    let event_type = mission_marker_event_type(activity)?;
    let mut fields = rem_marker_event_fields(event_type, marker, source);
    if activity != "marker.deleted" {
        if let (Some(fields), Value::Object(telemetry)) = (
            fields.as_object_mut(),
            rem_marker_telemetry_command_fields(activity, marker, source),
        ) {
            fields.extend(telemetry);
        }
    }
    Some(fields)
}

/// Sends a marker change made through the RCH API to REM clients.
///
/// Creates and updates keep the legacy marker-as-telemetry command for older
/// REM builds and add the replica event; deletes carry only the event. New
/// REM builds apply the event and ignore telemetry whose object type is
/// `marker`, so markers stay separate from user telemetry.
pub(super) fn fanout_marker_activity_to_recipients(
    state: &AppState,
    activity: &str,
    marker: &MarkerRecord,
) -> Result<Value, ApiError> {
    let Some(fields) = marker_activity_fields(activity, marker, rch_source_identity(state)) else {
        return Ok(not_attempted("marker_event_not_deliverable"));
    };
    send_to_rem_recipients(
        state,
        &fields,
        json!({
            "fanout_kind": "marker_activity",
            "fanout_channel": "rem_marker_command",
            "source_event_type": activity,
            "object_destination_hash": marker.object_destination_hash,
        }),
        true,
    )
}

#[cfg(test)]
mod tests {
    use r3akt_profile_rch::{FIELD_COMMANDS, FIELD_EVENT};

    use super::{MarkerRecord, marker_activity_fields};

    fn marker() -> MarkerRecord {
        let draft = r3akt_map_core::MarkerDraft {
            marker_type: "fire".into(),
            symbol: "fire".into(),
            name: "Ridge".into(),
            category: "incident".into(),
            position: r3akt_map_core::Position::new(44.5, -1.25).expect("position"),
            notes: None,
            origin_rch: String::new(),
        };
        MarkerRecord::create(draft, "local".into(), 1_700_000_000_000)
    }

    #[test]
    fn marker_activity_carries_a_replica_event_and_legacy_telemetry() {
        let marker = marker();
        let created = marker_activity_fields("marker.created", &marker, "rch").expect("fields");
        let event = &created[FIELD_EVENT.to_string()];
        assert_eq!(event["event_type"], "mission.marker.created");
        assert_eq!(event["source"]["rns_identity"], "rch");
        assert_eq!(event["payload"], marker.api_value());
        let replica = r3akt_map_core::replica::from_api_value(&event["payload"], "rem".into())
            .expect("replica");
        assert_eq!(
            replica.object_destination_hash,
            marker.object_destination_hash
        );
        assert!(
            created.get(FIELD_COMMANDS.to_string()).is_some(),
            "legacy telemetry kept"
        );

        let deleted = marker_activity_fields("marker.deleted", &marker, "rch").expect("fields");
        assert_eq!(
            deleted[FIELD_EVENT.to_string()]["event_type"],
            "mission.marker.deleted"
        );
        assert!(deleted.get(FIELD_COMMANDS.to_string()).is_none());
        assert!(marker_activity_fields("marker.renamed", &marker, "rch").is_none());
    }
}
