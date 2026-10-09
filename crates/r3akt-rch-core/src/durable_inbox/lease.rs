use super::{RchCoreError, recovery};

/// `SQLite`'s OS lock is released on process death, including SIGKILL. This lock database is separate
/// from business WAL and carries no application data or long-lived business read snapshot.
pub struct RchConsumerLease {
    _connection: rusqlite::Connection,
}
impl RchConsumerLease {
    pub fn acquire(path: &std::path::Path) -> Result<Self, RchCoreError> {
        let mut lock_path = path.as_os_str().to_os_string();
        lock_path.push(".broker-owner.sqlite");
        let connection = rusqlite::Connection::open(std::path::PathBuf::from(lock_path))?;
        connection.busy_timeout(std::time::Duration::ZERO)?;
        connection
            .execute_batch("PRAGMA journal_mode=DELETE;BEGIN EXCLUSIVE;")
            .map_err(|e| {
                recovery(&format!(
                    "another RCH process owns this durable consumer: {e}"
                ))
            })?;
        Ok(Self {
            _connection: connection,
        })
    }
}
