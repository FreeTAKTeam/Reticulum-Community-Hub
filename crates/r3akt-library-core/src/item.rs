//! The Library item contract and its identities.

use serde::{Deserialize, Serialize};

/// Longest accepted display name, in UTF-8 bytes.
pub const MAX_NAME_BYTES: usize = 255;
/// Longest accepted media type, in bytes.
pub const MAX_MEDIA_TYPE_BYTES: usize = 127;

/// What the item is. Images get previews; everything else is a file.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ItemKind {
    File,
    Image,
}

impl ItemKind {
    /// `image/*` media types are images; anything else, or none, is a file.
    #[must_use]
    pub fn for_media_type(media_type: Option<&str>) -> Self {
        match media_type {
            Some(value) if value.to_ascii_lowercase().starts_with("image/") => Self::Image,
            _ => Self::File,
        }
    }

    /// The RCH attachment category (`file` / `image`).
    #[must_use]
    pub fn category(self) -> &'static str {
        match self {
            Self::File => "file",
            Self::Image => "image",
        }
    }
}

/// Where the catalog entry came from.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Source {
    /// Imported on this device.
    Local,
    /// Listed by an RCH hub.
    Rch,
    /// Offered by another peer.
    Peer,
}

/// Whether the bytes are on this device. A remote entry is metadata only.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Availability {
    /// Listed remotely; no bytes here.
    Remote,
    /// A requested transfer is in progress.
    Downloading,
    /// Verified bytes are stored locally.
    Local,
    /// The last transfer failed; verified partial data may remain.
    Failed,
}

/// Published RPP identities. These are distinct from the item ID, the RCH
/// numeric file ID and the content digest: knowing them grants nothing.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RppReference {
    /// RDO Package Destination, 32 lowercase hex digits.
    pub package_destination: String,
    /// RDO File Destination, 32 lowercase hex digits.
    pub file_destination: String,
    /// SHA-256 of the signed manifest, 64 lowercase hex digits.
    pub manifest_hash: String,
}

/// One catalog entry. Metadata only: bytes never travel in this record.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LibraryItem {
    /// Catalog-local ID (for RCH entries `rch:<file_id>`).
    pub item_id: String,
    /// RCH legacy numeric `FileID`, for the HTTP routes.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub legacy_file_id: Option<u64>,
    pub kind: ItemKind,
    pub source: Source,
    pub availability: Availability,
    pub name: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub media_type: Option<String>,
    pub size: u64,
    /// SHA-256 of the file bytes, 64 lowercase hex digits.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub content_sha256: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub rpp: Option<RppReference>,
    /// Publisher identity hash, 32 lowercase hex digits.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub publisher: Option<String>,
    /// Missions the item is linked to. Empty means not mission-scoped.
    #[serde(default)]
    pub mission_uids: Vec<String>,
    /// TEAM scope the item was shared under, if any.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub team_uid: Option<String>,
    pub created_ts_ms: i64,
    pub updated_ts_ms: i64,
}

fn is_lower_hex(value: &str, len: usize) -> bool {
    value.len() == len
        && value
            .bytes()
            .all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
}

/// Checks a display name: nonempty, bounded, a single path component without
/// separators or control characters.
///
/// # Errors
/// Returns the reason the name is unsafe.
pub fn validate_name(name: &str) -> Result<(), String> {
    if name.trim().is_empty() || name.len() > MAX_NAME_BYTES {
        return Err(format!("name must be 1..={MAX_NAME_BYTES} bytes"));
    }
    if name == "."
        || name == ".."
        || name
            .chars()
            .any(|c| c.is_control() || matches!(c, '/' | '\\' | ':'))
    {
        return Err("name must be one file name without separators or control characters".into());
    }
    Ok(())
}

impl LibraryItem {
    /// Validates identities and metadata before an item is stored or sent.
    ///
    /// # Errors
    /// Returns the first invalid field.
    pub fn validate(&self) -> Result<(), String> {
        if self.item_id.trim().is_empty() || self.item_id.len() > 128 {
            return Err("item_id must be 1..=128 bytes".into());
        }
        validate_name(&self.name)?;
        if let Some(media_type) = &self.media_type {
            let valid = media_type.len() <= MAX_MEDIA_TYPE_BYTES
                && media_type
                    .split_once('/')
                    .is_some_and(|(a, b)| !a.is_empty() && !b.is_empty())
                && media_type.is_ascii()
                && !media_type.chars().any(|c| c.is_ascii_control() || c == ' ');
            if !valid {
                return Err("media_type must be type/subtype".into());
            }
        }
        if self.kind != ItemKind::for_media_type(self.media_type.as_deref())
            && self.kind == ItemKind::Image
        {
            return Err("image items need an image/* media type".into());
        }
        if self
            .content_sha256
            .as_deref()
            .is_some_and(|v| !is_lower_hex(v, 64))
        {
            return Err("content_sha256 must be 64 lowercase hex digits".into());
        }
        if self
            .publisher
            .as_deref()
            .is_some_and(|v| !is_lower_hex(v, 32))
        {
            return Err("publisher must be 32 lowercase hex digits".into());
        }
        if let Some(rpp) = &self.rpp
            && (!is_lower_hex(&rpp.package_destination, 32)
                || !is_lower_hex(&rpp.file_destination, 32)
                || !is_lower_hex(&rpp.manifest_hash, 64))
        {
            return Err("rpp reference has malformed hex identities".into());
        }
        if self.mission_uids.iter().any(|uid| uid.trim().is_empty()) {
            return Err("mission_uids must not contain empty values".into());
        }
        Ok(())
    }
}
