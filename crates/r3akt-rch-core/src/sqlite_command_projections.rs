//! SQLite-derived relationship indexes. Domain records remain authoritative.
use super::{
    RchCoreError, SqlValue, decode_msgpack, normalize_hash, normalize_topic_id, params_from_iter,
};
use rusqlite::Connection;
use serde::Serialize;
use serde_json::Value;

const PROJECTIONS: &[(&str, &[&str])] = &[
    (
        "rch_messages",
        &[
            "topic_id",
            "destination",
            "sender",
            "direction",
            "chat_visible",
            "resident_bytes",
            "cache_activity_ts_ms",
        ],
    ),
    ("rch_clients", &["identity_normalized"]),
    ("rch_identity_rem_modes", &["mode"]),
    ("rch_teams", &["mission_uid"]),
    ("rch_missions", &["parent_uid", "topic_id"]),
    ("rch_team_members", &["team_uid", "rns_identity_normalized"]),
    ("rch_markers", &["local_id"]),
    ("rch_assets", &["team_member_uid"]),
    ("rch_checklists", &["mission_uid", "template_uid"]),
    ("rch_log_entries", &["mission_uid"]),
    ("rch_file_attachments", &["topic_id"]),
];

pub(super) fn columns<T: Serialize>(
    table: &str,
    record: &T,
) -> Result<Vec<(&'static str, SqlValue)>, RchCoreError> {
    if table == "rch_messages" {
        let value =
            serde_json::to_value(record).map_err(|e| RchCoreError::Encode(e.to_string()))?;
        let message: super::MessageRecord =
            serde_json::from_value(value).map_err(|e| RchCoreError::Decode(e.to_string()))?;
        let direction = if message.delivery_metadata["direction"].as_str() == Some("inbound") {
            "inbound"
        } else {
            "outbound"
        };
        let hidden = message.delivery_metadata["fanout_channel"]
            .as_str()
            .is_some_and(|channel| {
                matches!(
                    channel,
                    "rem_checklist_command"
                        | "rem_log_command"
                        | "rem_eam_command"
                        | "rem_telemetry_command"
                        | "rem_marker_command"
                        | "rem_marker_link_command"
                        | "rem_zone_command"
                )
            });
        return Ok(vec![
            (
                "topic_id",
                super::sql_optional_text(message.topic_id.as_deref()),
            ),
            (
                "destination",
                super::sql_optional_text(message.destination.as_deref()),
            ),
            ("sender", super::sql_text(&message.sender)),
            ("direction", super::sql_text(direction)),
            ("chat_visible", SqlValue::Integer(i64::from(!hidden))),
            (
                "cache_activity_ts_ms",
                SqlValue::Integer(message.created_ts_ms),
            ),
            (
                "resident_bytes",
                SqlValue::Integer(
                    i64::try_from(message.estimated_resident_bytes())
                        .map_err(|e| RchCoreError::Encode(e.to_string()))?,
                ),
            ),
        ]);
    }
    let Some((_, fields)) = PROJECTIONS.iter().find(|(name, _)| *name == table) else {
        return Ok(vec![]);
    };
    let value = serde_json::to_value(record).map_err(|e| RchCoreError::Encode(e.to_string()))?;
    fields
        .iter()
        .map(|field| {
            let source = match *field {
                "identity_normalized" => "identity",
                "rns_identity_normalized" => "rns_identity",
                other => other,
            };
            let text = match value.get(source) {
                None | Some(Value::Null) => None,
                Some(Value::String(text)) => Some(text.clone()),
                Some(_) => {
                    return Err(RchCoreError::Decode(format!(
                        "{table}.{source} must be text or null"
                    )));
                }
            };
            let text = if field.ends_with("_normalized") {
                text.as_deref().and_then(|v| normalize_hash(Some(v)))
            } else if table == "rch_file_attachments" {
                text.as_deref().and_then(|v| normalize_topic_id(Some(v)))
            } else {
                text
            };
            let text = if table == "rch_identity_rem_modes" {
                text.map(|value| value.trim().to_ascii_lowercase())
            } else {
                text
            };
            Ok((*field, text.map_or(SqlValue::Null, SqlValue::Text)))
        })
        .collect()
}

pub(super) fn maintain_companion_indexes<T: Serialize>(
    connection: &Connection,
    table: &str,
    record: &T,
) -> Result<(), RchCoreError> {
    if table == "rch_team_members" {
        let value =
            serde_json::to_value(record).map_err(|e| RchCoreError::Encode(e.to_string()))?;
        let uid = value["uid"]
            .as_str()
            .ok_or_else(|| RchCoreError::Decode("member uid must be text".into()))?;
        connection.execute(
            "DELETE FROM rch_member_payload_clients WHERE team_member_uid=?1",
            [uid],
        )?;
        if let Some(ids) = value.get("client_identities").and_then(Value::as_array) {
            for id in ids {
                let id = id.as_str().ok_or_else(|| {
                    RchCoreError::Decode("member client identity must be text".into())
                })?;
                if let Some(id) = normalize_hash(Some(id)) {
                    connection.execute(
                        "INSERT OR IGNORE INTO rch_member_payload_clients VALUES(?1,?2)",
                        rusqlite::params![uid, id],
                    )?;
                }
            }
        }
        return Ok(());
    }
    if table != "rch_assignments" {
        return Ok(());
    }
    let value = serde_json::to_value(record).map_err(|e| RchCoreError::Encode(e.to_string()))?;
    let uid = value["assignment_uid"]
        .as_str()
        .ok_or_else(|| RchCoreError::Decode("assignment_uid must be text".into()))?;
    connection.execute(
        "DELETE FROM rch_assignment_payload_assets WHERE assignment_uid=?1",
        [uid],
    )?;
    if let Some(assets) = value.get("assets").and_then(Value::as_array) {
        for asset in assets {
            let asset = asset
                .as_str()
                .ok_or_else(|| RchCoreError::Decode("assignment asset must be text".into()))?;
            connection.execute(
                "INSERT OR IGNORE INTO rch_assignment_payload_assets VALUES (?1,?2)",
                [uid, asset],
            )?;
        }
    }
    Ok(())
}

/// Compatibility writers and import call this inside their existing transaction.
/// One payload is decoded at a time; ordinary commands use the central keyed upsert.
pub(super) fn rebuild(connection: &Connection) -> Result<(), RchCoreError> {
    for table in PROJECTIONS
        .iter()
        .map(|(table, _)| *table)
        .chain(["rch_assignments"])
    {
        let mut statement = connection.prepare(&format!("SELECT rowid,payload FROM {table}"))?;
        let mut rows = statement.query([])?;
        while let Some(row) = rows.next()? {
            let id: i64 = row.get(0)?;
            let payload: Vec<u8> = row.get(1)?;
            let record: Value = decode_msgpack(&payload).map_err(|error| {
                RchCoreError::Decode(format!("command index rebuild {table} row {id}: {error}"))
            })?;
            let projected = columns(table, &record)?;
            if !projected.is_empty() {
                let assignments = projected
                    .iter()
                    .enumerate()
                    .map(|(i, (field, _))| {
                        if *field == "cache_activity_ts_ms" {
                            format!("{field}=COALESCE({field},?{})", i + 1)
                        } else {
                            format!("{field}=?{}", i + 1)
                        }
                    })
                    .collect::<Vec<_>>()
                    .join(",");
                let mut values = projected.into_iter().map(|(_, v)| v).collect::<Vec<_>>();
                values.push(SqlValue::Integer(id));
                connection.execute(
                    &format!(
                        "UPDATE {table} SET {assignments} WHERE rowid=?{}",
                        values.len()
                    ),
                    params_from_iter(values),
                )?;
            }
            maintain_companion_indexes(connection, table, &record)?;
        }
    }
    Ok(())
}

pub(super) fn migrate(connection: &Connection) -> Result<(), RchCoreError> {
    for (table, fields) in PROJECTIONS {
        for field in *fields {
            if !super::sqlite_table_has_column(connection, table, field)? {
                connection.execute(
                    &format!(
                        "ALTER TABLE {table} ADD COLUMN {field} {}",
                        if matches!(
                            *field,
                            "chat_visible" | "resident_bytes" | "cache_activity_ts_ms"
                        ) {
                            "INTEGER"
                        } else {
                            "TEXT"
                        }
                    ),
                    [],
                )?;
            }
            connection.execute(
                &format!("CREATE INDEX IF NOT EXISTS idx_{table}_{field} ON {table}({field})"),
                [],
            )?;
        }
    }
    connection.execute_batch("CREATE TABLE IF NOT EXISTS rch_member_payload_clients (team_member_uid TEXT NOT NULL,client_identity TEXT NOT NULL,PRIMARY KEY(team_member_uid,client_identity));
        CREATE INDEX IF NOT EXISTS idx_rch_member_payload_clients_identity ON rch_member_payload_clients(client_identity,team_member_uid);
        CREATE TRIGGER IF NOT EXISTS rch_member_payload_clients_delete AFTER DELETE ON rch_team_members BEGIN DELETE FROM rch_member_payload_clients WHERE team_member_uid=old.uid; END;
        CREATE TABLE IF NOT EXISTS rch_assignment_payload_assets (assignment_uid TEXT NOT NULL, asset_uid TEXT NOT NULL, PRIMARY KEY(assignment_uid,asset_uid));
        CREATE INDEX IF NOT EXISTS idx_rch_assignment_payload_assets_asset ON rch_assignment_payload_assets(asset_uid,assignment_uid);
        CREATE TRIGGER IF NOT EXISTS rch_assignment_payload_assets_delete AFTER DELETE ON rch_assignments BEGIN DELETE FROM rch_assignment_payload_assets WHERE assignment_uid=old.assignment_uid; END;
        CREATE INDEX IF NOT EXISTS idx_rch_rem_mode_summary ON rch_identity_rem_modes(mode,identity);
        CREATE INDEX IF NOT EXISTS idx_rch_messages_cache_activity ON rch_messages(cache_activity_ts_ms DESC,created_ts_ms DESC,id DESC);
        CREATE INDEX IF NOT EXISTS idx_rch_messages_chat ON rch_messages(chat_visible,created_ts_ms DESC,id ASC);
        CREATE INDEX IF NOT EXISTS idx_rch_messages_topic_chat ON rch_messages(topic_id,chat_visible,created_ts_ms DESC,id ASC);
        CREATE INDEX IF NOT EXISTS idx_rch_mission_team_links_team ON rch_mission_team_links(team_uid,mission_uid);
        CREATE INDEX IF NOT EXISTS idx_rch_member_clients_identity ON rch_team_member_client_links(client_identity,team_member_uid);
        CREATE INDEX IF NOT EXISTS idx_rch_assignment_assets_asset ON rch_assignment_asset_links(asset_uid,assignment_uid);
        CREATE INDEX IF NOT EXISTS idx_rch_assignments_task ON rch_assignments(task_uid,assignment_uid);
        CREATE INDEX IF NOT EXISTS idx_rch_checklist_publications_checklist ON rch_checklist_feed_publications(checklist_uid);
        CREATE INDEX IF NOT EXISTS idx_rch_eam_member ON rch_eam_snapshots(team_member_uid);
        CREATE INDEX IF NOT EXISTS idx_rch_rights_subject_id ON rch_subject_operation_rights(subject_id);
        CREATE INDEX IF NOT EXISTS idx_rch_access_subject_id ON rch_mission_access_assignments(subject_id);
        CREATE INDEX IF NOT EXISTS idx_rch_member_skill_identity ON rch_team_member_skills(team_member_rns_identity);
        CREATE INDEX IF NOT EXISTS idx_rch_task_requirement_skill ON rch_task_skill_requirements(skill_uid);
        CREATE INDEX IF NOT EXISTS idx_rch_access_subject ON rch_mission_access_assignments(subject_type,subject_id,mission_uid);")?;
    rebuild(connection)
}

impl super::RchSqliteStore {
    pub(super) fn migrate_command_indexes(&self) -> Result<(), RchCoreError> {
        let applied: bool = self.connection.query_row(
            "SELECT EXISTS(SELECT 1 FROM rch_schema_migrations WHERE version=6)",
            [],
            |r| r.get(0),
        )?;
        if applied {
            return Ok(());
        }
        self.backup_before_migration(6)?;
        let transaction = rusqlite::Transaction::new_unchecked(
            &self.connection,
            rusqlite::TransactionBehavior::Immediate,
        )?;
        let applied: bool = transaction.query_row(
            "SELECT EXISTS(SELECT 1 FROM rch_schema_migrations WHERE version=6)",
            [],
            |row| row.get(0),
        )?;
        if applied {
            transaction.commit()?;
            return Ok(());
        }
        migrate(&transaction)?;
        transaction.execute(
            "INSERT INTO rch_schema_migrations VALUES(6,'command relationship indexes',?1)",
            [super::utc_now_ms()],
        )?;
        transaction.execute(
            "INSERT OR REPLACE INTO rch_settings VALUES('schema_version','6')",
            [],
        )?;
        transaction.commit()?;
        Ok(())
    }
}
