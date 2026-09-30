use std::time::Duration;

use serde_json::Value;
use ureq::http::{HeaderValue, Uri};
use ureq::tls::{RootCerts, TlsConfig, TlsProvider};

type Error = Box<dyn std::error::Error>;

pub(super) struct RchNorthboundClient {
    base: HttpBase,
    api_key: Option<HeaderValue>,
    agent: ureq::Agent,
}

impl RchNorthboundClient {
    pub(super) fn new(base_url: &str, api_key: Option<String>) -> Result<Self, Error> {
        Ok(Self {
            base: HttpBase::parse(base_url)?,
            api_key: api_key.map(|key| HeaderValue::from_str(&key)).transpose()?,
            agent: ureq::Agent::config_builder()
                .timeout_global(Some(Duration::from_secs(5)))
                .max_redirects(0)
                .http_status_as_error(false)
                .proxy(None)
                .tls_config(
                    TlsConfig::builder()
                        .provider(TlsProvider::NativeTls)
                        .root_certs(RootCerts::PlatformVerifier)
                        .build(),
                )
                .build()
                .new_agent(),
        })
    }

    pub(super) fn get_json(&self, path: &str) -> Result<Value, Error> {
        let mut request = self.agent.get(self.base.url_for(path));
        if let Some(key) = &self.api_key {
            request = request.header("X-API-Key", key);
        }
        Self::read_json(request.header("Accept", "application/json").call()?)
    }

    pub(super) fn post_json_idempotent(
        &self,
        path: &str,
        body: &Value,
        key: &str,
    ) -> Result<Value, Error> {
        let mut request = self.agent.post(self.base.url_for(path));
        if let Some(key) = &self.api_key {
            request = request.header("X-API-Key", key);
        }
        Self::read_json(
            request
                .header("Accept", "application/json")
                .header("Idempotency-Key", HeaderValue::from_str(key)?)
                .header("Content-Type", "application/json")
                .send(body.to_string().as_bytes())?,
        )
    }

    fn read_json(mut response: ureq::http::Response<ureq::Body>) -> Result<Value, Error> {
        if !response.status().is_success() {
            return Err(format!(
                "RCH northbound request failed with HTTP {}",
                response.status()
            )
            .into());
        }
        let body = response
            .body_mut()
            .with_config()
            .limit(4 * 1024 * 1024)
            .read_to_string()?;
        if body.trim().is_empty() {
            Ok(Value::Null)
        } else {
            Ok(serde_json::from_str(&body)?)
        }
    }
}

pub(super) struct HttpBase {
    origin: String,
    path_prefix: String,
}

impl HttpBase {
    pub(super) fn parse(base_url: &str) -> Result<Self, Error> {
        let uri: Uri = base_url.trim().parse()?;
        let scheme = uri.scheme_str().ok_or("RCH base URL scheme is required")?;
        let authority = uri.authority().ok_or("RCH base URL host is required")?;
        let host = uri.host().ok_or("RCH base URL host is required")?;
        if !matches!(scheme, "http" | "https")
            || authority.as_str().contains('@')
            || uri.query().is_some()
        {
            return Err(
                "RCH base URL must be an HTTP(S) URL without credentials or a query".into(),
            );
        }
        let suffix = if authority.as_str().starts_with('[') {
            authority
                .as_str()
                .split_once(']')
                .ok_or("invalid IPv6 host")?
                .1
        } else {
            authority
                .as_str()
                .find(':')
                .map_or("", |index| &authority.as_str()[index..])
        };
        if !suffix.is_empty() {
            suffix
                .strip_prefix(':')
                .ok_or("invalid URL port")?
                .parse::<u16>()?;
        }
        if scheme == "http"
            && !matches!(
                host.to_ascii_lowercase().as_str(),
                "localhost" | "127.0.0.1" | "[::1]" | "::1"
            )
        {
            return Err(
                "Remote RCH northbound connections require HTTPS; HTTP is limited to loopback"
                    .into(),
            );
        }
        Ok(Self {
            origin: format!("{scheme}://{authority}"),
            path_prefix: uri.path().trim_matches('/').to_string(),
        })
    }

    pub(super) fn path_for(&self, path: &str) -> String {
        let path = path.trim_start_matches('/');
        if self.path_prefix.is_empty() {
            format!("/{path}")
        } else {
            format!("/{}/{path}", self.path_prefix)
        }
    }

    fn url_for(&self, path: &str) -> String {
        format!("{}{}", self.origin, self.path_for(path))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn northbound_trust_boundary_rejects_plaintext_remote_and_malformed_authorities() {
        for url in [
            "http://remote.example",
            "http://localhost:bad",
            "http://localhost:65536",
            "http://localhost:",
            "https://user:pass@rch.example",
            "https://rch.example?query",
            "file:///tmp/rch",
        ] {
            assert!(HttpBase::parse(url).is_err(), "{url}");
        }
        for url in [
            "http://localhost:8000/api",
            "http://127.0.0.1:8000",
            "http://[::1]:8000",
            "https://rch.example",
        ] {
            assert!(HttpBase::parse(url).is_ok(), "{url}");
        }
        assert!(
            RchNorthboundClient::new(
                "http://localhost:8000",
                Some("key\r\nInjected: true".to_string())
            )
            .is_err()
        );
    }

    #[test]
    fn northbound_client_decodes_a_real_chunked_response() {
        use std::io::{Read, Write};
        let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("listener");
        let client = RchNorthboundClient::new(
            &format!("http://{}", listener.local_addr().expect("address")),
            None,
        )
        .expect("client");
        let server = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("accept");
            stream
                .set_read_timeout(Some(Duration::from_secs(2)))
                .expect("timeout");
            let mut buffer = [0; 2048];
            let size = stream.read(&mut buffer).expect("request");
            assert!(buffer[..size].starts_with(b"GET /Status HTTP/1.1\r\n"));
            stream.write_all(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n6\r\n{\"ok\":\r\n4\r\ntrue\r\n1\r\n}\r\n0\r\n\r\n").expect("response");
        });
        assert_eq!(
            client.get_json("/Status").expect("JSON"),
            serde_json::json!({"ok":true})
        );
        server.join().expect("server");
    }
}
