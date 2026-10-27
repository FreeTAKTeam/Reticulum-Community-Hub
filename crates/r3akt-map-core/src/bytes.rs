//! Byte payloads carried in JSON projections of LXMF fields.

use base64::Engine as _;
use serde_json::Value as JsonValue;

/// Decodes bytes from a JSON projection: an array of byte values, or text
/// that is `base64:`/data-URL encoded, plausible bare base64, or raw UTF-8.
/// Returns an empty vector when the value has no byte interpretation.
#[must_use]
pub fn json_bytes(value: &JsonValue) -> Vec<u8> {
    if let Some(text) = value.as_str() {
        return decode_attachment_text(text);
    }
    if let Some(items) = value.as_array() {
        let mut bytes = Vec::with_capacity(items.len());
        for item in items {
            let Some(value) = item.as_u64() else {
                return Vec::new();
            };
            let Ok(byte) = u8::try_from(value) else {
                return Vec::new();
            };
            bytes.push(byte);
        }
        return bytes;
    }
    Vec::new()
}

fn decode_attachment_text(text: &str) -> Vec<u8> {
    let trimmed = text.trim();
    let encoded = trimmed
        .strip_prefix("base64:")
        .or_else(|| trimmed.split_once("base64,").map(|(_, encoded)| encoded));
    if let Some(encoded) = encoded
        && let Ok(bytes) = decode_base64_attachment(encoded)
    {
        return bytes;
    }
    if should_decode_base64_attachment(trimmed)
        && let Ok(bytes) = decode_base64_attachment(trimmed)
    {
        return bytes;
    }
    trimmed.as_bytes().to_vec()
}

fn decode_base64_attachment(text: &str) -> Result<Vec<u8>, base64::DecodeError> {
    let compact = text.split_whitespace().collect::<String>();
    base64::engine::general_purpose::STANDARD.decode(compact)
}

fn should_decode_base64_attachment(text: &str) -> bool {
    let compact = text.split_whitespace().collect::<String>();
    if compact.starts_with("data:") && compact.contains("base64,") {
        return true;
    }
    if compact
        .chars()
        .any(|value| matches!(value, '=' | '+' | '/'))
    {
        return true;
    }
    compact.len() >= 12 && compact.len() % 4 == 0 && compact.chars().all(is_base64_attachment_char)
}

fn is_base64_attachment_char(value: char) -> bool {
    value.is_ascii_alphanumeric() || matches!(value, '+' | '/' | '=')
}
