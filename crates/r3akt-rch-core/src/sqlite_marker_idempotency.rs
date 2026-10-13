use super::{MarkerRecord, RchCoreError, RchSqliteStore};

pub use r3akt_map_core::sqlite::MarkerCreation;

impl RchSqliteStore {
    /// Commit the marker and its replay result in the existing durable command
    /// result table. Read only this key under the write reservation; never load
    /// an unbounded command history into the server's request cache.
    pub fn create_marker_once(
        &mut self,
        marker: &MarkerRecord,
        command_id: &str,
        fingerprint: &str,
    ) -> Result<MarkerCreation, RchCoreError> {
        Ok(r3akt_map_core::sqlite::create_once(
            &mut self.connection,
            marker,
            command_id,
            fingerprint,
        )?)
    }
}
