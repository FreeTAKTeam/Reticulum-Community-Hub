//! Transactional scalar identity directory. Historical payloads remain authoritative.
mod maintenance;
#[cfg(test)]
mod tests;

use super::{
    IdentityAnnounceRecord, IdentityRemModeRecord, IdentityStateRecord, RchCoreError,
    RchSqliteStore, decode_msgpack, normalize_hash,
};
pub(super) use maintenance::{columns, rebuild_compatibility};
use rusqlite::{params, types::Value as SqlValue};
use serde::Serialize;

#[derive(Debug, Clone, Default)]
pub struct IdentityDirectoryQuery {
    pub search: Option<String>,
    pub identity: Option<String>,
    pub client_type: Option<String>,
    pub recent_cutoff_ms: Option<i64>,
    pub newest_first: bool,
    pub offset: usize,
    pub limit: usize,
}
#[derive(Debug, Clone, Serialize)]
pub struct IdentityDirectoryClientOverlay {
    pub identity: String,
    pub display_name: Option<String>,
    pub voice_destination: Option<String>,
}
#[derive(Debug)]
pub struct IdentityDirectoryPage {
    pub total: usize,
    pub entries: Vec<IdentityDirectoryEntry>,
}
#[derive(Debug)]
pub struct IdentityDirectoryEntry {
    pub state: IdentityStateRecord,
    pub announce: Option<IdentityAnnounceRecord>,
    pub rem_mode: Option<IdentityRemModeRecord>,
    pub last_heard_ts_ms: Option<i64>,
}

// Search projections use Unicode lowercasing; source payloads and hash rules stay unchanged.
pub(super) fn search_text(value: Option<&str>) -> Option<String> {
    value
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .map(str::to_lowercase)
}

pub(super) fn client_type(value: &str) -> String {
    let value = value.trim().to_ascii_lowercase();
    if value.is_empty() {
        "generic_lxmf".into()
    } else {
        value
    }
}

const FILTER: &str = "WITH overlays AS MATERIALIZED (
    SELECT json_extract(value,'$.identity') AS identity,
        json_extract(value,'$.display_name') AS display_name,
        json_extract(value,'$.voice_destination') AS voice_destination
    FROM json_each(?1)
), eligible AS (
    SELECT d.*, CASE WHEN d.announce_key IS NULL THEN o.display_name ELSE d.display_name END AS effective_name
    FROM rch_identity_directory d LEFT JOIN overlays o ON o.identity=d.identity
    WHERE ($IDENTITY_MATCH)
      AND (?3 IS NULL OR d.client_type=?3)
      AND NOT EXISTS(SELECT 1 FROM overlays voice
        WHERE voice.voice_destination=d.identity AND voice.identity<>d.identity
          AND NOT EXISTS(SELECT 1 FROM rch_identity_announces annotation WHERE annotation.directory_owner=voice.identity))
      AND (?4 IS NULL OR d.last_heard_ts_ms>=?4 OR d.moderated=1 OR d.client_type='rem'
        OR EXISTS(SELECT 1 FROM overlays joined WHERE joined.identity=d.identity)
        OR EXISTS(SELECT 1 FROM rch_clients c WHERE c.identity_normalized=d.identity)
        OR EXISTS(SELECT 1 FROM rch_team_members m WHERE m.rns_identity_normalized=d.identity)
        OR EXISTS(SELECT 1 FROM rch_team_member_client_links l JOIN rch_team_members m ON m.uid=l.team_member_uid WHERE l.directory_identity=d.identity)
        OR EXISTS(SELECT 1 FROM rch_member_payload_clients l JOIN rch_team_members m ON m.uid=l.team_member_uid WHERE l.client_identity=d.identity))
), filtered AS (
    SELECT * FROM eligible WHERE ?5 IS NULL OR instr(identity,?5)>0
        OR instr(COALESCE(effective_name,''),?5)>0
        OR EXISTS(SELECT 1 FROM rch_identity_announces a WHERE a.directory_owner=eligible.identity AND instr(a.normalized_destination_hash,?5)>0)
) ";

const IDENTITY_MATCH: &str = "d.identity=COALESCE((
        SELECT a.directory_owner FROM rch_identity_announces a
        WHERE a.normalized_destination_hash=?2
          AND EXISTS(SELECT 1 FROM rch_identity_directory owner WHERE owner.identity=a.directory_owner)
        ORDER BY a.directory_priority DESC,a.destination_hash ASC LIMIT 1),?2)";

fn filter_sql(exact: bool) -> String {
    let predicate = if exact {
        IDENTITY_MATCH.to_string()
    } else {
        format!("?2 IS NULL OR {IDENTITY_MATCH}")
    };
    FILTER.replace("$IDENTITY_MATCH", &predicate)
}

fn page_sql(newest_first: bool, exact: bool) -> String {
    let order = if newest_first {
        "d.last_heard_ts_ms DESC,d.identity ASC"
    } else {
        "d.identity ASC"
    };
    let filter = filter_sql(exact);
    format!(
        "{filter} SELECT s.payload,a.payload,m.payload,d.last_heard_ts_ms
            FROM (SELECT * FROM filtered d ORDER BY {order} LIMIT ?6 OFFSET ?7) d
            JOIN rch_identity_states s ON s.identity=d.state_key
            LEFT JOIN rch_identity_announces a ON a.destination_hash=d.announce_key
            LEFT JOIN rch_identity_rem_modes m ON m.identity=d.mode_key
            ORDER BY {order}"
    )
}

impl RchSqliteStore {
    /// Filter/count scalar rows first; decode only the selected state, annotation and mode.
    /// Runtime overlays are caller-selected roster scalars, never historical client payloads.
    pub fn load_identity_directory_page(
        &self,
        query: &IdentityDirectoryQuery,
        overlays: &[IdentityDirectoryClientOverlay],
    ) -> Result<IdentityDirectoryPage, RchCoreError> {
        let transaction = self.connection.unchecked_transaction()?;
        let mut normalized = std::collections::BTreeMap::new();
        for overlay in overlays {
            if let Some(identity) = normalize_hash(Some(&overlay.identity)) {
                normalized.insert(
                    identity.clone(),
                    IdentityDirectoryClientOverlay {
                        identity,
                        display_name: search_text(overlay.display_name.as_deref()),
                        voice_destination: overlay
                            .voice_destination
                            .as_deref()
                            .and_then(|v| normalize_hash(Some(v))),
                    },
                );
            }
        }
        let overlays = serde_json::to_string(&normalized.into_values().collect::<Vec<_>>())
            .map_err(|e| RchCoreError::Encode(e.to_string()))?;
        let identity = query
            .identity
            .as_deref()
            .map(|v| normalize_hash(Some(v)).unwrap_or_default());
        let search = search_text(query.search.as_deref());
        let kind = query
            .client_type
            .as_deref()
            .map(client_type)
            .filter(|v| v != "all");
        let bindings = params![overlays, identity, kind, query.recent_cutoff_ms, search];
        let total = transaction.query_row(
            &format!(
                "{} SELECT COUNT(*) FROM filtered",
                filter_sql(query.identity.is_some())
            ),
            bindings,
            |r| super::sqlite_read_usize(r, 0),
        )?;
        let sql = page_sql(query.newest_first, query.identity.is_some());
        let entries = {
            let mut statement = transaction.prepare(&sql)?;
            let mut rows = statement.query(params![
                overlays,
                identity,
                kind,
                query.recent_cutoff_ms,
                search,
                i64::try_from(query.limit).unwrap_or(i64::MAX),
                i64::try_from(query.offset).unwrap_or(i64::MAX)
            ])?;
            let mut entries = Vec::new();
            while let Some(row) = rows.next()? {
                let state: Vec<u8> = row.get(0)?;
                let announce: Option<Vec<u8>> = row.get(1)?;
                let mode: Option<Vec<u8>> = row.get(2)?;
                entries.push(IdentityDirectoryEntry {
                    state: decode_msgpack(&state)?,
                    announce: announce.map(|v| decode_msgpack(&v)).transpose()?,
                    rem_mode: mode.map(|v| decode_msgpack(&v)).transpose()?,
                    last_heard_ts_ms: row.get(3)?,
                });
            }
            entries
        };
        transaction.commit()?;
        Ok(IdentityDirectoryPage { total, entries })
    }
}
