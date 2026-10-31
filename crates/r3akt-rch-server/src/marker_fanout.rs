//! Southbound marker notifications for REM and standard LXMF clients.
//!
//! Mission marker link changes go out as reduced REM commands. Marker
//! changes made through the RCH API go out as `mission.marker.*` events whose
//! payload is the shared marker API representation, the same `FIELD_EVENT`
//! shape RCH relays for team-scoped REM marker commands, so REM applies every
//! replica through `r3akt_map_core::replica`.

use base64::{Engine as _, engine::general_purpose::STANDARD};
use serde_json::{Value, json};
use std::collections::HashMap;

use super::{
    ApiError, AppState, MarkerRecord, OUTBOUND_RETRY_MAX_ATTEMPTS, REM_COMMAND_PLACEHOLDER_BODY,
    compact_rem_command_id, compact_rem_identifier_string, iso8601_from_unix_ms,
    normalize_identity_key, outbound_identity_allowed, record_outbound_message_with_metadata,
    rem_command_transport_fields, rem_marker_telemetry_command_fields, roster_fanout_recipients,
    unix_now_ms,
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

/// Keep REM commands on REM recipients; optionally send standard marker streams
/// to other current clients through the same durable delivery queue.
fn send_to_recipients(
    state: &AppState,
    fields: &Value,
    mut metadata: Value,
    reliable: bool,
    generic: Option<(&Value, &str)>,
    non_rem_skip_reason: &str,
) -> Result<Value, ApiError> {
    let recipients = roster_fanout_recipients(state, false)?;
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
    // The annotation-based recipient list does not retain roster preferences.
    let preferences: HashMap<_, _> = state
        .clients
        .read()
        .map_err(|error| ApiError::Internal(error.to_string()))?
        .values()
        .filter_map(|client| {
            normalize_identity_key(&client.identity)
                .map(|identity| (identity, (client.paused, client.text_only)))
        })
        .collect();
    let (mut sent, mut failed, mut skipped) = (0usize, 0usize, 0usize);
    let mut errors = Vec::new();
    let mut skipped_reasons = HashMap::<&str, usize>::new();
    let mut skipped_recipients = Vec::new();
    for recipient in recipients {
        let (paused, text_only) = preferences
            .get(&recipient.identity)
            .copied()
            .unwrap_or((false, false));
        let reason = if paused {
            Some("paused")
        } else if text_only {
            Some("text_only")
        } else if !outbound_identity_allowed(state, &recipient.identity, &recipient.identity) {
            Some("outbound_policy")
        } else if !recipient.is_rem_capable && generic.is_none() {
            Some(non_rem_skip_reason)
        } else {
            None
        };
        if let Some(reason) = reason {
            skipped += 1;
            *skipped_reasons.entry(reason).or_default() += 1;
            skipped_recipients.push(json!({"destination": recipient.identity, "reason": reason}));
            continue;
        }
        let mut delivery_metadata = metadata.clone();
        let content = if let Some((fields, content)) = generic.filter(|_| !recipient.is_rem_capable)
        {
            delivery_metadata["lxmf_fields"] = fields.clone();
            delivery_metadata["fanout_channel"] = json!("marker_telemetry");
            content
        } else {
            REM_COMMAND_PLACEHOLDER_BODY
        };
        match record_outbound_message_with_metadata(
            state,
            content,
            None,
            Some(recipient.identity),
            Vec::new(),
            false,
            delivery_metadata,
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
        "skipped_reasons": skipped_reasons,
        "skipped_recipients": skipped_recipients,
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
    send_to_recipients(
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
        None,
        "rem_command_required",
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

/// Shared fields, packed once so stream hashes and sensor payloads stay binary.
fn marker_activity_fields(
    activity: &str,
    marker: &MarkerRecord,
    source: &str,
    include_commands: bool,
) -> Result<Option<Value>, ApiError> {
    let Some(event_type) = mission_marker_event_type(activity) else {
        return Ok(None);
    };
    let legacy = rem_marker_telemetry_command_fields(activity, marker, source);
    let commands = (include_commands && activity != "marker.deleted")
        .then(|| legacy.get(r3akt_profile_rch::FIELD_COMMANDS.to_string()))
        .flatten();
    let packed = r3akt_map_core::marker_wire::encode_fields(event_type, marker, source, commands)
        .map_err(ApiError::Internal)?;
    Ok(Some(
        json!({"_lxmf_fields_msgpack_b64": STANDARD.encode(packed)}),
    ))
}

/// Sends marker creates and updates to current REM and standard LXMF clients.
///
/// Creates and updates keep the legacy marker-as-telemetry command for older
/// REM builds and add the replica event; deletes carry only the event. New
/// REM builds apply the event and ignore telemetry whose object type is
/// `marker`, so markers stay separate from user telemetry. Non-REM recipients
/// receive the standard field 3 stream without REM commands. Deletes remain
/// REM-only because the standard stream cannot represent a tombstone.
pub(super) fn fanout_marker_activity_to_recipients(
    state: &AppState,
    activity: &str,
    marker: &MarkerRecord,
) -> Result<Value, ApiError> {
    let source = rch_source_identity(state);
    let Some(fields) = marker_activity_fields(activity, marker, source, true)? else {
        return Ok(not_attempted("marker_event_not_deliverable"));
    };
    let generic_fields = if activity == "marker.deleted" {
        None
    } else {
        marker_activity_fields(activity, marker, source, false)?
    };
    let content = format!("Map marker: {}", marker.name);
    send_to_recipients(
        state,
        &fields,
        json!({
            "fanout_kind": "marker_activity",
            "fanout_channel": "rem_marker_command",
            "source_event_type": activity,
            "object_destination_hash": marker.object_destination_hash,
        }),
        true,
        generic_fields
            .as_ref()
            .map(|fields| (fields, content.as_str())),
        "standard_marker_delete_unsupported",
    )
}

#[cfg(test)]
mod tests {
    use r3akt_profile_rch::{FIELD_COMMANDS, FIELD_EVENT};

    use super::{MarkerRecord, marker_activity_fields};

    fn decoded(activity: &str, marker: &MarkerRecord) -> serde_json::Value {
        use base64::Engine as _;
        let wrapped = marker_activity_fields(activity, marker, "rch", true)
            .unwrap()
            .unwrap();
        let packed = super::STANDARD
            .decode(wrapped["_lxmf_fields_msgpack_b64"].as_str().unwrap())
            .unwrap();
        r3akt_map_core::msgpack::to_json(&packed).unwrap()
    }

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
        let created = decoded("marker.created", &marker);
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

        let deleted = decoded("marker.deleted", &marker);
        assert_eq!(
            deleted[FIELD_EVENT.to_string()]["event_type"],
            "mission.marker.deleted"
        );
        assert!(deleted.get(FIELD_COMMANDS.to_string()).is_none());
        assert!(
            marker_activity_fields("marker.renamed", &marker, "rch", true)
                .unwrap()
                .is_none()
        );
    }
}
