use super::{
    DEFAULT_LOG_MISSION_UID, IdentityAnnounceRecord, MissionAccessAssignment,
    MissionCommandEnvelope, OptionalExtension, RECENT_ANNOUNCE_WINDOW_MS, RchCore, RchCoreError,
    ReadSet, Value, canonical_team_from_team_args, decode_msgpack, normalize_hash,
    normalize_subscriber_node_id, normalize_topic_id, text, utc_now_ms, value_as_str,
};

impl ReadSet<'_> {
    #[allow(clippy::too_many_lines)]
    pub fn command(
        &mut self,
        command: &MissionCommandEnvelope,
        inactive_modes: &[String],
    ) -> Result<(), RchCoreError> {
        let r = self;
        let a = &command.args;
        let kind = command.command_type.as_str();
        let source = normalize_hash(Some(&command.source.rns_identity));
        r.authorization = Some(r.connection.query_row("SELECT setting_value='true' FROM rch_settings WHERE setting_key='authorization_required'", [], |row|row.get(0)).optional()?.unwrap_or(false));
        select!(
            r,
            command_results,
            "rch_command_results",
            "command_id",
            Some(command.command_id.as_str())
        );
        select!(
            r,
            clients,
            "rch_clients",
            "identity_normalized",
            source.as_deref()
        );
        select!(
            r,
            identity_states,
            "rch_identity_states",
            "identity",
            source.as_deref()
        );
        select!(
            r,
            identity_capabilities,
            "rch_identity_capabilities",
            "identity",
            source.as_deref()
        );
        select!(
            r,
            identity_rem_modes,
            "rch_identity_rem_modes",
            "identity",
            source.as_deref()
        );
        select!(
            r,
            identity_announces,
            "rch_identity_announces",
            "normalized_destination_hash",
            source.as_deref()
        );
        select!(
            r,
            identity_announces,
            "rch_identity_announces",
            "normalized_announced_identity_hash",
            source.as_deref()
        );
        select!(
            r,
            team_members,
            "rch_team_members",
            "rns_identity_normalized",
            source.as_deref()
        );
        select!(
            r,
            team_member_client_links,
            "rch_team_member_client_links",
            "client_identity",
            source.as_deref()
        );
        let uid = text(a, &["uid"]);
        let mission = text(a, &["mission_uid", "mission_id"]);
        let team = text(a, &["team_uid", "_rem_team_uid"]);
        let member = text(a, &["team_member_uid"]);
        let task = text(a, &["task_uid"]);
        let checklist = text(a, &["checklist_uid"]);
        let template = text(a, &["template_uid", "source_template_uid"]);
        select!(r, missions, "rch_missions", "uid", mission);
        select!(r, teams, "rch_teams", "uid", team);
        select!(r, team_members, "rch_team_members", "uid", member);
        select!(r, checklist_tasks, "rch_checklist_tasks", "task_uid", task);
        select!(r, checklists, "rch_checklists", "uid", checklist);
        select!(
            r,
            checklist_templates,
            "rch_checklist_templates",
            "uid",
            template
        );
        select!(
            r,
            skills,
            "rch_skills",
            "skill_uid",
            text(a, &["skill_uid"])
        );
        select!(
            r,
            assets,
            "rch_assets",
            "asset_uid",
            text(a, &["asset_uid"])
        );
        select!(
            r,
            assignments,
            "rch_assignments",
            "assignment_uid",
            text(a, &["assignment_uid"])
        );
        select!(
            r,
            team_members,
            "rch_team_members",
            "rns_identity_normalized",
            text(a, &["team_member_rns_identity"])
                .and_then(|v| normalize_hash(Some(&v)))
                .as_deref()
        );
        let topic = text(
            a,
            &["topic_id", "TopicID", "topic_path", "TopicPath", "id", "ID"],
        )
        .and_then(|v| normalize_topic_id(Some(&v)));
        select!(r, topics, "rch_topics", "topic_id", topic.as_deref());
        select!(r, missions, "rch_missions", "topic_id", topic.as_deref());
        select!(
            r,
            subscribers,
            "rch_subscribers",
            "topic_id",
            topic.as_deref()
        );
        select!(
            r,
            clients,
            "rch_clients",
            "identity_normalized",
            text(a, &["destination", "Destination"])
                .and_then(|v| normalize_hash(Some(&v)))
                .as_deref()
        );
        if kind.starts_with("mission.registry.mission.") {
            select!(r, missions, "rch_missions", "uid", uid);
        }
        if kind.starts_with("mission.registry.team.") {
            select!(r, teams, "rch_teams", "uid", uid);
            if let Some(color) =
                canonical_team_from_team_args(a, uid.as_deref()).map(|(uid, _)| uid)
            {
                select!(r, teams, "rch_teams", "uid", Some(color));
            }
        }
        if kind.starts_with("mission.registry.team_member.") {
            select!(r, team_members, "rch_team_members", "uid", uid);
        }
        if kind.starts_with("mission.registry.asset.") {
            select!(r, assets, "rch_assets", "asset_uid", uid);
        }
        if kind.starts_with("mission.registry.skill.") {
            select!(r, skills, "rch_skills", "skill_uid", uid);
        }
        if kind.starts_with("mission.registry.log_entry.") {
            select!(
                r,
                log_entries,
                "rch_log_entries",
                "entry_uid",
                text(a, &["entry_uid", "uid"])
            );
            if mission.is_none() {
                select!(
                    r,
                    missions,
                    "rch_missions",
                    "uid",
                    Some(DEFAULT_LOG_MISSION_UID)
                );
            }
        }
        if kind.starts_with("mission.registry.mission_change.") {
            select!(
                r,
                mission_changes,
                "rch_mission_changes",
                "uid",
                text(a, &["change_uid", "uid"])
            );
        }
        if kind.starts_with("mission.registry.eam.") {
            select!(
                r,
                eam_snapshots,
                "rch_eam_snapshots",
                "eam_uid",
                text(a, &["eam_uid"])
            );
            select!(
                r,
                eam_snapshots,
                "rch_eam_snapshots",
                "callsign",
                text(a, &["callsign"])
            );
            select!(
                r,
                eam_snapshots,
                "rch_eam_snapshots",
                "team_member_uid",
                member
            );
            if kind == "mission.registry.eam.team.summary" {
                select!(r, eam_snapshots, "rch_eam_snapshots", "team_uid", team);
            }
        }
        if kind.starts_with("mission.marker.") {
            select!(
                r,
                markers,
                "rch_markers",
                "object_destination_hash",
                text(a, &["object_destination_hash"])
                    .and_then(|v| normalize_hash(Some(&v)))
                    .as_deref()
            );
        }
        select!(
            r,
            zones,
            "rch_zones",
            "zone_id",
            text(a, &["zone_id", "zone_ref"])
        );
        select!(
            r,
            markers,
            "rch_markers",
            "object_destination_hash",
            text(a, &["marker_id", "marker_ref"])
        );
        if kind.starts_with("checklist.template.") {
            select!(
                r,
                checklist_templates,
                "rch_checklist_templates",
                "uid",
                uid
            );
        }
        if kind.starts_with("checklist.") && !kind.starts_with("checklist.template.") {
            select!(r, checklists, "rch_checklists", "uid", uid);
        }
        if kind == "mission.leave" {
            select!(
                r,
                subscribers,
                "rch_subscribers",
                "node_id",
                source.as_deref()
            );
        }
        if kind == "topic.delete" {
            select!(
                r,
                file_attachments,
                "rch_file_attachments",
                "topic_id",
                topic.as_deref()
            );
        }
        if matches!(kind, "mission.message.send" | "PublishMessage")
            && topic.is_none()
            && text(a, &["destination", "Destination"]).is_none()
        {
            all!(r, clients, "rch_clients");
        }
        if kind.starts_with("rem.registry.") && kind.ends_with("peers.list") {
            let mut statement = r
                .connection
                .prepare("SELECT payload FROM rch_identity_announces WHERE last_seen_ts_ms>=?1")?;
            let mut rows =
                statement.query([utc_now_ms().saturating_sub(RECENT_ANNOUNCE_WINDOW_MS)])?;
            while let Some(row) = rows.next()? {
                let payload: Vec<u8> = row.get(0)?;
                let record: IdentityAnnounceRecord = decode_msgpack(&payload)?;
                r.rows += 1;
                r.bytes += payload.len();
                if record.client_type.trim().eq_ignore_ascii_case("rem") {
                    r.snapshot.identity_announces.push(record);
                }
            }
        }
        match kind {
            "mission.users" => {
                all!(r, clients, "rch_clients");
            }
            "mission.events.list" => {
                let mut statement = r
                    .connection
                    .prepare("SELECT payload FROM rch_audit_events ORDER BY id DESC LIMIT 50")?;
                let rows = statement.query_map([], |row| row.get::<_, Vec<u8>>(0))?;
                for row in rows {
                    let bytes = row?;
                    r.rows += 1;
                    r.bytes += bytes.len();
                    r.snapshot.audit_events.push(decode_msgpack(&bytes)?);
                }
                r.snapshot.audit_events.reverse();
            }
            "topic.list" | "ListTopic" => {
                all!(r, topics, "rch_topics");
                all!(r, subscribers, "rch_subscribers");
            }
            "mission.marker.list" => {
                all!(r, markers, "rch_markers");
            }
            "mission.zone.list" => {
                all!(r, zones, "rch_zones");
            }
            "mission.registry.mission.list" => {
                all!(r, missions, "rch_missions");
            }
            "mission.registry.team.list" => {
                all!(r, teams, "rch_teams");
            }
            "mission.registry.team_member.list" => {
                if team.is_some() {
                    select!(r, team_members, "rch_team_members", "team_uid", team);
                } else {
                    all!(r, team_members, "rch_team_members");
                }
            }
            "mission.registry.rights.subjects.list" => {
                all!(r, team_members, "rch_team_members");
            }
            "mission.registry.asset.list" => {
                if let Some(key) = member {
                    select!(
                        r,
                        assets,
                        "rch_assets",
                        "team_member_uid",
                        Some(key.as_str())
                    );
                } else {
                    all!(r, assets, "rch_assets");
                }
            }
            "mission.registry.skill.list" => {
                all!(r, skills, "rch_skills");
            }
            "mission.registry.team_member_skill.list" => {
                if let Some(key) = text(a, &["team_member_rns_identity"]) {
                    select!(
                        r,
                        team_member_skills,
                        "rch_team_member_skills",
                        "team_member_rns_identity",
                        Some(key.as_str())
                    );
                } else {
                    all!(r, team_member_skills, "rch_team_member_skills");
                }
            }
            "mission.registry.task_skill_requirement.list" => {
                if let Some(key) = task {
                    select!(
                        r,
                        task_skill_requirements,
                        "rch_task_skill_requirements",
                        "task_uid",
                        Some(key.as_str())
                    );
                } else {
                    all!(r, task_skill_requirements, "rch_task_skill_requirements");
                }
            }
            "mission.registry.assignment.list" => {
                if let Some(id) = mission.as_deref() {
                    select!(r, assignments, "rch_assignments", "mission_uid", Some(id));
                } else if let Some(id) = task.as_deref() {
                    select!(r, assignments, "rch_assignments", "task_uid", Some(id));
                } else {
                    all!(r, assignments, "rch_assignments");
                }
            }
            "mission.registry.eam.list" => {
                if let Some(key) = team {
                    select!(
                        r,
                        eam_snapshots,
                        "rch_eam_snapshots",
                        "team_uid",
                        Some(key.as_str())
                    );
                } else {
                    all!(r, eam_snapshots, "rch_eam_snapshots");
                }
            }
            "mission.registry.mission_change.list" => {
                if mission.is_some() {
                    select!(
                        r,
                        mission_changes,
                        "rch_mission_changes",
                        "mission_uid",
                        mission
                    );
                } else {
                    all!(r, mission_changes, "rch_mission_changes");
                }
            }
            "mission.registry.log_entry.list" => {
                if mission.is_some() {
                    select!(r, log_entries, "rch_log_entries", "mission_uid", mission);
                } else {
                    all!(r, log_entries, "rch_log_entries");
                }
            }
            "mission.registry.rights.mission_access.list" => {
                if mission.is_some() {
                    select!(
                        r,
                        mission_access_assignments,
                        "rch_mission_access_assignments",
                        "mission_uid",
                        mission
                    );
                } else {
                    all!(
                        r,
                        mission_access_assignments,
                        "rch_mission_access_assignments"
                    );
                }
            }
            "checklist.template.list" => {
                all!(r, checklist_templates, "rch_checklist_templates");
            }
            "checklist.list.active" => {
                if mission.is_some() {
                    select!(r, checklists, "rch_checklists", "mission_uid", mission);
                } else {
                    all!(r, checklists, "rch_checklists");
                }
            }
            _ => {}
        }
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
        r.dependencies(kind, a)
    }
}
