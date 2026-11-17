//! Picture-marker manifest (r3akt-uas #19): picture ID (LXMF message ID) to
//! the marker, its stored thumbnail and its reduced image. Image bytes live
//! in the attachment store; this table only links them.
use super::super::Connection;
use super::{RchCommandTransaction, RchCoreError, params};
use rusqlite::OptionalExtension;

pub(crate) fn initialize(connection: &Connection) -> Result<(), RchCoreError> {
    connection.execute_batch(
        "CREATE TABLE IF NOT EXISTS rch_marker_pictures(
            message_id TEXT PRIMARY KEY,
            object_destination_hash TEXT NOT NULL,
            thumbnail_file_id INTEGER,
            image_file_id INTEGER,
            image_format TEXT,
            image_sha256 TEXT,
            image_media_type TEXT,
            image_width INTEGER,
            image_height INTEGER);",
    )?;
    Ok(())
}

/// One manifest row; the `image_*` fields are set once the reduced image is uploaded.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MarkerPictureRow {
    pub message_id: String,
    pub object_destination_hash: String,
    pub thumbnail_file_id: Option<u64>,
    pub image_file_id: Option<u64>,
    pub image_format: Option<String>,
    pub image_sha256: Option<String>,
    pub image_media_type: Option<String>,
    pub image_width: Option<u32>,
    pub image_height: Option<u32>,
}

fn file_id(value: Option<i64>) -> Result<Option<u64>, RchCoreError> {
    value
        .map(|v| u64::try_from(v).map_err(|e| RchCoreError::Decode(e.to_string())))
        .transpose()
}

impl RchCommandTransaction<'_> {
    /// Links a picture ID to its marker and stored thumbnail; a repeat is ignored.
    pub fn stage_marker_picture(
        &self,
        message_id: &str,
        object_destination_hash: &str,
        thumbnail_file_id: Option<u64>,
    ) -> Result<(), RchCoreError> {
        let thumbnail = thumbnail_file_id
            .map(super::super::sqlite_u64)
            .transpose()?;
        self.transaction.execute(
            "INSERT OR IGNORE INTO rch_marker_pictures(message_id,object_destination_hash,thumbnail_file_id) VALUES(?1,?2,?3)",
            params![message_id, object_destination_hash, thumbnail],
        )?;
        Ok(())
    }

    /// Records the stored reduced image of a picture.
    #[allow(clippy::too_many_arguments)]
    pub fn stage_marker_picture_image(
        &self,
        message_id: &str,
        image_file_id: u64,
        format: &str,
        sha256: &str,
        media_type: &str,
        width: u32,
        height: u32,
    ) -> Result<(), RchCoreError> {
        self.transaction.execute(
            "UPDATE rch_marker_pictures SET image_file_id=?2,image_format=?3,image_sha256=?4,image_media_type=?5,image_width=?6,image_height=?7 WHERE message_id=?1",
            params![
                message_id,
                super::super::sqlite_u64(image_file_id)?,
                format,
                sha256,
                media_type,
                width,
                height
            ],
        )?;
        Ok(())
    }

    pub fn marker_picture(
        &self,
        message_id: &str,
    ) -> Result<Option<MarkerPictureRow>, RchCoreError> {
        let row = self
            .transaction
            .query_row(
                "SELECT message_id,object_destination_hash,thumbnail_file_id,image_file_id,image_format,image_sha256,image_media_type,image_width,image_height FROM rch_marker_pictures WHERE message_id=?1",
                [message_id],
                |r| {
                    Ok((
                        MarkerPictureRow {
                            message_id: r.get(0)?,
                            object_destination_hash: r.get(1)?,
                            thumbnail_file_id: None,
                            image_file_id: None,
                            image_format: r.get(4)?,
                            image_sha256: r.get(5)?,
                            image_media_type: r.get(6)?,
                            image_width: r.get(7)?,
                            image_height: r.get(8)?,
                        },
                        r.get::<_, Option<i64>>(2)?,
                        r.get::<_, Option<i64>>(3)?,
                    ))
                },
            )
            .optional()?;
        row.map(|(mut row, thumbnail, image)| {
            row.thumbnail_file_id = file_id(thumbnail)?;
            row.image_file_id = file_id(image)?;
            Ok(row)
        })
        .transpose()
    }

    /// The identity that created the marker, when RCH recorded one.
    pub fn marker_writer(
        &self,
        object_destination_hash: &str,
    ) -> Result<Option<String>, RchCoreError> {
        self.transaction
            .query_row(
                "SELECT writer_id FROM r3s_marker_writers WHERE origin_id=?1",
                [object_destination_hash],
                |r| r.get(0),
            )
            .optional()
            .map_err(Into::into)
    }

    /// Stored attachment bytes, including ones staged in this transaction.
    pub fn attachment_bytes(&self, file_id: u64) -> Result<Option<Vec<u8>>, RchCoreError> {
        self.transaction
            .query_row(
                "SELECT bytes FROM rch_broker_attachment_bytes WHERE file_id=?1",
                [super::super::sqlite_u64(file_id)?],
                |r| r.get(0),
            )
            .optional()
            .map_err(Into::into)
    }
}
