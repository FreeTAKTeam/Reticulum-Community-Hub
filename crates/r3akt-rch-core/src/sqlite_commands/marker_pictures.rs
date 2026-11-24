//! Picture-marker manifest (r3akt-uas #19): picture ID (LXMF message ID) to
//! the marker, its stored thumbnail and its reduced image. Image bytes live
//! in the attachment store; this table only links them.
use super::super::Connection;
use super::{RchCommandTransaction, RchCoreError, params};
use rusqlite::OptionalExtension;

/// The next attachment file ID: above every ID ever issued, not just the
/// current maximum, so a deleted file's ID is never handed out again (#365).
/// `MAX(file_id)` still counts when a database wipe cleared the mark.
pub(crate) const NEXT_FILE_ATTACHMENT_ID_SQL: &str = "SELECT MAX(
    COALESCE((SELECT file_id FROM rch_file_attachment_high_water WHERE id = 1), 0),
    COALESCE((SELECT MAX(file_id) FROM rch_file_attachments), 0)) + 1";

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
            image_height INTEGER);
        -- Every insert raises the mark, whichever code path wrote the row.
        CREATE TABLE IF NOT EXISTS rch_file_attachment_high_water(
            id INTEGER PRIMARY KEY CHECK(id = 1),
            file_id INTEGER NOT NULL);
        INSERT OR IGNORE INTO rch_file_attachment_high_water(id, file_id)
            SELECT 1, COALESCE(MAX(file_id), 0) FROM rch_file_attachments;
        CREATE TRIGGER IF NOT EXISTS rch_file_attachments_high_water
        AFTER INSERT ON rch_file_attachments BEGIN
            INSERT INTO rch_file_attachment_high_water(id, file_id) VALUES(1, NEW.file_id)
            ON CONFLICT(id) DO UPDATE SET file_id = MAX(file_id, excluded.file_id);
        END;
        -- A deleted file leaves its picture without that file, never with another's.
        CREATE TRIGGER IF NOT EXISTS rch_file_attachments_clear_pictures
        AFTER DELETE ON rch_file_attachments BEGIN
            UPDATE rch_marker_pictures SET thumbnail_file_id = NULL
                WHERE thumbnail_file_id = OLD.file_id;
            UPDATE rch_marker_pictures SET image_file_id = NULL
                WHERE image_file_id = OLD.file_id;
        END;
        -- Repair hubs where a reused ID already points at another picture's file:
        -- a picture's own files are named picture-<message_id>[-thumbnail].<format>.
        UPDATE rch_marker_pictures SET thumbnail_file_id = NULL
            WHERE thumbnail_file_id IS NOT NULL AND NOT EXISTS(
                SELECT 1 FROM rch_file_attachments f WHERE f.file_id = thumbnail_file_id
                AND instr(f.payload, CAST('picture-' || message_id AS BLOB)) > 0);
        UPDATE rch_marker_pictures SET image_file_id = NULL
            WHERE image_file_id IS NOT NULL AND NOT EXISTS(
                SELECT 1 FROM rch_file_attachments f WHERE f.file_id = image_file_id
                AND instr(f.payload, CAST('picture-' || message_id AS BLOB)) > 0);",
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

#[cfg(test)]
mod file_id_reuse_tests {
    use super::super::super::{FileAttachmentRecord, RchSqliteStore};

    fn file(name: &str) -> FileAttachmentRecord {
        FileAttachmentRecord {
            file_id: 0,
            name: name.into(),
            path: String::new(),
            category: "image".into(),
            size: 1,
            media_type: None,
            topic_id: None,
            created_ts_ms: 0,
            updated_ts_ms: 0,
        }
    }

    fn picture_files(store: &RchSqliteStore, message_id: &str) -> (Option<i64>, Option<i64>) {
        store
            .connection
            .query_row(
                "SELECT thumbnail_file_id,image_file_id FROM rch_marker_pictures WHERE message_id=?1",
                [message_id],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .expect("picture row")
    }

    #[test]
    fn deleted_file_ids_are_not_reused_and_pictures_never_point_at_another_file() {
        let directory = std::env::temp_dir().join(format!("rch-file-ids-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&directory).expect("dir");
        let mut store = RchSqliteStore::open(directory.join("state.db")).expect("store");
        let thumb = store
            .insert_file_attachment_with_next_id(file("picture-aa-thumbnail.jpg"))
            .expect("thumbnail")
            .file_id;
        let image = store
            .insert_file_attachment_with_next_id(file("picture-aa.jpg"))
            .expect("image")
            .file_id;
        store
            .connection
            .execute(
                "INSERT INTO rch_marker_pictures(message_id,object_destination_hash,thumbnail_file_id,image_file_id,image_sha256) VALUES('aa','m',?1,?2,'h')",
                [super::super::super::sqlite_u64(thumb).expect("id"), super::super::super::sqlite_u64(image).expect("id")],
            )
            .expect("picture");

        // Deleting the highest file clears the reference and retires its ID.
        store
            .delete_file_attachment(image, "image")
            .expect("delete");
        assert_eq!(picture_files(&store, "aa"), (Some(1), None));
        assert_eq!(store.next_file_attachment_id().expect("next"), image + 1);

        let unit = store.begin_outbound_application().expect("unit");
        let staged = unit
            .stage_attachment(file("picture-bb-thumbnail.jpg"), b"x")
            .expect("stage")
            .file_id;
        unit.commit().expect("commit");
        assert_eq!(staged, image + 1);

        // Repair: a reference to another picture's file is cleared on open.
        store
            .connection
            .execute(
                "UPDATE rch_marker_pictures SET image_file_id=?1 WHERE message_id='aa'",
                [super::super::super::sqlite_u64(staged).expect("id")],
            )
            .expect("corrupt");
        super::initialize(&store.connection).expect("repair");
        assert_eq!(picture_files(&store, "aa"), (Some(1), None));
        drop(store);
        let _ = std::fs::remove_dir_all(directory);
    }
}
