use super::{RchCoreError, RchSqliteStore, params};
use rusqlite::{OptionalExtension, TransactionBehavior};

impl RchSqliteStore {
    /// Replace a related record only if the complete observed version is still current.
    pub fn compare_and_set_setting_values(
        &mut self,
        expected: &[(&str, &str)],
        replacement: &[(&str, &str)],
    ) -> Result<bool, RchCoreError> {
        let transaction = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        for (key, value) in expected {
            let current: Option<String> = transaction
                .query_row(
                    "SELECT setting_value FROM rch_settings WHERE setting_key = ?1",
                    [key],
                    |row| row.get(0),
                )
                .optional()?;
            if current.as_deref() != Some(value) {
                return Ok(false);
            }
        }
        for (key, value) in replacement {
            transaction.execute(
                "INSERT OR REPLACE INTO rch_settings (setting_key, setting_value) VALUES (?1, ?2)",
                params![key, value],
            )?;
        }
        transaction.commit()?;
        Ok(true)
    }

    /// Read related fields from a single database snapshot.
    pub fn setting_values<const N: usize>(
        &mut self,
        keys: [&str; N],
    ) -> Result<[Option<String>; N], RchCoreError> {
        let transaction = self.connection.transaction()?;
        let mut values = std::array::from_fn(|_| None);
        for (index, key) in keys.iter().enumerate() {
            values[index] = transaction
                .query_row(
                    "SELECT setting_value FROM rch_settings WHERE setting_key = ?1",
                    [key],
                    |row| row.get(0),
                )
                .optional()?;
        }
        transaction.commit()?;
        Ok(values)
    }

    /// Claim first-run settings once, installing configuration before committing the claim.
    /// The caller must restore installed configuration if installation or commit fails.
    pub fn initialize_setting_values(
        &mut self,
        absent_key: &str,
        values: &[(&str, &str)],
        install_configuration: impl FnOnce() -> Result<(), RchCoreError>,
    ) -> Result<bool, RchCoreError> {
        let transaction = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let enrolled: Option<String> = transaction
            .query_row(
                "SELECT setting_value FROM rch_settings WHERE setting_key = ?1",
                [absent_key],
                |row| row.get(0),
            )
            .optional()?;
        if enrolled.is_some() {
            return Ok(false);
        }
        for (key, value) in values {
            transaction.execute(
                "INSERT OR REPLACE INTO rch_settings (setting_key, setting_value) VALUES (?1, ?2)",
                params![key, value],
            )?;
        }
        install_configuration()?;
        transaction.commit()?;
        Ok(true)
    }

    /// Commit related settings together so partial credential records are never visible.
    pub fn set_setting_values_atomic(
        &mut self,
        values: &[(&str, &str)],
    ) -> Result<(), RchCoreError> {
        let transaction = self.connection.transaction()?;
        for (key, value) in values {
            transaction.execute(
                "INSERT OR REPLACE INTO rch_settings (setting_key, setting_value) VALUES (?1, ?2)",
                params![key, value],
            )?;
        }
        transaction.commit()?;
        Ok(())
    }
    pub fn setting_value(&self, key: &str) -> Result<Option<String>, RchCoreError> {
        let mut statement = self
            .connection
            .prepare("SELECT setting_value FROM rch_settings WHERE setting_key = ?1")?;
        let mut rows = statement.query([key])?;
        let Some(row) = rows.next()? else {
            return Ok(None);
        };
        Ok(Some(row.get(0)?))
    }

    pub fn set_setting_value(&self, key: &str, value: &str) -> Result<(), RchCoreError> {
        self.connection.execute(
            "INSERT OR REPLACE INTO rch_settings (setting_key, setting_value)
             VALUES (?1, ?2)",
            params![key, value],
        )?;
        Ok(())
    }

    pub(super) fn settings_with_prefix(
        &self,
        prefix: &str,
    ) -> Result<Vec<(String, String)>, RchCoreError> {
        let pattern = format!("{prefix}%");
        let mut statement = self.connection.prepare(
            "SELECT setting_key, setting_value FROM rch_settings WHERE setting_key LIKE ?1",
        )?;
        let rows = statement.query_map([pattern], |row| Ok((row.get(0)?, row.get(1)?)))?;
        let mut settings = Vec::new();
        for row in rows {
            settings.push(row?);
        }
        Ok(settings)
    }
}
