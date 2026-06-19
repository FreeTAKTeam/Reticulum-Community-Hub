#![allow(clippy::too_many_lines, clippy::similar_names)]

use std::collections::{BTreeMap, BTreeSet};
use std::fmt::Write as _;
use std::path::{Path, PathBuf};

use rusqlite::types::Value as SqlValue;
use rusqlite::{Connection, OpenFlags, Row, Transaction, params, params_from_iter};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use time::{
    Date, Month, OffsetDateTime, PrimitiveDateTime, Time, format_description::well_known::Rfc3339,
};

use crate::{RchSqliteStore, TelemetryRecord};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PythonMigrationReport {
    pub legacy_db_path: PathBuf,
    pub target_db_path: PathBuf,
    pub rows: BTreeMap<String, usize>,
    pub warnings: Vec<String>,
}

pub fn migrate_python_database(
    legacy_db_path: impl AsRef<Path>,
    target_db_path: impl AsRef<Path>,
) -> Result<PythonMigrationReport, Box<dyn std::error::Error>> {
    let legacy_db_path = legacy_db_path.as_ref().to_path_buf();
    let target_db_path = target_db_path.as_ref().to_path_buf();
    let source = Connection::open_with_flags(
        &legacy_db_path,
        OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )?;
    let store = RchSqliteStore::open(&target_db_path)?;
    drop(store);
    let mut target = Connection::open(&target_db_path)?;
    let mut report = PythonMigrationReport {
        legacy_db_path,
        target_db_path,
        rows: BTreeMap::new(),
        warnings: Vec::new(),
    };

    let transaction = target.transaction()?;
    clear_target_tables(&transaction)?;
    migrate_topics(&source, &transaction, &mut report)?;
    migrate_subscribers(&source, &transaction, &mut report)?;
    migrate_messages(&source, &transaction, &mut report)?;
    migrate_clients(&source, &transaction, &mut report)?;
    migrate_identity_announces(&source, &transaction, &mut report)?;
    migrate_identity_states(&source, &transaction, &mut report)?;
    migrate_identity_rem_modes(&source, &transaction, &mut report)?;
    migrate_markers(&source, &transaction, &mut report)?;
    migrate_zones(&source, &transaction, &mut report)?;
    migrate_missions(&source, &transaction, &mut report)?;
    migrate_mission_changes(&source, &transaction, &mut report)?;
    migrate_log_entries(&source, &transaction, &mut report)?;
    migrate_file_records(&source, &transaction, &mut report)?;
    migrate_eams(&source, &transaction, &mut report)?;
    migrate_teams(&source, &transaction, &mut report)?;
    migrate_simple_links(
        &source,
        &transaction,
        &mut report,
        SimpleLinkSpec {
            source_table: "r3akt_mission_team_links",
            target_table: "rch_mission_team_links",
            target_columns: ("mission_uid", "team_uid"),
            source_columns: ("mission_uid", "team_uid"),
        },
    )?;
    migrate_simple_links(
        &source,
        &transaction,
        &mut report,
        SimpleLinkSpec {
            source_table: "r3akt_mission_zone_links",
            target_table: "rch_mission_zone_links",
            target_columns: ("mission_uid", "zone_id"),
            source_columns: ("mission_uid", "zone_id"),
        },
    )?;
    migrate_simple_links(
        &source,
        &transaction,
        &mut report,
        SimpleLinkSpec {
            source_table: "r3akt_mission_marker_links",
            target_table: "rch_mission_marker_links",
            target_columns: ("mission_uid", "marker_id"),
            source_columns: ("mission_uid", "marker_id"),
        },
    )?;
    migrate_team_members(&source, &transaction, &mut report)?;
    migrate_simple_links(
        &source,
        &transaction,
        &mut report,
        SimpleLinkSpec {
            source_table: "r3akt_team_member_client_links",
            target_table: "rch_team_member_client_links",
            target_columns: ("team_member_uid", "client_identity"),
            source_columns: ("team_member_uid", "client_identity"),
        },
    )?;
    migrate_assets(&source, &transaction, &mut report)?;
    migrate_skills(&source, &transaction, &mut report)?;
    migrate_team_member_skills(&source, &transaction, &mut report)?;
    migrate_task_skill_requirements(&source, &transaction, &mut report)?;
    migrate_assignments(&source, &transaction, &mut report)?;
    migrate_simple_links(
        &source,
        &transaction,
        &mut report,
        SimpleLinkSpec {
            source_table: "r3akt_assignment_assets",
            target_table: "rch_assignment_asset_links",
            target_columns: ("assignment_uid", "asset_uid"),
            source_columns: ("assignment_uid", "asset_uid"),
        },
    )?;
    migrate_checklist_templates(&source, &transaction, &mut report)?;
    migrate_checklists(&source, &transaction, &mut report)?;
    migrate_checklist_columns(&source, &transaction, &mut report)?;
    migrate_checklist_tasks(&source, &transaction, &mut report)?;
    migrate_checklist_cells(&source, &transaction, &mut report)?;
    migrate_checklist_feed_publications(&source, &transaction, &mut report)?;
    migrate_identity_capabilities(&source, &transaction, &mut report)?;
    migrate_mission_access_assignments(&source, &transaction, &mut report)?;
    migrate_subject_operation_rights(&source, &transaction, &mut report)?;
    record_unmapped_tables(&source, &mut report)?;
    transaction.execute(
        "INSERT OR REPLACE INTO rch_settings (setting_key, setting_value) VALUES (?1, ?2)",
        params!["schema_version", "1"],
    )?;
    transaction.execute(
        "INSERT OR REPLACE INTO rch_settings (setting_key, setting_value) VALUES (?1, ?2)",
        params![
            "python_migration_source_db",
            report.legacy_db_path.display().to_string()
        ],
    )?;
    transaction.execute(
        "INSERT OR REPLACE INTO rch_settings (setting_key, setting_value) VALUES (?1, ?2)",
        params![
            "python_migration_completed_at",
            OffsetDateTime::now_utc().format(&Rfc3339)?
        ],
    )?;
    transaction.commit()?;
    Ok(report)
}

pub fn import_legacy_config_settings(
    target_db_path: impl AsRef<Path>,
    config_path: impl AsRef<Path>,
) -> Result<usize, Box<dyn std::error::Error>> {
    let config_path = config_path.as_ref();
    let content = std::fs::read_to_string(config_path)?;
    let connection = Connection::open(target_db_path)?;
    let mut section = String::from("default");
    let mut count = 0_usize;
    for raw_line in content.lines() {
        let line = raw_line.trim();
        if line.is_empty() || line.starts_with('#') || line.starts_with(';') {
            continue;
        }
        if let Some(name) = line
            .strip_prefix('[')
            .and_then(|value| value.strip_suffix(']'))
        {
            section = normalize_setting_segment(name);
            continue;
        }
        let Some((key, value)) = line.split_once('=') else {
            continue;
        };
        let setting_key = format!(
            "python_config.{}.{}",
            section,
            normalize_setting_segment(key.trim())
        );
        connection.execute(
            "INSERT OR REPLACE INTO rch_settings (setting_key, setting_value) VALUES (?1, ?2)",
            params![setting_key, value.trim()],
        )?;
        count += 1;
    }
    connection.execute(
        "INSERT OR REPLACE INTO rch_settings (setting_key, setting_value) VALUES (?1, ?2)",
        params![
            "python_config_source_path",
            config_path.display().to_string()
        ],
    )?;
    Ok(count)
}

#[derive(Debug)]
struct LegacyTelemetryRecord {
    peer_destination: String,
    timestamp_s: i64,
    telemetry: Map<String, Value>,
}

pub fn import_legacy_telemetry_database(
    target_db_path: impl AsRef<Path>,
    telemetry_db_path: impl AsRef<Path>,
) -> Result<usize, Box<dyn std::error::Error>> {
    let telemetry_db_path = telemetry_db_path.as_ref().to_path_buf();
    let source = Connection::open_with_flags(
        &telemetry_db_path,
        OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )?;
    if !table_exists(&source, "Telemeter")? || !table_exists(&source, "Sensor")? {
        return Ok(0);
    }

    let store = RchSqliteStore::open(&target_db_path)?;
    drop(store);
    let mut target = Connection::open(target_db_path)?;
    let mut records = load_legacy_telemeter_records(&source, &telemetry_db_path)?;
    if records.is_empty() {
        return Ok(0);
    }

    let sensor_to_telemeter = load_legacy_sensor_map(&source, &mut records)?;
    import_legacy_sensor_tables(&source, &sensor_to_telemeter, &mut records)?;

    let transaction = target.transaction()?;
    let mut statement = transaction.prepare(
        "INSERT INTO rch_telemetry_records (peer_destination, timestamp_s, payload) VALUES (?1, ?2, ?3)",
    )?;
    let mut count = 0_usize;
    for record in records.into_values() {
        let telemetry_record = TelemetryRecord {
            peer_destination: record.peer_destination,
            timestamp_s: record.timestamp_s,
            telemetry: Value::Object(record.telemetry),
            display_name: None,
            identity_label: None,
        };
        statement.execute(params![
            telemetry_record.peer_destination,
            telemetry_record.timestamp_s,
            rmp_serde::to_vec_named(&telemetry_record)?
        ])?;
        count += 1;
    }
    drop(statement);
    transaction.commit()?;
    Ok(count)
}

fn load_legacy_telemeter_records(
    source: &Connection,
    telemetry_db_path: &Path,
) -> rusqlite::Result<BTreeMap<i64, LegacyTelemetryRecord>> {
    let mut statement = source.prepare("SELECT id, time, peer_dest FROM Telemeter ORDER BY id")?;
    let rows = statement.query_map([], |row| {
        let id: i64 = row.get("id")?;
        let time: String = row.get("time")?;
        let peer_destination: String = row.get("peer_dest")?;
        let timestamp_s = parse_datetime_ms(&time).unwrap_or_default() / 1000;
        let mut telemetry = Map::new();
        telemetry.insert("legacy_source".to_string(), json!("reticulum_telemeter"));
        telemetry.insert(
            "legacy_source_path".to_string(),
            json!(telemetry_db_path.display().to_string()),
        );
        telemetry.insert("legacy_telemeter_id".to_string(), json!(id));
        telemetry.insert("recorded_at".to_string(), json!(time));
        Ok((
            id,
            LegacyTelemetryRecord {
                peer_destination,
                timestamp_s,
                telemetry,
            },
        ))
    })?;
    let mut records = BTreeMap::new();
    for row in rows {
        let (id, record) = row?;
        records.insert(id, record);
    }
    Ok(records)
}

fn load_legacy_sensor_map(
    source: &Connection,
    records: &mut BTreeMap<i64, LegacyTelemetryRecord>,
) -> rusqlite::Result<BTreeMap<i64, i64>> {
    let mut statement = source
        .prepare("SELECT id, sid, stale_time, data, synthesized, telemeter_id FROM Sensor")?;
    let rows = statement.query_map([], |row| {
        let sensor_id: i64 = row.get("id")?;
        let sid: i64 = row.get("sid")?;
        let stale_time: Option<f64> = row.get("stale_time")?;
        let data: Option<Vec<u8>> = row.get("data")?;
        let synthesized: Option<i64> = row.get("synthesized")?;
        let telemeter_id: i64 = row.get("telemeter_id")?;
        let mut metadata = Map::new();
        metadata.insert("sensor_id".to_string(), json!(sensor_id));
        metadata.insert("sid".to_string(), json!(sid));
        if let Some(value) = stale_time {
            metadata.insert("stale_time".to_string(), json!(value));
        }
        if let Some(value) = data {
            metadata.insert("data_hex".to_string(), json!(blob_to_hex(&value)));
        }
        if let Some(value) = synthesized {
            metadata.insert("synthesized".to_string(), json!(value != 0));
        }
        Ok((sensor_id, telemeter_id, Value::Object(metadata)))
    })?;

    let mut sensor_to_telemeter = BTreeMap::new();
    for row in rows {
        let (sensor_id, telemeter_id, metadata) = row?;
        sensor_to_telemeter.insert(sensor_id, telemeter_id);
        if let Some(record) = records.get_mut(&telemeter_id) {
            append_telemetry_array(&mut record.telemetry, "legacy_sensors", metadata);
        }
    }
    Ok(sensor_to_telemeter)
}

fn import_legacy_sensor_tables(
    source: &Connection,
    sensor_to_telemeter: &BTreeMap<i64, i64>,
    records: &mut BTreeMap<i64, LegacyTelemetryRecord>,
) -> rusqlite::Result<()> {
    for table in legacy_telemetry_table_names(source)? {
        if matches!(table.as_str(), "Telemeter" | "Sensor") {
            continue;
        }
        import_legacy_sensor_table(source, sensor_to_telemeter, records, &table)?;
    }
    Ok(())
}

fn import_legacy_sensor_table(
    source: &Connection,
    sensor_to_telemeter: &BTreeMap<i64, i64>,
    records: &mut BTreeMap<i64, LegacyTelemetryRecord>,
    table: &str,
) -> rusqlite::Result<()> {
    let columns = legacy_table_columns(source, table)?;
    let Some(id_index) = columns
        .iter()
        .position(|column| column.eq_ignore_ascii_case("id"))
    else {
        return Ok(());
    };
    let select_list = columns
        .iter()
        .map(|column| quote_identifier(column))
        .collect::<Vec<_>>()
        .join(", ");
    let sql = format!(
        "SELECT {select_list} FROM {} ORDER BY {}",
        quote_identifier(table),
        quote_identifier(&columns[id_index])
    );
    let mut statement = source.prepare(&sql)?;
    let mut rows = statement.query([])?;
    while let Some(row) = rows.next()? {
        let sensor_id = sql_value_as_i64(row.get::<_, SqlValue>(id_index)?).unwrap_or_default();
        let Some(telemeter_id) = sensor_to_telemeter.get(&sensor_id) else {
            continue;
        };
        let Some(record) = records.get_mut(telemeter_id) else {
            continue;
        };
        let mut payload = Map::new();
        payload.insert("sensor_id".to_string(), json!(sensor_id));
        for (index, column) in columns.iter().enumerate() {
            if index == id_index {
                continue;
            }
            let value = row.get::<_, SqlValue>(index)?;
            if matches!(value, SqlValue::Null) {
                continue;
            }
            payload.insert(normalize_setting_segment(column), sql_value_to_json(value));
        }
        merge_telemetry_value(
            &mut record.telemetry,
            &legacy_telemetry_key(table),
            Value::Object(payload),
        );
    }
    Ok(())
}

fn legacy_telemetry_table_names(source: &Connection) -> rusqlite::Result<Vec<String>> {
    let mut statement = source.prepare(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name",
    )?;
    let rows = statement.query_map([], |row| row.get::<_, String>(0))?;
    let mut tables = Vec::new();
    for row in rows {
        tables.push(row?);
    }
    Ok(tables)
}

fn legacy_table_columns(source: &Connection, table: &str) -> rusqlite::Result<Vec<String>> {
    let mut statement =
        source.prepare(&format!("PRAGMA table_info({})", quote_identifier(table)))?;
    let rows = statement.query_map([], |row| row.get::<_, String>(1))?;
    let mut columns = Vec::new();
    for row in rows {
        columns.push(row?);
    }
    Ok(columns)
}

fn quote_identifier(value: &str) -> String {
    format!("\"{}\"", value.replace('"', "\"\""))
}

fn legacy_telemetry_key(table: &str) -> String {
    let mut key = String::new();
    let mut previous_was_lower_or_digit = false;
    for ch in table.chars() {
        if ch.is_ascii_uppercase() {
            if previous_was_lower_or_digit {
                key.push('_');
            }
            key.push(ch.to_ascii_lowercase());
            previous_was_lower_or_digit = false;
        } else if ch.is_ascii_alphanumeric() {
            key.push(ch.to_ascii_lowercase());
            previous_was_lower_or_digit = ch.is_ascii_lowercase() || ch.is_ascii_digit();
        } else if !key.ends_with('_') {
            key.push('_');
            previous_was_lower_or_digit = false;
        }
    }
    key.trim_matches('_').to_string()
}

fn sql_value_to_json(value: SqlValue) -> Value {
    match value {
        SqlValue::Null => Value::Null,
        SqlValue::Integer(value) => json!(value),
        SqlValue::Real(value) => json!(value),
        SqlValue::Text(value) => Value::String(value),
        SqlValue::Blob(value) => Value::String(blob_to_hex(&value)),
    }
}

fn sql_value_as_i64(value: SqlValue) -> Option<i64> {
    match value {
        SqlValue::Integer(value) => Some(value),
        #[allow(clippy::cast_possible_truncation)]
        SqlValue::Real(value) => Some(value as i64),
        SqlValue::Text(value) => value.parse().ok(),
        SqlValue::Null | SqlValue::Blob(_) => None,
    }
}

fn append_telemetry_array(telemetry: &mut Map<String, Value>, key: &str, value: Value) {
    match telemetry.get_mut(key) {
        Some(Value::Array(values)) => values.push(value),
        Some(existing) => {
            let first = existing.take();
            *existing = Value::Array(vec![first, value]);
        }
        None => {
            telemetry.insert(key.to_string(), Value::Array(vec![value]));
        }
    }
}

fn merge_telemetry_value(telemetry: &mut Map<String, Value>, key: &str, value: Value) {
    match telemetry.get_mut(key) {
        Some(Value::Array(values)) => values.push(value),
        Some(existing) => {
            let first = existing.take();
            *existing = Value::Array(vec![first, value]);
        }
        None => {
            telemetry.insert(key.to_string(), value);
        }
    }
}

fn blob_to_hex(value: &[u8]) -> String {
    value.iter().fold(
        String::with_capacity(value.len().saturating_mul(2)),
        |mut output, byte| {
            let _ = write!(output, "{byte:02x}");
            output
        },
    )
}

fn normalize_setting_segment(value: &str) -> String {
    value
        .trim()
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || ch == '_' || ch == '-' {
                ch.to_ascii_lowercase()
            } else {
                '_'
            }
        })
        .collect()
}

fn clear_target_tables(transaction: &Transaction<'_>) -> rusqlite::Result<()> {
    for table in [
        "rch_topics",
        "rch_subscribers",
        "rch_messages",
        "rch_clients",
        "rch_identity_announces",
        "rch_identity_states",
        "rch_identity_rem_modes",
        "rch_audit_events",
        "rch_system_events",
        "rch_telemetry_records",
        "rch_markers",
        "rch_zones",
        "rch_missions",
        "rch_mission_changes",
        "rch_log_entries",
        "rch_file_attachments",
        "rch_eam_snapshots",
        "rch_teams",
        "rch_mission_team_links",
        "rch_mission_zone_links",
        "rch_mission_marker_links",
        "rch_team_members",
        "rch_team_member_client_links",
        "rch_assets",
        "rch_skills",
        "rch_team_member_skills",
        "rch_task_skill_requirements",
        "rch_assignments",
        "rch_assignment_asset_links",
        "rch_checklists",
        "rch_checklist_templates",
        "rch_checklist_columns",
        "rch_checklist_tasks",
        "rch_checklist_cells",
        "rch_checklist_feed_publications",
        "rch_command_results",
        "rch_identity_capabilities",
        "rch_mission_access_assignments",
        "rch_subject_operation_rights",
        "rch_settings",
    ] {
        transaction.execute(&format!("DELETE FROM {table}"), [])?;
    }
    Ok(())
}

fn migrate_topics(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(source, target, report, "topics", |row| {
        let created = datetime_ms(row, "created_at")?;
        Ok(InsertRow::one_key(
            "rch_topics",
            "topic_id",
            text(row, "id")?,
            json!({
                "topic_id": text(row, "id")?,
                "topic_name": text(row, "name")?,
                "topic_path": text(row, "path")?,
                "topic_description": opt_text(row, "description")?.unwrap_or_default(),
                "retention": "persistent",
                "visibility": "public",
                "created_ts_ms": created,
                "last_activity_ts_ms": created
            }),
        ))
    })
}

fn migrate_subscribers(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(source, target, report, "subscribers", |row| {
        let created = datetime_ms(row, "created_at")?;
        let node_id = opt_text(row, "destination")?.unwrap_or(text(row, "id")?);
        Ok(InsertRow::two_key(
            "rch_subscribers",
            ("node_id", node_id.clone()),
            ("topic_id", text(row, "topic_id")?),
            json!({
                "node_id": node_id,
                "topic_id": text(row, "topic_id")?,
                "first_seen_ts_ms": created,
                "last_seen_ts_ms": created,
                "reject_tests": opt_i64(row, "reject_tests")?,
                "metadata": json_value(row, "metadata")?
            }),
        ))
    })
}

fn migrate_messages(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(source, target, report, "chat_messages", |row| {
        let topic_id = opt_text(row, "topic_id")?;
        let destination = opt_text(row, "destination")?;
        let delivery_mode = if destination
            .as_deref()
            .is_some_and(|value| !value.is_empty())
        {
            "targeted"
        } else if topic_id.as_deref().is_some_and(|value| !value.is_empty()) {
            "fanout"
        } else {
            "broadcast"
        };
        Ok(InsertRow::one_key(
            "rch_messages",
            "message_id",
            text(row, "id")?,
            json!({
                "message_id": text(row, "id")?,
                "topic_id": topic_id,
                "destination": destination,
                "sender": opt_text(row, "source")?.unwrap_or_else(|| "legacy-python".to_string()),
                "content": text(row, "content")?,
                "delivery_mode": delivery_mode,
                "delivery_method": "legacy_python",
                "delivery_policy_reason": "python_migration",
                "delivery_state": text(row, "state")?,
                "delivery_metadata": json_value(row, "delivery_metadata")?,
                "created_ts_ms": datetime_ms(row, "created_at")?,
                "attachments": chat_attachments(row, "attachments")?
            }),
        ))
    })
}

fn migrate_clients(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(source, target, report, "clients", |row| {
        let last_seen = datetime_ms(row, "last_seen")?;
        Ok(InsertRow::one_key(
            "rch_clients",
            "identity",
            text(row, "identity")?,
            json!({
                "identity": text(row, "identity")?,
                "first_seen_ts_ms": last_seen,
                "last_seen_ts_ms": last_seen
            }),
        ))
    })
}

fn migrate_identity_announces(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(source, target, report, "identity_announces", |row| {
        Ok(InsertRow::one_key(
            "rch_identity_announces",
            "destination_hash",
            text(row, "destination_hash")?,
            json!({
                "destination_hash": text(row, "destination_hash")?,
                "announced_identity_hash": Value::Null,
                "display_name": opt_text(row, "display_name")?,
                "source_interface": opt_text(row, "source_interface")?,
                "announce_capabilities": [],
                "client_type": "generic_lxmf",
                "first_seen_ts_ms": datetime_ms(row, "first_seen")?,
                "last_seen_ts_ms": datetime_ms(row, "last_seen")?
            }),
        ))
    })
}

fn migrate_identity_states(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(source, target, report, "identity_states", |row| {
        Ok(InsertRow::one_key(
            "rch_identity_states",
            "identity",
            text(row, "identity")?,
            json!({
                "identity": text(row, "identity")?,
                "is_banned": bool_value(row, "is_banned")?,
                "is_blackholed": bool_value(row, "is_blackholed")?,
                "updated_ts_ms": datetime_ms(row, "updated_at")?
            }),
        ))
    })
}

fn migrate_identity_rem_modes(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    if !table_exists(source, "identity_rem_modes")? {
        return Ok(());
    }
    migrate_rows(source, target, report, "identity_rem_modes", |row| {
        Ok(InsertRow::one_key(
            "rch_identity_rem_modes",
            "identity",
            text(row, "identity")?,
            json!({
                "identity": text(row, "identity")?,
                "mode": text(row, "mode")?,
                "updated_ts_ms": datetime_ms(row, "updated_at")?
            }),
        ))
    })
}

fn migrate_markers(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(source, target, report, "markers", |row| {
        let local_id = text(row, "id")?;
        let object_hash =
            opt_text(row, "object_destination_hash")?.unwrap_or_else(|| local_id.clone());
        Ok(InsertRow::one_key(
            "rch_markers",
            "object_destination_hash",
            object_hash.clone(),
            json!({
                "local_id": local_id,
                "object_destination_hash": object_hash,
                "origin_rch": opt_text(row, "origin_rch")?.unwrap_or_else(|| "legacy-python".to_string()),
                "marker_type": text(row, "marker_type")?,
                "symbol": text(row, "symbol")?,
                "name": text(row, "name")?,
                "category": text(row, "category")?,
                "lat": f64_value(row, "lat")?,
                "lon": f64_value(row, "lon")?,
                "notes": opt_text(row, "notes")?,
                "created_ts_ms": datetime_ms(row, "created_at")?,
                "updated_ts_ms": datetime_ms(row, "updated_at")?
            }),
        ))
    })
}

fn migrate_zones(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(source, target, report, "zones", |row| {
        Ok(InsertRow::one_key(
            "rch_zones",
            "zone_id",
            text(row, "id")?,
            json!({
                "zone_id": text(row, "id")?,
                "name": text(row, "name")?,
                "points": json_value(row, "points")?,
                "created_ts_ms": datetime_ms(row, "created_at")?,
                "updated_ts_ms": datetime_ms(row, "updated_at")?
            }),
        ))
    })
}

fn migrate_missions(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    let mission_rde_roles = mission_rde_roles(source)?;
    if !mission_rde_roles.is_empty() {
        report
            .rows
            .insert("r3akt_mission_rde".to_string(), mission_rde_roles.len());
    }
    migrate_rows(source, target, report, "r3akt_missions", |row| {
        let uid = text(row, "uid")?;
        Ok(InsertRow::one_key(
            "rch_missions",
            "uid",
            uid.clone(),
            json!({
                "uid": uid,
                "mission_name": text(row, "mission_name")?,
                "description": opt_text(row, "description")?.unwrap_or_default(),
                "topic_id": opt_text(row, "topic_id")?,
                "path": opt_text(row, "path")?,
                "classification": opt_text(row, "classification")?,
                "tool": opt_text(row, "tool")?,
                "keywords": json_array(row, "keywords")?,
                "parent_uid": opt_text(row, "parent_uid")?,
                "feeds": json_array(row, "feeds")?,
                "password_hash": opt_text(row, "password_hash")?,
                "default_role": opt_text(row, "default_role")?,
                "mission_priority": opt_i64(row, "mission_priority")?,
                "mission_status": opt_text(row, "mission_status")?.unwrap_or_else(|| "MISSION_ACTIVE".to_string()),
                "owner_role": opt_text(row, "owner_role")?,
                "token": opt_text(row, "token")?,
                "invite_only": bool_value(row, "invite_only")?,
                "expiration": opt_text(row, "expiration")?,
                "mission_rde_role": mission_rde_roles.get(&text(row, "uid")?).cloned(),
                "created_ts_ms": datetime_ms(row, "created_at")?,
                "updated_ts_ms": datetime_ms(row, "updated_at")?
            }),
        ))
    })
}

fn mission_rde_roles(
    source: &Connection,
) -> Result<BTreeMap<String, String>, Box<dyn std::error::Error>> {
    let mut roles = BTreeMap::new();
    if !table_exists(source, "r3akt_mission_rde")? {
        return Ok(roles);
    }
    let mut statement = source.prepare("SELECT mission_uid, role FROM r3akt_mission_rde")?;
    let rows = statement.query_map([], |row| {
        Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
    })?;
    for row in rows {
        let (mission_uid, role) = row?;
        roles.insert(mission_uid, role);
    }
    Ok(roles)
}

fn migrate_mission_changes(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(source, target, report, "r3akt_mission_changes", |row| {
        Ok(InsertRow::one_key(
            "rch_mission_changes",
            "uid",
            text(row, "uid")?,
            json!({
                "uid": text(row, "uid")?,
                "mission_uid": text(row, "mission_uid")?,
                "name": opt_text(row, "name")?,
                "team_member_rns_identity": opt_text(row, "team_member_rns_identity")?,
                "timestamp_ms": datetime_ms(row, "timestamp")?,
                "notes": opt_text(row, "notes")?,
                "change_type": opt_text(row, "change_type")?.unwrap_or_else(|| "legacy_python".to_string()),
                "is_federated_change": bool_value(row, "is_federated_change")?,
                "hashes": json_array(row, "hashes")?,
                "delta": json_value(row, "delta")?
            }),
        ))
    })
}

fn migrate_log_entries(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(source, target, report, "r3akt_log_entries", |row| {
        Ok(InsertRow::one_key(
            "rch_log_entries",
            "entry_uid",
            text(row, "entry_uid")?,
            json!({
                "entry_uid": text(row, "entry_uid")?,
                "mission_uid": text(row, "mission_uid")?,
                "callsign": opt_text(row, "callsign")?,
                "content": text(row, "content")?,
                "server_time_ms": datetime_ms(row, "server_time")?,
                "client_time": opt_text(row, "client_time")?,
                "content_hashes": json_array(row, "content_hashes")?,
                "keywords": json_array(row, "keywords")?,
                "created_ts_ms": datetime_ms(row, "created_at")?,
                "updated_ts_ms": datetime_ms(row, "updated_at")?
            }),
        ))
    })
}

fn migrate_file_records(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(source, target, report, "file_records", |row| {
        let file_id = u64_value(row, "id")?;
        let category = text(row, "category")?;
        Ok(InsertRow::one_key(
            "rch_file_attachments",
            "file_id",
            file_id.to_string(),
            json!({
                "file_id": file_id,
                "name": text(row, "name")?,
                "path": text(row, "path")?,
                "category": category.clone(),
                "size": u64_value(row, "size")?,
                "media_type": opt_text(row, "media_type")?,
                "topic_id": opt_text(row, "topic_id")?,
                "created_ts_ms": datetime_ms(row, "created_at")?,
                "updated_ts_ms": datetime_ms(row, "updated_at")?
            }),
        )
        .with_column("category", category))
    })
}

fn migrate_eams(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(source, target, report, "emergency_action_messages", |row| {
        let id = text(row, "id")?;
        let callsign = text(row, "callsign")?;
        let team_member_uid = opt_text(row, "subject_id")?.unwrap_or_default();
        let team_uid = text(row, "team_id")?;
        Ok(InsertRow::one_key(
            "rch_eam_snapshots",
            "eam_uid",
            id.clone(),
            json!({
                "eam_uid": id,
                "callsign": callsign.clone(),
                "group_name": Value::Null,
                "team_member_uid": team_member_uid.clone(),
                "team_uid": team_uid.clone(),
                "reported_by": opt_text(row, "reported_by")?,
                "reported_ts_ms": datetime_ms(row, "reported_at")?,
                "overall_status": text(row, "overall_status")?,
                "security_status": text(row, "security_status")?,
                "capability_status": text(row, "capability_status")?,
                "preparedness_status": text(row, "preparedness_status")?,
                "medical_status": text(row, "medical_status")?,
                "mobility_status": text(row, "mobility_status")?,
                "comms_status": text(row, "comms_status")?,
                "notes": opt_text(row, "notes")?,
                "confidence": opt_f64(row, "confidence")?,
                "ttl_seconds": opt_i64(row, "ttl_seconds")?,
                "source": opt_text(row, "source")?.map(Value::String),
                "updated_ts_ms": datetime_ms(row, "updated_at")?,
                "deleted_ts_ms": Value::Null
            }),
        )
        .with_column("callsign", callsign)
        .with_column("team_member_uid", team_member_uid)
        .with_column("team_uid", team_uid))
    })
}

fn migrate_teams(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(source, target, report, "r3akt_teams", |row| {
        let mission_uid = opt_text(row, "mission_uid")?;
        Ok(InsertRow::one_key(
            "rch_teams",
            "uid",
            text(row, "uid")?,
            json!({
                "uid": text(row, "uid")?,
                "mission_uid": mission_uid,
                "mission_uids": mission_uid.into_iter().collect::<Vec<_>>(),
                "color": opt_text(row, "color")?,
                "team_name": text(row, "team_name")?,
                "team_description": opt_text(row, "team_description")?.unwrap_or_default(),
                "created_ts_ms": datetime_ms(row, "created_at")?,
                "updated_ts_ms": datetime_ms(row, "updated_at")?
            }),
        ))
    })
}

fn migrate_team_members(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(source, target, report, "r3akt_team_members", |row| {
        Ok(InsertRow::one_key(
            "rch_team_members",
            "uid",
            text(row, "uid")?,
            json!({
                "uid": text(row, "uid")?,
                "team_uid": opt_text(row, "team_uid")?,
                "rns_identity": text(row, "rns_identity")?,
                "display_name": text(row, "display_name")?,
                "icon": opt_text(row, "icon")?,
                "role": opt_text(row, "role")?,
                "callsign": opt_text(row, "callsign")?,
                "freq": opt_f64(row, "freq")?,
                "email": opt_text(row, "email")?,
                "phone": opt_text(row, "phone")?,
                "modulation": opt_text(row, "modulation")?,
                "availability": opt_text(row, "availability")?,
                "certifications": json_array(row, "certifications")?,
                "last_active": opt_text(row, "last_active")?,
                "client_identities": [],
                "created_ts_ms": datetime_ms(row, "created_at")?,
                "updated_ts_ms": datetime_ms(row, "updated_at")?
            }),
        ))
    })
}

fn migrate_assets(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(source, target, report, "r3akt_assets", |row| {
        Ok(InsertRow::one_key(
            "rch_assets",
            "asset_uid",
            text(row, "asset_uid")?,
            json!({
                "asset_uid": text(row, "asset_uid")?,
                "team_member_uid": opt_text(row, "team_member_uid")?,
                "name": text(row, "name")?,
                "asset_type": text(row, "asset_type")?,
                "serial_number": opt_text(row, "serial_number")?,
                "status": text(row, "status")?,
                "location": opt_text(row, "location")?,
                "notes": opt_text(row, "notes")?,
                "created_ts_ms": datetime_ms(row, "created_at")?,
                "updated_ts_ms": datetime_ms(row, "updated_at")?
            }),
        ))
    })
}

fn migrate_skills(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(source, target, report, "r3akt_skills", |row| {
        Ok(InsertRow::one_key(
            "rch_skills",
            "skill_uid",
            text(row, "skill_uid")?,
            json!({
                "skill_uid": text(row, "skill_uid")?,
                "name": text(row, "name")?,
                "category": opt_text(row, "category")?,
                "description": opt_text(row, "description")?,
                "proficiency_scale": opt_text(row, "proficiency_scale")?,
                "created_ts_ms": datetime_ms(row, "created_at")?,
                "updated_ts_ms": datetime_ms(row, "updated_at")?
            }),
        ))
    })
}

fn migrate_team_member_skills(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(source, target, report, "r3akt_team_member_skills", |row| {
        Ok(InsertRow::two_key(
            "rch_team_member_skills",
            (
                "team_member_rns_identity",
                text(row, "team_member_rns_identity")?,
            ),
            ("skill_uid", text(row, "skill_uid")?),
            json!({
                "uid": text(row, "uid")?,
                "team_member_rns_identity": text(row, "team_member_rns_identity")?,
                "skill_uid": text(row, "skill_uid")?,
                "level": i64_value(row, "level")?,
                "validated_by": opt_text(row, "validated_by")?,
                "validated_at": opt_text(row, "validated_at")?,
                "expires_at": opt_text(row, "expires_at")?
            }),
        ))
    })
}

fn migrate_task_skill_requirements(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(
        source,
        target,
        report,
        "r3akt_task_skill_requirements",
        |row| {
            Ok(InsertRow::two_key(
                "rch_task_skill_requirements",
                ("task_uid", text(row, "task_uid")?),
                ("skill_uid", text(row, "skill_uid")?),
                json!({
                    "uid": text(row, "uid")?,
                    "task_uid": text(row, "task_uid")?,
                    "skill_uid": text(row, "skill_uid")?,
                    "minimum_level": i64_value(row, "minimum_level")?,
                    "is_mandatory": bool_value(row, "is_mandatory")?
                }),
            ))
        },
    )
}

fn migrate_assignments(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(
        source,
        target,
        report,
        "r3akt_mission_task_assignments",
        |row| {
            Ok(InsertRow::one_key(
                "rch_assignments",
                "assignment_uid",
                text(row, "assignment_uid")?,
                json!({
                    "assignment_uid": text(row, "assignment_uid")?,
                    "mission_uid": text(row, "mission_uid")?,
                    "task_uid": text(row, "task_uid")?,
                    "team_member_rns_identity": text(row, "team_member_rns_identity")?,
                    "assigned_by": opt_text(row, "assigned_by")?,
                    "assigned_ts_ms": datetime_ms(row, "assigned_at")?,
                    "due_dtg": opt_text(row, "due_dtg")?,
                    "status": text(row, "status")?,
                    "notes": opt_text(row, "notes")?,
                    "assets": json_array(row, "assets")?
                }),
            ))
        },
    )
}

fn migrate_checklist_templates(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(source, target, report, "r3akt_checklist_templates", |row| {
        Ok(InsertRow::one_key(
            "rch_checklist_templates",
            "uid",
            text(row, "uid")?,
            json!({
                "uid": text(row, "uid")?,
                "template_name": text(row, "template_name")?,
                "description": opt_text(row, "description")?.unwrap_or_default(),
                "created_by_team_member_rns_identity": text(row, "created_by_team_member_rns_identity")?,
                "source_template_uid": opt_text(row, "source_template_uid")?,
                "server_only": bool_value(row, "server_only")?,
                "created_ts_ms": datetime_ms(row, "created_at")?,
                "updated_ts_ms": datetime_ms(row, "updated_at")?
            }),
        ))
    })
}

fn migrate_checklists(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(source, target, report, "r3akt_checklists", |row| {
        Ok(InsertRow::one_key(
            "rch_checklists",
            "uid",
            text(row, "uid")?,
            json!({
                "uid": text(row, "uid")?,
                "mission_uid": opt_text(row, "mission_uid")?,
                "template_uid": opt_text(row, "template_uid")?,
                "template_version": opt_i64(row, "template_version")?,
                "template_name": opt_text(row, "template_name")?,
                "name": text(row, "name")?,
                "description": text(row, "description")?,
                "start_ts_ms": datetime_ms(row, "start_time")?,
                "mode": text(row, "mode")?,
                "sync_state": text(row, "sync_state")?,
                "origin_type": text(row, "origin_type")?,
                "checklist_status": text(row, "checklist_status")?,
                "created_by_team_member_rns_identity": text(row, "created_by_team_member_rns_identity")?,
                "created_ts_ms": datetime_ms(row, "created_at")?,
                "updated_ts_ms": datetime_ms(row, "updated_at")?,
                "uploaded_ts_ms": opt_datetime_ms(row, "uploaded_at")?,
                "progress_percent": f64_value(row, "progress_percent")?,
                "pending_count": i64_value(row, "pending_count")?,
                "late_count": i64_value(row, "late_count")?,
                "complete_count": i64_value(row, "complete_count")?
            }),
        ))
    })
}

fn migrate_checklist_columns(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(source, target, report, "r3akt_checklist_columns", |row| {
        let checklist_uid = opt_text(row, "checklist_uid")?;
        let template_uid = opt_text(row, "template_uid")?;
        Ok(InsertRow::one_key(
            "rch_checklist_columns",
            "column_uid",
            text(row, "column_uid")?,
            json!({
                "column_uid": text(row, "column_uid")?,
                "checklist_uid": checklist_uid.clone(),
                "template_uid": template_uid.clone(),
                "column_name": text(row, "column_name")?,
                "display_order": i64_value(row, "display_order")?,
                "column_type": text(row, "column_type")?,
                "column_editable": bool_value(row, "column_editable")?,
                "background_color": opt_text(row, "background_color")?,
                "text_color": opt_text(row, "text_color")?,
                "is_removable": bool_value(row, "is_removable")?,
                "system_key": opt_text(row, "system_key")?,
                "created_ts_ms": datetime_ms(row, "created_at")?,
                "updated_ts_ms": datetime_ms(row, "updated_at")?
            }),
        )
        .with_optional_text_column("checklist_uid", checklist_uid)
        .with_optional_text_column("template_uid", template_uid))
    })
}

fn migrate_checklist_tasks(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(source, target, report, "r3akt_checklist_tasks", |row| {
        let task_uid = text(row, "task_uid")?;
        let checklist_uid = text(row, "checklist_uid")?;
        Ok(InsertRow::one_key(
            "rch_checklist_tasks",
            "task_uid",
            task_uid.clone(),
            json!({
                "task_uid": task_uid,
                "checklist_uid": checklist_uid.clone(),
                "number": i64_value(row, "number")?,
                "user_status": text(row, "user_status")?,
                "task_status": text(row, "task_status")?,
                "is_late": bool_value(row, "is_late")?,
                "custom_status": opt_i64(row, "custom_status")?.map(|value| value.to_string()),
                "due_relative_minutes": opt_i64(row, "due_relative_minutes")?,
                "due_ts_ms": opt_datetime_ms(row, "due_dtg")?,
                "notes": opt_text(row, "notes")?,
                "row_background_color": opt_text(row, "row_background_color")?,
                "line_break_enabled": bool_value(row, "line_break_enabled")?,
                "completed_ts_ms": opt_datetime_ms(row, "completed_at")?,
                "completed_by_team_member_rns_identity": opt_text(row, "completed_by_team_member_rns_identity")?,
                "legacy_value": opt_text(row, "legacy_value")?,
                "created_ts_ms": datetime_ms(row, "created_at")?,
                "updated_ts_ms": datetime_ms(row, "updated_at")?
            }),
        )
        .with_column("checklist_uid", checklist_uid))
    })
}

fn migrate_checklist_cells(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(source, target, report, "r3akt_checklist_cells", |row| {
        let cell_uid = text(row, "cell_uid")?;
        let task_uid = text(row, "task_uid")?;
        let column_uid = text(row, "column_uid")?;
        Ok(InsertRow::one_key(
            "rch_checklist_cells",
            "cell_uid",
            cell_uid.clone(),
            json!({
                "cell_uid": cell_uid,
                "task_uid": task_uid.clone(),
                "column_uid": column_uid.clone(),
                "value": opt_text(row, "value")?,
                "updated_ts_ms": datetime_ms(row, "updated_at")?,
                "updated_by_team_member_rns_identity": opt_text(row, "updated_by_team_member_rns_identity")?
            }),
        )
        .with_column("task_uid", task_uid)
        .with_column("column_uid", column_uid))
    })
}

fn migrate_checklist_feed_publications(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(
        source,
        target,
        report,
        "r3akt_checklist_feed_publications",
        |row| {
            let publication_uid = text(row, "publication_uid")?;
            let checklist_uid = text(row, "checklist_uid")?;
            let mission_feed_uid = text(row, "mission_feed_uid")?;
            let published_ts_ms = datetime_ms(row, "published_at")?;
            Ok(InsertRow::one_key(
                    "rch_checklist_feed_publications",
                    "publication_uid",
                    publication_uid.clone(),
                    json!({
                        "publication_uid": publication_uid,
                        "checklist_uid": checklist_uid.clone(),
                        "mission_feed_uid": mission_feed_uid.clone(),
                        "published_ts_ms": published_ts_ms,
                        "published_by_team_member_rns_identity": text(row, "published_by_team_member_rns_identity")?
                    }),
                )
                .with_column("checklist_uid", checklist_uid)
                .with_column("mission_feed_uid", mission_feed_uid)
                .with_i64_column("published_ts_ms", published_ts_ms))
        },
    )
}

fn migrate_identity_capabilities(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(
        source,
        target,
        report,
        "identity_capability_grants",
        |row| {
            Ok(InsertRow::two_key(
                "rch_identity_capabilities",
                ("identity", text(row, "identity")?),
                ("capability", text(row, "capability")?),
                json!({
                    "identity": text(row, "identity")?,
                    "capability": text(row, "capability")?
                }),
            ))
        },
    )
}

fn migrate_mission_access_assignments(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(
        source,
        target,
        report,
        "mission_access_assignments",
        |row| {
            Ok(InsertRow::three_key(
                "rch_mission_access_assignments",
                ("mission_uid", text(row, "mission_uid")?),
                ("subject_type", text(row, "subject_type")?),
                ("subject_id", text(row, "subject_id")?),
                json!({
                    "mission_uid": text(row, "mission_uid")?,
                    "subject_type": text(row, "subject_type")?,
                    "subject_id": text(row, "subject_id")?,
                    "role": text(row, "role")?
                }),
            ))
        },
    )
}

fn migrate_subject_operation_rights(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(source, target, report, "subject_operation_grants", |row| {
        Ok(InsertRow::five_key(
            "rch_subject_operation_rights",
            ("subject_type", text(row, "subject_type")?),
            ("subject_id", text(row, "subject_id")?),
            ("operation", text(row, "operation")?),
            ("scope_type", text(row, "scope_type")?),
            ("scope_id", text(row, "scope_id")?),
            json!({
                "grant_uid": text(row, "grant_uid")?,
                "subject_type": text(row, "subject_type")?,
                "subject_id": text(row, "subject_id")?,
                "operation": text(row, "operation")?,
                "scope_type": text(row, "scope_type")?,
                "scope_id": text(row, "scope_id")?,
                "granted": bool_value(row, "granted")?
            }),
        ))
    })
}

#[derive(Clone, Copy)]
struct SimpleLinkSpec {
    source_table: &'static str,
    target_table: &'static str,
    target_columns: (&'static str, &'static str),
    source_columns: (&'static str, &'static str),
}

fn migrate_simple_links(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
    spec: SimpleLinkSpec,
) -> Result<(), Box<dyn std::error::Error>> {
    migrate_rows(source, target, report, spec.source_table, |row| {
        let left = text(row, spec.source_columns.0)?;
        let right = text(row, spec.source_columns.1)?;
        Ok(InsertRow::two_key(
            spec.target_table,
            (spec.target_columns.0, left.clone()),
            (spec.target_columns.1, right.clone()),
            json!({
                spec.target_columns.0: left,
                spec.target_columns.1: right
            }),
        ))
    })
}

fn migrate_rows<F>(
    source: &Connection,
    target: &Transaction<'_>,
    report: &mut PythonMigrationReport,
    source_table: &'static str,
    mut convert: F,
) -> Result<(), Box<dyn std::error::Error>>
where
    F: FnMut(&Row<'_>) -> Result<InsertRow, Box<dyn std::error::Error>>,
{
    if !table_exists(source, source_table)? {
        return Ok(());
    }
    let mut statement = source.prepare(&format!("SELECT * FROM {source_table}"))?;
    let mut rows = statement.query([])?;
    let mut count = 0_usize;
    while let Some(row) = rows.next()? {
        let insert = convert(row)?;
        insert.apply(target)?;
        count += 1;
    }
    report.rows.insert(source_table.to_string(), count);
    Ok(())
}

struct InsertRow {
    table: &'static str,
    columns: Vec<(&'static str, SqlValue)>,
    payload: Value,
}

impl InsertRow {
    fn one_key(table: &'static str, key_column: &'static str, key: String, payload: Value) -> Self {
        Self {
            table,
            columns: vec![(key_column, SqlValue::Text(key))],
            payload,
        }
    }

    fn two_key(
        table: &'static str,
        left: (&'static str, String),
        right: (&'static str, String),
        payload: Value,
    ) -> Self {
        Self {
            table,
            columns: vec![
                (left.0, SqlValue::Text(left.1)),
                (right.0, SqlValue::Text(right.1)),
            ],
            payload,
        }
    }

    fn three_key(
        table: &'static str,
        first: (&'static str, String),
        second: (&'static str, String),
        third: (&'static str, String),
        payload: Value,
    ) -> Self {
        Self {
            table,
            columns: vec![
                (first.0, SqlValue::Text(first.1)),
                (second.0, SqlValue::Text(second.1)),
                (third.0, SqlValue::Text(third.1)),
            ],
            payload,
        }
    }

    fn five_key(
        table: &'static str,
        first: (&'static str, String),
        second: (&'static str, String),
        third: (&'static str, String),
        fourth: (&'static str, String),
        fifth: (&'static str, String),
        payload: Value,
    ) -> Self {
        Self {
            table,
            columns: vec![
                (first.0, SqlValue::Text(first.1)),
                (second.0, SqlValue::Text(second.1)),
                (third.0, SqlValue::Text(third.1)),
                (fourth.0, SqlValue::Text(fourth.1)),
                (fifth.0, SqlValue::Text(fifth.1)),
            ],
            payload,
        }
    }

    fn with_column(mut self, column: &'static str, value: String) -> Self {
        self.columns.push((column, SqlValue::Text(value)));
        self
    }

    fn with_optional_text_column(mut self, column: &'static str, value: Option<String>) -> Self {
        self.columns
            .push((column, value.map_or(SqlValue::Null, SqlValue::Text)));
        self
    }

    fn with_i64_column(mut self, column: &'static str, value: i64) -> Self {
        self.columns.push((column, SqlValue::Integer(value)));
        self
    }

    fn apply(&self, target: &Transaction<'_>) -> Result<(), Box<dyn std::error::Error>> {
        let payload = rmp_serde::to_vec_named(&self.payload)?;
        let mut columns = self
            .columns
            .iter()
            .map(|(column, _)| *column)
            .collect::<Vec<_>>();
        columns.push("payload");
        let placeholders = (1..=columns.len())
            .map(|index| format!("?{index}"))
            .collect::<Vec<_>>();
        let mut values = self
            .columns
            .iter()
            .map(|(_, value)| value.clone())
            .collect::<Vec<_>>();
        values.push(SqlValue::Blob(payload));
        target.execute(
            &format!(
                "INSERT OR REPLACE INTO {} ({}) VALUES ({})",
                self.table,
                columns.join(", "),
                placeholders.join(", ")
            ),
            params_from_iter(values),
        )?;
        Ok(())
    }
}

fn table_exists(connection: &Connection, table: &str) -> rusqlite::Result<bool> {
    connection.query_row(
        "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?1)",
        [table],
        |row| row.get::<_, bool>(0),
    )
}

fn record_unmapped_tables(
    source: &Connection,
    report: &mut PythonMigrationReport,
) -> Result<(), Box<dyn std::error::Error>> {
    let mapped = BTreeSet::from([
        "topics",
        "subscribers",
        "chat_messages",
        "clients",
        "identity_announces",
        "identity_states",
        "identity_rem_modes",
        "markers",
        "zones",
        "r3akt_missions",
        "r3akt_mission_rde",
        "r3akt_mission_changes",
        "r3akt_log_entries",
        "file_records",
        "emergency_action_messages",
        "r3akt_teams",
        "r3akt_mission_team_links",
        "r3akt_mission_zone_links",
        "r3akt_mission_marker_links",
        "r3akt_team_members",
        "r3akt_team_member_client_links",
        "r3akt_assets",
        "r3akt_skills",
        "r3akt_team_member_skills",
        "r3akt_task_skill_requirements",
        "r3akt_mission_task_assignments",
        "r3akt_assignment_assets",
        "r3akt_checklist_templates",
        "r3akt_checklists",
        "r3akt_checklist_columns",
        "r3akt_checklist_tasks",
        "r3akt_checklist_cells",
        "r3akt_checklist_feed_publications",
        "identity_capability_grants",
        "mission_access_assignments",
        "subject_operation_grants",
    ]);
    let mut statement = source.prepare(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'",
    )?;
    let rows = statement.query_map([], |row| row.get::<_, String>(0))?;
    for row in rows {
        let table = row?;
        if !mapped.contains(table.as_str()) {
            report.warnings.push(format!(
                "legacy table '{table}' has no Rust snapshot target yet"
            ));
        }
    }
    Ok(())
}

fn text(row: &Row<'_>, column: &str) -> rusqlite::Result<String> {
    Ok(opt_text(row, column)?.unwrap_or_default())
}

fn opt_text(row: &Row<'_>, column: &str) -> rusqlite::Result<Option<String>> {
    let value: Option<String> = row.get(column)?;
    Ok(value.and_then(|value| {
        let trimmed = value.trim();
        if trimmed.is_empty() {
            None
        } else {
            Some(trimmed.to_string())
        }
    }))
}

fn i64_value(row: &Row<'_>, column: &str) -> rusqlite::Result<i64> {
    Ok(opt_i64(row, column)?.unwrap_or_default())
}

fn opt_i64(row: &Row<'_>, column: &str) -> rusqlite::Result<Option<i64>> {
    row.get(column)
}

fn u64_value(row: &Row<'_>, column: &str) -> rusqlite::Result<u64> {
    let value = i64_value(row, column)?;
    Ok(u64::try_from(value).unwrap_or_default())
}

fn f64_value(row: &Row<'_>, column: &str) -> rusqlite::Result<f64> {
    Ok(opt_f64(row, column)?.unwrap_or_default())
}

fn opt_f64(row: &Row<'_>, column: &str) -> rusqlite::Result<Option<f64>> {
    row.get(column)
}

fn bool_value(row: &Row<'_>, column: &str) -> rusqlite::Result<bool> {
    let value: Option<i64> = row.get(column)?;
    Ok(value.unwrap_or_default() != 0)
}

fn json_value(row: &Row<'_>, column: &str) -> rusqlite::Result<Value> {
    let Some(value) = opt_text(row, column)? else {
        return Ok(Value::Object(Map::new()));
    };
    Ok(serde_json::from_str(&value).unwrap_or(Value::String(value)))
}

fn json_array(row: &Row<'_>, column: &str) -> rusqlite::Result<Value> {
    match json_value(row, column)? {
        Value::Array(values) => Ok(Value::Array(values)),
        Value::Null => Ok(Value::Array(Vec::new())),
        Value::Object(values) if values.is_empty() => Ok(Value::Array(Vec::new())),
        value if value.as_str().is_some_and(str::is_empty) => Ok(Value::Array(Vec::new())),
        value => Ok(Value::Array(vec![value])),
    }
}

fn chat_attachments(row: &Row<'_>, column: &str) -> rusqlite::Result<Value> {
    let Value::Array(values) = json_array(row, column)? else {
        return Ok(Value::Array(Vec::new()));
    };
    let attachments = values
        .into_iter()
        .filter_map(|value| {
            let object = value.as_object()?;
            let mut attachment = Map::new();
            attachment.insert(
                "file_id".to_string(),
                json!(json_u64(object, &["file_id", "FileID", "id", "ID"]).unwrap_or_default()),
            );
            attachment.insert(
                "category".to_string(),
                json!(json_string(object, &["category", "Category"]).unwrap_or_default()),
            );
            attachment.insert(
                "name".to_string(),
                json!(json_string(object, &["name", "Name"]).unwrap_or_default()),
            );
            attachment.insert(
                "size".to_string(),
                json!(json_u64(object, &["size", "Size"]).unwrap_or_default()),
            );
            attachment.insert(
                "media_type".to_string(),
                json_string(object, &["media_type", "mediaType", "MediaType"])
                    .map_or(Value::Null, Value::String),
            );
            Some(Value::Object(attachment))
        })
        .collect::<Vec<_>>();
    Ok(Value::Array(attachments))
}

fn json_string(object: &Map<String, Value>, keys: &[&str]) -> Option<String> {
    keys.iter()
        .find_map(|key| object.get(*key).and_then(Value::as_str).map(str::to_string))
}

fn json_u64(object: &Map<String, Value>, keys: &[&str]) -> Option<u64> {
    keys.iter().find_map(|key| {
        object.get(*key).and_then(|value| {
            value
                .as_u64()
                .or_else(|| value.as_str().and_then(|text| text.parse().ok()))
        })
    })
}

fn datetime_ms(row: &Row<'_>, column: &str) -> rusqlite::Result<i64> {
    Ok(opt_datetime_ms(row, column)?.unwrap_or_default())
}

fn opt_datetime_ms(row: &Row<'_>, column: &str) -> rusqlite::Result<Option<i64>> {
    Ok(opt_text(row, column)?.and_then(|value| parse_datetime_ms(&value)))
}

fn parse_datetime_ms(value: &str) -> Option<i64> {
    if let Ok(ms) = value.parse::<i64>() {
        return Some(ms);
    }
    if let Ok(timestamp) = OffsetDateTime::parse(value, &Rfc3339) {
        return nanos_to_ms(timestamp.unix_timestamp_nanos());
    }
    parse_python_datetime_ms(value)
}

fn parse_python_datetime_ms(value: &str) -> Option<i64> {
    let normalized = value.trim().trim_end_matches('Z').replace('T', " ");
    let mut parts = normalized.split_whitespace();
    let date = parts.next()?;
    let time = parts.next()?;
    let mut date_parts = date.split('-');
    let year = date_parts.next()?.parse::<i32>().ok()?;
    let month = Month::try_from(date_parts.next()?.parse::<u8>().ok()?).ok()?;
    let day = date_parts.next()?.parse::<u8>().ok()?;
    let mut time_parts = time.split(':');
    let hour = time_parts.next()?.parse::<u8>().ok()?;
    let minute = time_parts.next()?.parse::<u8>().ok()?;
    let second_part = time_parts.next()?;
    let (second_text, fraction_text) = second_part
        .split_once('.')
        .map_or((second_part, ""), |(second, fraction)| (second, fraction));
    let second = second_text.parse::<u8>().ok()?;
    let nanos = if fraction_text.is_empty() {
        0
    } else {
        let padded = format!("{fraction_text:0<9}");
        padded.get(..9)?.parse::<u32>().ok()?
    };
    let date = Date::from_calendar_date(year, month, day).ok()?;
    let time = Time::from_hms_nano(hour, minute, second, nanos).ok()?;
    nanos_to_ms(
        PrimitiveDateTime::new(date, time)
            .assume_utc()
            .unix_timestamp_nanos(),
    )
}

fn nanos_to_ms(nanos: i128) -> Option<i64> {
    i64::try_from(nanos / 1_000_000).ok()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::RchSqliteStore;
    use rusqlite::Connection;
    use serde_json::json;
    use uuid::Uuid;

    #[test]
    fn migrates_python_identity_and_topic_tables_into_rust_snapshot() {
        let legacy_path = std::env::temp_dir().join(format!(
            "r3akt-python-migration-legacy-{}.sqlite3",
            Uuid::new_v4()
        ));
        let target_path = std::env::temp_dir().join(format!(
            "r3akt-python-migration-target-{}.sqlite3",
            Uuid::new_v4()
        ));
        create_minimal_legacy_database(&legacy_path);

        let report = migrate_python_database(&legacy_path, &target_path).expect("migration");

        assert_eq!(report.rows["topics"], 1);
        assert_eq!(report.rows["clients"], 1);
        assert_eq!(report.rows["identity_announces"], 1);
        let store = RchSqliteStore::open(&target_path).expect("target store");
        let snapshot = store
            .load_snapshot()
            .expect("load snapshot")
            .expect("snapshot");
        assert_eq!(snapshot.topics[0].topic_id, "ops");
        assert_eq!(snapshot.topics[0].topic_name, "Ops");
        assert_eq!(
            snapshot.clients[0].identity,
            "11112222333344445555666677778888"
        );
        assert_eq!(
            snapshot.identity_announces[0].destination_hash,
            "aaaabbbbccccddddeeeeffff00001111"
        );
        assert!(snapshot.identity_states[0].is_banned);

        let _ = std::fs::remove_file(legacy_path);
        let _ = std::fs::remove_file(target_path);
    }

    #[test]
    fn migrates_python_r3akt_operational_tables_into_rust_snapshot() {
        let legacy_path = std::env::temp_dir().join(format!(
            "r3akt-python-migration-legacy-r3akt-{}.sqlite3",
            Uuid::new_v4()
        ));
        let target_path = std::env::temp_dir().join(format!(
            "r3akt-python-migration-target-r3akt-{}.sqlite3",
            Uuid::new_v4()
        ));
        create_r3akt_operational_legacy_database(&legacy_path);

        let report = migrate_python_database(&legacy_path, &target_path).expect("migration");

        for table in [
            "markers",
            "zones",
            "r3akt_missions",
            "r3akt_mission_rde",
            "r3akt_mission_changes",
            "r3akt_log_entries",
            "file_records",
            "emergency_action_messages",
            "r3akt_teams",
            "r3akt_team_members",
            "r3akt_mission_team_links",
            "r3akt_mission_zone_links",
            "r3akt_mission_marker_links",
            "r3akt_team_member_client_links",
            "r3akt_assets",
            "r3akt_skills",
            "r3akt_team_member_skills",
            "r3akt_task_skill_requirements",
            "r3akt_mission_task_assignments",
            "r3akt_assignment_assets",
            "r3akt_checklist_templates",
            "r3akt_checklists",
            "r3akt_checklist_columns",
            "r3akt_checklist_tasks",
            "r3akt_checklist_cells",
            "r3akt_checklist_feed_publications",
            "identity_capability_grants",
            "mission_access_assignments",
            "subject_operation_grants",
        ] {
            assert_eq!(report.rows[table], 1, "row count for {table}");
        }
        assert_eq!(
            report.warnings,
            vec!["legacy table 'r3akt_domain_events' has no Rust snapshot target yet"]
        );

        let store = RchSqliteStore::open(&target_path).expect("target store");
        let snapshot = store
            .load_snapshot()
            .expect("load snapshot")
            .expect("snapshot");

        assert_eq!(snapshot.markers[0].object_destination_hash, "marker-hash");
        assert_eq!(snapshot.markers[0].origin_rch, "legacy-python");
        assert!((snapshot.zones[0].points[0].lat - 45.5).abs() < f64::EPSILON);
        assert_eq!(
            snapshot.missions[0].mission_rde_role.as_deref(),
            Some("rescue")
        );
        assert!(snapshot.missions[0].invite_only);
        assert_eq!(
            snapshot.mission_changes[0].delta["status"],
            "MISSION_ACTIVE"
        );
        assert_eq!(snapshot.log_entries[0].content_hashes, vec!["hash-1"]);
        assert_eq!(snapshot.file_attachments[0].file_id, 42);
        assert_eq!(snapshot.eam_snapshots[0].team_member_uid, "member-1");
        assert_eq!(snapshot.teams[0].mission_uids, vec!["mission-1"]);
        assert_eq!(snapshot.team_members[0].certifications, vec!["medic"]);
        assert_eq!(snapshot.mission_team_links[0].team_uid, "team-1");
        assert_eq!(snapshot.mission_zone_links[0].zone_id, "zone-1");
        assert_eq!(snapshot.mission_marker_links[0].marker_id, "marker-hash");
        assert_eq!(
            snapshot.team_member_client_links[0].client_identity,
            "client-identity"
        );
        assert_eq!(snapshot.assets[0].asset_type, "radio");
        assert_eq!(snapshot.skills[0].proficiency_scale.as_deref(), Some("1-5"));
        assert_eq!(snapshot.team_member_skills[0].level, 4);
        assert!(snapshot.task_skill_requirements[0].is_mandatory);
        assert_eq!(snapshot.assignments[0].assets, vec!["asset-1"]);
        assert_eq!(snapshot.assignment_asset_links[0].asset_uid, "asset-1");
        assert_eq!(
            snapshot.checklist_templates[0].template_name,
            "SAR Template"
        );
        assert_eq!(snapshot.checklists[0].complete_count, 1);
        assert_eq!(
            snapshot.checklist_columns[0].system_key.as_deref(),
            Some("task")
        );
        assert_eq!(
            snapshot.checklist_tasks[0].custom_status.as_deref(),
            Some("7")
        );
        assert_eq!(
            snapshot.checklist_cells[0].value.as_deref(),
            Some("Sweep sector")
        );
        assert_eq!(
            snapshot.checklist_feed_publications[0].mission_feed_uid,
            "feed-1"
        );
        assert_eq!(
            snapshot.identity_capabilities[0].capability,
            "mission.write"
        );
        assert_eq!(snapshot.mission_access_assignments[0].role, "owner");
        assert!(snapshot.subject_operation_rights[0].granted);

        let _ = std::fs::remove_file(legacy_path);
        let _ = std::fs::remove_file(target_path);
    }

    fn create_minimal_legacy_database(path: &Path) {
        let db = Connection::open(path).expect("legacy db");
        db.execute_batch(
            r"
            CREATE TABLE topics (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                path VARCHAR NOT NULL,
                description VARCHAR,
                created_at DATETIME NOT NULL
            );
            CREATE TABLE clients (
                identity VARCHAR PRIMARY KEY,
                last_seen DATETIME NOT NULL,
                metadata JSON
            );
            CREATE TABLE identity_announces (
                destination_hash VARCHAR PRIMARY KEY,
                display_name VARCHAR,
                first_seen DATETIME NOT NULL,
                last_seen DATETIME NOT NULL,
                source_interface VARCHAR
            );
            CREATE TABLE identity_states (
                identity VARCHAR PRIMARY KEY,
                is_banned BOOLEAN NOT NULL,
                is_blackholed BOOLEAN NOT NULL,
                updated_at DATETIME NOT NULL
            );
            CREATE TABLE chat_messages (
                id VARCHAR PRIMARY KEY,
                direction VARCHAR NOT NULL,
                scope VARCHAR NOT NULL,
                state VARCHAR NOT NULL,
                content VARCHAR NOT NULL,
                source VARCHAR,
                destination VARCHAR,
                topic_id VARCHAR,
                attachments JSON,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                delivery_metadata JSON
            );
            ",
        )
        .expect("schema");
        db.execute(
            "INSERT INTO topics (id, name, path, description, created_at) VALUES (?1, ?2, ?3, ?4, ?5)",
            ("ops", "Ops", "/ops", "operations", "2026-05-12 10:11:12.000000"),
        )
        .expect("topic");
        db.execute(
            "INSERT INTO clients (identity, last_seen, metadata) VALUES (?1, ?2, ?3)",
            (
                "11112222333344445555666677778888",
                "2026-05-12 10:12:12.000000",
                json!({}).to_string(),
            ),
        )
        .expect("client");
        db.execute(
            "INSERT INTO identity_announces (destination_hash, display_name, first_seen, last_seen, source_interface) VALUES (?1, ?2, ?3, ?4, ?5)",
            (
                "aaaabbbbccccddddeeeeffff00001111",
                "Alpha",
                "2026-05-12 10:00:00.000000",
                "2026-05-12 10:15:00.000000",
                "destination",
            ),
        )
        .expect("announce");
        db.execute(
            "INSERT INTO identity_states (identity, is_banned, is_blackholed, updated_at) VALUES (?1, ?2, ?3, ?4)",
            (
                "11112222333344445555666677778888",
                1_i64,
                0_i64,
                "2026-05-12 10:16:00.000000",
            ),
        )
        .expect("state");
        db.execute(
            "INSERT INTO chat_messages (id, direction, scope, state, content, source, destination, topic_id, attachments, created_at, updated_at, delivery_metadata) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)",
            (
                "msg-1",
                "inbound",
                "topic",
                "received",
                "hello",
                "11112222333344445555666677778888",
                Option::<String>::None,
                "ops",
                json!([]).to_string(),
                "2026-05-12 10:17:00.000000",
                "2026-05-12 10:17:00.000000",
                json!({}).to_string(),
            ),
        )
        .expect("message");
    }

    fn create_r3akt_operational_legacy_database(path: &Path) {
        let db = Connection::open(path).expect("legacy db");
        db.execute_batch(
            r#"
            CREATE TABLE markers (
                id VARCHAR PRIMARY KEY,
                object_destination_hash VARCHAR,
                origin_rch VARCHAR,
                marker_type VARCHAR NOT NULL,
                symbol VARCHAR NOT NULL,
                name VARCHAR NOT NULL,
                category VARCHAR NOT NULL,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                notes VARCHAR,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
            INSERT INTO markers VALUES (
                'marker-local', 'marker-hash', NULL, 'point', 'a-f-G-U-C',
                'Primary LZ', 'landing-zone', 45.4, -63.6, 'clear approach',
                '2026-05-12 10:00:00.000000', '2026-05-12 10:05:00.000000'
            );

            CREATE TABLE zones (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                points JSON NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
            INSERT INTO zones VALUES (
                'zone-1', 'Search Box',
                '[{"lat":45.5,"lon":-63.5},{"lat":45.6,"lon":-63.4}]',
                '2026-05-12 10:00:00.000000', '2026-05-12 10:05:00.000000'
            );

            CREATE TABLE r3akt_missions (
                uid VARCHAR PRIMARY KEY,
                mission_name VARCHAR NOT NULL,
                description VARCHAR,
                topic_id VARCHAR,
                path VARCHAR,
                classification VARCHAR,
                tool VARCHAR,
                keywords JSON,
                parent_uid VARCHAR,
                feeds JSON,
                password_hash VARCHAR,
                default_role VARCHAR,
                mission_priority INTEGER,
                mission_status VARCHAR,
                owner_role VARCHAR,
                token VARCHAR,
                invite_only BOOLEAN NOT NULL,
                expiration VARCHAR,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
            INSERT INTO r3akt_missions VALUES (
                'mission-1', 'Storm Response', 'Coastal SAR', 'ops',
                '/mission/storm', 'UNCLASSIFIED', 'R3AKT', '["sar","storm"]',
                NULL, '["feed-1"]', NULL, 'viewer', 2, 'MISSION_ACTIVE',
                'owner', 'token-1', 1, NULL,
                '2026-05-12 10:00:00.000000', '2026-05-12 10:05:00.000000'
            );
            CREATE TABLE r3akt_mission_rde (mission_uid VARCHAR PRIMARY KEY, role VARCHAR NOT NULL);
            INSERT INTO r3akt_mission_rde VALUES ('mission-1', 'rescue');

            CREATE TABLE r3akt_mission_changes (
                uid VARCHAR PRIMARY KEY,
                mission_uid VARCHAR NOT NULL,
                name VARCHAR,
                team_member_rns_identity VARCHAR,
                timestamp DATETIME NOT NULL,
                notes VARCHAR,
                change_type VARCHAR,
                is_federated_change BOOLEAN NOT NULL,
                hashes JSON,
                delta JSON
            );
            INSERT INTO r3akt_mission_changes VALUES (
                'change-1', 'mission-1', 'Mission activated', 'member-rns',
                '2026-05-12 10:06:00.000000', 'ready', 'status', 1,
                '["hash-1"]', '{"status":"MISSION_ACTIVE"}'
            );

            CREATE TABLE r3akt_log_entries (
                entry_uid VARCHAR PRIMARY KEY,
                mission_uid VARCHAR NOT NULL,
                callsign VARCHAR,
                content VARCHAR NOT NULL,
                server_time DATETIME NOT NULL,
                client_time VARCHAR,
                content_hashes JSON,
                keywords JSON,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
            INSERT INTO r3akt_log_entries VALUES (
                'log-1', 'mission-1', 'ALPHA', 'Team inserted',
                '2026-05-12 10:07:00.000000', '2026-05-12T10:07:00Z',
                '["hash-1"]', '["insert"]',
                '2026-05-12 10:07:00.000000', '2026-05-12 10:07:00.000000'
            );

            CREATE TABLE file_records (
                id INTEGER PRIMARY KEY,
                name VARCHAR NOT NULL,
                path VARCHAR NOT NULL,
                category VARCHAR NOT NULL,
                size INTEGER NOT NULL,
                media_type VARCHAR,
                topic_id VARCHAR,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
            INSERT INTO file_records VALUES (
                42, 'photo.jpg', 'files/photo.jpg', 'image', 2048,
                'image/jpeg', 'ops',
                '2026-05-12 10:08:00.000000', '2026-05-12 10:08:00.000000'
            );

            CREATE TABLE emergency_action_messages (
                id VARCHAR PRIMARY KEY,
                callsign VARCHAR NOT NULL,
                subject_id VARCHAR,
                team_id VARCHAR NOT NULL,
                reported_by VARCHAR,
                reported_at DATETIME NOT NULL,
                overall_status VARCHAR NOT NULL,
                security_status VARCHAR NOT NULL,
                capability_status VARCHAR NOT NULL,
                preparedness_status VARCHAR NOT NULL,
                medical_status VARCHAR NOT NULL,
                mobility_status VARCHAR NOT NULL,
                comms_status VARCHAR NOT NULL,
                notes VARCHAR,
                confidence REAL,
                ttl_seconds INTEGER,
                source JSON,
                updated_at DATETIME NOT NULL
            );
            INSERT INTO emergency_action_messages VALUES (
                'eam-1', 'ALPHA', 'member-1', 'team-1', 'ops-chief',
                '2026-05-12 10:09:00.000000', 'green', 'green', 'amber',
                'green', 'green', 'green', 'green', 'nominal', 0.9, 600,
                '{"feed":"manual"}', '2026-05-12 10:10:00.000000'
            );

            CREATE TABLE r3akt_teams (
                uid VARCHAR PRIMARY KEY,
                mission_uid VARCHAR,
                color VARCHAR,
                team_name VARCHAR NOT NULL,
                team_description VARCHAR,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
            INSERT INTO r3akt_teams VALUES (
                'team-1', 'mission-1', '#ff0000', 'Alpha', 'Ground team',
                '2026-05-12 10:11:00.000000', '2026-05-12 10:11:00.000000'
            );

            CREATE TABLE r3akt_team_members (
                uid VARCHAR PRIMARY KEY,
                team_uid VARCHAR,
                rns_identity VARCHAR NOT NULL,
                display_name VARCHAR NOT NULL,
                icon VARCHAR,
                role VARCHAR,
                callsign VARCHAR,
                freq REAL,
                email VARCHAR,
                phone VARCHAR,
                modulation VARCHAR,
                availability VARCHAR,
                certifications JSON,
                last_active VARCHAR,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
            INSERT INTO r3akt_team_members VALUES (
                'member-1', 'team-1', 'member-rns', 'Alice', NULL, 'medic',
                'ALPHA', 146.52, 'alice@example.invalid', '555-0100', 'FM',
                'available', '["medic"]', '2026-05-12T10:11:00Z',
                '2026-05-12 10:11:00.000000', '2026-05-12 10:11:00.000000'
            );

            CREATE TABLE r3akt_mission_team_links (mission_uid VARCHAR NOT NULL, team_uid VARCHAR NOT NULL);
            INSERT INTO r3akt_mission_team_links VALUES ('mission-1', 'team-1');
            CREATE TABLE r3akt_mission_zone_links (mission_uid VARCHAR NOT NULL, zone_id VARCHAR NOT NULL);
            INSERT INTO r3akt_mission_zone_links VALUES ('mission-1', 'zone-1');
            CREATE TABLE r3akt_mission_marker_links (mission_uid VARCHAR NOT NULL, marker_id VARCHAR NOT NULL);
            INSERT INTO r3akt_mission_marker_links VALUES ('mission-1', 'marker-hash');
            CREATE TABLE r3akt_team_member_client_links (team_member_uid VARCHAR NOT NULL, client_identity VARCHAR NOT NULL);
            INSERT INTO r3akt_team_member_client_links VALUES ('member-1', 'client-identity');

            CREATE TABLE r3akt_assets (
                asset_uid VARCHAR PRIMARY KEY,
                team_member_uid VARCHAR,
                name VARCHAR NOT NULL,
                asset_type VARCHAR NOT NULL,
                serial_number VARCHAR,
                status VARCHAR NOT NULL,
                location VARCHAR,
                notes VARCHAR,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
            INSERT INTO r3akt_assets VALUES (
                'asset-1', 'member-1', 'Radio', 'radio', 'SN-1', 'ready',
                'kit', 'charged',
                '2026-05-12 10:12:00.000000', '2026-05-12 10:12:00.000000'
            );

            CREATE TABLE r3akt_skills (
                skill_uid VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                category VARCHAR,
                description VARCHAR,
                proficiency_scale VARCHAR,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
            INSERT INTO r3akt_skills VALUES (
                'skill-1', 'Medical', 'field', 'First aid', '1-5',
                '2026-05-12 10:13:00.000000', '2026-05-12 10:13:00.000000'
            );

            CREATE TABLE r3akt_team_member_skills (
                uid VARCHAR PRIMARY KEY,
                team_member_rns_identity VARCHAR NOT NULL,
                skill_uid VARCHAR NOT NULL,
                level INTEGER NOT NULL,
                validated_by VARCHAR,
                validated_at VARCHAR,
                expires_at VARCHAR
            );
            INSERT INTO r3akt_team_member_skills VALUES (
                'member-skill-1', 'member-rns', 'skill-1', 4,
                'lead', '2026-05-12T10:13:00Z', NULL
            );

            CREATE TABLE r3akt_task_skill_requirements (
                uid VARCHAR PRIMARY KEY,
                task_uid VARCHAR NOT NULL,
                skill_uid VARCHAR NOT NULL,
                minimum_level INTEGER NOT NULL,
                is_mandatory BOOLEAN NOT NULL
            );
            INSERT INTO r3akt_task_skill_requirements VALUES (
                'requirement-1', 'task-1', 'skill-1', 3, 1
            );

            CREATE TABLE r3akt_mission_task_assignments (
                assignment_uid VARCHAR PRIMARY KEY,
                mission_uid VARCHAR NOT NULL,
                task_uid VARCHAR NOT NULL,
                team_member_rns_identity VARCHAR NOT NULL,
                assigned_by VARCHAR,
                assigned_at DATETIME NOT NULL,
                due_dtg VARCHAR,
                status VARCHAR NOT NULL,
                notes VARCHAR,
                assets JSON
            );
            INSERT INTO r3akt_mission_task_assignments VALUES (
                'assignment-1', 'mission-1', 'task-1', 'member-rns', 'lead',
                '2026-05-12 10:14:00.000000', '2026-05-12T12:00:00Z',
                'assigned', 'take asset', '["asset-1"]'
            );
            CREATE TABLE r3akt_assignment_assets (assignment_uid VARCHAR NOT NULL, asset_uid VARCHAR NOT NULL);
            INSERT INTO r3akt_assignment_assets VALUES ('assignment-1', 'asset-1');

            CREATE TABLE r3akt_checklist_templates (
                uid VARCHAR PRIMARY KEY,
                template_name VARCHAR NOT NULL,
                description VARCHAR,
                created_by_team_member_rns_identity VARCHAR NOT NULL,
                source_template_uid VARCHAR,
                server_only BOOLEAN NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
            INSERT INTO r3akt_checklist_templates VALUES (
                'template-1', 'SAR Template', 'Search pattern',
                'member-rns', NULL, 1,
                '2026-05-12 10:15:00.000000', '2026-05-12 10:15:00.000000'
            );

            CREATE TABLE r3akt_checklists (
                uid VARCHAR PRIMARY KEY,
                mission_uid VARCHAR,
                template_uid VARCHAR,
                template_version INTEGER,
                template_name VARCHAR,
                name VARCHAR NOT NULL,
                description VARCHAR NOT NULL,
                start_time DATETIME NOT NULL,
                mode VARCHAR NOT NULL,
                sync_state VARCHAR NOT NULL,
                origin_type VARCHAR NOT NULL,
                checklist_status VARCHAR NOT NULL,
                created_by_team_member_rns_identity VARCHAR NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                uploaded_at DATETIME,
                progress_percent REAL NOT NULL,
                pending_count INTEGER NOT NULL,
                late_count INTEGER NOT NULL,
                complete_count INTEGER NOT NULL
            );
            INSERT INTO r3akt_checklists VALUES (
                'checklist-1', 'mission-1', 'template-1', 1, 'SAR Template',
                'Sector Sweep', 'Sweep assigned sector',
                '2026-05-12 10:16:00.000000', 'shared', 'synced', 'mission',
                'active', 'member-rns',
                '2026-05-12 10:16:00.000000', '2026-05-12 10:16:00.000000',
                NULL, 50.0, 1, 0, 1
            );

            CREATE TABLE r3akt_checklist_columns (
                column_uid VARCHAR PRIMARY KEY,
                checklist_uid VARCHAR,
                template_uid VARCHAR,
                column_name VARCHAR NOT NULL,
                display_order INTEGER NOT NULL,
                column_type VARCHAR NOT NULL,
                column_editable BOOLEAN NOT NULL,
                background_color VARCHAR,
                text_color VARCHAR,
                is_removable BOOLEAN NOT NULL,
                system_key VARCHAR,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
            INSERT INTO r3akt_checklist_columns VALUES (
                'column-1', 'checklist-1', 'template-1', 'Task', 1, 'text', 1,
                '#ffffff', '#000000', 0, 'task',
                '2026-05-12 10:17:00.000000', '2026-05-12 10:17:00.000000'
            );

            CREATE TABLE r3akt_checklist_tasks (
                task_uid VARCHAR PRIMARY KEY,
                checklist_uid VARCHAR NOT NULL,
                number INTEGER NOT NULL,
                user_status VARCHAR NOT NULL,
                task_status VARCHAR NOT NULL,
                is_late BOOLEAN NOT NULL,
                custom_status INTEGER,
                due_relative_minutes INTEGER,
                due_dtg DATETIME,
                notes VARCHAR,
                row_background_color VARCHAR,
                line_break_enabled BOOLEAN NOT NULL,
                completed_at DATETIME,
                completed_by_team_member_rns_identity VARCHAR,
                legacy_value VARCHAR,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
            INSERT INTO r3akt_checklist_tasks VALUES (
                'task-1', 'checklist-1', 1, 'in_progress', 'open', 0, 7, 30,
                '2026-05-12 11:00:00.000000', 'north side', NULL, 1, NULL,
                NULL, 'legacy task text',
                '2026-05-12 10:18:00.000000', '2026-05-12 10:18:00.000000'
            );

            CREATE TABLE r3akt_checklist_cells (
                cell_uid VARCHAR PRIMARY KEY,
                task_uid VARCHAR NOT NULL,
                column_uid VARCHAR NOT NULL,
                value VARCHAR,
                updated_at DATETIME NOT NULL,
                updated_by_team_member_rns_identity VARCHAR
            );
            INSERT INTO r3akt_checklist_cells VALUES (
                'cell-1', 'task-1', 'column-1', 'Sweep sector',
                '2026-05-12 10:19:00.000000', 'member-rns'
            );

            CREATE TABLE r3akt_checklist_feed_publications (
                publication_uid VARCHAR PRIMARY KEY,
                checklist_uid VARCHAR NOT NULL,
                mission_feed_uid VARCHAR NOT NULL,
                published_at DATETIME NOT NULL,
                published_by_team_member_rns_identity VARCHAR NOT NULL
            );
            INSERT INTO r3akt_checklist_feed_publications VALUES (
                'publication-1', 'checklist-1', 'feed-1',
                '2026-05-12 10:20:00.000000', 'member-rns'
            );

            CREATE TABLE identity_capability_grants (
                identity VARCHAR NOT NULL,
                capability VARCHAR NOT NULL
            );
            INSERT INTO identity_capability_grants VALUES ('member-rns', 'mission.write');

            CREATE TABLE mission_access_assignments (
                mission_uid VARCHAR NOT NULL,
                subject_type VARCHAR NOT NULL,
                subject_id VARCHAR NOT NULL,
                role VARCHAR NOT NULL
            );
            INSERT INTO mission_access_assignments VALUES ('mission-1', 'identity', 'member-rns', 'owner');

            CREATE TABLE subject_operation_grants (
                grant_uid VARCHAR PRIMARY KEY,
                subject_type VARCHAR NOT NULL,
                subject_id VARCHAR NOT NULL,
                operation VARCHAR NOT NULL,
                scope_type VARCHAR NOT NULL,
                scope_id VARCHAR NOT NULL,
                granted BOOLEAN NOT NULL
            );
            INSERT INTO subject_operation_grants VALUES (
                'grant-1', 'identity', 'member-rns', 'write', 'mission',
                'mission-1', 1
            );

            CREATE TABLE r3akt_domain_events (event_uid VARCHAR PRIMARY KEY);
            INSERT INTO r3akt_domain_events VALUES ('domain-event-1');
            "#,
        )
        .expect("schema");
    }
}
