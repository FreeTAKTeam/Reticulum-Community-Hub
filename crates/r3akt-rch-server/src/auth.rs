use std::net::SocketAddr;

use argon2::Argon2;
use argon2::password_hash::{PasswordHash, PasswordHasher, PasswordVerifier, SaltString};
use axum::http::HeaderMap;
use rand_core::OsRng;
use serde_json::{Value, json};
use uuid::Uuid;

use super::{
    ApiError, AppState, KILL_SWITCH_PIN_CREATED_AT_SETTING, KILL_SWITCH_PIN_HASH_SETTING,
    KILL_SWITCH_PIN_SALT_SETTING, KillSwitchPinSecret, REMOTE_ACCESS_PASSWORD_CREATED_AT_SETTING,
    REMOTE_ACCESS_PASSWORD_HASH_SETTING, REMOTE_ACCESS_PASSWORD_SALT_SETTING, StoredPasswordSecret,
    bearer_token, is_local_client_addr, openapi_json_response, openapi_operation,
    openapi_schema_ref, sha256_lower_hex, with_required_core_store_write,
};

impl AppState {
    pub(super) fn validate_http_headers(
        &self,
        headers: &HeaderMap,
        client_addr: Option<SocketAddr>,
    ) -> Result<bool, ApiError> {
        let api_key = headers
            .get("X-API-Key")
            .and_then(|value| value.to_str().ok());
        let bearer = bearer_token(headers);
        if let Some(expected) = &self.api_key {
            if api_key.is_some_and(|value| secure_string_eq(value, expected))
                || bearer.is_some_and(|value| secure_string_eq(value, expected))
            {
                self.clear_auth_failures("http", client_addr)?;
                return Ok(true);
            }
        }
        self.ensure_auth_attempt_allowed("http", client_addr)?;
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
        if let Some(expected) = &self.api_key {
            if api_key.is_some_and(|value| secure_string_eq(value, expected))
                || token.is_some_and(|value| secure_string_eq(value, expected))
            {
                self.clear_auth_failures("websocket", client_addr)?;
                return Ok(true);
            }
        }
        self.ensure_auth_attempt_allowed("websocket", client_addr)?;
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

    pub(super) fn remote_password_configured(&self) -> Result<bool, ApiError> {
        if self.sqlite_path.is_none() {
            return Ok(false);
        }
        Ok(load_stored_remote_password(self)?.is_some())
    }

    pub(super) fn credentials_configured(&self) -> Result<bool, ApiError> {
        Ok(self.api_key.is_some() || self.remote_password_configured()?)
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
            eprintln!("migrating legacy remote password hash to Argon2id");
            if !migrate_remote_access_password(self, password, &secret)? {
                // Enrollment or another migration won the race. Authenticate against its record.
                let current = load_stored_remote_password(self)?.ok_or_else(|| {
                    ApiError::Internal(
                        "authentication record disappeared during migration".to_string(),
                    )
                })?;
                return verify_versioned_secret(&current.salt, &current.hash, password);
            }
        }
        Ok(valid)
    }
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
        if salt.is_empty() || hash.len() != 64 || !hash.bytes().all(|byte| byte.is_ascii_hexdigit())
        {
            return Err(ApiError::Internal(
                "invalid legacy authentication secret".to_string(),
            ));
        }
        return Ok(secure_string_eq(&password_hash(salt, value), hash));
    }
    let parsed = PasswordHash::new(hash)
        .map_err(|error| ApiError::Internal(format!("invalid Argon2id PHC secret: {error}")))?;
    if parsed.salt.is_none() || parsed.hash.is_none() {
        return Err(ApiError::Internal(
            "incomplete Argon2id authentication secret".to_string(),
        ));
    }
    match Argon2::default().verify_password(value.as_bytes(), &parsed) {
        Ok(()) => Ok(true),
        Err(argon2::password_hash::Error::Password) => Ok(false),
        Err(error) => Err(ApiError::Internal(format!(
            "invalid Argon2id authentication secret: {error}"
        ))),
    }
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
    let [salt, hash, created_at] = with_required_core_store_write(state, |store| {
        store.setting_values([
            KILL_SWITCH_PIN_SALT_SETTING,
            KILL_SWITCH_PIN_HASH_SETTING,
            KILL_SWITCH_PIN_CREATED_AT_SETTING,
        ])
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

pub(super) fn save_kill_switch_pin_secret(
    state: &AppState,
    salt: &str,
    hash: &str,
    created_at_ts_ms: i64,
) -> Result<(), ApiError> {
    with_required_core_store_write(state, |store| {
        store.set_setting_values_atomic(&[
            (KILL_SWITCH_PIN_SALT_SETTING, salt),
            (KILL_SWITCH_PIN_HASH_SETTING, hash),
            (
                KILL_SWITCH_PIN_CREATED_AT_SETTING,
                &created_at_ts_ms.to_string(),
            ),
        ])
    })
}

pub(super) fn load_stored_remote_password(
    state: &AppState,
) -> Result<Option<StoredPasswordSecret>, ApiError> {
    let [salt, hash, created_at] = with_required_core_store_write(state, |store| {
        store.setting_values([
            REMOTE_ACCESS_PASSWORD_SALT_SETTING,
            REMOTE_ACCESS_PASSWORD_HASH_SETTING,
            REMOTE_ACCESS_PASSWORD_CREATED_AT_SETTING,
        ])
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

fn migrate_remote_access_password(
    state: &AppState,
    password: &str,
    observed: &StoredPasswordSecret,
) -> Result<bool, ApiError> {
    let salt = Uuid::new_v4().to_string();
    let hash = argon2id_hash(password)?;
    with_required_core_store_write(state, |store| {
        store.compare_and_set_setting_values(
            &[
                (REMOTE_ACCESS_PASSWORD_SALT_SETTING, &observed.salt),
                (REMOTE_ACCESS_PASSWORD_HASH_SETTING, &observed.hash),
                (
                    REMOTE_ACCESS_PASSWORD_CREATED_AT_SETTING,
                    &observed.created_at_ts_ms.to_string(),
                ),
            ],
            &[
                (REMOTE_ACCESS_PASSWORD_SALT_SETTING, &salt),
                (REMOTE_ACCESS_PASSWORD_HASH_SETTING, &hash),
                (
                    REMOTE_ACCESS_PASSWORD_CREATED_AT_SETTING,
                    &observed.created_at_ts_ms.to_string(),
                ),
            ],
        )
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

#[cfg(test)]
mod migration_tests {
    use super::*;

    #[test]
    fn late_legacy_migration_cannot_overwrite_a_new_enrollment() {
        let path = std::env::temp_dir().join(format!("rch-password-race-{}.db", Uuid::new_v4()));
        let state = AppState::from_sqlite_path(&path).expect("state");
        let observed = StoredPasswordSecret {
            salt: "legacy-salt".to_string(),
            hash: password_hash("legacy-salt", "old-password"),
            created_at_ts_ms: 1234,
        };
        let new_hash = argon2id_hash("new-password").expect("new hash");
        with_required_core_store_write(&state, |store| {
            store.set_setting_values_atomic(&[
                (REMOTE_ACCESS_PASSWORD_SALT_SETTING, "new-salt"),
                (REMOTE_ACCESS_PASSWORD_HASH_SETTING, &new_hash),
                (REMOTE_ACCESS_PASSWORD_CREATED_AT_SETTING, "5678"),
            ])
        })
        .expect("intervening enrollment");
        assert!(
            !migrate_remote_access_password(&state, "old-password", &observed)
                .expect("stale migration")
        );
        assert!(
            !state
                .validate_stored_remote_password(Some("old-password"))
                .expect("old password")
        );
        assert!(
            state
                .validate_stored_remote_password(Some("new-password"))
                .expect("new password")
        );
        assert_eq!(
            load_stored_remote_password(&state)
                .expect("record")
                .expect("credential")
                .created_at_ts_ms,
            5678
        );
        std::fs::remove_file(path).expect("cleanup");
    }
}
