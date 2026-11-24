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
        library::ITEM_FETCH_COMMAND => {
            let item = find(items, &mission.args).filter(|item| {
                library::permits(item, Right::Read, &mut |uid, right| {
                    auth.allowed(uid, right)
                })
            });
            match item {
                None => rejected(mission, "not_found", "no such Library item"),
                Some(item) => fetch(auth.unit, envelope, mission, &item)?,
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

/// The LXMF delivery Destination of an identity hash: it binds the
/// `rpp_identity` the caller claims to the source the hub authenticated.
fn lxmf_delivery_destination(identity_hash: &[u8; 16]) -> [u8; 16] {
    use sha2::Digest as _;
    let name = sha2::Sha256::digest(b"lxmf.delivery");
    let mut material = [0u8; 26];
    material[..10].copy_from_slice(&name[..10]);
    material[10..].copy_from_slice(identity_hash);
    let mut out = [0u8; 16];
    out.copy_from_slice(&sha2::Sha256::digest(material)[..16]);
    out
}

fn fetch(
    unit: &mut RchCommandTransaction<'_>,
    envelope: &ProtocolEnvelope,
    mission: &MissionCommandEnvelope,
    item: &LibraryItem,
) -> Result<Response, ApiError> {
    let identity: Option<[u8; 16]> = mission
        .args
        .get("rpp_identity")
        .and_then(Value::as_str)
        .and_then(|text| hex::decode(text).ok())
        .and_then(|bytes| bytes.try_into().ok());
    let Some(identity) = identity else {
        return Ok(rejected(
            mission,
            "invalid_payload",
            "rpp_identity is required",
        ));
    };
    if hex::encode(lxmf_delivery_destination(&identity))
        != envelope.source.as_str().to_ascii_lowercase()
    {
        return Ok(rejected(
            mission,
            "unauthorized",
            "rpp_identity does not match the sender",
        ));
    }
    let Some(rpp) = crate::library_rpp::library_rpp() else {
        return Ok(rejected(
            mission,
            "rpp_unavailable",
            "this hub does not serve RPP",
        ));
    };
    let file_id = item.legacy_file_id.unwrap_or_default();
    let Some(record) = unit.library_attachment(file_id).map_err(storage)? else {
        return Ok(rejected(mission, "not_found", "no such Library item"));
    };
    let path = rpp.source_path(file_id, &record.path);
    // A file that cannot be read is answered, never retried: an error here
    // would hold every later message in the inbox behind this one.
    let unreadable = |error: &dyn std::fmt::Display| {
        eprintln!(
            "library rpp: file {file_id} at {} is not readable: {error}",
            path.display()
        );
        rejected(
            mission,
            "file_unavailable",
            "the Library file is not readable on this hub",
        )
    };
    if record.path.starts_with("rch-db:") {
        let Some(bytes) = unit.attachment_bytes(file_id).map_err(storage)? else {
            return Ok(unreadable(&"no stored bytes"));
        };
        if let Err(error) = rpp.write_blob(&path, &bytes) {
            return Ok(unreadable(&error));
        }
    }
    let shared = if let Some(package) = unit.library_rpp_package(file_id).map_err(storage)? {
        crate::library_rpp::shared_package(
            &package.package_token,
            package.manifest,
            package.publication,
        )
    } else {
        {
            let shared =
                match rpp
                    .node
                    .prepare_file(&path, &record.name, record.media_type.as_deref())
                {
                    Ok(shared) => shared,
                    Err(error) => return Ok(unreadable(&error)),
                };
            unit.set_library_rpp_package(&r3akt_rch_core::LibraryRppPackage {
                file_id,
                package_token: shared.package_token.to_vec(),
                manifest: shared.manifest.clone(),
                publication: shared.publication.clone(),
            })
            .map_err(storage)?;
            Some(shared)
        }
    };
    let Some(shared) = shared else {
        return Ok(rejected(mission, "internal", "stored package is corrupt"));
    };
    let reference = package_reference(rpp, &shared)?;
    unit.set_library_rpp_reference(file_id, &reference.0, &reference.1)
        .map_err(storage)?;
    rpp.serve(shared, path, identity);
    Ok(completed(
        mission,
        json!({
            "status": "ok",
            "item_id": item.item_id,
            "name": record.name,
            "media_type": record.media_type,
            "size": record.size,
            "rpp": reference.0,
            "content_sha256": reference.1,
        }),
    ))
}

fn package_reference(
    rpp: &crate::library_rpp::LibraryRpp,
    shared: &rpp_core::rns_share::SharedPackage,
) -> Result<(library::RppReference, String), ApiError> {
    let invalid =
        |error: rpp_core::RppError| ApiError::Internal(format!("library package: {error}"));
    let owner = rpp.node.me();
    let publication =
        rpp_core::publication::Publication::verify(&shared.publication, &owner).map_err(invalid)?;
    let binding = rpp_core::OwnerBinding {
        owner,
        package_destination: rpp.node.package_destination(shared),
        manifest_destination: publication.manifest_destination,
    };
    let manifest =
        rpp_core::VerifiedManifest::verify(&shared.manifest, &binding).map_err(invalid)?;
    let file = manifest
        .manifest
        .files
        .first()
        .ok_or_else(|| ApiError::Internal("empty package".into()))?;
    Ok((
        library::RppReference {
            package_destination: hex::encode(binding.package_destination),
            file_destination: hex::encode(file.destination),
            manifest_hash: hex::encode(manifest.hash),
        },
        hex::encode(file.digest),
    ))
}
