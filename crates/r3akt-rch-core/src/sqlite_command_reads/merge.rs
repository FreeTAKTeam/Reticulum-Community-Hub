use super::{
    AssetRecord, AssignmentAssetLinkRecord, AssignmentRecord, ChecklistCellRecord,
    ChecklistColumnRecord, ChecklistFeedPublicationRecord, ChecklistRecord, ChecklistTaskRecord,
    ChecklistTemplateRecord, ClientRecord, CommandResultEnvelope, EamSnapshotRecord,
    FileAttachmentRecord, HashSet, IdentityAnnounceRecord, IdentityCapabilityGrant,
    IdentityRemModeRecord, IdentityStateRecord, LogEntryRecord, MarkerRecord, MessageRecord,
    MissionAccessAssignment, MissionAuditEvent, MissionChangeRecord, MissionMarkerLinkRecord,
    MissionRecord, MissionTeamLinkRecord, MissionZoneLinkRecord, RchCore, RchCoreError,
    RchCoreSnapshot, SkillRecord, SubjectOperationRight, SubscriberRecord, SystemEventRecord,
    TaskSkillRequirementRecord, TeamMemberClientLinkRecord, TeamMemberRecord,
    TeamMemberSkillRecord, TeamRecord, TelemetryRecord, TopicRecord, ZoneRecord,
};

/// Merge new original rows without resurrecting deletions or overwriting staged mutations.
pub(crate) fn extend(
    before: &mut RchCoreSnapshot,
    core: &mut RchCore,
    next: RchCoreSnapshot,
    authorization: Option<bool>,
) -> Result<(), RchCoreError> {
    let mut current = core.snapshot();
    macro_rules! merge {
        ($field:ident, $key:expr) => {{
            let known = before
                .$field
                .iter()
                .chain(current.$field.iter())
                .map($key)
                .collect::<HashSet<_>>();
            for record in next.$field {
                if !known.contains(&($key)(&record)) {
                    current.$field.push(record.clone());
                    before.$field.push(record);
                }
            }
        }};
    }
    merge!(topics, |record: &TopicRecord| record.topic_id.clone());
    merge!(subscribers, |record: &SubscriberRecord| (
        record.node_id.clone(),
        record.topic_id.clone()
    ));
    merge!(messages, |record: &MessageRecord| record.message_id.clone());
    merge!(clients, |record: &ClientRecord| record.identity.clone());
    merge!(identity_announces, |record: &IdentityAnnounceRecord| record
        .destination_hash
        .clone());
    merge!(identity_states, |record: &IdentityStateRecord| record
        .identity
        .clone());
    merge!(identity_rem_modes, |record: &IdentityRemModeRecord| record
        .identity
        .clone());
    merge!(audit_events, |record: &MissionAuditEvent| record
        .event_id
        .clone());
    merge!(system_events, |record: &SystemEventRecord| record
        .event_id
        .clone());
    merge!(telemetry_records, |record: &TelemetryRecord| record
        .peer_destination
        .clone());
    merge!(markers, |record: &MarkerRecord| record
        .object_destination_hash
        .clone());
    merge!(zones, |record: &ZoneRecord| record.zone_id.clone());
    merge!(missions, |record: &MissionRecord| record.uid.clone());
    merge!(mission_changes, |record: &MissionChangeRecord| record
        .uid
        .clone());
    merge!(log_entries, |record: &LogEntryRecord| record
        .entry_uid
        .clone());
    merge!(file_attachments, |record: &FileAttachmentRecord| record
        .file_id);
    merge!(eam_snapshots, |record: &EamSnapshotRecord| record
        .eam_uid
        .clone());
    merge!(teams, |record: &TeamRecord| record.uid.clone());
    merge!(mission_team_links, |record: &MissionTeamLinkRecord| (
        record.mission_uid.clone(),
        record.team_uid.clone()
    ));
    merge!(mission_zone_links, |record: &MissionZoneLinkRecord| (
        record.mission_uid.clone(),
        record.zone_id.clone()
    ));
    merge!(mission_marker_links, |record: &MissionMarkerLinkRecord| (
        record.mission_uid.clone(),
        record.marker_id.clone()
    ));
    merge!(team_members, |record: &TeamMemberRecord| record.uid.clone());
    merge!(
        team_member_client_links,
        |record: &TeamMemberClientLinkRecord| (
            record.team_member_uid.clone(),
            record.client_identity.clone()
        )
    );
    merge!(assets, |record: &AssetRecord| record.asset_uid.clone());
    merge!(skills, |record: &SkillRecord| record.skill_uid.clone());
    merge!(team_member_skills, |record: &TeamMemberSkillRecord| (
        record.team_member_rns_identity.clone(),
        record.skill_uid.clone()
    ));
    merge!(
        task_skill_requirements,
        |record: &TaskSkillRequirementRecord| (record.task_uid.clone(), record.skill_uid.clone())
    );
    merge!(assignments, |record: &AssignmentRecord| record
        .assignment_uid
        .clone());
    merge!(
        assignment_asset_links,
        |record: &AssignmentAssetLinkRecord| (
            record.assignment_uid.clone(),
            record.asset_uid.clone()
        )
    );
    merge!(checklists, |record: &ChecklistRecord| record.uid.clone());
    merge!(checklist_templates, |record: &ChecklistTemplateRecord| {
        record.uid.clone()
    });
    merge!(checklist_columns, |record: &ChecklistColumnRecord| record
        .column_uid
        .clone());
    merge!(checklist_tasks, |record: &ChecklistTaskRecord| record
        .task_uid
        .clone());
    merge!(checklist_cells, |record: &ChecklistCellRecord| record
        .cell_uid
        .clone());
    merge!(
        checklist_feed_publications,
        |record: &ChecklistFeedPublicationRecord| record.publication_uid.clone()
    );
    merge!(command_results, |record: &CommandResultEnvelope| record
        .command_id
        .clone());
    merge!(identity_capabilities, |record: &IdentityCapabilityGrant| (
        record.identity.clone(),
        record.capability.clone()
    ));
    merge!(
        mission_access_assignments,
        |record: &MissionAccessAssignment| (
            record.mission_uid.clone(),
            record.subject_type.clone(),
            record.subject_id.clone()
        )
    );
    merge!(
        subject_operation_rights,
        |record: &SubjectOperationRight| (
            record.subject_type.clone(),
            record.subject_id.clone(),
            record.operation.clone(),
            record.scope_type.clone(),
            record.scope_id.clone()
        )
    );
    if let Some(value) = authorization {
        if before.authorization_required == current.authorization_required {
            current.authorization_required = value;
        }
        before.authorization_required = value;
    }
    *core = RchCore::from_snapshot(current)?;
    Ok(())
}
