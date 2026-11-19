//! `mission.time` (`/time [mission_uid]`): a plain-text LXMF reply with the
//! time left until a mission's `expiration`; without an id, the newest mission.
use super::envelope::reply_text;
use super::{
    ApiError, InboxEvent, OutboundMessageRecord, ProtocolEnvelope, RchCommandTransaction, Value,
    command_arg_text_with_position, json, storage,
};
use chrono::{DateTime, Utc};
use r3akt_profile_rch::MissionCommandEnvelope;

pub(super) fn reply(
    unit: &mut RchCommandTransaction<'_>,
    event: &InboxEvent,
    envelope: &ProtocolEnvelope,
    command: &MissionCommandEnvelope,
    published: &mut Vec<OutboundMessageRecord>,
) -> Result<(), ApiError> {
    let uid = command_arg_text_with_position(
        &command.args,
        &["mission_uid", "mission_id", "uid", "MissionID"],
        0,
    );
    // Reuse the registry read so SQLite loading and read rights stay identical.
    let mut lookup = command.clone();
    (lookup.command_type, lookup.args) = match &uid {
        Some(uid) => (
            "mission.registry.mission.get".into(),
            json!({ "mission_uid": uid }),
        ),
        None => ("mission.registry.mission.list".into(), json!({})),
    };
    unit.prepare_command(&lookup).map_err(storage)?;
    let core = unit.core_mut();
    let text = if let Some(rejection) = core.mission_command_rejection(&lookup) {
        let reason = rejection
            .results_field()
            .and_then(|r| r.get("reason"))
            .and_then(Value::as_str)
            .unwrap_or("rejected");
        format!("Mission time unavailable: {reason}")
    } else {
        let missions = core.missions();
        let mission = match &uid {
            Some(uid) => missions.iter().find(|m| &m.uid == uid),
            None => missions.first(),
        };
        match mission {
            Some(m) => {
                mission_time_text(&m.mission_name, &m.uid, m.expiration.as_deref(), Utc::now())
            }
            None => match uid {
                Some(uid) => format!("Mission {uid} not found"),
                None => "No missions found".to_string(),
            },
        }
    };
    reply_text(unit, event, envelope, &text, published)
}

fn mission_time_text(
    name: &str,
    uid: &str,
    expiration: Option<&str>,
    now: DateTime<Utc>,
) -> String {
    let label = if name.trim().is_empty() {
        uid
    } else {
        name.trim()
    };
    let Some(raw) = expiration.map(str::trim).filter(|v| !v.is_empty()) else {
        return format!("Mission {label} has no end time set");
    };
    let Ok(end) = DateTime::parse_from_rfc3339(raw) else {
        return format!("Mission {label} has an unreadable end time: {raw}");
    };
    let end = end.with_timezone(&Utc);
    let seconds = (end - now).num_seconds();
    let stamp = end.format("%Y-%m-%d %H:%M UTC");
    if seconds > 0 {
        format!(
            "Mission {label}: {} remaining (ends {stamp})",
            human_duration(seconds)
        )
    } else {
        format!(
            "Mission {label} ended {} ago ({stamp})",
            human_duration(-seconds)
        )
    }
}

fn human_duration(seconds: i64) -> String {
    let units = [("day", 86_400), ("hour", 3_600), ("minute", 60)];
    let parts: Vec<String> = units
        .iter()
        .scan(seconds, |left, (unit, size)| {
            let count = *left / size;
            *left %= size;
            Some((count, unit))
        })
        .filter(|(count, _)| *count > 0)
        .map(|(count, unit)| format!("{count} {unit}{}", if count == 1 { "" } else { "s" }))
        .collect();
    if parts.is_empty() {
        "less than a minute".into()
    } else {
        parts.join(", ")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn formats_remaining_elapsed_and_missing_end_times() {
        let now = DateTime::parse_from_rfc3339("2026-11-19T10:00:00Z")
            .unwrap()
            .with_timezone(&Utc);
        assert_eq!(
            mission_time_text("Rescue", "m1", Some("2026-11-21T13:01:30Z"), now),
            "Mission Rescue: 2 days, 3 hours, 1 minute remaining (ends 2026-11-21 13:01 UTC)"
        );
        assert_eq!(
            mission_time_text("", "m1", Some("2026-11-19T09:00:00+00:00"), now),
            "Mission m1 ended 1 hour ago (2026-11-19 09:00 UTC)"
        );
        assert_eq!(
            mission_time_text("Rescue", "m1", Some("2026-11-19T10:00:20Z"), now),
            "Mission Rescue: less than a minute remaining (ends 2026-11-19 10:00 UTC)"
        );
        assert_eq!(
            mission_time_text("Rescue", "m1", None, now),
            "Mission Rescue has no end time set"
        );
        assert!(mission_time_text("Rescue", "m1", Some("soon"), now).contains("unreadable"));
    }
}
