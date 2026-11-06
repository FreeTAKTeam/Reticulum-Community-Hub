use super::{
    ApiError, AppState, ConfigFileKind, HUB_NAME_SETTING, RchSqliteStore, backup_config_file,
    config_text_section_raw_value, config_text_section_value, normalize_optional_text,
    read_config_file, setup_files, upsert_ini_setting, validate_ini_text, with_core_store_write,
};

pub(super) fn validate(name: &str) -> Result<(), ApiError> {
    if name.trim().is_empty() {
        return Err(ApiError::BadRequest("Hub name is required".to_string()));
    }
    if name.chars().count() > 80 {
        return Err(ApiError::BadRequest(
            "Hub name must be 80 characters or fewer".to_string(),
        ));
    }
    if name.chars().any(char::is_control) {
        return Err(ApiError::BadRequest(
            "Hub name must not contain control characters".to_string(),
        ));
    }
    Ok(())
}

pub(super) fn configured(body: &str) -> Option<String> {
    config_text_section_value(body, "hub", &["name"])
        .or_else(|| config_text_section_value(body, "hub", &["display_name"]))
}

pub(super) fn resolve(state: &AppState) -> Result<String, ApiError> {
    let saved = state
        .sqlite_path
        .as_ref()
        .map(|path| {
            RchSqliteStore::open_read_only(path.as_ref())
                .and_then(|store| store.setting_value(HUB_NAME_SETTING))
                .map_err(|error| ApiError::Internal(format!("cannot read hub name: {error}")))
        })
        .transpose()?
        .flatten();
    let name = match normalize_optional_text(saved) {
        Some(name) => name,
        None => configured(&read_config_file(state.config_path.as_deref())?)
            .unwrap_or_else(|| "RCH".to_string()),
    };
    validate(&name)?;
    Ok(name)
}

fn mirrored(body: &str, name: &str) -> Result<String, ApiError> {
    let body = upsert_ini_setting(body, "hub", "display_name", name)?;
    upsert_ini_setting(&body, "hub", "name", name)
}

fn validate_config(body: &str) -> Result<(), ApiError> {
    let errors = validate_ini_text(body);
    if !errors.is_empty() {
        return Err(ApiError::BadRequest(format!(
            "Invalid configuration payload: {}",
            errors.join("; ")
        )));
    }
    Ok(())
}

pub(super) fn save(state: &AppState, body: &str, name: &str) -> Result<(), ApiError> {
    validate(name)?;
    validate_config(body)?;
    let mut files = setup_files::SetupFiles::default();
    if let Some(path) = state.config_path.as_deref() {
        let updated = mirrored(body, name)?;
        if updated != read_config_file(Some(path))? {
            files.stage(path, updated)?;
        }
    }
    let result = files.install().and_then(|()| {
        with_core_store_write(state, |store| {
            store.set_setting_value(HUB_NAME_SETTING, name)
        })
    });
    if let Err(error) = result {
        files.restore().map_err(|rollback| {
            ApiError::Internal(format!(
                "hub name save failed: {error}; rollback: {rollback}"
            ))
        })?;
        return Err(error);
    }
    Ok(())
}

// Caller holds setup_lock until the matching announce result is recorded.
pub(super) fn reconcile(state: &AppState) -> Result<String, ApiError> {
    let body = read_config_file(state.config_path.as_deref())?;
    let name = resolve(state)?;
    if let Some(path) = state.config_path.as_deref()
        && mirrored(&body, &name)? != body
    {
        backup_config_file(path, ConfigFileKind::Hub)?;
    }
    save(state, &body, &name)?;
    Ok(name)
}

pub(super) fn renamed(state: &AppState, submitted: &str) -> Result<String, ApiError> {
    validate_config(submitted)?;
    let current = read_config_file(state.config_path.as_deref())?;
    let mut changed = None;
    for key in ["name", "display_name"] {
        if let Some(value) = config_text_section_raw_value(submitted, "hub", &[key])
            && Some(&value) != config_text_section_raw_value(&current, "hub", &[key]).as_ref()
        {
            validate(&value)?;
            if changed.as_ref().is_some_and(|name| name != &value) {
                return Err(ApiError::BadRequest(
                    "Conflicting hub name edits: name and display_name must agree".to_string(),
                ));
            }
            changed = Some(value);
        }
    }
    changed.map_or_else(|| resolve(state), Ok)
}

impl AppState {
    /// Reconcile legacy name settings before registering the existing service identity.
    pub fn reconcile_hub_display_name(&self) -> Result<String, String> {
        let _guard = self.setup_lock.lock().map_err(|error| error.to_string())?;
        reconcile(self).map_err(|error| error.to_string())
    }
}

#[cfg(test)]
mod tests;
