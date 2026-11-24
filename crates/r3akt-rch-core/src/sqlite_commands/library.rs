//! Mission Library catalog over the existing attachment registry (RCH #354).
//! `rch_file_attachments` stays untouched; mission links and published RPP
//! references are additive tables keyed by the legacy `FileID`.
use super::super::Connection;
use super::{
    FileAttachmentRecord, RchCommandTransaction, RchCoreError, RchSqliteStore, decode_msgpack,
    params,
};
use r3akt_library_core::{Availability, ItemKind, LibraryItem, RppReference, Source, rch_item_id};
use rusqlite::OptionalExtension;
use std::collections::BTreeMap;

pub(crate) fn initialize(connection: &Connection) -> Result<(), RchCoreError> {
    connection.execute_batch(
        "CREATE TABLE IF NOT EXISTS rch_library_mission_files(
            mission_uid TEXT NOT NULL,
            file_id INTEGER NOT NULL,
            linked_ts_ms INTEGER NOT NULL,
            PRIMARY KEY(mission_uid, file_id));
         CREATE INDEX IF NOT EXISTS idx_rch_library_mission_files_file
            ON rch_library_mission_files(file_id);
         CREATE TABLE IF NOT EXISTS rch_library_rpp_refs(
            file_id INTEGER PRIMARY KEY,
            package_destination TEXT NOT NULL,
            file_destination TEXT NOT NULL,
            manifest_hash TEXT NOT NULL,
            content_sha256 TEXT NOT NULL);
         CREATE TABLE IF NOT EXISTS rch_library_rpp_packages(
            file_id INTEGER PRIMARY KEY,
            package_token BLOB NOT NULL,
            manifest BLOB NOT NULL,
            publication BLOB NOT NULL);",
    )?;
    Ok(())
}

fn file_id(value: i64) -> Result<u64, RchCoreError> {
    u64::try_from(value).map_err(|e| RchCoreError::Decode(e.to_string()))
}

fn signed(value: u64) -> Result<i64, RchCoreError> {
    i64::try_from(value).map_err(|e| RchCoreError::Decode(e.to_string()))
}

fn item(
    record: FileAttachmentRecord,
    missions: Vec<String>,
    rpp: Option<(RppReference, String)>,
) -> LibraryItem {
    let kind = if record.category == "image" {
        ItemKind::Image
    } else {
        ItemKind::File
    };
    let (rpp, content_sha256) = rpp.map_or((None, None), |(r, sha)| (Some(r), Some(sha)));
    LibraryItem {
        item_id: rch_item_id(record.file_id),
        legacy_file_id: Some(record.file_id),
        kind,
        source: Source::Rch,
        availability: Availability::Remote,
        name: record.name,
        media_type: record.media_type,
        size: record.size,
        content_sha256,
        rpp,
        publisher: None,
        mission_uids: missions,
        team_uid: None,
        created_ts_ms: record.created_ts_ms,
        updated_ts_ms: record.updated_ts_ms,
    }
}

/// Every file and image attachment as catalog metadata, with its mission
/// links and published RPP reference. Callers authorize and filter with
/// `r3akt_library_core::LibraryQuery`.
pub(crate) fn load_items(connection: &Connection) -> Result<Vec<LibraryItem>, RchCoreError> {
    let mut missions: BTreeMap<u64, Vec<String>> = BTreeMap::new();
    let mut statement = connection.prepare(
        "SELECT file_id, mission_uid FROM rch_library_mission_files ORDER BY mission_uid",
    )?;
    for row in statement.query_map([], |row| {
        Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
    })? {
        let (id, mission) = row?;
        missions.entry(file_id(id)?).or_default().push(mission);
    }
    let mut refs = BTreeMap::new();
    let mut statement = connection.prepare(
        "SELECT file_id, package_destination, file_destination, manifest_hash, content_sha256 FROM rch_library_rpp_refs",
    )?;
    for row in statement.query_map([], |row| {
        Ok((
            row.get::<_, i64>(0)?,
            RppReference {
                package_destination: row.get(1)?,
                file_destination: row.get(2)?,
                manifest_hash: row.get(3)?,
            },
            row.get::<_, String>(4)?,
        ))
    })? {
        let (id, reference, sha) = row?;
        refs.insert(file_id(id)?, (reference, sha));
    }
    let mut statement = connection
        .prepare("SELECT payload FROM rch_file_attachments WHERE category IN ('file','image') ORDER BY file_id")?;
    let mut items = Vec::new();
    for row in statement.query_map([], |row| row.get::<_, Vec<u8>>(0))? {
        let record: FileAttachmentRecord = decode_msgpack(&row?)?;
        let id = record.file_id;
        items.push(item(
            record,
            missions.remove(&id).unwrap_or_default(),
            refs.remove(&id),
        ));
    }
    Ok(items)
}

fn attachment_exists(connection: &Connection, id: u64) -> Result<bool, RchCoreError> {
    Ok(connection
        .query_row(
            "SELECT 1 FROM rch_file_attachments WHERE file_id = ?1 AND category IN ('file','image')",
            params![signed(id)?],
            |_| Ok(()),
        )
        .optional()?
        .is_some())
}

impl RchSqliteStore {
    /// Catalog metadata for the REST registry; same projection as LXMF.
    ///
    /// # Errors
    /// Storage or decode failures.
    pub fn library_items(&self) -> Result<Vec<LibraryItem>, RchCoreError> {
        load_items(&self.connection)
    }
}

impl RchCommandTransaction<'_> {
    /// Catalog metadata read inside the command transaction.
    ///
    /// # Errors
    /// Storage or decode failures.
    pub fn library_items(&self) -> Result<Vec<LibraryItem>, RchCoreError> {
        load_items(&self.transaction)
    }

    /// Links an existing attachment to a mission. Returns `false` when the
    /// attachment does not exist; a repeated link is a no-op.
    ///
    /// # Errors
    /// Storage failures.
    pub fn link_library_item(
        &self,
        id: u64,
        mission_uid: &str,
        now_ms: i64,
    ) -> Result<bool, RchCoreError> {
        if !attachment_exists(&self.transaction, id)? {
            return Ok(false);
        }
        self.transaction.execute(
            "INSERT OR IGNORE INTO rch_library_mission_files(mission_uid, file_id, linked_ts_ms) VALUES(?1, ?2, ?3)",
            params![mission_uid, signed(id)?, now_ms],
        )?;
        Ok(true)
    }

    /// Records the published RPP identities for an attachment after the
    /// publisher has verified the signed manifest against the stored bytes.
    ///
    /// # Errors
    /// Storage failures.
    pub fn set_library_rpp_reference(
        &self,
        id: u64,
        reference: &RppReference,
        content_sha256: &str,
    ) -> Result<bool, RchCoreError> {
        if !attachment_exists(&self.transaction, id)? {
            return Ok(false);
        }
        self.transaction.execute(
            "INSERT INTO rch_library_rpp_refs(file_id, package_destination, file_destination, manifest_hash, content_sha256)
             VALUES(?1, ?2, ?3, ?4, ?5)
             ON CONFLICT(file_id) DO UPDATE SET package_destination=excluded.package_destination,
               file_destination=excluded.file_destination, manifest_hash=excluded.manifest_hash,
               content_sha256=excluded.content_sha256",
            params![
                signed(id)?,
                reference.package_destination,
                reference.file_destination,
                reference.manifest_hash,
                content_sha256
            ],
        )?;
        Ok(true)
    }
}

/// A signed one-file RPP Package published for an attachment.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LibraryRppPackage {
    pub file_id: u64,
    pub package_token: Vec<u8>,
    pub manifest: Vec<u8>,
    pub publication: Vec<u8>,
}

fn load_packages(
    connection: &Connection,
    only: Option<u64>,
) -> Result<Vec<LibraryRppPackage>, RchCoreError> {
    let mut statement = connection.prepare(
        "SELECT file_id, package_token, manifest, publication FROM rch_library_rpp_packages
         WHERE ?1 IS NULL OR file_id = ?1",
    )?;
    let only = only.map(signed).transpose()?;
    let rows = statement.query_map(params![only], |row| {
        Ok((row.get::<_, i64>(0)?, row.get(1)?, row.get(2)?, row.get(3)?))
    })?;
    let mut packages = Vec::new();
    for row in rows {
        let (id, package_token, manifest, publication) = row?;
        packages.push(LibraryRppPackage {
            file_id: file_id(id)?,
            package_token,
            manifest,
            publication,
        });
    }
    Ok(packages)
}

impl RchSqliteStore {
    /// Every published Package, to serve again after restart.
    ///
    /// # Errors
    /// Storage failures.
    pub fn library_rpp_packages(&self) -> Result<Vec<LibraryRppPackage>, RchCoreError> {
        load_packages(&self.connection, None)
    }
}

impl RchCommandTransaction<'_> {
    /// The Package already published for an attachment, if any.
    ///
    /// # Errors
    /// Storage failures.
    pub fn library_rpp_package(&self, id: u64) -> Result<Option<LibraryRppPackage>, RchCoreError> {
        Ok(load_packages(&self.transaction, Some(id))?
            .into_iter()
            .next())
    }

    /// Records a newly signed Package for an attachment.
    ///
    /// # Errors
    /// Storage failures.
    pub fn set_library_rpp_package(&self, package: &LibraryRppPackage) -> Result<(), RchCoreError> {
        self.transaction.execute(
            "INSERT OR REPLACE INTO rch_library_rpp_packages(file_id, package_token, manifest, publication)
             VALUES(?1, ?2, ?3, ?4)",
            params![signed(package.file_id)?, package.package_token, package.manifest, package.publication],
        )?;
        Ok(())
    }

    /// The stored attachment record (path, name, media type).
    ///
    /// # Errors
    /// Storage or decode failures.
    pub fn library_attachment(
        &self,
        id: u64,
    ) -> Result<Option<FileAttachmentRecord>, RchCoreError> {
        let payload: Option<Vec<u8>> = self
            .transaction
            .query_row(
                "SELECT payload FROM rch_file_attachments WHERE file_id = ?1 AND category IN ('file','image')",
                params![signed(id)?],
                |row| row.get(0),
            )
            .optional()?;
        payload.map(|bytes| decode_msgpack(&bytes)).transpose()
    }
}
