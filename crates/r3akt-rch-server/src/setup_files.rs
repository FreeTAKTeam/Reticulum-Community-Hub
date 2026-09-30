use std::fs::{File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};

use super::{ApiError, ensure_parent_dir};

#[derive(Default)]
pub(super) struct SetupFiles(Vec<SetupFile>);

struct SetupFile {
    path: PathBuf,
    original: Option<Vec<u8>>,
    updated: Vec<u8>,
    installed: bool,
}

impl SetupFiles {
    pub(super) fn stage(&mut self, path: &Path, contents: String) -> Result<(), ApiError> {
        if self.0.iter().any(|file| file.path == path) {
            return Err(ApiError::BadRequest(
                "Setup configuration paths must be distinct".to_string(),
            ));
        }
        let original = match std::fs::read(path) {
            Ok(contents) => Some(contents),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => None,
            Err(error) => {
                return Err(ApiError::Internal(format!(
                    "cannot stage setup configuration {}: {error}",
                    path.display()
                )));
            }
        };
        self.0.push(SetupFile {
            path: path.to_path_buf(),
            original,
            updated: contents.into_bytes(),
            installed: false,
        });
        Ok(())
    }

    pub(super) fn install(&mut self) -> Result<(), ApiError> {
        for file in &mut self.0 {
            atomic_write(&file.path, &file.updated)?;
            file.installed = true;
        }
        Ok(())
    }

    pub(super) fn restore(&mut self) -> Result<(), ApiError> {
        let mut errors = Vec::new();
        for file in self.0.iter_mut().rev().filter(|file| file.installed) {
            let restored = match &file.original {
                Some(contents) => atomic_write(&file.path, contents),
                None => std::fs::remove_file(&file.path).map_err(|error| {
                    ApiError::Internal(format!(
                        "cannot remove failed setup file {}: {error}",
                        file.path.display()
                    ))
                }),
            };
            match restored {
                Ok(()) => file.installed = false,
                Err(error) => errors.push(format!("{error:?}")),
            }
        }
        if errors.is_empty() {
            Ok(())
        } else {
            Err(ApiError::Internal(format!(
                "setup configuration rollback failed: {}",
                errors.join("; ")
            )))
        }
    }
}

fn atomic_write(path: &Path, contents: &[u8]) -> Result<(), ApiError> {
    ensure_parent_dir(path)?;
    let temporary = path.with_extension(format!("setup-{}.tmp", uuid::Uuid::new_v4()));
    let operation = || -> std::io::Result<()> {
        let mut options = OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let mut file: File = options.open(&temporary)?;
        if let Ok(metadata) = std::fs::metadata(path) {
            file.set_permissions(metadata.permissions())?;
        }
        file.write_all(contents)?;
        file.sync_all()?;
        drop(file);
        std::fs::rename(&temporary, path)
    };
    if let Err(error) = operation() {
        if let Err(cleanup) = std::fs::remove_file(&temporary) {
            if cleanup.kind() != std::io::ErrorKind::NotFound {
                eprintln!(
                    "failed to clean staged setup file {}: {cleanup}",
                    temporary.display()
                );
            }
        }
        return Err(ApiError::Internal(format!(
            "cannot install setup configuration {}: {error}",
            path.display()
        )));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn second_install_failure_restores_the_first_configuration() {
        let directory =
            std::env::temp_dir().join(format!("rch-setup-rollback-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&directory).expect("directory");
        let first = directory.join("hub.ini");
        let second = directory.join("reticulum.ini");
        std::fs::write(&first, b"original hub configuration").expect("original");
        let mut files = SetupFiles::default();
        files
            .stage(&first, "new hub configuration".to_string())
            .expect("stage first");
        files
            .stage(&second, "new reticulum configuration".to_string())
            .expect("stage second");
        // Simulate a destination becoming unavailable after staging.
        std::fs::create_dir(&second).expect("unavailable destination");
        assert!(files.install().is_err());
        files.restore().expect("rollback");
        assert_eq!(
            std::fs::read(&first).expect("restored"),
            b"original hub configuration"
        );
        assert!(second.is_dir());
        assert_eq!(std::fs::read_dir(&directory).expect("files").count(), 2);
        std::fs::remove_dir_all(directory).expect("cleanup");
    }
}
