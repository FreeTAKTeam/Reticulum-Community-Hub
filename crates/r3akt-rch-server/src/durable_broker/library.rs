//! Mission Library over LXMF (RCH #355): `mission.library.list`,
//! `mission.library.item.get` and `mission.library.item.link`, answered to
//! the sender only. Metadata only; bytes move over RPP or the HTTP routes.
use super::envelope::outgoing;
use super::{
    ApiError, InboxEvent, OutboundMessageRecord, ProtocolEnvelope, RchCommandTransaction, Value,
    json, rem_team_routing, storage,
};
use r3akt_library_core::{self as library, LibraryItem, LibraryQuery, Right};
use r3akt_profile_rch::{CommandResultEnvelope, CommandResultStatus, MissionCommandEnvelope};
use std::collections::HashMap;

type Response = r3akt_rch_core::MissionSyncResponse;

fn result(
    mission: &MissionCommandEnvelope,
    status: CommandResultStatus,
    code: Option<&str>,
    reason: Option<&str>,
    value: Value,
) -> Response {
    Response::results(CommandResultEnvelope {
        command_id: mission.command_id.clone(),
        status,
        detail: None,
        reason_code: code.map(str::to_string),
        reason: reason.map(str::to_string),
        required_capabilities: vec![],
        accepted_at: None,
        by_identity: None,
        correlation_id: mission.correlation_id.clone(),
        result: value,
    })
}

fn rejected(mission: &MissionCommandEnvelope, code: &str, reason: &str) -> Response {
    result(
        mission,
        CommandResultStatus::Rejected,
        Some(code),
        Some(reason),
        json!({"status": "rejected"}),
    )
}

fn completed(mission: &MissionCommandEnvelope, value: Value) -> Response {
    result(mission, CommandResultStatus::Completed, None, None, value)
}

/// Authorizes the sender per mission with RCH's own command rules (TEAM
/// scope, capability, mission rights), caching each mission's answer.
struct Authorizer<'a, 'conn> {
    unit: &'a mut RchCommandTransaction<'conn>,
    mission: &'a MissionCommandEnvelope,
    cache: HashMap<(Option<String>, bool), bool>,
    failure: Option<ApiError>,
}

impl Authorizer<'_, '_> {
    fn allowed(&mut self, mission_uid: Option<&str>, right: Right) -> bool {
        let write = right != Right::Read;
        let key = (mission_uid.map(str::to_string), write);
        if let Some(answer) = self.cache.get(&key) {
            return *answer;
        }
        let mut args = json!({});
        if let Some(team) = self.mission.args.get("_rem_team_uid") {
            args["_rem_team_uid"] = team.clone();
        }
        if let Some(uid) = mission_uid {
            args["mission_uid"] = json!(uid);
        }
        let command_type = if write {
            library::ITEM_LINK_COMMAND
        } else {
            library::LIST_COMMAND
        };
        let probe = MissionCommandEnvelope {
            command_type: command_type.into(),
            args,
            ..self.mission.clone()
        };
        let answer = match self.unit.prepare_command(&probe) {
            Ok(()) => self
                .unit
                .core_mut()
                .mission_command_rejection(&probe)
                .is_none(),
            Err(error) => {
                self.failure = Some(storage(error));
                false
            }
        };
        self.cache.insert(key, answer);
        answer
    }
}

fn find(items: Vec<LibraryItem>, args: &Value) -> Option<LibraryItem> {
    let wanted = args
        .get("item_id")
        .and_then(Value::as_str)
        .and_then(library::rch_file_id)
        .or_else(|| args.get("file_id").and_then(Value::as_u64))?;
    items
        .into_iter()
        .find(|item| item.legacy_file_id == Some(wanted))
}

fn answer(
    unit: &mut RchCommandTransaction<'_>,
    envelope: &ProtocolEnvelope,
    mission: &MissionCommandEnvelope,
) -> Result<Response, ApiError> {
    let items = unit.library_items().map_err(storage)?;
    let mut auth = Authorizer {
        unit,
        mission,
        cache: HashMap::new(),
        failure: None,
    };
    let response = match mission.command_type.as_str() {
        library::LIST_COMMAND => match LibraryQuery::from_args(&mission.args) {
            Err(reason) => rejected(mission, "invalid_payload", &reason),
            Ok(query) => {
                let page = query.apply(items, |uid, right| auth.allowed(uid, right));
                let mut value =
                    serde_json::to_value(&page).map_err(|e| ApiError::Internal(e.to_string()))?;
                value["status"] = json!("ok");
                completed(mission, value)
            }
        },
        library::ITEM_GET_COMMAND => {
            // Unknown and unauthorized look the same: nothing is disclosed.
            match find(items, &mission.args).filter(|item| {
                library::permits(item, Right::Read, &mut |uid, right| {
                    auth.allowed(uid, right)
                })
            }) {
                Some(item) => completed(mission, json!({"status": "ok", "item": item})),
                None => rejected(mission, "not_found", "no such Library item"),
            }
        }
        library::ITEM_LINK_COMMAND => {
            let target = mission
                .args
                .get("mission_uid")
                .and_then(Value::as_str)
                .map(str::trim)
                .filter(|v| !v.is_empty());
            let item = find(items, &mission.args).filter(|item| {
                library::permits(item, Right::Read, &mut |uid, right| {
                    auth.allowed(uid, right)
                })
            });
            match (item, target) {
                (_, None) => rejected(mission, "invalid_payload", "mission_uid is required"),
                (None, _) => rejected(mission, "not_found", "no such Library item"),
                (Some(_), Some(uid)) if !auth.allowed(Some(uid), Right::Publish) => rejected(
                    mission,
                    "unauthorized",
                    "not authorized to publish to this mission",
                ),
                (Some(item), Some(uid)) => {
                    let file_id = item.legacy_file_id.unwrap_or_default();
                    auth.unit
                        .link_library_item(file_id, uid, envelope.timestamp.timestamp_millis())
                        .map_err(storage)?;
                    completed(
                        mission,
                        json!({"status": "linked", "item_id": item.item_id, "mission_uid": uid}),
                    )
                }
            }
        }
        _ => rejected(mission, "unknown_command", "Unsupported Library command"),
    };
    match auth.failure {
        Some(error) => Err(error),
        None => Ok(response),
    }
}

/// Answers a `mission.library.*` command to its sender, echoing TEAM scope.
pub(super) fn handle(
    unit: &mut RchCommandTransaction<'_>,
    event: &InboxEvent,
    envelope: &ProtocolEnvelope,
    mission: &MissionCommandEnvelope,
    reply_allowed: bool,
    published: &mut Vec<OutboundMessageRecord>,
) -> Result<(), ApiError> {
    let response = answer(unit, envelope, mission)?;
    if !reply_allowed {
        return Ok(());
    }
    let team = mission.args.get("_rem_team_uid").and_then(Value::as_str);
    let fields = rem_team_routing::mission_response_fields(&response, team)?;
    published.push(outgoing(
        unit,
        event,
        envelope.source.as_str(),
        &response.content,
        fields,
        envelope.timestamp.timestamp_millis(),
    )?);
    Ok(())
}
