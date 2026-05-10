#![allow(clippy::missing_errors_doc)]

use std::collections::HashMap;

use r3akt_protocol::NodeId;
use serde::{Deserialize, Serialize};
use time::OffsetDateTime;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NodeIdentity {
    pub id: NodeId,
    pub display_name: String,
    pub public_key_hint: String,
}

impl NodeIdentity {
    #[must_use]
    pub fn new(
        id: NodeId,
        display_name: impl Into<String>,
        public_key_hint: impl Into<String>,
    ) -> Self {
        Self {
            id,
            display_name: display_name.into(),
            public_key_hint: public_key_hint.into(),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum TrustLevel {
    Unknown,
    Enrolled,
    Trusted,
    Revoked,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TrustRecord {
    pub node_id: NodeId,
    pub level: TrustLevel,
    pub updated_at: OffsetDateTime,
    pub reason: Option<String>,
}

impl TrustRecord {
    #[must_use]
    pub fn unknown(node_id: NodeId) -> Self {
        Self {
            node_id,
            level: TrustLevel::Unknown,
            updated_at: OffsetDateTime::now_utc(),
            reason: None,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EnrollmentRequest {
    pub identity: NodeIdentity,
    pub requested_at: OffsetDateTime,
    pub attestation_hint: Option<String>,
}

impl EnrollmentRequest {
    #[must_use]
    pub fn new(identity: NodeIdentity) -> Self {
        Self {
            identity,
            requested_at: OffsetDateTime::now_utc(),
            attestation_hint: None,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum EnrollmentDecision {
    Pending,
    Accepted { trust: TrustRecord },
    Rejected { reason: String },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum IdentityError {
    EmptyIdentity,
    EnrollmentNotFound,
    AlreadyRejected,
}

impl std::fmt::Display for IdentityError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::EmptyIdentity => formatter.write_str("identity is required"),
            Self::EnrollmentNotFound => formatter.write_str("enrollment request not found"),
            Self::AlreadyRejected => formatter.write_str("enrollment request is rejected"),
        }
    }
}

impl std::error::Error for IdentityError {}

#[derive(Debug, Default, Clone)]
pub struct IdentityDirectory {
    identities: HashMap<NodeId, NodeIdentity>,
    trust: HashMap<NodeId, TrustRecord>,
    enrollments: HashMap<NodeId, EnrollmentDecision>,
}

impl IdentityDirectory {
    #[must_use]
    pub fn new() -> Self {
        Self::default()
    }

    pub fn submit_enrollment(
        &mut self,
        request: EnrollmentRequest,
    ) -> Result<EnrollmentDecision, IdentityError> {
        validate_node_id(&request.identity.id)?;
        let node_id = request.identity.id.clone();
        self.identities.insert(node_id.clone(), request.identity);
        let decision = EnrollmentDecision::Pending;
        self.enrollments.insert(node_id, decision.clone());
        Ok(decision)
    }

    pub fn accept_enrollment(
        &mut self,
        node_id: &NodeId,
        reason: Option<String>,
    ) -> Result<EnrollmentDecision, IdentityError> {
        validate_node_id(node_id)?;
        match self.enrollments.get(node_id) {
            Some(EnrollmentDecision::Rejected { .. }) => {
                return Err(IdentityError::AlreadyRejected);
            }
            Some(_) => {}
            None => return Err(IdentityError::EnrollmentNotFound),
        }
        let trust = TrustRecord {
            node_id: node_id.clone(),
            level: TrustLevel::Trusted,
            updated_at: OffsetDateTime::now_utc(),
            reason,
        };
        self.trust.insert(node_id.clone(), trust.clone());
        let decision = EnrollmentDecision::Accepted { trust };
        self.enrollments.insert(node_id.clone(), decision.clone());
        Ok(decision)
    }

    pub fn reject_enrollment(
        &mut self,
        node_id: &NodeId,
        reason: impl Into<String>,
    ) -> Result<EnrollmentDecision, IdentityError> {
        validate_node_id(node_id)?;
        if !self.enrollments.contains_key(node_id) {
            return Err(IdentityError::EnrollmentNotFound);
        }
        let decision = EnrollmentDecision::Rejected {
            reason: reason.into(),
        };
        self.enrollments.insert(node_id.clone(), decision.clone());
        Ok(decision)
    }

    pub fn revoke(
        &mut self,
        node_id: &NodeId,
        reason: Option<String>,
    ) -> Result<(), IdentityError> {
        validate_node_id(node_id)?;
        self.trust.insert(
            node_id.clone(),
            TrustRecord {
                node_id: node_id.clone(),
                level: TrustLevel::Revoked,
                updated_at: OffsetDateTime::now_utc(),
                reason,
            },
        );
        Ok(())
    }

    #[must_use]
    pub fn trust_record(&self, node_id: &NodeId) -> TrustRecord {
        self.trust
            .get(node_id)
            .cloned()
            .unwrap_or_else(|| TrustRecord::unknown(node_id.clone()))
    }

    #[must_use]
    pub fn identity(&self, node_id: &NodeId) -> Option<&NodeIdentity> {
        self.identities.get(node_id)
    }

    #[must_use]
    pub fn enrollment(&self, node_id: &NodeId) -> Option<&EnrollmentDecision> {
        self.enrollments.get(node_id)
    }
}

fn validate_node_id(node_id: &NodeId) -> Result<(), IdentityError> {
    if node_id.is_empty() {
        Err(IdentityError::EmptyIdentity)
    } else {
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn identity(value: &str) -> NodeIdentity {
        NodeIdentity::new(NodeId::new(value), "Field Node", "pubkey")
    }

    #[test]
    fn enrollment_acceptance_records_trusted_identity() {
        let mut directory = IdentityDirectory::new();
        let request = EnrollmentRequest::new(identity("node-a"));

        assert_eq!(
            directory.submit_enrollment(request).expect("submit"),
            EnrollmentDecision::Pending
        );
        let decision = directory
            .accept_enrollment(
                &NodeId::new("node-a"),
                Some("operator approved".to_string()),
            )
            .expect("accept");

        let EnrollmentDecision::Accepted { trust } = decision else {
            panic!("expected accepted decision");
        };
        assert_eq!(trust.level, TrustLevel::Trusted);
        assert_eq!(
            directory.trust_record(&NodeId::new("node-a")).level,
            TrustLevel::Trusted
        );
        assert_eq!(
            directory
                .identity(&NodeId::new("node-a"))
                .expect("identity")
                .display_name,
            "Field Node"
        );
    }

    #[test]
    fn enrollment_rejection_blocks_later_acceptance() {
        let mut directory = IdentityDirectory::new();
        directory
            .submit_enrollment(EnrollmentRequest::new(identity("node-a")))
            .expect("submit");

        let rejected = directory
            .reject_enrollment(&NodeId::new("node-a"), "bad attestation")
            .expect("reject");
        assert_eq!(
            rejected,
            EnrollmentDecision::Rejected {
                reason: "bad attestation".to_string()
            }
        );
        assert_eq!(
            directory.accept_enrollment(&NodeId::new("node-a"), None),
            Err(IdentityError::AlreadyRejected)
        );
    }

    #[test]
    fn revoke_overrides_trust_record() {
        let mut directory = IdentityDirectory::new();
        directory
            .submit_enrollment(EnrollmentRequest::new(identity("node-a")))
            .expect("submit");
        directory
            .accept_enrollment(&NodeId::new("node-a"), None)
            .expect("accept");

        directory
            .revoke(&NodeId::new("node-a"), Some("compromised".to_string()))
            .expect("revoke");

        let trust = directory.trust_record(&NodeId::new("node-a"));
        assert_eq!(trust.level, TrustLevel::Revoked);
        assert_eq!(trust.reason.as_deref(), Some("compromised"));
    }

    #[test]
    fn empty_identity_is_rejected() {
        let mut directory = IdentityDirectory::new();
        assert_eq!(
            directory.submit_enrollment(EnrollmentRequest::new(identity("   "))),
            Err(IdentityError::EmptyIdentity)
        );
    }
}
