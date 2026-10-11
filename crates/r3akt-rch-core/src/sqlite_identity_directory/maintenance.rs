use super::{RchCoreError, RchSqliteStore, SqlValue, client_type, normalize_hash};
use rusqlite::{Connection, params_from_iter};
use serde::Serialize;
use serde_json::Value;

const SOURCES: &[(&str, &[(&str, &str)])] = &[
    (
        "rch_identity_states",
        &[
            ("directory_identity", "TEXT"),
            ("directory_moderated", "INTEGER"),
        ],
    ),
    (
        "rch_identity_announces",
        &[
            ("directory_owner", "TEXT"),
            ("directory_name", "TEXT"),
            ("directory_type", "TEXT"),
            ("directory_priority", "INTEGER"),
        ],
    ),
    ("rch_identity_rem_modes", &[("directory_identity", "TEXT")]),
    (
        "rch_team_member_client_links",
        &[("directory_identity", "TEXT")],
    ),
];

pub(crate) fn columns<T: Serialize>(
    table: &str,
    record: &T,
) -> Result<Vec<(&'static str, SqlValue)>, RchCoreError> {
    if !SOURCES.iter().any(|(name, _)| *name == table) {
        return Ok(Vec::new());
    }
    let value = serde_json::to_value(record).map_err(|e| RchCoreError::Encode(e.to_string()))?;
    let normalized = |field: &str| {
        value[field]
            .as_str()
            .and_then(|v| normalize_hash(Some(v)))
            .map_or(SqlValue::Null, SqlValue::Text)
    };
    let text = |field: &str| {
        super::search_text(value[field].as_str()).map_or(SqlValue::Null, SqlValue::Text)
    };
    Ok(match table {
        "rch_identity_states" => vec![
            ("directory_identity", normalized("identity")),
            (
                "directory_moderated",
                SqlValue::Integer(i64::from(
                    value["is_banned"].as_bool() == Some(true)
                        || value["is_blackholed"].as_bool() == Some(true),
                )),
            ),
        ],
        "rch_identity_rem_modes" => vec![("directory_identity", normalized("identity"))],
        "rch_team_member_client_links" => {
            vec![("directory_identity", normalized("client_identity"))]
        }
        "rch_identity_announces" => vec![
            (
                "directory_owner",
                value["announced_identity_hash"]
                    .as_str()
                    .and_then(|v| normalize_hash(Some(v)))
                    .or_else(|| {
                        value["destination_hash"]
                            .as_str()
                            .and_then(|v| normalize_hash(Some(v)))
                    })
                    .map_or(SqlValue::Null, SqlValue::Text),
            ),
            ("directory_name", text("display_name")),
            (
                "directory_type",
                SqlValue::Text(client_type(value["client_type"].as_str().unwrap_or(""))),
            ),
            (
                "directory_priority",
                SqlValue::Integer(i64::from(
                    value["source_interface"]
                        .as_str()
                        .is_some_and(|v| v.trim().eq_ignore_ascii_case("destination")),
                )),
            ),
        ],
        _ => unreachable!(),
    })
}

/// Compatibility snapshot/import writers backfill within their own transaction.
/// No record is deleted or re-encoded; only scalar columns are updated.
pub(crate) fn backfill(connection: &Connection) -> Result<(), RchCoreError> {
    rebuild(connection, true)
}

pub(crate) fn rebuild_compatibility(connection: &Connection) -> Result<(), RchCoreError> {
    rebuild(connection, false)
}

fn rebuild(connection: &Connection, include_announces: bool) -> Result<(), RchCoreError> {
    for (table, _) in SOURCES {
        if *table == "rch_identity_announces" && !include_announces {
            continue;
        }
        let mut statement = connection.prepare(&format!("SELECT rowid,payload FROM {table}"))?;
        let mut rows = statement.query([])?;
        while let Some(row) = rows.next()? {
            let rowid: i64 = row.get(0)?;
            let bytes: Vec<u8> = row.get(1)?;
            let value = validated_value(table, &bytes).map_err(|e| {
                RchCoreError::Decode(format!(
                    "identity directory rebuild {table} row {rowid}: {e}"
                ))
            })?;
            let columns = columns(table, &value)?;
            let assignments = columns
                .iter()
                .enumerate()
                .map(|(i, (column, _))| format!("{column}=?{}", i + 1))
                .collect::<Vec<_>>()
                .join(",");
            let mut values = columns.into_iter().map(|(_, v)| v).collect::<Vec<_>>();
            values.push(SqlValue::Integer(rowid));
            connection.execute(
                &format!(
                    "UPDATE {table} SET {assignments} WHERE rowid=?{}",
                    values.len()
                ),
                params_from_iter(values),
            )?;
        }
    }
    Ok(())
}

fn validated_value(table: &str, bytes: &[u8]) -> Result<Value, RchCoreError> {
    macro_rules! decoded {
        ($kind:ty) => {
            serde_json::to_value(super::super::decode_msgpack::<$kind>(bytes)?)
                .map_err(|e| RchCoreError::Encode(e.to_string()))
        };
    }
    match table {
        "rch_identity_states" => decoded!(super::super::IdentityStateRecord),
        "rch_identity_announces" => decoded!(super::super::IdentityAnnounceRecord),
        "rch_identity_rem_modes" => decoded!(super::super::IdentityRemModeRecord),
        "rch_team_member_client_links" => decoded!(super::super::TeamMemberClientLinkRecord),
        _ => Err(RchCoreError::Decode(format!(
            "unsupported identity projection source {table}"
        ))),
    }
}

// Every refresh addresses one normalized identity through indexed source probes.
// Raw state/mode MAX preserves the previous sorted-reader overwrite semantics.
fn refresh(key: &str) -> String {
    format!("DELETE FROM rch_identity_directory WHERE identity={key};
        INSERT INTO rch_identity_directory(identity,state_key,announce_key,mode_key,last_heard_ts_ms,display_name,client_type,moderated)
        SELECT s.directory_identity,s.identity,a.destination_hash,
            (SELECT MAX(m.identity) FROM rch_identity_rem_modes m WHERE m.directory_identity=s.directory_identity),
            (SELECT MAX(h.last_seen_ts_ms) FROM rch_identity_announces h WHERE h.directory_owner=s.directory_identity),
            a.directory_name,COALESCE(a.directory_type,'generic_lxmf'),s.directory_moderated
        FROM rch_identity_states s LEFT JOIN rch_identity_announces a ON a.destination_hash=(
            SELECT p.destination_hash FROM rch_identity_announces p WHERE p.directory_owner={key}
            ORDER BY p.directory_priority DESC,p.destination_hash ASC LIMIT 1)
        WHERE s.identity=(SELECT MAX(w.identity) FROM rch_identity_states w WHERE w.directory_identity={key});")
}

impl RchSqliteStore {
    pub(crate) fn migrate_identity_directory(&self) -> Result<(), RchCoreError> {
        let applied: bool = self.connection.query_row(
            "SELECT EXISTS(SELECT 1 FROM rch_schema_migrations WHERE version=7)",
            [],
            |r| r.get(0),
        )?;
        if applied {
            return Ok(());
        }
        self.backup_before_migration(7)?;
        let tx = rusqlite::Transaction::new_unchecked(
            &self.connection,
            rusqlite::TransactionBehavior::Immediate,
        )?;
        let applied: bool = tx.query_row(
            "SELECT EXISTS(SELECT 1 FROM rch_schema_migrations WHERE version=7)",
            [],
            |r| r.get(0),
        )?;
        if applied {
            tx.commit()?;
            return Ok(());
        }
        for (table, fields) in SOURCES {
            for (column, kind) in *fields {
                tx.execute(
                    &format!("ALTER TABLE {table} ADD COLUMN {column} {kind}"),
                    [],
                )?;
            }
        }
        tx.execute_batch("CREATE INDEX idx_rch_directory_states ON rch_identity_states(directory_identity,identity);
            CREATE INDEX idx_rch_directory_announces ON rch_identity_announces(directory_owner,directory_priority DESC,destination_hash);
            CREATE INDEX idx_rch_directory_heard ON rch_identity_announces(directory_owner,last_seen_ts_ms DESC);
            CREATE INDEX idx_rch_directory_modes ON rch_identity_rem_modes(directory_identity,identity);
            CREATE INDEX idx_rch_directory_member_clients ON rch_team_member_client_links(directory_identity,team_member_uid);
            CREATE TABLE rch_identity_directory(identity TEXT PRIMARY KEY,state_key TEXT NOT NULL,announce_key TEXT,mode_key TEXT,last_heard_ts_ms INTEGER,display_name TEXT,client_type TEXT NOT NULL,moderated INTEGER NOT NULL);
            CREATE INDEX idx_rch_directory_recency ON rch_identity_directory(last_heard_ts_ms DESC,identity);
            CREATE INDEX idx_rch_directory_type ON rch_identity_directory(client_type,identity);")?;
        for (table, column) in [
            ("rch_identity_states", "directory_identity"),
            ("rch_identity_announces", "directory_owner"),
            ("rch_identity_rem_modes", "directory_identity"),
        ] {
            for (event, keys) in [
                ("INSERT", vec!["new"]),
                ("DELETE", vec!["old"]),
                ("UPDATE", vec!["old", "new"]),
            ] {
                let body = keys
                    .iter()
                    .map(|prefix| refresh(&format!("{prefix}.{column}")))
                    .collect::<String>();
                let event = if event == "UPDATE" {
                    let fields = match table {
                        "rch_identity_states" => "directory_identity,directory_moderated",
                        "rch_identity_announces" => {
                            "directory_owner,directory_name,directory_type,directory_priority,last_seen_ts_ms"
                        }
                        _ => "directory_identity",
                    };
                    format!("UPDATE OF {fields}")
                } else {
                    event.to_string()
                };
                let suffix = event
                    .split_whitespace()
                    .next()
                    .unwrap_or("update")
                    .to_ascii_lowercase();
                tx.execute_batch(&format!("CREATE TRIGGER {table}_directory_{suffix} AFTER {event} ON {table} BEGIN {body} END;"))?;
            }
        }
        backfill(&tx)?;
        tx.execute(
            "INSERT INTO rch_schema_migrations VALUES(7,'indexed identity directory',?1)",
            [super::super::utc_now_ms()],
        )?;
        tx.execute(
            "INSERT OR REPLACE INTO rch_settings VALUES('schema_version','7')",
            [],
        )?;
        tx.commit()?;
        Ok(())
    }
}
