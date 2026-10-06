use super::{
    Connection, IdentityAnnounceRecord, RchCoreError, RchSqliteStore, decode_msgpack,
    encode_msgpack, normalize_hash, params,
};
use rusqlite::OptionalExtension;
use std::collections::{BTreeMap, HashSet};

#[derive(Debug, Default)]
pub struct IdentityAnnounceSummary {
    pub total: usize,
    pub fresh: usize,
    pub oldest_stale: Option<(String, i64)>,
    pub recent: Vec<IdentityAnnounceRecord>,
}

impl RchSqliteStore {
    /// Read counts and at most ten payloads from one consistent `SQLite` snapshot.
    pub fn identity_announce_summary(
        &self,
        fresh_cutoff_ms: i64,
    ) -> Result<IdentityAnnounceSummary, RchCoreError> {
        let transaction = self.connection.unchecked_transaction()?;
        let total =
            transaction.query_row("SELECT COUNT(*) FROM rch_identity_announces", [], |row| {
                row.get(0)
            })?;
        let fresh = transaction.query_row(
            "SELECT COUNT(*) FROM rch_identity_announces WHERE last_seen_ts_ms >= ?1",
            [fresh_cutoff_ms],
            |row| row.get(0),
        )?;
        // Probe the timestamp index, then resolve equal timestamps in the same
        // raw destination order as the former full-history sort.
        let oldest_stale = transaction
            .query_row(
                "SELECT destination_hash, last_seen_ts_ms FROM rch_identity_announces
             WHERE last_seen_ts_ms = (
                 SELECT MIN(last_seen_ts_ms) FROM rch_identity_announces
                 WHERE last_seen_ts_ms < ?1
             ) ORDER BY destination_hash ASC LIMIT 1",
                [fresh_cutoff_ms],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .optional()?;
        let recent = {
            let mut statement = transaction.prepare(
                "SELECT payload FROM rch_identity_announces
                 ORDER BY last_seen_ts_ms DESC, destination_hash ASC LIMIT 10",
            )?;
            let mut rows = statement.query([])?;
            let mut records = Vec::with_capacity(10);
            while let Some(row) = rows.next()? {
                let payload: Vec<u8> = row.get(0)?;
                records.push(decode_msgpack(&payload)?);
            }
            records
        };
        transaction.commit()?;
        Ok(IdentityAnnounceSummary {
            total,
            fresh,
            oldest_stale,
            recent,
        })
    }

    /// Count missing subscribers against one consistent indexed snapshot.
    pub fn missing_identity_announce_count(
        &self,
        destinations: &[String],
    ) -> Result<usize, RchCoreError> {
        if destinations.is_empty() {
            return Ok(0);
        }
        let transaction = self.connection.unchecked_transaction()?;
        let missing = {
            let mut statement = transaction.prepare(
                "SELECT EXISTS(
                SELECT 1 FROM rch_identity_announces WHERE normalized_destination_hash = ?1
                UNION ALL
                SELECT 1 FROM rch_identity_announces WHERE normalized_announced_identity_hash = ?1
             )",
            )?;
            let mut missing = 0;
            for destination in destinations {
                let known = if let Some(destination) = normalize_hash(Some(destination)) {
                    statement.query_row([destination], |row| row.get::<_, bool>(0))?
                } else {
                    false
                };
                if !known {
                    missing += 1;
                }
            }
            missing
        };
        transaction.commit()?;
        Ok(missing)
    }

    /// Read only destination/announced-identity matches, preserving the full
    /// history reader's raw destination order and returning each row once.
    pub fn load_identity_announces_for_identities(
        &self,
        identities: &[String],
    ) -> Result<Vec<IdentityAnnounceRecord>, RchCoreError> {
        if identities.is_empty() {
            return Ok(Vec::new());
        }
        let transaction = self.connection.unchecked_transaction()?;
        let records = {
            let mut statement = transaction.prepare(
                "SELECT destination_hash, payload FROM rch_identity_announces
                 WHERE normalized_destination_hash = ?1
                 UNION ALL
                 SELECT destination_hash, payload FROM rch_identity_announces
                 WHERE normalized_announced_identity_hash = ?1",
            )?;
            let mut seen = HashSet::new();
            let mut payloads = BTreeMap::new();
            for identity in identities {
                let Some(identity) = normalize_hash(Some(identity)) else {
                    continue;
                };
                if !seen.insert(identity.clone()) {
                    continue;
                }
                let mut rows = statement.query([identity])?;
                while let Some(row) = rows.next()? {
                    payloads.insert(row.get::<_, String>(0)?, row.get::<_, Vec<u8>>(1)?);
                }
            }
            payloads
                .into_values()
                .map(|payload| decode_msgpack(&payload))
                .collect::<Result<Vec<_>, _>>()?
        };
        transaction.commit()?;
        Ok(records)
    }

    /// Probe indexed timestamps without decoding historical payloads.
    pub fn has_identity_announce_since_for_any(
        &self,
        identities: &[&str],
        cutoff_ts_ms: i64,
    ) -> Result<bool, RchCoreError> {
        if identities.is_empty() {
            return Ok(false);
        }
        let transaction = self.connection.unchecked_transaction()?;
        let found = {
            let mut statement = transaction.prepare(
                "SELECT EXISTS(
                    SELECT 1 FROM rch_identity_announces
                    WHERE normalized_destination_hash = ?1 AND last_seen_ts_ms >= ?2
                    UNION ALL
                    SELECT 1 FROM rch_identity_announces
                    WHERE normalized_announced_identity_hash = ?1 AND last_seen_ts_ms >= ?2
                 )",
            )?;
            let mut found = false;
            for identity in identities {
                let Some(identity) = normalize_hash(Some(identity)) else {
                    continue;
                };
                if statement
                    .query_row(params![identity, cutoff_ts_ms], |row| row.get::<_, bool>(0))?
                {
                    found = true;
                    break;
                }
            }
            found
        };
        transaction.commit()?;
        Ok(found)
    }

    pub fn has_identity_announce(&self, destination: &str) -> Result<bool, RchCoreError> {
        Ok(self.missing_identity_announce_count(&[destination.to_string()])? == 0)
    }
}

pub(super) fn write_identity_announce(
    connection: &Connection,
    record: &IdentityAnnounceRecord,
    replace: bool,
) -> Result<(), RchCoreError> {
    let sql = if replace {
        "INSERT OR REPLACE INTO rch_identity_announces (
            destination_hash, payload, last_seen_ts_ms,
            normalized_destination_hash, normalized_announced_identity_hash
         ) VALUES (?1, ?2, ?3, ?4, ?5)"
    } else {
        "INSERT INTO rch_identity_announces (
            destination_hash, payload, last_seen_ts_ms,
            normalized_destination_hash, normalized_announced_identity_hash
         ) VALUES (?1, ?2, ?3, ?4, ?5)"
    };
    connection.execute(
        sql,
        params![
            record.destination_hash,
            encode_msgpack(record)?,
            record.last_seen_ts_ms,
            normalize_hash(Some(&record.destination_hash)),
            normalize_hash(record.announced_identity_hash.as_deref()),
        ],
    )?;
    Ok(())
}

pub(super) fn backfill_identity_announce_projections(
    connection: &Connection,
) -> Result<(), RchCoreError> {
    let mut statement =
        connection.prepare("SELECT destination_hash, payload FROM rch_identity_announces")?;
    let mut rows = statement.query([])?;
    while let Some(row) = rows.next()? {
        let key: String = row.get(0)?;
        let payload: Vec<u8> = row.get(1)?;
        let record: IdentityAnnounceRecord = decode_msgpack(&payload)?;
        connection.execute(
            "UPDATE rch_identity_announces SET last_seen_ts_ms = ?2,
                normalized_destination_hash = ?3, normalized_announced_identity_hash = ?4
             WHERE destination_hash = ?1",
            params![
                key,
                record.last_seen_ts_ms,
                normalize_hash(Some(&record.destination_hash)),
                normalize_hash(record.announced_identity_hash.as_deref())
            ],
        )?;
    }
    Ok(())
}

#[cfg(test)]
mod tests;
