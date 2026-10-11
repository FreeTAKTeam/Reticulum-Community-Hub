//! Command read sets, hydrated under the command's write reservation.
use super::{
    AssetRecord, AssignmentAssetLinkRecord, AssignmentRecord, ChecklistCellRecord,
    ChecklistColumnRecord, ChecklistFeedPublicationRecord, ChecklistRecord, ChecklistTaskRecord,
    ChecklistTemplateRecord, ClientRecord, CommandResultEnvelope, Connection,
    DEFAULT_LOG_MISSION_UID, DeserializeOwned, EamSnapshotRecord, FileAttachmentRecord,
    IdentityAnnounceRecord, IdentityCapabilityGrant, IdentityRemModeRecord, IdentityStateRecord,
    LogEntryRecord, MarkerRecord, MessageRecord, MissionAccessAssignment, MissionAuditEvent,
    MissionChangeRecord, MissionCommandEnvelope, MissionMarkerLinkRecord, MissionRecord,
    MissionTeamLinkRecord, MissionZoneLinkRecord, RECENT_ANNOUNCE_WINDOW_MS, RchCore, RchCoreError,
    RchCoreSnapshot, SkillRecord, SubjectOperationRight, SubscriberRecord, SystemEventRecord,
    TaskSkillRequirementRecord, TeamMemberClientLinkRecord, TeamMemberRecord,
    TeamMemberSkillRecord, TeamRecord, TelemetryRecord, TopicRecord, Value, ZoneRecord,
    canonical_team_from_team_args, checklist_required_capability, decode_msgpack,
    mission_expand_values, normalize_hash, normalize_subscriber_node_id, normalize_topic_id,
    optional_text, params_from_iter, required_capability, utc_now_ms, value_as_str,
};
use rusqlite::OptionalExtension;
use std::collections::HashSet;

pub(super) struct ReadSet<'a> {
    connection: &'a Connection,
    pub snapshot: RchCoreSnapshot,
    queried: HashSet<(String, String, Option<String>)>,
    pub rows: usize,
    pub bytes: usize,
    pub authorization: Option<bool>,
}
impl<'a> ReadSet<'a> {
    pub fn new(connection: &'a Connection) -> Self {
        Self {
            connection,
            snapshot: RchCore::new().snapshot(),
            queried: HashSet::new(),
            rows: 0,
            bytes: 0,
            authorization: None,
        }
    }
    fn read<T: DeserializeOwned>(
        &mut self,
        table: &str,
        column: &str,
        key: Option<&str>,
    ) -> Result<Vec<T>, RchCoreError> {
        if !self
            .queried
            .insert((table.into(), column.into(), key.map(str::to_string)))
        {
            return Ok(vec![]);
        }
        let sql = if column.is_empty() {
            format!("SELECT payload FROM {table}")
        } else {
            format!("SELECT payload FROM {table} WHERE {column}=?1")
        };
        let mut statement = self.connection.prepare(&sql)?;
        let mut rows = if let Some(key) = key {
            statement.query([key])?
        } else {
            statement.query([])?
        };
        let mut values = Vec::new();
        while let Some(row) = rows.next()? {
            let payload: Vec<u8> = row.get(0)?;
            self.rows += 1;
            self.bytes = self.bytes.saturating_add(payload.len());
            values.push(
                decode_msgpack(&payload).map_err(|error| {
                    RchCoreError::Decode(format!("command read {table}: {error}"))
                })?,
            );
        }
        Ok(values)
    }
}
macro_rules! select {
    ($r:ident,$field:ident,$table:literal,$column:literal,$key:expr) => {
        if let Some(key) = ($key).as_deref() {
            let records = $r.read($table, $column, Some(key))?;
            for record in records {
                if !$r.snapshot.$field.contains(&record) {
                    $r.snapshot.$field.push(record);
                }
            }
        }
    };
}
macro_rules! all {
    ($r:ident,$field:ident,$table:literal) => {
        let records = $r.read($table, "", None)?;
        for record in records {
            if !$r.snapshot.$field.contains(&record) {
                $r.snapshot.$field.push(record);
            }
        }
    };
}
fn text(args: &Value, keys: &[&str]) -> Option<String> {
    optional_text(args, keys)
}

mod access;
mod dependencies;
mod merge;
mod mission_dependencies;
mod seeds;
mod supplemental_seeds;
pub(super) use merge::extend;
