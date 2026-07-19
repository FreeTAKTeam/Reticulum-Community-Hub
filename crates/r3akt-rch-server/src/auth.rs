use std::collections::{HashMap, VecDeque};
use std::net::SocketAddr;

use argon2::Argon2;
use argon2::password_hash::{PasswordHash, PasswordHasher, PasswordVerifier, SaltString};
use axum::http::HeaderMap;
use rand_core::OsRng;
use serde_json::{Value, json};
use uuid::Uuid;

use super::{
    AUTH_FAILURE_LIMIT, AUTH_FAILURE_WINDOW_MS, AUTH_LOCKOUT_MS, AUTH_LOCKOUT_RETRY_AFTER_SECS,
    ApiError, AppState, KILL_SWITCH_PIN_CREATED_AT_SETTING, KILL_SWITCH_PIN_HASH_SETTING,
    KILL_SWITCH_PIN_SALT_SETTING, KillSwitchPinSecret, REMOTE_ACCESS_PASSWORD_CREATED_AT_SETTING,
    REMOTE_ACCESS_PASSWORD_HASH_SETTING, REMOTE_ACCESS_PASSWORD_SALT_SETTING, StoredPasswordSecret,
    bearer_token, is_local_client_addr, openapi_json_response, openapi_operation,
    openapi_schema_ref, sha256_lower_hex, unix_now_ms, with_required_core_store_write,
};

#[derive(Debug, Default)]
pub(super) struct AuthThrottleState {
    clients: HashMap<String, AuthFailureWindow>,
}

#[derive(Debug, Default)]
struct AuthFailureWindow {
    failures: VecDeque<i64>,
    locked_until_ts_ms: Option<i64>,
}

impl AppState {
    pub(super) fn validate_http_headers(
        &self,
        headers: &HeaderMap,
        client_addr: Option<SocketAddr>,
    ) -> Result<bool, ApiError> {
        if is_local_client_addr(client_addr) {
            return Ok(true);
        }
        if client_addr.is_none() && self.api_key.is_none() {
            return Ok(true);
        }
        self.ensure_auth_attempt_allowed("http", client_addr)?;
        let api_key = headers
            .get("X-API-Key")
            .and_then(|value| value.to_str().ok());
        let bearer = bearer_token(headers);
        if let Some(expected) = &self.api_key {
            if api_key == Some(expected.as_str()) || bearer == Some(expected.as_str()) {
                self.clear_auth_failures("http", client_addr)?;
                return Ok(true);
            }
        }
        let supplied_credential = api_key.or(bearer);
        if self.validate_stored_remote_password(supplied_credential)? {
            self.clear_auth_failures("http", client_addr)?;
            return Ok(true);
        }
        if supplied_credential.is_some() {
            self.record_auth_failure("http", client_addr)?;
        }
        Ok(false)
    }

    pub(super) fn http_auth_failure_detail(
        &self,
        client_addr: Option<SocketAddr>,
    ) -> Result<String, ApiError> {
        if !is_local_client_addr(client_addr)
            && self.api_key.is_none()
            && !self.remote_password_configured()?
        {
            Ok(
                "Remote access requires first-run setup or RTH_API_KEY (RCH_API_KEY is also supported)."
                    .to_string(),
            )
        } else {
            Ok("Unauthorized".to_string())
        }
    }

    pub(super) fn validate_ws_credentials(
        &self,
        api_key: Option<&str>,
        token: Option<&str>,
        client_addr: Option<SocketAddr>,
    ) -> Result<bool, ApiError> {
        if is_local_client_addr(client_addr) {
            return Ok(true);
        }
        if client_addr.is_none() && self.api_key.is_none() {
            return Ok(true);
        }
        self.ensure_auth_attempt_allowed("websocket", client_addr)?;
        if let Some(expected) = &self.api_key {
            if api_key == Some(expected.as_str()) || token == Some(expected.as_str()) {
                self.clear_auth_failures("websocket", client_addr)?;
                return Ok(true);
            }
        }
        let supplied_credential = api_key.or(token);
        if self.validate_stored_remote_password(supplied_credential)? {
            self.clear_auth_failures("websocket", client_addr)?;
            return Ok(true);
        }
        if supplied_credential.is_some() {
            self.record_auth_failure("websocket", client_addr)?;
        }
        Ok(false)
    }

    pub(super) fn ws_auth_failure_detail(
        &self,
        client_addr: Option<SocketAddr>,
    ) -> Result<String, ApiError> {
        self.http_auth_failure_detail(client_addr)
    }

    fn remote_password_configured(&self) -> Result<bool, ApiError> {
        if self.sqlite_path.is_none() {
            return Ok(false);
        }
        Ok(load_stored_remote_password(self)?.is_some())
    }

    pub(super) fn validate_stored_remote_password(
        &self,
        password: Option<&str>,
    ) -> Result<bool, ApiError> {
        let Some(password) = password.map(str::trim).filter(|value| !value.is_empty()) else {
            return Ok(false);
        };
        if self.sqlite_path.is_none() {
            return Ok(false);
        }
        let Some(secret) = load_stored_remote_password(self)? else {
            return Ok(false);
        };
        let valid = verify_versioned_secret(&secret.salt, &secret.hash, password)?;
        if valid && !is_argon2id_phc(&secret.hash) {
            save_remote_access_password_with_created_at(self, password, secret.created_at_ts_ms)?;
        }
        Ok(valid)
    }

    pub(super) fn ensure_auth_attempt_allowed(
        &self,
        surface: &str,
        client_addr: Option<SocketAddr>,
    ) -> Result<(), ApiError> {
        let now_ms = unix_now_ms();
        let key = auth_throttle_key(surface, client_addr);
        let mut throttle = self.auth_throttle.lock().map_err(|error| {
            ApiError::Internal(format!("authentication throttle lock poisoned: {error}"))
        })?;
        let Some(window) = throttle.clients.get_mut(&key) else {
            return Ok(());
        };
        if window
            .locked_until_ts_ms
            .is_some_and(|until| until > now_ms)
        {
            return Err(rate_limit_error());
        }
        window.locked_until_ts_ms = None;
        window
            .failures
            .retain(|failure| now_ms.saturating_sub(*failure) <= AUTH_FAILURE_WINDOW_MS);
        Ok(())
    }

    pub(super) fn record_auth_failure(
        &self,
        surface: &str,
        client_addr: Option<SocketAddr>,
    ) -> Result<(), ApiError> {
        let now_ms = unix_now_ms();
        let key = auth_throttle_key(surface, client_addr);
        let mut throttle = self.auth_throttle.lock().map_err(|error| {
            ApiError::Internal(format!("authentication throttle lock poisoned: {error}"))
        })?;
        let window = throttle.clients.entry(key).or_default();
        window
            .failures
            .retain(|failure| now_ms.saturating_sub(*failure) <= AUTH_FAILURE_WINDOW_MS);
        window.failures.push_back(now_ms);
        if window.failures.len() >= AUTH_FAILURE_LIMIT {
            window.locked_until_ts_ms = Some(now_ms.saturating_add(AUTH_LOCKOUT_MS));
            return Err(rate_limit_error());
        }
        Ok(())
    }

    pub(super) fn clear_auth_failures(
        &self,
        surface: &str,
        client_addr: Option<SocketAddr>,
    ) -> Result<(), ApiError> {
        let key = auth_throttle_key(surface, client_addr);
        self.auth_throttle
            .lock()
            .map_err(|error| {
                ApiError::Internal(format!("authentication throttle lock poisoned: {error}"))
            })?
            .clients
            .remove(&key);
        Ok(())
    }
}

fn rate_limit_error() -> ApiError {
    ApiError::TooManyRequests {
        detail: "Too many authentication failures; retry after five minutes".to_string(),
        retry_after_secs: AUTH_LOCKOUT_RETRY_AFTER_SECS,
    }
}

fn auth_throttle_key(surface: &str, client_addr: Option<SocketAddr>) -> String {
    let client = client_addr
        .map(|address| address.ip().to_string())
        .unwrap_or_else(|| "unknown".to_string());
    format!("{surface}:{client}")
}

pub(super) fn password_hash(salt: &str, value: &str) -> String {
    sha256_lower_hex(format!("{salt}:{value}").as_bytes())
}

pub(super) fn is_argon2id_phc(hash: &str) -> bool {
    hash.starts_with("$argon2id$")
}

pub(super) fn argon2id_hash(value: &str) -> Result<String, ApiError> {
    let salt = SaltString::generate(&mut OsRng);
    Argon2::default()
        .hash_password(value.as_bytes(), &salt)
        .map(|hash| hash.to_string())
        .map_err(|error| {
            ApiError::Internal(format!("failed to hash authentication secret: {error}"))
        })
}

pub(super) fn verify_versioned_secret(
    salt: &str,
    hash: &str,
    value: &str,
) -> Result<bool, ApiError> {
    if !is_argon2id_phc(hash) {
        return Ok(secure_string_eq(&password_hash(salt, value), hash));
    }
    let parsed = PasswordHash::new(hash)
        .map_err(|error| ApiError::Internal(format!("invalid Argon2id PHC secret: {error}")))?;
    Ok(Argon2::default()
        .verify_password(value.as_bytes(), &parsed)
        .is_ok())
}

fn secure_string_eq(left: &str, right: &str) -> bool {
    let left = left.as_bytes();
    let right = right.as_bytes();
    if left.len() != right.len() {
        return false;
    }
    left.iter()
        .zip(right.iter())
        .fold(0u8, |accumulator, (left, right)| {
            accumulator | (*left ^ *right)
        })
        == 0
}

pub(super) fn load_kill_switch_pin(
    state: &AppState,
) -> Result<Option<KillSwitchPinSecret>, ApiError> {
    let (salt, hash, created_at) = with_required_core_store_write(state, |store| {
        let salt = store.setting_value(KILL_SWITCH_PIN_SALT_SETTING)?;
        let hash = store.setting_value(KILL_SWITCH_PIN_HASH_SETTING)?;
        let created_at = store.setting_value(KILL_SWITCH_PIN_CREATED_AT_SETTING)?;
        Ok((salt, hash, created_at))
    })?;
    match (salt, hash, created_at) {
        (None, None, None) => Ok(None),
        (Some(salt), Some(hash), Some(created_at)) if !salt.is_empty() && !hash.is_empty() => {
            let created_at_ts_ms = created_at.parse::<i64>().map_err(|error| {
                ApiError::Internal(format!(
                    "invalid kill switch PIN creation timestamp: {error}"
                ))
            })?;
            Ok(Some(KillSwitchPinSecret {
                salt,
                hash,
                created_at_ts_ms,
            }))
        }
        _ => Err(ApiError::Internal(
            "incomplete kill switch PIN authentication record".to_string(),
        )),
    }
}

pub(super) fn require_kill_switch_pin(state: &AppState) -> Result<KillSwitchPinSecret, ApiError> {
    load_kill_switch_pin(state)?.ok_or_else(|| {
        ApiError::Conflict("First-run setup must configure the kill switch PIN".to_string())
    })
}

pub(super) fn save_kill_switch_pin(
    state: &AppState,
    pin: &str,
) -> Result<KillSwitchPinSecret, ApiError> {
    let salt = Uuid::new_v4().to_string();
    let created_at_ts_ms = unix_now_ms();
    let hash = argon2id_hash(pin)?;
    save_kill_switch_pin_secret(state, &salt, &hash, created_at_ts_ms)?;
    Ok(KillSwitchPinSecret {
        salt,
        hash,
        created_at_ts_ms,
    })
}

pub(super) fn save_kill_switch_pin_secret(
    state: &AppState,
    salt: &str,
    hash: &str,
    created_at_ts_ms: i64,
) -> Result<(), ApiError> {
    with_required_core_store_write(state, |store| {
        store.set_setting_value(KILL_SWITCH_PIN_SALT_SETTING, salt)?;
        store.set_setting_value(KILL_SWITCH_PIN_HASH_SETTING, hash)?;
        store.set_setting_value(
            KILL_SWITCH_PIN_CREATED_AT_SETTING,
            &created_at_ts_ms.to_string(),
        )?;
        Ok(())
    })
}

pub(super) fn load_stored_remote_password(
    state: &AppState,
) -> Result<Option<StoredPasswordSecret>, ApiError> {
    let (salt, hash, created_at) = with_required_core_store_write(state, |store| {
        let salt = store.setting_value(REMOTE_ACCESS_PASSWORD_SALT_SETTING)?;
        let hash = store.setting_value(REMOTE_ACCESS_PASSWORD_HASH_SETTING)?;
        let created_at = store.setting_value(REMOTE_ACCESS_PASSWORD_CREATED_AT_SETTING)?;
        Ok((salt, hash, created_at))
    })?;
    match (salt, hash, created_at) {
        (None, None, None) => Ok(None),
        (Some(salt), Some(hash), Some(created_at)) if !salt.is_empty() && !hash.is_empty() => {
            let created_at_ts_ms = created_at.parse::<i64>().map_err(|error| {
                ApiError::Internal(format!(
                    "invalid remote password creation timestamp: {error}"
                ))
            })?;
            Ok(Some(StoredPasswordSecret {
                salt,
                hash,
                created_at_ts_ms,
            }))
        }
        _ => Err(ApiError::Internal(
            "incomplete remote password authentication record".to_string(),
        )),
    }
}

pub(super) fn save_remote_access_password(
    state: &AppState,
    password: &str,
) -> Result<StoredPasswordSecret, ApiError> {
    save_remote_access_password_with_created_at(state, password, unix_now_ms())
}

fn save_remote_access_password_with_created_at(
    state: &AppState,
    password: &str,
    created_at_ts_ms: i64,
) -> Result<StoredPasswordSecret, ApiError> {
    let salt = Uuid::new_v4().to_string();
    let hash = argon2id_hash(password)?;
    with_required_core_store_write(state, |store| {
        store.set_setting_value(REMOTE_ACCESS_PASSWORD_SALT_SETTING, &salt)?;
        store.set_setting_value(REMOTE_ACCESS_PASSWORD_HASH_SETTING, &hash)?;
        store.set_setting_value(
            REMOTE_ACCESS_PASSWORD_CREATED_AT_SETTING,
            &created_at_ts_ms.to_string(),
        )?;
        Ok(())
    })?;
    Ok(StoredPasswordSecret {
        salt,
        hash,
        created_at_ts_ms,
    })
}

pub(super) fn openapi_auth_validation_operation() -> Value {
    openapi_operation(
        Vec::new(),
        None,
        json!({
            "200": openapi_json_response(
                "Authentication validation response.",
                openapi_schema_ref("AuthValidationResponse")
            ),
            "401": openapi_json_response("Authentication failed.", openapi_schema_ref("Error")),
            "429": {
                "description": "Five failures within five minutes lock this client and auth surface for five minutes.",
                "headers": {
                    "Retry-After": {
                        "description": "Seconds until authentication may be retried.",
                        "schema": { "type": "integer", "example": 300 }
                    }
                },
                "content": {
                    "application/json": { "schema": openapi_schema_ref("Error") }
                }
            },
            "500": {
                "description": "Unexpected authentication storage failure. Correlate the sanitized response identifier with server logs.",
                "headers": {
                    "X-Request-ID": {
                        "description": "Identifier written with the underlying server-side error.",
                        "schema": { "type": "string", "format": "uuid" }
                    }
                },
                "content": {
                    "application/json": { "schema": openapi_schema_ref("Error") }
                }
            }
        }),
    )
}
