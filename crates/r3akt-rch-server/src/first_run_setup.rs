use super::{
    ApiError, AppState, ConnectInfo, Extension, FirstRunSetupPayload, HUB_NAME_SETTING, HeaderMap,
    Json, KILL_SWITCH_PIN_CREATED_AT_SETTING, KILL_SWITCH_PIN_HASH_SETTING,
    KILL_SWITCH_PIN_SALT_SETTING, KillSwitchRuntimeMode, REMOTE_ACCESS_PASSWORD_CREATED_AT_SETTING,
    REMOTE_ACCESS_PASSWORD_HASH_SETTING, REMOTE_ACCESS_PASSWORD_SALT_SETTING, Request, SocketAddr,
    State, Uuid, Value, argon2id_hash, browser_security, ensure_reticulum_identity_status,
    is_local_client_addr, iso8601_from_unix_ms, json, load_kill_switch_pin,
    load_stored_remote_password, read_config_file, request_client_addr, setup_files, unix_now_ms,
    upsert_ini_setting, validate_ini_text, with_required_core_store_write,
    with_required_core_store_write_unchecked,
};

pub(super) async fn first_run_setup_status(
    State(state): State<AppState>,
    request: Request,
) -> Result<Json<Value>, ApiError> {
    let client_addr = request_client_addr(&request);
    let include_sensitive_paths = bootstrap_authorized(&state, request.headers(), client_addr)?;
    if !include_sensitive_paths {
        return Ok(Json(
            json!({"setup_required": load_kill_switch_pin(&state)?.is_none()}),
        ));
    }
    Ok(Json(first_run_setup_status_payload(
        &state,
        include_sensitive_paths,
    )?))
}

pub(super) async fn first_run_setup_complete(
    State(state): State<AppState>,
    connect_info: Option<Extension<ConnectInfo<SocketAddr>>>,
    headers: HeaderMap,
    Json(payload): Json<FirstRunSetupPayload>,
) -> Result<Json<Value>, ApiError> {
    let peer = connect_info.map(|Extension(ConnectInfo(peer))| peer);
    if !bootstrap_authorized(&state, &headers, peer)? {
        return Err(ApiError::Unauthorized);
    }
    tokio::task::spawn_blocking(move || complete_setup(&state, &payload))
        .await
        .map_err(|error| ApiError::Internal(format!("first-run setup worker failed: {error}")))?
        .map(Json)
}

fn bootstrap_authorized(
    state: &AppState,
    headers: &HeaderMap,
    peer: Option<SocketAddr>,
) -> Result<bool, ApiError> {
    if !state.credentials_configured()? {
        return Ok(is_local_client_addr(peer)
            && browser_security::trusted_bootstrap_authority(state, headers));
    }
    state.validate_http_headers(headers, peer)
}

fn complete_setup(state: &AppState, payload: &FirstRunSetupPayload) -> Result<Value, ApiError> {
    let _setup_guard = state
        .setup_lock
        .lock()
        .map_err(|error| ApiError::Internal(format!("setup lock poisoned: {error}")))?;
    if load_kill_switch_pin(&state)?.is_some() {
        return Err(ApiError::Conflict(
            "First-run setup has already enrolled a kill switch PIN".to_string(),
        ));
    }

    let hub_name = payload.hub_name.trim();
    if hub_name.is_empty() {
        return Err(ApiError::BadRequest("Hub name is required".to_string()));
    }
    if hub_name.chars().count() > 80 {
        return Err(ApiError::BadRequest(
            "Hub name must be 80 characters or fewer".to_string(),
        ));
    }
    if hub_name.chars().any(char::is_control) {
        return Err(ApiError::BadRequest(
            "Hub name must not contain control characters".to_string(),
        ));
    }

    let remote_password = payload.remote_password.trim();
    if remote_password.len() < 8 {
        return Err(ApiError::BadRequest(
            "Remote access password must contain at least eight characters".to_string(),
        ));
    }
    if remote_password.len() > 1024 {
        return Err(ApiError::BadRequest(
            "Remote access password must be 1024 bytes or fewer".to_string(),
        ));
    }

    let kill_switch_pin = payload.kill_switch_pin.trim();
    if kill_switch_pin.len() != 6 || !kill_switch_pin.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(ApiError::BadRequest(
            "Kill switch PIN must contain exactly six digits".to_string(),
        ));
    }

    if let Some(reticulum_config_text) = payload.reticulum_config_text.as_deref() {
        let errors = validate_ini_text(reticulum_config_text);
        if !errors.is_empty() {
            return Err(ApiError::BadRequest(format!(
                "Invalid Reticulum configuration payload: {}",
                errors.join("; ")
            )));
        }
        if !reticulum_config_text.trim().is_empty() && state.reticulum_config_path.is_none() {
            return Err(ApiError::BadRequest(
                "Reticulum configuration path is required before setup can save TCP interfaces"
                    .to_string(),
            ));
        }
    }

    let mut files = setup_files::SetupFiles::default();
    if let Some(path) = state.config_path.as_deref() {
        let current = read_config_file(Some(path))?;
        let updated = upsert_ini_setting(&current, "hub", "name", hub_name)?;
        files.stage(path, updated)?;
    }

    if let (Some(path), Some(reticulum_config_text)) = (
        state.reticulum_config_path.as_deref(),
        payload.reticulum_config_text.as_deref(),
    ) {
        files.stage(path, reticulum_config_text.to_string())?;
    }

    let now_ms = unix_now_ms();
    let now = now_ms.to_string();
    let password_salt = Uuid::new_v4().to_string();
    let password_hash = argon2id_hash(remote_password)?;
    let pin_salt = Uuid::new_v4().to_string();
    let pin_hash = argon2id_hash(kill_switch_pin)?;
    // Prepare all fallible response state before enrolling credentials.
    let mut response = first_run_setup_status_payload(state, true)?;
    let mut runtime = state
        .kill_switch
        .write()
        .map_err(|error| ApiError::Internal(format!("kill switch state poisoned: {error}")))?;
    if matches!(
        runtime.mode,
        KillSwitchRuntimeMode::Deleting | KillSwitchRuntimeMode::Completed
    ) {
        return Err(ApiError::ServiceUnavailable(
            "RCH persistence is locked by kill switch purge".to_string(),
        ));
    }
    let enrollment = with_required_core_store_write_unchecked(state, |store| {
        store.initialize_setting_values(
            KILL_SWITCH_PIN_HASH_SETTING,
            &[
                (HUB_NAME_SETTING, hub_name),
                (REMOTE_ACCESS_PASSWORD_SALT_SETTING, &password_salt),
                (REMOTE_ACCESS_PASSWORD_HASH_SETTING, &password_hash),
                (REMOTE_ACCESS_PASSWORD_CREATED_AT_SETTING, &now),
                (KILL_SWITCH_PIN_SALT_SETTING, &pin_salt),
                (KILL_SWITCH_PIN_HASH_SETTING, &pin_hash),
                (KILL_SWITCH_PIN_CREATED_AT_SETTING, &now),
            ],
            || {
                files.install().map_err(|error| {
                    r3akt_rch_core::RchCoreError::Encode(format!(
                        "setup configuration installation failed: {error:?}"
                    ))
                })
            },
        )
    });
    match enrollment {
        Ok(true) => {}
        Ok(false) => {
            return Err(ApiError::Conflict(
                "First-run setup has already enrolled a kill switch PIN".to_string(),
            ));
        }
        Err(error) => {
            if let Err(rollback) = files.restore() {
                eprintln!(
                    "failed setup requires configuration recovery: {error}; rollback: {rollback}"
                );
                return Err(rollback);
            }
            return Err(error);
        }
    }
    runtime.message = "Kill switch PIN enrolled by first-run setup.".to_string();
    runtime.updated_at_ts_ms = unix_now_ms();
    response["setup_required"] = json!(false);
    response["pin_enrolled"] = json!(true);
    response["pin_created_at"] = json!(iso8601_from_unix_ms(now_ms));
    response["remote_password_configured"] = json!(true);
    response["remote_password_created_at"] = response["pin_created_at"].clone();
    response["hub_name"] = json!(hub_name);
    Ok(response)
}

pub(super) fn first_run_setup_status_payload(
    state: &AppState,
    include_sensitive_paths: bool,
) -> Result<Value, ApiError> {
    let pin = load_kill_switch_pin(state)?;
    let setup_required = pin.is_none();
    let expose_paths = include_sensitive_paths;
    let remote_password = load_stored_remote_password(state)?;
    let hub_name =
        with_required_core_store_write(state, |store| store.setting_value(HUB_NAME_SETTING))?;
    let reticulum_identity = ensure_reticulum_identity_status(state)?;
    Ok(json!({
        "setup_required": setup_required,
        "pin_enrolled": pin.is_some(),
        "pin_created_at": pin.as_ref().map(|secret| iso8601_from_unix_ms(secret.created_at_ts_ms)),
        "hub_name": hub_name,
        "remote_password_configured": remote_password.is_some(),
        "remote_password_created_at": remote_password
            .as_ref()
            .map(|secret| iso8601_from_unix_ms(secret.created_at_ts_ms)),
        "config_path": expose_paths
            .then(|| state.config_path.as_deref().map(|path| path.display().to_string()))
            .flatten(),
        "reticulum_config_path": expose_paths
            .then(|| {
                state
                    .reticulum_config_path
                    .as_deref()
                    .map(|path| path.display().to_string())
            })
            .flatten(),
        "reticulum_identity_hash": reticulum_identity.as_ref().map(|identity| identity.hash.clone()),
        "reticulum_identity_path": expose_paths
            .then(|| {
                reticulum_identity
                    .as_ref()
                    .map(|identity| identity.path.display().to_string())
            })
            .flatten(),
        "reticulum_identity_created": reticulum_identity.as_ref().map(|identity| identity.created),
    }))
}
