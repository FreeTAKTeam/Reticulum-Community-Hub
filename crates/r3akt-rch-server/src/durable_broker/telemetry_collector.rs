//! Sideband/Columba numeric command 1 collector replies, within inbox custody.
use super::*;
use serde::{Serialize, Serializer};
use std::collections::BTreeMap;

#[derive(Serialize)]
struct StreamEntry(Binary, i64, Binary, Option<Value>);
#[derive(Serialize)]
#[serde(untagged)]
enum WireField {
    Stream(Vec<StreamEntry>),
    Event(Value),
}
struct Binary(Vec<u8>);
impl Serialize for Binary {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.serialize_bytes(&self.0)
    }
}

pub(super) fn reply(
    unit: &mut RchCommandTransaction<'_>,
    event: &InboxEvent,
    envelope: &ProtocolEnvelope,
    command: &r3akt_protocol::Command,
    published: &mut Vec<OutboundMessageRecord>,
    allowlist: Option<&HashSet<String>>,
) -> Result<(), ApiError> {
    let topic = command.args.get("topic_id").and_then(Value::as_str);
    let Some(since) = command
        .args
        .get("since")
        .and_then(Value::as_i64)
        .filter(|s| *s >= 0)
    else {
        return failure_reply(
            unit,
            event,
            envelope,
            published,
            "malformed",
            "Invalid telemetry collector timebase.",
            topic,
        );
    };
    if command
        .args
        .get("topic_id")
        .is_some_and(|v| v.as_str().is_none_or(|s| s.trim().is_empty()))
    {
        return failure_reply(
            unit,
            event,
            envelope,
            published,
            "malformed",
            "Invalid telemetry collector topic.",
            None,
        );
    }
    let source = normalize_identity_key(envelope.source.as_str());
    let destinations = topic.map(|topic| {
        unit.core_mut()
            .subscribers(topic)
            .into_iter()
            .filter_map(|s| normalize_identity_key(&s.node_id))
            .collect::<HashSet<_>>()
    });
    let authorized = topic.is_none_or(|topic| {
        unit.core_mut().topics().iter().any(|t| t.topic_id == topic)
            && source
                .as_ref()
                .is_some_and(|s| destinations.as_ref().is_some_and(|d| d.contains(s)))
    });
    if !authorized {
        return failure_reply(
            unit,
            event,
            envelope,
            published,
            "denied",
            "Telemetry request denied: sender is not subscribed to the topic.",
            topic,
        );
    }
    let identity_states = unit.core_mut().identity_states();
    let records = match unit.collector_telemetry_since(since) {
        Ok(records) => records,
        Err(r3akt_rch_core::RchCoreError::InvalidPayload(reason)) => {
            return failure_reply(
                unit,
                event,
                envelope,
                published,
                "unavailable",
                &reason,
                topic,
            );
        }
        Err(error) => return Err(storage(error)),
    };
    let mut stream = Vec::new();
    let mut seen = HashSet::new();
    let mut skipped = 0;
    let mut bytes = 0_usize;
    for record in records {
        let Some(peer) = normalize_identity_key(&record.peer_destination) else {
            skipped += 1;
            continue;
        };
        if destinations.as_ref().is_some_and(|d| !d.contains(&peer))
            || identity_states.iter().any(|s| {
                normalize_identity_key(&s.identity).as_ref() == Some(&peer)
                    && (s.is_banned || s.is_blackholed)
            })
            || allowlist.is_some_and(|set| !set.contains(&peer))
            || !telemetry_has_location(&record.telemetry)
            || !seen.insert(peer.clone())
        {
            continue;
        }
        if peer.len() != 32 || !peer.bytes().all(|byte| byte.is_ascii_hexdigit()) {
            skipped += 1;
            continue;
        }
        let hash = peer
            .as_bytes()
            .chunks_exact(2)
            .map(|pair| {
                let digit = |byte: u8| {
                    if byte <= b'9' {
                        byte - b'0'
                    } else {
                        byte - b'a' + 10
                    }
                };
                digit(pair[0]) * 16 + digit(pair[1])
            })
            .collect::<Vec<_>>();
        let Some(packed) = record.packed_telemeter else {
            skipped += 1;
            continue;
        };
        bytes = bytes.saturating_add(packed.len());
        if bytes > 1024 * 1024 {
            return failure_reply(
                unit,
                event,
                envelope,
                published,
                "unavailable",
                "Telemetry collector response exceeds 1 MiB.",
                topic,
            );
        }
        stream.push(StreamEntry(
            Binary(hash),
            record.timestamp_s,
            Binary(packed),
            None,
        ));
    }
    let count = stream.len();
    // Encode the fields map once: field 3 remains an array, with binary peer
    // hashes and packed Telemeter values. The SDK wrapper is transport-only.
    let fields = BTreeMap::from([
        (3_u8, WireField::Stream(stream)),
        (
            13_u8,
            WireField::Event(
                json!({"event_type":"rch.telemetry.response","status":"ok","topic_id":topic,"entry_count":count,"unavailable_records":skipped}),
            ),
        ),
    ]);
    let packed = rmp_serde::to_vec(&fields).map_err(|e| ApiError::Internal(e.to_string()))?;
    published.push(super::envelope::outgoing(
        unit,
        event,
        published.len(),
        envelope.source.as_str(),
        "",
        json!({"_lxmf_fields_msgpack_b64":BASE64_STANDARD.encode(packed)}),
        event.created_at.saturating_mul(1000),
    )?);
    unit.stage_system_event(&SystemEventRecord {
        event_id: format!(
            "broker:{}:collector:{}",
            unit.inbox_event_key().map_err(storage)?,
            published.len()
        ),
        event_type: "telemetry_request".into(),
        message: "Telemetry collector snapshot served".into(),
        timestamp_ms: event.created_at.saturating_mul(1000),
        metadata: json!({"entry_count":count,"unavailable_records":skipped}),
    })
    .map_err(storage)?;
    Ok(())
}

fn failure_reply(
    unit: &RchCommandTransaction<'_>,
    event: &InboxEvent,
    envelope: &ProtocolEnvelope,
    published: &mut Vec<OutboundMessageRecord>,
    status: &str,
    content: &str,
    topic: Option<&str>,
) -> Result<(), ApiError> {
    published.push(super::envelope::outgoing(
        unit,
        event,
        published.len(),
        envelope.source.as_str(),
        content,
        json!({"13":{"event_type":"rch.telemetry.response","status":status,"topic_id":topic}}),
        event.created_at.saturating_mul(1000),
    )?);
    unit.stage_system_event(&SystemEventRecord {
        event_id: format!(
            "broker:{}:collector:{}",
            unit.inbox_event_key().map_err(storage)?,
            published.len()
        ),
        event_type: "telemetry_request".into(),
        message: content.into(),
        timestamp_ms: event.created_at.saturating_mul(1000),
        metadata: json!({"status":status}),
    })
    .map_err(storage)
}

#[cfg(test)]
mod tests;
