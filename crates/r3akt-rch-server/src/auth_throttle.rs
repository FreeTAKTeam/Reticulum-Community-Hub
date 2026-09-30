use std::collections::{HashMap, VecDeque};
use std::net::SocketAddr;

use super::{
    AUTH_FAILURE_LIMIT, AUTH_FAILURE_WINDOW_MS, AUTH_LOCKOUT_MS, AUTH_LOCKOUT_RETRY_AFTER_SECS,
    ApiError, AppState, unix_now_ms,
};

const MAX_AUTH_CLIENTS: usize = 4096;
const PRUNE_INTERVAL_MS: i64 = 1000;

#[derive(Debug, Default)]
pub(super) struct AuthThrottleState {
    clients: HashMap<String, AuthFailureWindow>,
    last_prune_ts_ms: i64,
}

#[derive(Debug, Default)]
struct AuthFailureWindow {
    failures: VecDeque<i64>,
    locked_until_ts_ms: Option<i64>,
}

impl AuthThrottleState {
    fn prune(&mut self, now_ms: i64) {
        if now_ms.saturating_sub(self.last_prune_ts_ms) < PRUNE_INTERVAL_MS {
            return;
        }
        self.last_prune_ts_ms = now_ms;
        self.clients.retain(|_, window| {
            window
                .failures
                .retain(|failure| now_ms.saturating_sub(*failure) <= AUTH_FAILURE_WINDOW_MS);
            if window
                .locked_until_ts_ms
                .is_some_and(|until| until <= now_ms)
            {
                window.locked_until_ts_ms = None;
            }
            !window.failures.is_empty() || window.locked_until_ts_ms.is_some()
        });
    }

    fn ensure_capacity(&self, key: &str) -> Result<(), ApiError> {
        if self.clients.len() >= MAX_AUTH_CLIENTS && !self.clients.contains_key(key) {
            return Err(rate_limit_error());
        }
        Ok(())
    }
}

impl AppState {
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
        throttle.prune(now_ms);
        throttle.ensure_capacity(&key)?;
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
        throttle.prune(now_ms);
        throttle.ensure_capacity(&key)?;
        let window = throttle.clients.entry(key).or_default();
        if window
            .locked_until_ts_ms
            .is_some_and(|until| until > now_ms)
        {
            return Err(rate_limit_error());
        }
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

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::{HeaderMap, HeaderValue};

    #[test]
    fn expired_clients_are_reclaimed_and_capacity_is_finite() {
        let state = AppState::default().with_api_key("secret");
        for client in 0..MAX_AUTH_CLIENTS {
            let peer = SocketAddr::from(([10, 1, (client >> 8) as u8, client as u8], 5000));
            state
                .record_auth_failure("http", Some(peer))
                .expect("record failure");
        }
        let new_peer = Some(SocketAddr::from(([10, 2, 0, 1], 5000)));
        assert!(matches!(
            state.record_auth_failure("http", new_peer),
            Err(ApiError::TooManyRequests { .. })
        ));
        assert_eq!(
            state.auth_throttle.lock().expect("throttle").clients.len(),
            MAX_AUTH_CLIENTS
        );
        let mut headers = HeaderMap::new();
        headers.insert("X-API-Key", HeaderValue::from_static("secret"));
        assert!(
            state
                .validate_http_headers(&headers, new_peer)
                .expect("valid key during overload")
        );
        let mut throttle = state.auth_throttle.lock().expect("throttle");
        throttle.prune(unix_now_ms() + AUTH_FAILURE_WINDOW_MS + PRUNE_INTERVAL_MS + 1);
        assert!(throttle.clients.is_empty());
    }

    #[test]
    fn lockout_is_not_extended_by_concurrent_rejected_attempts() {
        let state = AppState::default();
        for _ in 0..AUTH_FAILURE_LIMIT {
            let _ = state.record_auth_failure("http", None);
        }
        for _ in 0..20 {
            assert!(state.record_auth_failure("http", None).is_err());
        }
        let throttle = state.auth_throttle.lock().expect("throttle");
        assert_eq!(
            throttle.clients["http:unknown"].failures.len(),
            AUTH_FAILURE_LIMIT
        );
    }
}
