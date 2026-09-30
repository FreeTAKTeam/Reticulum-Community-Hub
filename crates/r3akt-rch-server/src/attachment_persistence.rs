use super::{ApiError, AppState, FileAttachmentRecord, PathBuf, insert_file_attachment_row};
use std::fs::{File, OpenOptions};
use std::io::Write;

struct UncommittedFile {
    path: Option<PathBuf>,
    file: Option<File>,
}

impl Drop for UncommittedFile {
    fn drop(&mut self) {
        drop(self.file.take());
        let Some(path) = self.path.as_ref() else {
            return;
        };
        if let Err(error) = std::fs::remove_file(path) {
            if error.kind() != std::io::ErrorKind::NotFound {
                eprintln!(
                    "Cannot remove uncommitted attachment {}: {error}",
                    path.display()
                );
            }
        }
    }
}

pub(super) fn persist(
    state: &AppState,
    record: FileAttachmentRecord,
    content: &[u8],
) -> Result<FileAttachmentRecord, ApiError> {
    persist_with_writer(state, record, |file| {
        file.write_all(content)?;
        file.sync_all()
    })
}

fn persist_with_writer(
    state: &AppState,
    record: FileAttachmentRecord,
    write: impl FnOnce(&mut File) -> std::io::Result<()>,
) -> Result<FileAttachmentRecord, ApiError> {
    let path = PathBuf::from(&record.path);
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|error| {
            ApiError::Internal(format!("Cannot create attachment directory: {error}"))
        })?;
    }
    let file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&path)
        .map_err(|error| ApiError::Internal(format!("Cannot create attachment: {error}")))?;
    let mut uncommitted = UncommittedFile {
        path: Some(path),
        file: Some(file),
    };
    let file = uncommitted
        .file
        .as_mut()
        .ok_or_else(|| ApiError::Internal("Attachment file owner is missing".to_string()))?;
    write(file).map_err(|error| ApiError::Internal(format!("Cannot write attachment: {error}")))?;
    drop(uncommitted.file.take());
    let persisted = insert_file_attachment_row(state, record)?;
    uncommitted.path = None;
    Ok(persisted)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::load_attachment_records;
    use std::sync::mpsc;
    use std::time::Duration;
    use uuid::Uuid;

    fn fixture() -> (AppState, PathBuf, FileAttachmentRecord) {
        let directory = std::env::temp_dir().join(format!("rch-upload-owner-{}", Uuid::new_v4()));
        std::fs::create_dir_all(&directory).expect("directory");
        let state = AppState::from_sqlite_path(directory.join("state.db")).expect("state");
        let record = FileAttachmentRecord {
            file_id: 0,
            name: "fixture.txt".to_string(),
            path: directory.join("partial.txt").display().to_string(),
            category: "file".to_string(),
            size: 8,
            media_type: None,
            topic_id: None,
            created_ts_ms: 1,
            updated_ts_ms: 1,
        };
        (state, directory, record)
    }

    #[test]
    fn partial_write_failure_removes_uncommitted_file_and_metadata() {
        let (state, directory, record) = fixture();
        let result = persist_with_writer(&state, record, |file| {
            file.write_all(b"partial")?;
            Err(std::io::Error::other("injected disk failure"))
        });
        assert!(matches!(result, Err(ApiError::Internal(_))));
        assert!(!directory.join("partial.txt").exists());
        assert!(
            load_attachment_records(&state, "file")
                .expect("records")
                .is_empty()
        );
        std::fs::remove_dir_all(directory).expect("cleanup");
    }

    #[tokio::test]
    async fn dropped_http_waiter_does_not_drop_partial_write_cleanup_owner() {
        let (state, directory, record) = fixture();
        let (started_tx, started_rx) = mpsc::channel();
        let (release_tx, release_rx) = mpsc::channel();
        let (done_tx, done_rx) = tokio::sync::oneshot::channel();
        let worker = tokio::task::spawn_blocking(move || {
            let result = persist_with_writer(&state, record, |file| {
                file.write_all(b"partial")?;
                started_tx.send(()).expect("started");
                release_rx
                    .recv_timeout(Duration::from_secs(3))
                    .expect("release");
                Err(std::io::Error::other("injected interrupted write"))
            });
            done_tx.send(result.is_err()).expect("completion observer");
        });
        let http_waiter = tokio::spawn(async move {
            worker.await.expect("worker");
        });
        started_rx
            .recv_timeout(Duration::from_secs(3))
            .expect("started");
        assert!(directory.join("partial.txt").exists());
        http_waiter.abort();
        assert!(
            http_waiter
                .await
                .expect_err("cancelled waiter")
                .is_cancelled()
        );
        release_tx.send(()).expect("release");
        assert!(
            tokio::time::timeout(Duration::from_secs(3), done_rx)
                .await
                .expect("deadline")
                .expect("completion")
        );
        assert!(!directory.join("partial.txt").exists());
        std::fs::remove_dir_all(directory).expect("cleanup");
    }
}
