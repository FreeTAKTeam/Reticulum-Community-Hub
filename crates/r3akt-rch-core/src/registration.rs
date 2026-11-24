//! Registered-member authorization.
//!
//! With the operator's authorization switch on, roster membership is the hub's
//! registration: an operator adds members from the UI. Registration admits a
//! member to the hub roster commands (`join`, `leave`, `pause`, `resume`,
//! `nick`, `users`) without per-command grants, unless an operator explicitly
//! denied that operation. Mission data (library, markers, zones, checklists,
//! registry, event log) still requires mission rights.

use super::{MissionCommandEnvelope, RchCore, normalize_hash};

/// Commands that act on the sender's own hub membership, not on mission data.
const ROSTER_COMMANDS: &[&str] = &[
    "mission.join",
    "mission.leave",
    "mission.pause",
    "mission.resume",
    "mission.nick",
    "mission.users",
];

impl RchCore {
    /// When true, only registered members may chat with the hub or send it commands.
    #[must_use]
    pub fn authorization_required(&self) -> bool {
        self.authorization_required
    }

    /// Whether the identity is on the hub roster.
    #[must_use]
    pub fn is_registered_member(&self, identity: &str) -> bool {
        normalize_hash(Some(identity)).is_some_and(|key| self.clients.contains_key(&key))
    }

    /// A global operation right (from the capability API or the Users rights
    /// matrix) authorizes the command, unless a global deny or a deny scoped to
    /// a mission the command targets overrides it. Mission roles never count
    /// here: they only authorize their own mission.
    pub(super) fn global_operation_right_allows(
        &self,
        command: &MissionCommandEnvelope,
        operation: &str,
    ) -> bool {
        let subject_refs = self.subject_refs_for_identity(&command.source.rns_identity);
        let matches = |scope: Option<&str>, granted: bool| {
            self.matching_operation_rights(&subject_refs, scope)
                .iter()
                .any(|record| record.granted == granted && record.operation == operation)
        };
        if !matches(None, true) || matches(None, false) {
            return false;
        }
        let mut missions = self.candidate_mission_uids(command);
        missions.extend(self.candidate_checklist_mission_uid(command));
        !missions
            .iter()
            .any(|mission_uid| matches(Some(mission_uid), false))
    }

    /// A registered member may run a roster command unless an operator denied it.
    pub(super) fn registered_member_allows(
        &self,
        command: &MissionCommandEnvelope,
        operation: &str,
    ) -> bool {
        let identity = command.source.rns_identity.as_str();
        if !ROSTER_COMMANDS.contains(&command.command_type.as_str())
            || !self.is_registered_member(identity)
        {
            return false;
        }
        let subject_refs = self.subject_refs_for_identity(identity);
        !self
            .matching_operation_rights(&subject_refs, None)
            .iter()
            .any(|record| !record.granted && record.operation == operation)
    }
}

#[cfg(test)]
mod tests {
    use crate::{MissionCommandEnvelope, RchCore};
    use r3akt_profile_rch::RchSource;
    use serde_json::{Value, json};

    fn command(kind: &str, args: Value) -> MissionCommandEnvelope {
        MissionCommandEnvelope {
            command_id: format!("{kind}-{args}"),
            source: RchSource::new("abcdef"),
            timestamp: "2026-11-24T12:00:00Z".to_string(),
            command_type: kind.to_string(),
            args,
            correlation_id: None,
            topics: Vec::new(),
        }
    }

    fn status(core: &mut RchCore, kind: &str, args: Value) -> Value {
        let responses = core.handle_mission_sync_command(&command(kind, args));
        responses[0].results_field().expect("result")["status"].clone()
    }

    #[test]
    fn global_rights_authorize_but_mission_roles_stay_in_their_mission() {
        let mut core = RchCore::new();
        core.set_authorization_required(true);
        let alpha = json!({"mission_uid": "alpha"});
        let bravo = json!({"mission_uid": "bravo"});
        core.assign_mission_access_role("alpha", "identity", "abcdef", "MISSION_SUBSCRIBER")
            .expect("alpha role");
        assert_eq!(
            status(&mut core, "mission.marker.list", alpha.clone()),
            "accepted"
        );
        assert_eq!(
            status(&mut core, "mission.marker.list", bravo.clone()),
            "rejected"
        );

        core.grant_operation_right("identity", "abcdef", "mission.content.read", "global", "")
            .expect("global grant");
        assert_eq!(
            status(&mut core, "mission.marker.list", bravo.clone()),
            "accepted"
        );

        core.revoke_operation_right(
            "identity",
            "abcdef",
            "mission.content.read",
            "mission",
            "bravo",
        )
        .expect("bravo deny");
        assert_eq!(status(&mut core, "mission.marker.list", bravo), "rejected");
        assert_eq!(status(&mut core, "mission.marker.list", alpha), "accepted");
    }
}
