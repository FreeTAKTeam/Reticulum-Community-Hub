//! Registered-member authorization.
//!
//! With the operator's authorization switch on, roster membership is the hub's
//! registration: an operator adds members from the UI, and a member may send
//! any command without per-command grants. An explicit deny an operator set for
//! the member (or its team member) still refuses that operation.

use super::{MissionCommandEnvelope, RchCore, normalize_hash};

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

    /// A registered member may run the operation unless an operator denied it.
    pub(super) fn registered_member_allows(
        &self,
        command: &MissionCommandEnvelope,
        operation: &str,
    ) -> bool {
        let identity = command.source.rns_identity.as_str();
        if !self.is_registered_member(identity) {
            return false;
        }
        let subject_refs = self.subject_refs_for_identity(identity);
        let mut scopes = vec![None];
        scopes.extend(self.candidate_mission_uids(command).into_iter().map(Some));
        scopes.extend(self.candidate_checklist_mission_uid(command).map(Some));
        !scopes.iter().any(|scope| {
            self.matching_operation_rights(&subject_refs, scope.as_deref())
                .iter()
                .any(|record| !record.granted && record.operation == operation)
        })
    }
}
