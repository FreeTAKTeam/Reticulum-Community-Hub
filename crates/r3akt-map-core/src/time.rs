//! Timestamp formatting shared by marker representations.

use chrono::{DateTime, SecondsFormat};

/// Formats Unix milliseconds as RFC 3339 UTC (`Z`), as the RCH API does.
/// Out-of-range values fall back to the Unix epoch.
#[must_use]
pub fn iso8601_from_unix_ms(ts_ms: i64) -> String {
    DateTime::from_timestamp_millis(ts_ms).map_or_else(
        || "1970-01-01T00:00:00Z".to_string(),
        |timestamp| timestamp.to_rfc3339_opts(SecondsFormat::AutoSi, true),
    )
}

/// Parses an RFC 3339 timestamp (as written by [`iso8601_from_unix_ms`]) to
/// Unix milliseconds.
#[must_use]
pub fn unix_ms_from_iso8601(value: &str) -> Option<i64> {
    DateTime::parse_from_rfc3339(value.trim())
        .ok()
        .map(|timestamp| timestamp.timestamp_millis())
}
