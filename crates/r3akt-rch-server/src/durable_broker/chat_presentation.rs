//! How inbound chat looks to people: roster command replies, relay labels,
//! roster presence and the received-message event log.
//!
//! Chat roster commands (`/join`, `/leave`, `/pause`, `/resume`, `/nick`,
//! `/users`) answer with one human-readable line, as the Python hub did.
//! Generic LXMF clients display message content, so the R3AKT mission-sync
//! acknowledgement pair would show up as two "mission-sync" chat messages.

use super::envelope::outgoing;
use super::{
    ApiError, InboxEvent, OutboundMessageRecord, ProtocolEnvelope, RchCommandTransaction, Value,
    json, normalize_identity_key, storage,
};

const JOIN_REPLAY_MAX_MESSAGES: usize = 10;

pub(super) fn is_roster_command(name: &str) -> bool {
    matches!(
        name,
        "mission.join"
            | "mission.leave"
            | "mission.pause"
            | "mission.resume"
            | "mission.nick"
            | "mission.users"
    )
}

/// Publishes the text reply and, after a successful `/join`, replays recent
/// topic chat from other senders to the joiner.
pub(super) fn publish(
    unit: &RchCommandTransaction<'_>,
    event: &InboxEvent,
    envelope: &ProtocolEnvelope,
    command_name: &str,
    responses: &[r3akt_rch_core::MissionSyncResponse],
    published: &mut Vec<OutboundMessageRecord>,
) -> Result<(), ApiError> {
    let source = envelope.source.as_str();
    let created = envelope.timestamp.timestamp_millis();
    let (reply, accepted) = reply_text(command_name, responses);
    published.push(outgoing(
        unit,
        event,
        published.len(),
        source,
        &reply,
        json!({}),
        created,
    )?);
    if command_name != "mission.join" || !accepted {
        return Ok(());
    }
    let topic = envelope.topic.as_str();
    for inbound in unit
        .recent_inbound_topic_messages(topic, source, JOIN_REPLAY_MAX_MESSAGES)
        .map_err(storage)?
    {
        published.push(outgoing(
            unit,
            event,
            published.len(),
            source,
            &format!("[replay:{topic}]\n{}", inbound.content),
            json!({}),
            created,
        )?);
    }
    Ok(())
}

fn reply_text(
    command_name: &str,
    responses: &[r3akt_rch_core::MissionSyncResponse],
) -> (String, bool) {
    let mut result = &Value::Null;
    for response in responses.iter().filter_map(|r| r.results_field()) {
        match response.get("status").and_then(Value::as_str) {
            Some("rejected") => {
                let reason = response
                    .get("reason")
                    .and_then(Value::as_str)
                    .unwrap_or("command rejected");
                return (reason.to_string(), false);
            }
            Some("result") => result = &response["result"],
            _ => {}
        }
    }
    let reply = match command_name {
        "mission.join" => "joined".to_string(),
        "mission.leave" if result["left"] == false => "not joined".to_string(),
        "mission.leave" => "left".to_string(),
        "mission.pause" => "paused".to_string(),
        "mission.resume" => "resumed".to_string(),
        "mission.nick" => format!(
            "nick set to {}",
            result["nickname"].as_str().unwrap_or_default()
        ),
        _ => users_reply(&result["users"]),
    };
    (reply, true)
}

fn users_reply(users: &Value) -> String {
    let mut users = users.as_array().cloned().unwrap_or_default();
    if users.is_empty() {
        return "users: none".to_string();
    }
    users.sort_by(|left, right| left["identity"].as_str().cmp(&right["identity"].as_str()));
    let entries = users
        .iter()
        .map(|user| {
            let identity = user["identity"].as_str().unwrap_or_default();
            let short: String = identity.trim().chars().take(8).collect();
            let name = user["nickname"].as_str().unwrap_or(short.as_str());
            let mut flags = Vec::new();
            if user["paused"] == true {
                flags.push("paused");
            }
            if user["text_only"] == true {
                flags.push("text-only");
            }
            if flags.is_empty() {
                format!("{name} ({short})")
            } else {
                format!("{name} ({short}, {})", flags.join(", "))
            }
        })
        .collect::<Vec<_>>();
    format!("users: {}", entries.join(", "))
}

/// Relays name the sender by roster nickname, then announced display name,
/// then a short identity prefix.
pub(super) fn relay_sender_label(
    core: &r3akt_rch_core::RchCore,
    nickname: Option<&str>,
    source: &str,
) -> String {
    if let Some(nickname) = nickname {
        return nickname.to_string();
    }
    let key = normalize_identity_key(source);
    core.identity_announces()
        .iter()
        .filter(|announce| normalize_identity_key(&announce.destination_hash) == key)
        .find_map(|announce| {
            announce
                .announce_capabilities
                .iter()
                .find_map(|capability| capability.strip_prefix("name="))
                .and_then(display_name)
                .or_else(|| announce.display_name.as_deref().and_then(display_name))
        })
        .unwrap_or_else(|| source.trim().chars().take(8).collect())
}

fn display_name(value: &str) -> Option<String> {
    let value = value
        .rsplit_once(";name=")
        .map_or(value, |(_, name)| name)
        .trim()
        .replace("%20", " ");
    let value = value.trim();
    (!value.is_empty()).then(|| {
        value
            .chars()
            .map(|c| if c.is_control() && c != '\t' { '?' } else { c })
            .collect()
    })
}

/// Sends one plain-text line back to the inbound sender.
pub(super) fn reply(
    unit: &RchCommandTransaction<'_>,
    event: &InboxEvent,
    envelope: &ProtocolEnvelope,
    content: &str,
    published: &mut Vec<OutboundMessageRecord>,
) -> Result<(), ApiError> {
    let index = published.len();
    let created = envelope.timestamp.timestamp_millis();
    published.push(outgoing(
        unit,
        event,
        index,
        envelope.source.as_str(),
        content,
        json!({}),
        created,
    )?);
    Ok(())
}

/// Records the inbound sender in the roster (last seen, and last chat for chat
/// messages), as the hub does for every inbound message. Bootstrap replays of
/// history never change presence.
pub(super) fn touch_client(
    unit: &mut RchCommandTransaction<'_>,
    event: &InboxEvent,
    envelope: &ProtocolEnvelope,
    bootstrap: bool,
    chat: bool,
) -> Result<r3akt_rch_core::ClientRecord, ApiError> {
    let observed = event.created_at.saturating_mul(1000);
    let source = envelope.source.as_str();
    let mut client = unit
        .core_mut()
        .clients()
        .into_iter()
        .find(|c| c.identity.eq_ignore_ascii_case(source))
        .unwrap_or(r3akt_rch_core::ClientRecord {
            identity: source.to_string(),
            first_seen_ts_ms: observed,
            last_seen_ts_ms: observed,
            nickname: None,
            role: "member".into(),
            paused: false,
            text_only: false,
            last_chat_ts_ms: None,
        });
    if !bootstrap {
        client.last_seen_ts_ms = client.last_seen_ts_ms.max(observed);
        if chat {
            client.last_chat_ts_ms = Some(client.last_chat_ts_ms.unwrap_or(0).max(observed));
        }
        unit.stage_client(&client).map_err(storage)?;
    }
    Ok(client)
}

/// Python RCH logs `message_received` for every inbound chat message.
pub(super) fn stage_received_event(
    unit: &mut RchCommandTransaction<'_>,
    event: &InboxEvent,
    envelope: &ProtocolEnvelope,
    message: &OutboundMessageRecord,
) -> Result<(), ApiError> {
    let label = relay_sender_label(unit.core_mut(), None, envelope.source.as_str());
    let correlation_id = match &envelope.payload {
        r3akt_protocol::Payload::TopicMessage(topic_message) => {
            topic_message.correlation_id.clone()
        }
        _ => None,
    };
    unit.stage_system_event(&r3akt_rch_core::SystemEventRecord {
        event_id: format!(
            "broker:{}:received",
            unit.inbox_event_key().map_err(storage)?
        ),
        event_type: "message_received".into(),
        message: format!("Message received from {label}"),
        timestamp_ms: event.created_at.saturating_mul(1000),
        metadata: json!({
            "message_id": message.message_id,
            "source": envelope.source.to_string(),
            "topic": envelope.topic.to_string(),
            "dedupe_key": envelope.dedupe_key,
            "correlation_id": correlation_id,
        }),
    })
    .map_err(storage)
}
