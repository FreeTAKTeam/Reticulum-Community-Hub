//! Resolve permission scope from the same persisted target the mutation uses.
use super::{MissionCommandEnvelope, RchCore, optional_text};
impl RchCore {
    pub(super) fn stored_command_missions(
        &self,
        command: &MissionCommandEnvelope,
    ) -> Option<Vec<String>> {
        let kind = command.command_type.as_str();
        if kind == "mission.registry.mission.upsert" {
            return optional_text(&command.args, &["uid", "mission_id"])
                .filter(|uid| self.missions.contains_key(uid))
                .map(|uid| vec![uid]);
        }
        if matches!(
            kind,
            "mission.registry.mission.get"
                | "mission.registry.mission.patch"
                | "mission.registry.mission.delete"
                | "mission.registry.mission.parent.set"
        ) {
            return optional_text(&command.args, &["mission_uid", "uid"]).map(|uid| vec![uid]);
        }
        if matches!(
            kind,
            "mission.registry.team.get" | "mission.registry.team.delete"
        ) {
            return optional_text(&command.args, &["team_uid", "uid"])
                .filter(|uid| self.teams.contains_key(uid))
                .map(|uid| self.team_mission_ids(&uid));
        }
        if matches!(
            kind,
            "mission.registry.team_member.get"
                | "mission.registry.team_member.delete"
                | "mission.registry.team_member.client.link"
                | "mission.registry.team_member.client.unlink"
        ) {
            return optional_text(&command.args, &["team_member_uid", "uid"])
                .filter(|uid| self.team_members.contains_key(uid))
                .map(|uid| self.mission_uids_for_team_member(&uid));
        }
        None
    }
    pub(super) fn command_scope_error(&self, command: &MissionCommandEnvelope) -> Option<String> {
        let alias = |key| optional_text(&command.args, &[key]);
        if alias("mission_uid")
            .zip(alias("mission_id"))
            .is_some_and(|(a, b)| a != b)
        {
            return Some("conflicting mission aliases".into());
        }
        if command
            .command_type
            .starts_with("mission.registry.mission.")
            && alias("mission_uid")
                .zip(alias("uid"))
                .is_some_and(|(a, b)| a != b)
        {
            return Some("conflicting mission target aliases".into());
        }
        if command.command_type == "mission.registry.mission.upsert"
            && alias("uid")
                .zip(alias("mission_id"))
                .is_some_and(|(a, b)| a != b)
        {
            return Some("conflicting mission upsert aliases".into());
        }
        let hint = optional_text(&command.args, &["mission_uid", "mission_id"]);
        if command.command_type.starts_with("checklist.") {
            if let Some(checklist) = optional_text(&command.args, &["checklist_uid"])
                .and_then(|uid| self.checklists.get(&uid))
            {
                if hint
                    .as_ref()
                    .is_some_and(|hint| checklist.mission_uid.as_ref() != Some(hint))
                {
                    return Some("mission hint differs from stored checklist scope".into());
                }
            }
        } else if let Some(targets) = self.stored_command_missions(command) {
            if hint.is_some_and(|hint| !targets.contains(&hint)) {
                return Some("mission hint differs from stored target scope".into());
            }
        }
        None
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use r3akt_profile_rch::RchSource;
    use serde_json::{Value, json};
    pub(super) fn command(kind: &str, args: Value) -> MissionCommandEnvelope {
        MissionCommandEnvelope {
            command_id: kind.into(),
            source: RchSource {
                rns_identity: "actor".into(),
                display_name: None,
            },
            timestamp: "2026-10-09T12:00:00Z".into(),
            command_type: kind.into(),
            args,
            correlation_id: None,
            topics: Vec::new(),
        }
    }
    #[test]
    fn mission_target_never_borrows_authority_from_unrelated_topic() {
        let core = RchCore::new();
        let request = command(
            "mission.registry.mission.delete",
            json!({"mission_uid":"B","topic_id":"topic-A"}),
        );
        assert_eq!(core.candidate_mission_uids(&request), vec!["B"]);
        assert!(
            core.command_scope_error(&command(
                "mission.registry.mission.delete",
                json!({"mission_uid":"B","uid":"A"})
            ))
            .is_some()
        );
    }
}

#[cfg(test)]
mod authority_regression {
    use super::tests::command;
    use super::*;
    use serde_json::json;
    #[test]
    fn scoped_mission_writer_cannot_upsert_another_mission_via_aliases() {
        let mut core = RchCore::new();
        for uid in ["A", "B"] {
            core.handle_mission_sync_command(&command(
                "mission.registry.mission.upsert",
                json!({"uid":uid,"mission_name":uid}),
            ));
        }
        core.grant_operation_right(
            "identity",
            "actor",
            "mission.registry.mission.write",
            "mission",
            "A",
        )
        .unwrap();
        core.set_authorization_required(true);
        for args in [
            json!({"uid":"B","mission_id":"A","mission_name":"stolen"}),
            json!({"uid":"B","mission_name":"stolen"}),
        ] {
            let replies =
                core.handle_mission_sync_command(&command("mission.registry.mission.upsert", args));
            assert!(
                replies
                    .iter()
                    .any(|r| r.results_field().is_some_and(|v| v["status"] == "rejected"))
            );
            assert_eq!(core.missions["B"].mission_name, "B");
        }
        let replies = core.handle_mission_sync_command(&command(
            "mission.registry.mission.upsert",
            json!({"uid":"A","mission_name":"allowed"}),
        ));
        assert!(
            !replies
                .iter()
                .any(|r| r.results_field().is_some_and(|v| v["status"] == "rejected"))
        );
        assert_eq!(core.missions["A"].mission_name, "allowed");
    }
}
