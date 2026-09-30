use std::collections::HashSet;
use std::sync::Arc;
use std::time::Duration;

use axum::extract::{Request, State};
use axum::http::{HeaderValue, StatusCode, Uri, header};
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use serde_json::json;
use tower_http::cors::{AllowOrigin, Any, CorsLayer};

use super::AppState;

pub(super) const UI_CONTENT_SECURITY_POLICY: &str = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https:; img-src 'self' data: blob: https:; font-src 'self' data: https://fonts.gstatic.com; connect-src 'self' https: wss: http://127.0.0.1:* http://localhost:* http://[::1]:* ws://127.0.0.1:* ws://localhost:* ws://[::1]:*; worker-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'";

pub(super) async fn response_security_headers(request: Request, next: Next) -> Response {
    let mut response = next.run(request).await;
    let headers = response.headers_mut();
    headers.insert(
        "X-Content-Type-Options",
        HeaderValue::from_static("nosniff"),
    );
    headers.insert("Referrer-Policy", HeaderValue::from_static("no-referrer"));
    headers.insert(
        "Permissions-Policy",
        HeaderValue::from_static("camera=(), microphone=(), geolocation=(self)"),
    );
    if headers
        .get(header::CONTENT_TYPE)
        .is_some_and(|value| value.as_bytes().starts_with(b"text/html"))
    {
        headers.insert(
            "Content-Security-Policy",
            HeaderValue::from_static(UI_CONTENT_SECURITY_POLICY),
        );
        headers.insert(
            "Cross-Origin-Opener-Policy",
            HeaderValue::from_static("same-origin"),
        );
        headers.insert("X-Frame-Options", HeaderValue::from_static("DENY"));
    }
    response
}

impl AppState {
    /// Add explicitly trusted UI origins, including a separately hosted UI or TLS proxy.
    /// Origins contain only scheme, host and optional port; credentials and paths are rejected.
    pub fn with_allowed_browser_origins(
        mut self,
        origins: impl IntoIterator<Item = String>,
    ) -> Result<Self, String> {
        let mut allowed = HashSet::new();
        for origin in origins {
            let origin = origin.trim();
            if origin.is_empty() {
                continue;
            }
            allowed.insert(canonical_origin(origin)?);
        }
        self.allowed_browser_origins = Arc::new(allowed);
        Ok(self)
    }
}

fn allowed_origin(state: &AppState, origin: &HeaderValue) -> bool {
    let Ok(origin) = origin.to_str() else {
        return false;
    };
    // The desktop shell hosts its own bundle. Its server always listens on loopback.
    if [
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
    ]
    .contains(&origin)
    {
        return state
            .api_bind
            .as_deref()
            .is_some_and(|bind| bind.ip().is_loopback());
    }
    let Ok(origin) = canonical_origin(origin) else {
        return false;
    };
    if state.allowed_browser_origins.contains(&origin) {
        return true;
    }
    let Some(bind) = state.api_bind.as_deref() else {
        return false;
    };
    let matches_origin =
        |candidate: String| canonical_origin(&candidate).is_ok_and(|candidate| candidate == origin);
    if !bind.ip().is_unspecified()
        && (matches_origin(format!("http://{bind}")) || matches_origin(format!("https://{bind}")))
    {
        return true;
    }
    if bind.ip().is_loopback() || bind.ip().is_unspecified() {
        let port = bind.port();
        return ["localhost", "127.0.0.1", "[::1]"].iter().any(|host| {
            matches_origin(format!("http://{host}:{port}"))
                || matches_origin(format!("https://{host}:{port}"))
        });
    }
    false
}

fn canonical_origin(origin: &str) -> Result<String, String> {
    let uri: Uri = origin
        .parse()
        .map_err(|error| format!("invalid browser origin: {error}"))?;
    if !matches!(uri.scheme_str(), Some("http" | "https"))
        || uri.host().is_none()
        || uri
            .authority()
            .is_some_and(|authority| authority.as_str().contains('@'))
        || uri.path() != "/"
        || uri.query().is_some()
        || origin.ends_with('/')
    {
        return Err(
            "Browser origins must be HTTP(S) origins without paths or credentials".to_string(),
        );
    }
    let scheme = uri.scheme_str().ok_or("missing browser origin scheme")?;
    let host = uri
        .host()
        .ok_or("missing browser origin host")?
        .to_ascii_lowercase();
    let authority = uri
        .authority()
        .ok_or("missing browser origin authority")?
        .as_str();
    let suffix = if authority.starts_with('[') {
        authority.split_once(']').ok_or("invalid IPv6 origin")?.1
    } else {
        authority
            .find(':')
            .map_or("", |offset| &authority[offset..])
    };
    let port = if suffix.is_empty() {
        if scheme == "https" { 443 } else { 80 }
    } else {
        suffix
            .strip_prefix(':')
            .ok_or("invalid browser origin port")?
            .parse::<u16>()
            .map_err(|_| "invalid browser origin port")?
    };
    Ok(format!("{scheme}://{host}:{port}"))
}

pub(super) fn trusted_bootstrap_authority(
    state: &AppState,
    headers: &axum::http::HeaderMap,
) -> bool {
    let Some(host) = headers.get(header::HOST) else {
        // In-process tests and non-browser adapters may lack HTTP authority metadata.
        return !headers.contains_key(header::ORIGIN) && !headers.contains_key("sec-fetch-site");
    };
    let Ok(host) = host.to_str() else {
        return false;
    };
    let Ok(origin) = canonical_origin(&format!("http://{host}")) else {
        return false;
    };
    let Some(bind) = state.api_bind.as_deref() else {
        return false;
    };
    ["localhost", "127.0.0.1", "[::1]"].iter().any(|host| {
        canonical_origin(&format!("http://{host}:{}", bind.port()))
            .is_ok_and(|candidate| candidate == origin)
    })
}

pub(super) fn cors_layer(state: &AppState) -> CorsLayer {
    let state = state.clone();
    CorsLayer::new()
        .allow_origin(AllowOrigin::predicate(move |origin, _| {
            allowed_origin(&state, origin)
        }))
        .allow_methods(Any)
        .allow_headers(Any)
        .max_age(Duration::from_secs(600))
}

pub(super) async fn enforce_browser_origin(
    State(state): State<AppState>,
    request: Request,
    next: Next,
) -> Response {
    let origin_allowed = request
        .headers()
        .get(header::ORIGIN)
        .is_none_or(|origin| allowed_origin(&state, origin));
    let cross_site_without_origin = !request.headers().contains_key(header::ORIGIN)
        && request
            .headers()
            .get("sec-fetch-site")
            .is_some_and(|value| value == "cross-site")
        && !super::is_ui_html_navigation(&state, &request);
    if !origin_allowed || cross_site_without_origin {
        return (
            StatusCode::FORBIDDEN,
            axum::Json(json!({"detail": "Browser origin is not allowed"})),
        )
            .into_response();
    }
    next.run(request).await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn origins_use_the_bound_authority_and_canonical_default_ports() {
        let state = AppState::default().with_api_bind("127.0.0.1:80".parse().expect("bind"));
        assert!(allowed_origin(
            &state,
            &HeaderValue::from_static("http://localhost")
        ));
        assert!(allowed_origin(
            &state,
            &HeaderValue::from_static("http://127.0.0.1")
        ));
        assert!(!allowed_origin(
            &state,
            &HeaderValue::from_static("http://attacker.example")
        ));
        assert!(!allowed_origin(
            &state,
            &HeaderValue::from_static("http://localhost:8000")
        ));
        assert!(!allowed_origin(&state, &HeaderValue::from_static("null")));
    }

    #[test]
    fn explicit_origins_are_validated_without_wildcards_or_user_info() {
        for origin in [
            "*",
            "null",
            "https://user:pass@rch.example",
            "https://rch.example/path",
            "https://rch.example?query",
            "https://rch.example/",
            "http://localhost:bad",
            "http://localhost:65536",
            "http://localhost:",
        ] {
            assert!(
                AppState::default()
                    .with_allowed_browser_origins([origin.to_string()])
                    .is_err(),
                "{origin}"
            );
        }
        let state = AppState::default()
            .with_allowed_browser_origins(["https://RCH.example:443".to_string()])
            .expect("origins");
        assert!(allowed_origin(
            &state,
            &HeaderValue::from_static("https://rch.example")
        ));
    }
}
