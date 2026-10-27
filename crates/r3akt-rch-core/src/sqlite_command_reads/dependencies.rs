use super::{HashSet, RchCoreError, ReadSet, Value, mission_expand_values, normalize_hash, text};

impl ReadSet<'_> {
    #[allow(clippy::too_many_lines)]
    pub(super) fn dependencies(&mut self, kind: &str, args: &Value) -> Result<(), RchCoreError> {
        let r = self;
        let aggregate = kind.starts_with("checklist.");
        let expansions = mission_expand_values(args);
        let expand = kind.starts_with("mission.registry.mission.") && !expansions.is_empty();
        let mut target_teams = text(args, &["team_uid", "_rem_team_uid"])
            .into_iter()
            .collect::<HashSet<_>>();
        if kind.starts_with("mission.registry.team.") {
            target_teams.extend(text(args, &["uid"]));
        }
        target_teams.extend(r.snapshot.teams.iter().map(|team| team.uid.clone()));
        let mut target_members = text(args, &["team_member_uid"])
            .into_iter()
            .collect::<HashSet<_>>();
        if kind.starts_with("mission.registry.team_member.") {
            target_members.extend(text(args, &["uid"]));
        }
        for asset in &r.snapshot.assets {
            target_members.extend(asset.team_member_uid.clone());
        }
        for member in &r.snapshot.team_members {
            if target_members.contains(&member.uid) {
                target_teams.extend(member.team_uid.clone());
            }
        }
        let target_missions = r
            .snapshot
            .missions
            .iter()
            .map(|record| record.uid.clone())
            .collect::<HashSet<_>>();
        loop {
            let before = r.rows;
            for subscriber in r.snapshot.subscribers.clone() {
                select!(
                    r,
                    topics,
                    "rch_topics",
                    "topic_id",
                    Some(subscriber.topic_id.as_str())
                );
                if matches!(kind, "mission.message.send" | "PublishMessage") {
                    select!(
                        r,
                        clients,
                        "rch_clients",
                        "identity_normalized",
                        Some(subscriber.node_id.as_str())
                    );
                    select!(
                        r,
                        identity_states,
                        "rch_identity_states",
                        "identity",
                        Some(subscriber.node_id.as_str())
                    );
                }
            }
            for link in r.snapshot.team_member_client_links.clone() {
                select!(
                    r,
                    team_members,
                    "rch_team_members",
                    "uid",
                    Some(link.team_member_uid.as_str())
                );
            }
            for member in r.snapshot.team_members.clone() {
                if target_members.contains(&member.uid)
                    || matches!(
                        kind,
                        "rem.registry.team_peers.list" | "mission.registry.rights.subjects.list"
                    )
                {
                    target_teams.extend(member.team_uid.clone());
                }
                select!(r, teams, "rch_teams", "uid", member.team_uid.as_deref());
                select!(
                    r,
                    team_member_client_links,
                    "rch_team_member_client_links",
                    "team_member_uid",
                    Some(member.uid.as_str())
                );
                if kind == "mission.registry.team_member.delete"
                    || kind == "mission.registry.team_member_skill.list"
                {
                    select!(
                        r,
                        team_member_skills,
                        "rch_team_member_skills",
                        "team_member_rns_identity",
                        Some(member.rns_identity.as_str())
                    );
                }
                if kind == "mission.registry.team_member.delete" || expansions.contains("assets") {
                    select!(
                        r,
                        assets,
                        "rch_assets",
                        "team_member_uid",
                        Some(member.uid.as_str())
                    );
                }
            }
            for team in r.snapshot.teams.clone() {
                if !target_teams.contains(&team.uid)
                    && !expand
                    && kind != "mission.registry.team.list"
                {
                    continue;
                }
                select!(
                    r,
                    mission_team_links,
                    "rch_mission_team_links",
                    "team_uid",
                    Some(team.uid.as_str())
                );
                for mission in &team.mission_uids {
                    select!(r, missions, "rch_missions", "uid", Some(mission.as_str()));
                }
                select!(
                    r,
                    missions,
                    "rch_missions",
                    "uid",
                    team.mission_uid.as_deref()
                );
                if kind == "mission.registry.team.delete"
                    || expansions.contains("team_members")
                    || expansions.contains("assets")
                    || kind == "rem.registry.team_peers.list"
                {
                    select!(
                        r,
                        team_members,
                        "rch_team_members",
                        "team_uid",
                        Some(team.uid.as_str())
                    );
                }
            }
            for link in r.snapshot.mission_team_links.clone() {
                select!(
                    r,
                    missions,
                    "rch_missions",
                    "uid",
                    Some(link.mission_uid.as_str())
                );
                if expansions.contains("teams")
                    || expansions.contains("team_members")
                    || expansions.contains("assets")
                {
                    select!(r, teams, "rch_teams", "uid", Some(link.team_uid.as_str()));
                }
            }
            for asset in r.snapshot.assets.clone() {
                target_members.extend(asset.team_member_uid.clone());
                select!(
                    r,
                    team_members,
                    "rch_team_members",
                    "uid",
                    asset.team_member_uid.as_deref()
                );
                if kind == "mission.registry.asset.delete" {
                    select!(
                        r,
                        assignment_asset_links,
                        "rch_assignment_asset_links",
                        "asset_uid",
                        Some(asset.asset_uid.as_str())
                    );
                    let mut statement=r.connection.prepare("SELECT assignment_uid FROM rch_assignment_payload_assets WHERE asset_uid=?1")?;
                    let ids = statement
                        .query_map([&asset.asset_uid], |row| row.get::<_, String>(0))?
                        .collect::<Result<Vec<_>, _>>()?;
                    for id in ids {
                        select!(
                            r,
                            assignments,
                            "rch_assignments",
                            "assignment_uid",
                            Some(id.as_str())
                        );
                    }
                }
            }
            for link in r.snapshot.assignment_asset_links.clone() {
                select!(
                    r,
                    assignments,
                    "rch_assignments",
                    "assignment_uid",
                    Some(link.assignment_uid.as_str())
                );
                select!(
                    r,
                    assets,
                    "rch_assets",
                    "asset_uid",
                    Some(link.asset_uid.as_str())
                );
            }
            for assignment in r.snapshot.assignments.clone() {
                select!(
                    r,
                    missions,
                    "rch_missions",
                    "uid",
                    Some(assignment.mission_uid.as_str())
                );
                select!(
                    r,
                    checklist_tasks,
                    "rch_checklist_tasks",
                    "task_uid",
                    Some(assignment.task_uid.as_str())
                );
                select!(
                    r,
                    team_members,
                    "rch_team_members",
                    "rns_identity_normalized",
                    normalize_hash(Some(&assignment.team_member_rns_identity)).as_deref()
                );
                select!(
                    r,
                    assignment_asset_links,
                    "rch_assignment_asset_links",
                    "assignment_uid",
                    Some(assignment.assignment_uid.as_str())
                );
                for asset in &assignment.assets {
                    select!(r, assets, "rch_assets", "asset_uid", Some(asset.as_str()));
                }
            }
            for task in r.snapshot.checklist_tasks.clone() {
                select!(
                    r,
                    checklists,
                    "rch_checklists",
                    "uid",
                    Some(task.checklist_uid.as_str())
                );
                if aggregate || kind == "mission.registry.asset.delete" {
                    select!(
                        r,
                        task_skill_requirements,
                        "rch_task_skill_requirements",
                        "task_uid",
                        Some(task.task_uid.as_str())
                    );
                }
                if kind == "checklist.delete" {
                    select!(
                        r,
                        assignments,
                        "rch_assignments",
                        "task_uid",
                        Some(task.task_uid.as_str())
                    );
                }
                if aggregate || expansions.contains("checklists") {
                    select!(
                        r,
                        checklist_cells,
                        "rch_checklist_cells",
                        "task_uid",
                        Some(task.task_uid.as_str())
                    );
                }
            }
            for checklist in r.snapshot.checklists.clone() {
                select!(
                    r,
                    missions,
                    "rch_missions",
                    "uid",
                    checklist.mission_uid.as_deref()
                );
                if aggregate || expansions.contains("checklists") {
                    select!(
                        r,
                        checklist_tasks,
                        "rch_checklist_tasks",
                        "checklist_uid",
                        Some(checklist.uid.as_str())
                    );
                    select!(
                        r,
                        checklist_columns,
                        "rch_checklist_columns",
                        "checklist_uid",
                        Some(checklist.uid.as_str())
                    );
                    select!(
                        r,
                        checklist_feed_publications,
                        "rch_checklist_feed_publications",
                        "checklist_uid",
                        Some(checklist.uid.as_str())
                    );
                }
                select!(
                    r,
                    checklist_templates,
                    "rch_checklist_templates",
                    "uid",
                    checklist.template_uid.as_deref()
                );
            }
            for template in r.snapshot.checklist_templates.clone() {
                select!(
                    r,
                    checklist_columns,
                    "rch_checklist_columns",
                    "template_uid",
                    Some(template.uid.as_str())
                );
                if kind == "checklist.template.delete" {
                    select!(
                        r,
                        checklists,
                        "rch_checklists",
                        "template_uid",
                        Some(template.uid.as_str())
                    );
                }
            }
            for requirement in r.snapshot.task_skill_requirements.clone() {
                select!(
                    r,
                    skills,
                    "rch_skills",
                    "skill_uid",
                    Some(requirement.skill_uid.as_str())
                );
            }
            if kind == "mission.registry.team_member_skill.upsert"
                && let (Some(identity), Some(skill)) = (
                    text(args, &["team_member_rns_identity"]),
                    text(args, &["skill_uid"]),
                )
                && r.queried.insert((
                    "member-skill-pair".into(),
                    identity.clone(),
                    Some(skill.clone()),
                ))
            {
                let records=r.query("SELECT payload FROM rch_team_member_skills WHERE team_member_rns_identity=?1 AND skill_uid=?2",&[&identity,&skill])?;
                for record in records {
                    if !r.snapshot.team_member_skills.contains(&record) {
                        r.snapshot.team_member_skills.push(record);
                    }
                }
            }
            if kind == "mission.registry.task_skill_requirement.upsert"
                && let (Some(task), Some(skill)) =
                    (text(args, &["task_uid"]), text(args, &["skill_uid"]))
                && r.queried
                    .insert(("requirement-pair".into(), task.clone(), Some(skill.clone())))
            {
                let records=r.query("SELECT payload FROM rch_task_skill_requirements WHERE task_uid=?1 AND skill_uid=?2",&[&task,&skill])?;
                r.snapshot.task_skill_requirements.extend(records);
            }
            for eam in r.snapshot.eam_snapshots.clone() {
                target_teams.insert(eam.team_uid.clone());
                target_members.insert(eam.team_member_uid.clone());
                select!(
                    r,
                    team_members,
                    "rch_team_members",
                    "uid",
                    Some(eam.team_member_uid.as_str())
                );
                select!(r, teams, "rch_teams", "uid", Some(eam.team_uid.as_str()));
            }
            r.mission_dependencies(kind, &target_missions, expand, &expansions)?;
            if r.rows == before {
                break;
            }
        }
        for client in r.snapshot.clients.clone() {
            select!(
                r,
                identity_states,
                "rch_identity_states",
                "identity",
                normalize_hash(Some(&client.identity)).as_deref()
            );
        }
        let mut identities = r
            .snapshot
            .team_members
            .iter()
            .flat_map(|m| {
                std::iter::once(m.rns_identity.clone()).chain(m.client_identities.iter().cloned())
            })
            .collect::<Vec<_>>();
        identities.extend(
            r.snapshot
                .team_member_client_links
                .iter()
                .map(|link| link.client_identity.clone()),
        );
        for identity in identities {
            let identity = normalize_hash(Some(&identity));
            select!(
                r,
                identity_states,
                "rch_identity_states",
                "identity",
                identity.as_deref()
            );
            select!(
                r,
                identity_announces,
                "rch_identity_announces",
                "normalized_destination_hash",
                identity.as_deref()
            );
            select!(
                r,
                identity_announces,
                "rch_identity_announces",
                "normalized_announced_identity_hash",
                identity.as_deref()
            );
        }
        for announce in r.snapshot.identity_announces.clone() {
            select!(
                r,
                identity_rem_modes,
                "rch_identity_rem_modes",
                "identity",
                normalize_hash(Some(&announce.destination_hash)).as_deref()
            );
            select!(
                r,
                identity_rem_modes,
                "rch_identity_rem_modes",
                "identity",
                announce
                    .announced_identity_hash
                    .as_deref()
                    .and_then(|v| normalize_hash(Some(v)))
            );
            select!(
                r,
                identity_states,
                "rch_identity_states",
                "identity",
                normalize_hash(Some(&announce.destination_hash)).as_deref()
            );
            select!(
                r,
                identity_states,
                "rch_identity_states",
                "identity",
                announce
                    .announced_identity_hash
                    .as_deref()
                    .and_then(|v| normalize_hash(Some(v)))
            );
        }
        Ok(())
    }
}
