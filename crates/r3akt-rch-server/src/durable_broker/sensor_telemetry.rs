//! R3S relay/collector snapshots retain the authenticated writer separately from object identity.
use super::*;
use r3akt_map_core::{
    sensor_store::SensorOrigin,
    sensor_wire::{
        ManifestEvent, OriginFixEvent, OriginRemovedEvent, SensorEvent, SensorRemovedEvent,
    },
};
use serde::{Serialize, Serializer};
struct Binary(Vec<u8>);
impl Serialize for Binary {
    fn serialize<S: Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_bytes(&self.0)
    }
}
#[derive(Serialize)]
struct Entry(Binary, u64, Binary, Option<Value>);
#[derive(Serialize)]
#[serde(untagged)]
enum Field {
    Stream(Vec<Entry>),
    Events(Vec<Value>),
}

pub(super) fn fields(
    unit: &mut RchCommandTransaction<'_>,
    source_filter: Option<&str>,
    origin_filter: Option<&str>,
    since: i64,
    metadata: bool,
    topic_members: Option<&HashSet<String>>,
    allowlist: Option<&HashSet<String>>,
) -> Result<Value, ApiError> {
    let origins = unit.sensor_origins().map_err(storage)?;
    let mut stream = Vec::new();
    let mut events = Vec::new();
    for origin in origins {
        if origin_filter.is_some_and(|id| id != origin.origin_id)
            || source_filter.is_some_and(|s| s != origin.writer_id)
            || topic_members.is_some_and(|m| !m.contains(&origin.writer_id))
            || allowlist.is_some_and(|m| !m.contains(&origin.writer_id))
        {
            continue;
        }
        if i64::try_from(
            origin
                .latest_source_time()
                .max(origin.deleted_at_ms.unwrap_or(0))
                / 1000,
        )
        .unwrap_or(i64::MAX)
            < since
        {
            continue;
        }
        unit.prepare_source(&origin.writer_id).map_err(storage)?;
        if !unit
            .sensor_writer_authorized(&origin.writer_id, &origin.origin_id, None)
            .map_err(storage)?
            || unit
                .core_mut()
                .identity_states()
                .iter()
                .any(|s| s.identity == origin.writer_id && (s.is_banned || s.is_blackholed))
        {
            continue;
        }
        append(&origin, unit, metadata, &mut stream, &mut events)?;
    }
    if stream.len() > 16 {
        return Err(ApiError::BadRequest(
            "sensor collector snapshot exceeds 16 origins".into(),
        ));
    }
    if stream.is_empty() && events.is_empty() {
        return Ok(Value::Null);
    }
    let fields = std::collections::BTreeMap::from([
        (3_u8, Field::Stream(stream)),
        (13_u8, Field::Events(events)),
    ]);
    let packed = rmp_serde::to_vec(&fields).map_err(|e| ApiError::Internal(e.to_string()))?;
    if packed.len() > 1024 * 1024 {
        return Err(ApiError::BadRequest(
            "sensor collector snapshot exceeds 1 MiB".into(),
        ));
    }
    Ok(json!({"_lxmf_fields_msgpack_b64":BASE64_STANDARD.encode(packed)}))
}
fn mission_policy(
    source: &str,
    operation: &str,
) -> Result<r3akt_profile_rch::MissionCommandEnvelope, ApiError> {
    serde_json::from_value(json!({"command_id":"r3s-policy","source":{"rns_identity":source},"timestamp":"","command_type":operation,"args":{}})).map_err(|e|ApiError::Internal(e.to_string()))
}
fn append(
    origin: &SensorOrigin,
    unit: &mut RchCommandTransaction<'_>,
    metadata: bool,
    stream: &mut Vec<Entry>,
    events: &mut Vec<Value>,
) -> Result<(), ApiError> {
    let id = &origin.origin_id;
    if metadata || origin.deleted_at_ms.is_some() {
        let label = if origin.label.len() <= 128 && !origin.label.chars().any(char::is_control) {
            &origin.label
        } else {
            id
        };
        events.push(json!({"event_type":r3akt_map_core::sensor_frame::ASSERT_EVENT,"payload":{"originId":id,"writerId":origin.writer_id,"originKind":origin.origin_kind,"label":label}}));
        if let Some(deleted_at_ms) = origin.deleted_at_ms {
            events.push(json!(SensorEvent::OriginRemoved(OriginRemovedEvent {
                origin_id: id.clone(),
                deleted_at_ms
            })));
            return Ok(());
        }
        if origin.origin_kind != "device"
            && let Some(marker) = unit.sensor_parent_marker(id).map_err(storage)?
        {
            let mut payload = marker.api_value();
            payload["origin_rch"] = json!(origin.writer_id);
            events.push(json!({"event_type":"mission.marker.created","payload":payload}));
        }
    }
    if let Some(position) = &origin.position {
        events.push(json!(SensorEvent::OriginFix(OriginFixEvent {
            origin_id: id.clone(),
            position: position.clone()
        })));
    }
    for (sensor_id, expires_at_ms) in &origin.sensor_expiry_ms {
        if let Some(sensor) = origin.sensors.get(sensor_id) {
            events.push(json!({"event_type":r3akt_map_core::sensor_expiry::EVENT,"payload":{"originId":id,"sensorId":sensor_id,"sampleAtMs":sensor.sample_at_ms,"expiresAtMs":expires_at_ms}}));
        }
    }
    if metadata {
        for manifest in origin.manifests.values() {
            events.push(json!(SensorEvent::Manifest(ManifestEvent {
                origin_id: id.clone(),
                manifest: manifest.clone(),
                updated_at_ms: *origin
                    .manifest_times
                    .get(&manifest.sensor_id)
                    .ok_or_else(|| ApiError::Internal("missing manifest revision".into()))?
            })));
        }
        for (sensor_id, time) in &origin.sensor_tombstones {
            events.push(json!(SensorEvent::SensorRemoved(SensorRemovedEvent {
                origin_id: id.clone(),
                sensor_id: sensor_id.clone(),
                deleted_at_ms: *time
            })));
        }
    }
    if !origin.sensors.is_empty() {
        let states = origin.sensors.values().cloned().collect::<Vec<_>>();
        let packed = r3akt_map_core::sensor_wire::current_packet(
            origin.packed_telemeter.as_deref(),
            origin.position.as_ref(),
            &states,
        )
        .map_err(|e| ApiError::BadRequest(e.into()))?;
        let hash = id
            .as_bytes()
            .as_chunks::<2>()
            .0
            .iter()
            .map(|p| {
                u8::from_str_radix(
                    std::str::from_utf8(p).map_err(|e| ApiError::Internal(e.to_string()))?,
                    16,
                )
                .map_err(|e| ApiError::Internal(e.to_string()))
            })
            .collect::<Result<Vec<_>, _>>()?;
        stream.push(Entry(
            Binary(hash),
            origin.latest_source_time() / 1000,
            Binary(packed),
            None,
        ));
    }
    Ok(())
}
pub(super) fn relay(
    unit: &mut RchCommandTransaction<'_>,
    event: &InboxEvent,
    envelope: &ProtocolEnvelope,
    input: &Value,
    changed: &[String],
    published: &mut Vec<OutboundMessageRecord>,
    allowlist: Option<&HashSet<String>>,
) -> Result<(), ApiError> {
    let Some(team) = input.get("11").and_then(Value::as_str) else {
        return Ok(());
    };
    unit.prepare_recipients(None, Some(team)).map_err(storage)?;
    let destinations = unit
        .core_mut()
        .rem_team_routing_destinations(envelope.source.as_str(), team);
    for origin in unit
        .sensor_origins()
        .map_err(storage)?
        .into_iter()
        .filter(|o| o.writer_id == envelope.source.as_str() && changed.contains(&o.origin_id))
    {
        let metadata_hash = metadata_hash(unit, &origin)?;
        for destination in &destinations {
            if destination == envelope.source.as_str()
                || allowlist.is_some_and(|a| !a.contains(destination))
            {
                continue;
            }
            if unit
                .core_mut()
                .identity_states()
                .iter()
                .any(|s| s.identity == *destination && (s.is_banned || s.is_blackholed))
            {
                continue;
            }
            let include = unit
                .sensor_relay_metadata(&origin.origin_id, destination)
                .map_err(storage)?
                .as_deref()
                != Some(metadata_hash.as_str());
            let mut fields = fields(
                unit,
                Some(envelope.source.as_str()),
                Some(&origin.origin_id),
                0,
                include,
                None,
                allowlist,
            )?;
            if fields.is_null() {
                continue;
            }
            fields["_r3s_relay_policy"] = json!({"mode":"relay","writer":envelope.source.as_str(),"team":team,"originId":origin.origin_id,"metadataHash":metadata_hash,"includeMetadata":include});
            published.push(super::envelope::outgoing(
                unit,
                event,
                destination,
                "R3S/1",
                fields.clone(),
                event.created_at.saturating_mul(1000),
            )?);
        }
    }
    Ok(())
}
pub(super) fn collector(
    unit: &mut RchCommandTransaction<'_>,
    event: &InboxEvent,
    envelope: &ProtocolEnvelope,
    since: i64,
    members: Option<&HashSet<String>>,
    topic: Option<&str>,
    published: &mut Vec<OutboundMessageRecord>,
    allowlist: Option<&HashSet<String>>,
) -> Result<(), ApiError> {
    unit.prepare_command(&mission_policy(
        envelope.source.as_str(),
        "mission.marker.list",
    )?)
    .map_err(storage)?;
    if !unit.core_mut().authorize_identity_operation(
        envelope.source.as_str(),
        "mission.content.read",
        None,
    ) {
        return Ok(());
    }
    for origin in unit.sensor_origins().map_err(storage)? {
        let mut fields = fields(
            unit,
            None,
            Some(&origin.origin_id),
            since,
            true,
            members,
            allowlist,
        )?;
        if fields.is_null() {
            continue;
        }
        fields["_r3s_relay_policy"] = json!({"mode":"collector","reader":envelope.source.as_str(),"topic":topic,"since":since,"originId":origin.origin_id});
        published.push(super::envelope::outgoing(
            unit,
            event,
            envelope.source.as_str(),
            "R3S/1",
            fields,
            event.created_at.saturating_mul(1000),
        )?);
    }
    Ok(())
}

pub(super) fn dispatch_allowed(
    store: &mut RchSqliteStore,
    destination: &str,
    fields: &Value,
    policy: &Value,
    allowlist: Option<&HashSet<String>>,
) -> Result<bool, ApiError> {
    if policy.is_null() {
        return Ok(true);
    }
    if policy["mode"] == "collector" {
        let reader = policy["reader"]
            .as_str()
            .ok_or_else(|| ApiError::BadRequest("invalid sensor collector policy".into()))?;
        if destination != reader {
            return Ok(false);
        }
        let topic = policy["topic"].as_str();
        let since = policy["since"]
            .as_i64()
            .filter(|v| *v >= 0)
            .ok_or_else(|| ApiError::BadRequest("invalid sensor collector time".into()))?;
        let mut unit = store.begin_outbound_application().map_err(storage)?;
        unit.prepare_command(&mission_policy(reader, "mission.marker.list")?)
            .map_err(storage)?;
        if !unit
            .core_mut()
            .authorize_identity_operation(reader, "mission.content.read", None)
        {
            return Ok(false);
        }
        unit.prepare_collector(topic).map_err(storage)?;
        let members = topic.map(|topic| {
            unit.core_mut()
                .subscribers(topic)
                .into_iter()
                .filter_map(|s| normalize_identity_key(&s.node_id))
                .collect::<HashSet<_>>()
        });
        if members.as_ref().is_some_and(|m| !m.contains(reader)) {
            return Ok(false);
        }
        let current = self::fields(
            &mut unit,
            None,
            policy["originId"].as_str(),
            since,
            true,
            members.as_ref(),
            allowlist,
        )?;
        return Ok(current["_lxmf_fields_msgpack_b64"] == fields["_lxmf_fields_msgpack_b64"]);
    }
    let writer = policy["writer"]
        .as_str()
        .ok_or_else(|| ApiError::BadRequest("invalid sensor writer policy".into()))?;
    let team = policy["team"]
        .as_str()
        .ok_or_else(|| ApiError::BadRequest("invalid sensor team policy".into()))?;
    let mut unit = store.begin_outbound_application().map_err(storage)?;
    let origin = policy["originId"]
        .as_str()
        .ok_or_else(|| ApiError::BadRequest("missing sensor origin policy".into()))?;
    if !unit
        .sensor_writer_authorized(writer, origin, Some(team))
        .map_err(storage)?
    {
        return Ok(false);
    }
    unit.prepare_recipients(None, Some(team)).map_err(storage)?;
    if !unit
        .core_mut()
        .rem_team_routing_destinations(writer, team)
        .iter()
        .any(|d| d == destination)
    {
        return Ok(false);
    }
    let current = self::fields(
        &mut unit,
        Some(writer),
        Some(origin),
        0,
        policy["includeMetadata"].as_bool().unwrap_or(true),
        None,
        allowlist,
    )?;
    Ok(current["_lxmf_fields_msgpack_b64"] == fields["_lxmf_fields_msgpack_b64"])
}

fn metadata_hash(
    unit: &mut RchCommandTransaction<'_>,
    origin: &SensorOrigin,
) -> Result<String, ApiError> {
    let style = unit
        .sensor_parent_marker(&origin.origin_id)
        .map_err(storage)?
        .map(|m| {
            (
                m.marker_type,
                m.symbol,
                m.name,
                m.category,
                m.notes,
                m.created_ts_ms,
            )
        });
    let data = serde_json::to_vec(&(
        &origin.origin_kind,
        &origin.label,
        &origin.manifests,
        &origin.manifest_times,
        &origin.sensor_tombstones,
        origin.deleted_at_ms,
        style,
    ))
    .map_err(|e| ApiError::Internal(e.to_string()))?;
    Ok(sha256_lower_hex(&data))
}
