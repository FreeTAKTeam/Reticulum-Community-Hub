//! Checked `MessagePack` parsing for untrusted LXMF field payloads.
//!
//! Requires exact consumption, finite floats and unambiguous map keys, limits
//! nesting to 32 levels and bounds container allocation by available bytes.

use base64::Engine as _;
use serde_json::Value as JsonValue;

/// A parsed `MessagePack` value.
#[derive(Debug)]
pub enum Value {
    Nil,
    Bool(bool),
    I64(i64),
    U64(u64),
    F64(f64),
    String(String),
    Bytes(Vec<u8>),
    Array(Vec<Value>),
    Map(Vec<(Value, Value)>),
}

/// Parses one value starting at the beginning of `bytes`, returning it and
/// the number of bytes consumed.
#[must_use]
pub fn parse_value(bytes: &[u8]) -> Option<(Value, usize)> {
    parse_lxmf_msgpack_value(bytes, 0, 0)
}

/// Parses `bytes` as exactly one value and converts it to JSON. Byte strings
/// become arrays of byte values; binary map keys become `base64:` keys.
#[must_use]
pub fn to_json(bytes: &[u8]) -> Option<JsonValue> {
    let (value, offset) = parse_value(bytes)?;
    (offset == bytes.len()).then(|| value_to_json(value))
}

fn parse_lxmf_msgpack_value(bytes: &[u8], offset: usize, depth: usize) -> Option<(Value, usize)> {
    if depth > 32 {
        return None;
    }
    let marker = *bytes.get(offset)?;
    let next = offset + 1;
    match marker {
        0x00..=0x7f => Some((Value::U64(u64::from(marker)), next)),
        0x80..=0x8f => parse_lxmf_msgpack_map(bytes, next, usize::from(marker & 0x0f), depth),
        0x90..=0x9f => parse_lxmf_msgpack_array(bytes, next, usize::from(marker & 0x0f), depth),
        0xa0..=0xbf => parse_lxmf_msgpack_string(bytes, next, usize::from(marker & 0x1f)),
        0xc0 => Some((Value::Nil, next)),
        0xc2 => Some((Value::Bool(false), next)),
        0xc3 => Some((Value::Bool(true), next)),
        0xc4 => {
            let len = usize::from(*bytes.get(next)?);
            parse_lxmf_msgpack_bytes(bytes, next + 1, len)
        }
        0xc5 => {
            let len = usize::from(read_be_u16_at(bytes, next)?);
            parse_lxmf_msgpack_bytes(bytes, next + 2, len)
        }
        0xc6 => {
            let len = usize::try_from(read_be_u32_at(bytes, next)?).ok()?;
            parse_lxmf_msgpack_bytes(bytes, next + 4, len)
        }
        0xca..=0xd3 => parse_lxmf_msgpack_number(bytes, next, marker),
        0xd9 => {
            let len = usize::from(*bytes.get(next)?);
            parse_lxmf_msgpack_string(bytes, next + 1, len)
        }
        0xda => {
            let len = usize::from(read_be_u16_at(bytes, next)?);
            parse_lxmf_msgpack_string(bytes, next + 2, len)
        }
        0xdb => {
            let len = usize::try_from(read_be_u32_at(bytes, next)?).ok()?;
            parse_lxmf_msgpack_string(bytes, next + 4, len)
        }
        0xdc => parse_lxmf_msgpack_array(
            bytes,
            next + 2,
            usize::from(read_be_u16_at(bytes, next)?),
            depth,
        ),
        0xdd => parse_lxmf_msgpack_array(
            bytes,
            next + 4,
            usize::try_from(read_be_u32_at(bytes, next)?).ok()?,
            depth,
        ),
        0xde => parse_lxmf_msgpack_map(
            bytes,
            next + 2,
            usize::from(read_be_u16_at(bytes, next)?),
            depth,
        ),
        0xdf => parse_lxmf_msgpack_map(
            bytes,
            next + 4,
            usize::try_from(read_be_u32_at(bytes, next)?).ok()?,
            depth,
        ),
        0xe0..=0xff => Some((Value::I64(i64::from(i8::from_be_bytes([marker]))), next)),
        _ => None,
    }
}

fn parse_lxmf_msgpack_number(bytes: &[u8], next: usize, marker: u8) -> Option<(Value, usize)> {
    match marker {
        0xca => {
            let value = f64::from(f32::from_bits(read_be_u32_at(bytes, next)?));
            value.is_finite().then_some((Value::F64(value), next + 4))
        }
        0xcb => {
            let value = f64::from_bits(read_be_u64_at(bytes, next)?);
            value.is_finite().then_some((Value::F64(value), next + 8))
        }
        0xcc => Some((Value::U64(u64::from(*bytes.get(next)?)), next + 1)),
        0xcd => Some((
            Value::U64(u64::from(read_be_u16_at(bytes, next)?)),
            next + 2,
        )),
        0xce => Some((
            Value::U64(u64::from(read_be_u32_at(bytes, next)?)),
            next + 4,
        )),
        0xcf => Some((Value::U64(read_be_u64_at(bytes, next)?), next + 8)),
        0xd0 => Some((
            Value::I64(i64::from(i8::from_be_bytes([*bytes.get(next)?]))),
            next + 1,
        )),
        0xd1 => Some((
            Value::I64(i64::from(i16::from_be_bytes(
                bytes.get(next..next + 2)?.try_into().ok()?,
            ))),
            next + 2,
        )),
        0xd2 => Some((
            Value::I64(i64::from(i32::from_be_bytes(
                bytes.get(next..next + 4)?.try_into().ok()?,
            ))),
            next + 4,
        )),
        0xd3 => Some((
            Value::I64(i64::from_be_bytes(
                bytes.get(next..next + 8)?.try_into().ok()?,
            )),
            next + 8,
        )),
        _ => None,
    }
}

fn parse_lxmf_msgpack_array(
    bytes: &[u8],
    mut offset: usize,
    len: usize,
    depth: usize,
) -> Option<(Value, usize)> {
    if len > bytes.len().saturating_sub(offset) {
        return None;
    }
    let mut items = Vec::with_capacity(len);
    for _ in 0..len {
        let (value, next) = parse_lxmf_msgpack_value(bytes, offset, depth + 1)?;
        items.push(value);
        offset = next;
    }
    Some((Value::Array(items), offset))
}

fn parse_lxmf_msgpack_map(
    bytes: &[u8],
    mut offset: usize,
    len: usize,
    depth: usize,
) -> Option<(Value, usize)> {
    if len > bytes.len().saturating_sub(offset) / 2 {
        return None;
    }
    let mut keys = std::collections::HashSet::new();
    let mut items = Vec::with_capacity(len);
    for _ in 0..len {
        let (key, next) = parse_lxmf_msgpack_value(bytes, offset, depth + 1)?;
        let key_name = match &key {
            Value::I64(v) => v.to_string(),
            Value::U64(v) => v.to_string(),
            Value::String(v) => v.clone(),
            Value::Bytes(v) => format!(
                "base64:{}",
                base64::engine::general_purpose::STANDARD.encode(v)
            ),
            _ => return None,
        };
        if !keys.insert(key_name) {
            return None;
        }
        let (value, next) = parse_lxmf_msgpack_value(bytes, next, depth + 1)?;
        items.push((key, value));
        offset = next;
    }
    Some((Value::Map(items), offset))
}

fn parse_lxmf_msgpack_bytes(bytes: &[u8], offset: usize, len: usize) -> Option<(Value, usize)> {
    let end = offset.checked_add(len)?;
    Some((Value::Bytes(bytes.get(offset..end)?.to_vec()), end))
}

fn parse_lxmf_msgpack_string(bytes: &[u8], offset: usize, len: usize) -> Option<(Value, usize)> {
    let end = offset.checked_add(len)?;
    let value = std::str::from_utf8(bytes.get(offset..end)?)
        .ok()?
        .to_string();
    Some((Value::String(value), end))
}

fn value_to_json(value: Value) -> JsonValue {
    match value {
        Value::Nil => JsonValue::Null,
        Value::Bool(value) => JsonValue::Bool(value),
        Value::I64(value) => JsonValue::from(value),
        Value::U64(value) => JsonValue::from(value),
        Value::F64(value) => JsonValue::from(value),
        Value::String(value) => JsonValue::String(value),
        Value::Bytes(bytes) => JsonValue::Array(bytes.into_iter().map(JsonValue::from).collect()),
        Value::Array(items) => JsonValue::Array(items.into_iter().map(value_to_json).collect()),
        Value::Map(items) => JsonValue::Object(
            items
                .into_iter()
                .filter_map(|(key, value)| {
                    lxmf_msgpack_key_to_string(key).map(|key| (key, value_to_json(value)))
                })
                .collect(),
        ),
    }
}

fn lxmf_msgpack_key_to_string(value: Value) -> Option<String> {
    match value {
        Value::I64(value) => Some(value.to_string()),
        Value::U64(value) => Some(value.to_string()),
        Value::String(value) => Some(value),
        Value::Bytes(value) => Some(format!(
            "base64:{}",
            base64::engine::general_purpose::STANDARD.encode(value)
        )),
        _ => None,
    }
}

fn read_be_u16_at(bytes: &[u8], offset: usize) -> Option<u16> {
    Some(u16::from_be_bytes(
        bytes.get(offset..offset + 2)?.try_into().ok()?,
    ))
}

fn read_be_u32_at(bytes: &[u8], offset: usize) -> Option<u32> {
    Some(u32::from_be_bytes(
        bytes.get(offset..offset + 4)?.try_into().ok()?,
    ))
}

fn read_be_u64_at(bytes: &[u8], offset: usize) -> Option<u64> {
    Some(u64::from_be_bytes(
        bytes.get(offset..offset + 8)?.try_into().ok()?,
    ))
}
