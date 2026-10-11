use super::{ApiError, AppState, FsPath, config_section_value};
use serde::Serialize;

/// Operator-selected directory policy, exposed to the UI rather than duplicated there.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct IdentityDirectoryConfig {
    pub page_size: usize,
    pub recent_hours: i64,
    pub lookup_max_entries: usize,
    pub lookup_concurrency: usize,
}

impl Default for IdentityDirectoryConfig {
    fn default() -> Self {
        Self {
            page_size: 50,
            recent_hours: 24,
            lookup_max_entries: 500,
            lookup_concurrency: 4,
        }
    }
}

impl IdentityDirectoryConfig {
    pub fn validate(&self) -> Result<(), ApiError> {
        if !(1..=super::API_PAGINATION_MAX_PAGE_SIZE).contains(&self.page_size) {
            return Err(ApiError::Unprocessable(
                "identity directory page_size must be 1..=500".into(),
            ));
        }
        if self.recent_hours <= 0 || self.recent_hours.checked_mul(3_600_000).is_none() {
            return Err(ApiError::Unprocessable(
                "identity directory recent_hours must be positive and fit a millisecond timestamp"
                    .into(),
            ));
        }
        if !(1..=10_000).contains(&self.lookup_max_entries)
            || !(1..=16).contains(&self.lookup_concurrency)
        {
            return Err(ApiError::Unprocessable(
                "identity lookup_max_entries must be 1..=10000 and lookup_concurrency 1..=16"
                    .into(),
            ));
        }
        Ok(())
    }

    fn from_settings(
        mut read: impl FnMut(&str) -> Result<Option<String>, ApiError>,
    ) -> Result<Self, ApiError> {
        let mut config = Self::default();
        for name in [
            "page_size",
            "recent_hours",
            "lookup_max_entries",
            "lookup_concurrency",
        ] {
            let Some(value) = read(name)? else { continue };
            let value = value.trim().parse::<i64>().map_err(|_| {
                ApiError::Unprocessable(format!("identity directory {name} must be an integer"))
            })?;
            match name {
                "recent_hours" => config.recent_hours = value,
                "page_size" => {
                    config.page_size = usize::try_from(value).map_err(|_| {
                        ApiError::Unprocessable(
                            "identity directory page_size must be positive".into(),
                        )
                    })?;
                }
                "lookup_max_entries" => {
                    config.lookup_max_entries = usize::try_from(value).map_err(|_| {
                        ApiError::Unprocessable(
                            "identity lookup_max_entries must be positive".into(),
                        )
                    })?;
                }
                _ => {
                    config.lookup_concurrency = usize::try_from(value).map_err(|_| {
                        ApiError::Unprocessable(
                            "identity lookup_concurrency must be positive".into(),
                        )
                    })?;
                }
            }
        }
        config.validate()?;
        Ok(config)
    }

    fn load(path: Option<&FsPath>) -> Result<Self, ApiError> {
        Self::from_settings(|name| {
            let env_name = format!("RCH_IDENTITY_{}", name.to_ascii_uppercase());
            match std::env::var(&env_name) {
                Ok(value) => Ok(Some(value)),
                Err(std::env::VarError::NotPresent) => {
                    Ok(path
                        .and_then(|path| config_section_value(path, "identity_directory", &[name])))
                }
                Err(error) => Err(ApiError::Unprocessable(format!("{env_name}: {error}"))),
            }
        })
    }
}

impl AppState {
    pub fn with_identity_directory_config(
        mut self,
        config: IdentityDirectoryConfig,
    ) -> Result<Self, ApiError> {
        config.validate()?;
        self.identity_directory_config = config;
        Ok(self)
    }

    /// Load validated environment/INI overrides before starting owned workers.
    pub fn configure_identity_directory(mut self) -> Result<Self, ApiError> {
        self.identity_directory_config = IdentityDirectoryConfig::load(
            self.config_path.as_deref().map(std::path::PathBuf::as_path),
        )?;
        Ok(self)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn configuration_defaults_and_overrides_are_validated() {
        assert_eq!(
            IdentityDirectoryConfig::from_settings(|_| Ok(None)).expect("defaults"),
            IdentityDirectoryConfig::default()
        );
        let config = IdentityDirectoryConfig::from_settings(|key| {
            Ok(match key {
                "page_size" => Some("25".into()),
                "recent_hours" => Some("48".into()),
                "lookup_max_entries" => Some("100".into()),
                "lookup_concurrency" => Some("2".into()),
                _ => None,
            })
        })
        .expect("configuration");
        assert_eq!(
            (
                config.page_size,
                config.recent_hours,
                config.lookup_max_entries,
                config.lookup_concurrency
            ),
            (25, 48, 100, 2)
        );
        for (name, value) in [
            ("page_size", "0"),
            ("page_size", "501"),
            ("recent_hours", "0"),
            ("recent_hours", "9223372036854775807"),
            ("lookup_max_entries", "-1"),
            ("lookup_concurrency", "17"),
            ("page_size", "bad"),
        ] {
            assert!(
                IdentityDirectoryConfig::from_settings(|key| Ok(
                    (key == name).then(|| value.into())
                ))
                .is_err(),
                "{name}={value}"
            );
        }
    }
    #[test]
    fn ini_policy_is_loaded_before_runtime_startup() {
        let directory =
            std::env::temp_dir().join(format!("rch-identity-policy-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir(&directory).expect("fixture");
        let path = directory.join("server.ini");
        std::fs::write(&path, "[identity_directory]\npage_size = 25\nrecent_hours = 48\nlookup_max_entries = 100\nlookup_concurrency = 2\n").expect("INI");
        let state = AppState::default()
            .with_config_path(&path)
            .configure_identity_directory()
            .expect("configuration");
        assert_eq!(state.identity_directory_config.page_size, 25);
        assert_eq!(state.identity_directory_config.recent_hours, 48);
        assert_eq!(state.identity_directory_config.lookup_max_entries, 100);
        assert_eq!(state.identity_directory_config.lookup_concurrency, 2);
        std::fs::write(&path, "[identity_directory]\npage_size = 0\n").expect("invalid INI");
        assert!(
            AppState::default()
                .with_config_path(&path)
                .configure_identity_directory()
                .is_err()
        );
        std::fs::remove_dir_all(directory).expect("cleanup");
    }
}
