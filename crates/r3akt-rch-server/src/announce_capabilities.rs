//! Optional announce capability metadata is untrusted, including embedded `MessagePack`.
use super::{Value, normalize_capability_value};
use std::sync::atomic::{AtomicU64, Ordering};

mod msgpack;
#[cfg(test)]
mod tests;

const MAX_APP_DATA_BYTES: usize = 16 * 1024;
const MAX_DEPTH: usize = 32;
const MAX_ITEMS: usize = 4096;
static REJECTED: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Copy, Debug, PartialEq, Eq, thiserror::Error)]
enum DecodeError {
    #[error("app data exceeds byte limit")]
    TooLarge,
    #[error("invalid app-data hex")]
    Hex,
    #[error("malformed or truncated MessagePack")]
    Malformed,
    #[error("MessagePack nesting exceeds limit")]
    Depth,
    #[error("MessagePack item count exceeds limit")]
    Items,
    #[error("unsupported capability value")]
    Value,
}

pub(super) fn diagnostics() -> Value {
    serde_json::json!({
        "rejected_total": REJECTED.load(Ordering::Relaxed),
        "max_app_data_bytes": MAX_APP_DATA_BYTES,
        "max_depth": MAX_DEPTH,
        "max_items": MAX_ITEMS,
    })
}

fn rejected(error: DecodeError) {
    let count = REJECTED.fetch_add(1, Ordering::Relaxed).saturating_add(1);
    // A replayed bad record must not turn into an unbounded journal flood.
    if count.is_power_of_two() {
        eprintln!("announce capability metadata rejected: {error}; rejected_total={count}");
    }
}

pub(super) fn decode_hex(raw_hex: &str) -> Vec<String> {
    match decode_hex_result(raw_hex) {
        Ok(capabilities) => capabilities,
        Err(error) => {
            rejected(error);
            Vec::new()
        }
    }
}

fn decode_hex_result(raw_hex: &str) -> Result<Vec<String>, DecodeError> {
    // Count surrounding whitespace too: never allocate from unbounded encoded input.
    if raw_hex.len() > MAX_APP_DATA_BYTES * 2 {
        return Err(DecodeError::TooLarge);
    }
    let text = raw_hex.trim();
    if text.is_empty() {
        return Ok(Vec::new());
    }
    if !text.len().is_multiple_of(2) {
        return Err(DecodeError::Hex);
    }
    let mut bytes = Vec::with_capacity(text.len() / 2);
    for pair in text.as_bytes().as_chunks::<2>().0 {
        let high = hex_digit(pair[0]).ok_or(DecodeError::Hex)?;
        let low = hex_digit(pair[1]).ok_or(DecodeError::Hex)?;
        bytes.push((high << 4) | low);
    }
    decode(&bytes)
}

fn hex_digit(byte: u8) -> Option<u8> {
    match byte {
        b'0'..=b'9' => Some(byte - b'0'),
        b'a'..=b'f' => Some(byte - b'a' + 10),
        b'A'..=b'F' => Some(byte - b'A' + 10),
        _ => None,
    }
}

fn decode(bytes: &[u8]) -> Result<Vec<String>, DecodeError> {
    if bytes.len() > MAX_APP_DATA_BYTES {
        return Err(DecodeError::TooLarge);
    }
    if let Ok(text) = std::str::from_utf8(bytes) {
        let capabilities = normalize_capability_value(&Value::String(text.to_owned()));
        if !capabilities.is_empty() {
            return Ok(capabilities);
        }
    }
    if bytes.is_empty() {
        return Ok(Vec::new());
    }
    // This validates the complete document before collecting any array slices.
    if let Some(slots) = msgpack::array_items(bytes)? {
        for slot in slots.into_iter().skip(2) {
            match decode_slot(slot) {
                Ok(capabilities) if !capabilities.is_empty() => return Ok(capabilities),
                Ok(_) => {}
                Err(error) => rejected(error),
            }
        }
        return Ok(Vec::new());
    }
    let value = decode_value(bytes)?;
    Ok(normalize_capability_value(&value))
}

fn decode_value(bytes: &[u8]) -> Result<Value, DecodeError> {
    // Every serde decode, including embedded values, crosses this same boundary.
    msgpack::validate(bytes)?;
    rmp_serde::from_slice(bytes).map_err(|_| DecodeError::Value)
}

fn decode_slot(slot: &[u8]) -> Result<Vec<String>, DecodeError> {
    if let Some((bytes, binary)) = msgpack::byte_payload(slot)? {
        match decode_value(bytes) {
            Ok(value) => {
                let caps = normalize_capability_value(&value);
                if !caps.is_empty() {
                    return Ok(caps);
                }
            }
            Err(error) if binary => return Err(error),
            // Ordinary string capabilities need not contain an embedded document.
            Err(_) => {}
        }
    }
    let value = decode_value(slot)?;
    let caps = normalize_capability_value(&value);
    if !caps.is_empty() {
        return Ok(caps);
    }
    if let Value::Array(items) = value {
        let bytes = items
            .iter()
            .map(|item| item.as_u64().and_then(|v| u8::try_from(v).ok()))
            .collect::<Option<Vec<u8>>>();
        if let Some(bytes) = bytes {
            return decode_value(&bytes).map(|value| normalize_capability_value(&value));
        }
    }
    Ok(Vec::new())
}
