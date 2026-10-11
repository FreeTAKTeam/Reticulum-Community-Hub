//! Patch, array, rights and transport references supplement primary command seeds.
use super::{
    MissionAccessAssignment, MissionCommandEnvelope, RchCore, RchCoreError, ReadSet, Value,
    normalize_hash, normalize_subscriber_node_id, text, value_as_str,
};

impl ReadSet<'_> {
    #[allow(clippy::too_many_lines)]
    pub(super) fn supplemental_seeds(
        &mut self,
        command: &MissionCommandEnvelope,
        inactive_modes: &[String],
    ) -> Result<(), RchCoreError> {
        let r = self;
        let a = &command.args;
        let kind = command.command_type.as_str();
        let source = normalize_hash(Some(&command.source.rns_identity));
        let mission = text(a, &["mission_uid", "mission_id"]);
        // Dependencies supplied by patch/upload/array arguments also participate in validation.
        for args in [a.get("patch"), a.get("checklist"), a.get("template")]
            .into_iter()
            .flatten()
        {
            select!(
                r,
                missions,
                "rch_missions",
                "uid",
                text(args, &["mission_uid", "mission_id"])
            );
            select!(
                r,
                missions,
                "rch_missions",
                "uid",
                RchCore::resolve_parent_uid(args, None)
            );
            select!(r, teams, "rch_teams", "uid", text(args, &["team_uid"]));
            select!(
                r,
                team_members,
                "rch_team_members",
                "uid",
                text(args, &["team_member_uid"])
            );
            select!(
                r,
                topics,
                "rch_topics",
                "topic_id",
                text(args, &["topic_id"])
            );
            select!(
                r,
                checklist_templates,
                "rch_checklist_templates",
                "uid",
                text(args, &["template_uid"])
            );
        }
        select!(
            r,
            missions,
            "rch_missions",
            "uid",
            RchCore::resolve_parent_uid(a, None)
        );
        if let Some(ids) = a.get("mission_uids").and_then(Value::as_array) {
            for id in ids {
                select!(r, missions, "rch_missions", "uid", value_as_str(id));
            }
        }
        if let Some(ids) = a.get("assets").and_then(Value::as_array) {
            for id in ids {
                select!(r, assets, "rch_assets", "asset_uid", value_as_str(id));
            }
        }
        if kind.starts_with("mission.registry.rights.") {
            if kind == "mission.registry.rights.bridge.update" {
                if let (Some(subject), Some(operation)) =
                    (text(a, &["subject_id"]), text(a, &["operation"]))
                {
                    if let Ok(key) = crate::operation_rights::operation_right_key(
                        text(a, &["subject_type"]).as_deref().unwrap_or("identity"),
                        &subject,
                        &operation,
                        text(a, &["scope_type"]).as_deref().unwrap_or(""),
                        text(a, &["scope_id"]).as_deref().unwrap_or(""),
                    ) {
                        let rights=r.query("SELECT payload FROM rch_subject_operation_rights WHERE subject_type=?1 AND subject_id=?2 AND operation=?3 AND scope_type=?4 AND scope_id=?5",&[&key.0,&key.1,&key.2,&key.3,&key.4])?;
                        r.snapshot.subject_operation_rights.extend(rights);
                    }
                }
            }
            select!(
                r,
                team_members,
                "rch_team_members",
                "uid",
                text(a, &["subject_id"])
            );
            if kind != "mission.registry.rights.bridge.update" {
                select!(
                    r,
                    mission_access_assignments,
                    "rch_mission_access_assignments",
                    "mission_uid",
                    mission
                );
            } else if let (Some(subject), Some(mission)) =
                (text(a, &["subject_id"]), mission.as_deref())
            {
                let access=r.query::<MissionAccessAssignment>("SELECT payload FROM rch_mission_access_assignments WHERE subject_id=?1 AND mission_uid=?2",&[&subject,mission])?;
                r.snapshot.mission_access_assignments.extend(access);
            }
        }
        select!(
            r,
            subscribers,
            "rch_subscribers",
            "node_id",
            text(a, &["subscriber_id", "SubscriberID", "id", "ID"])
                .and_then(|v| normalize_subscriber_node_id(Some(&v)))
        );
        let mut refs = text(a, &["marker_id", "marker_ref"])
            .into_iter()
            .collect::<Vec<_>>();
        for name in ["hashes", "content_hashes", "contenthashes"] {
            if let Some(values) = a.get(name).and_then(Value::as_array) {
                refs.extend(values.iter().filter_map(value_as_str));
            }
        }
        for id in refs {
            select!(
                r,
                markers,
                "rch_markers",
                "object_destination_hash",
                Some(id.as_str())
            );
            select!(r, markers, "rch_markers", "local_id", Some(id.as_str()));
        }
        if kind == "topic.subscriber.patch" {
            select!(
                r,
                subscribers,
                "rch_subscribers",
                "node_id",
                text(a, &["destination", "Destination", "node_id", "NodeID"])
                    .and_then(|id| normalize_subscriber_node_id(Some(&id)))
            );
        }
        // REM transport destinations may announce a distinct canonical member identity.
        let mut identities = source.iter().cloned().collect::<Vec<_>>();
        identities.extend(
            r.snapshot
                .identity_announces
                .iter()
                .filter_map(|record| record.announced_identity_hash.clone()),
        );
        for identity in identities {
            let identity = normalize_hash(Some(&identity));
            select!(
                r,
                team_members,
                "rch_team_members",
                "rns_identity_normalized",
                identity.as_deref()
            );
            select!(
                r,
                team_member_client_links,
                "rch_team_member_client_links",
                "client_identity",
                identity.as_deref()
            );
            if let Some(identity) = identity {
                let mut query=r.connection.prepare("SELECT team_member_uid FROM rch_member_payload_clients WHERE client_identity=?1")?;
                let ids = query
                    .query_map([identity], |row| row.get::<_, String>(0))?
                    .collect::<Result<Vec<_>, _>>()?;
                for id in ids {
                    select!(
                        r,
                        team_members,
                        "rch_team_members",
                        "uid",
                        Some(id.as_str())
                    );
                }
            }
        }
        if kind.starts_with("rem.registry.") {
            // The write reservation still contains the original modes. Exclude modes
            // already changed to inactive by earlier commands in this same unit.
            let placeholders = std::iter::repeat_n("?", inactive_modes.len())
                .collect::<Vec<_>>()
                .join(",");
            let exclusion = if inactive_modes.is_empty() {
                String::new()
            } else {
                format!(" AND identity NOT IN ({placeholders})")
            };
            let sql = format!(
                "SELECT payload FROM rch_identity_rem_modes WHERE mode='connected' AND identity<>?1{exclusion} LIMIT 1"
            );
            let mut values = vec![source.as_deref().unwrap_or("")];
            values.extend(inactive_modes.iter().map(String::as_str));
            let records = r.query(&sql, &values)?;
            r.snapshot.identity_rem_modes.extend(records);
        }
        Ok(())
    }
}
