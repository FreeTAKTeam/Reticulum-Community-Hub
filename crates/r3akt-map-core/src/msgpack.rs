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
    let parsed = parse_lxmf_msgpack_value(bytes, 0, 0, false)?;
    finite(&parsed.0).then_some(parsed)
}

fn finite(value: &Value) -> bool {
    match value {
        Value::F64(v) => v.is_finite(),
        Value::Array(v) => v.iter().all(finite),
        Value::Map(v) => v.iter().all(|(k, v)| finite(k) && finite(v)),
        _ => true,
    }
}

/// Parses standard telemetry while isolating malformed optional R3S geometry.
/// All other sensors retain the strict finite-number contract.
#[must_use]
pub fn telemetry_to_json(bytes: &[u8]) -> Option<JsonValue> {
    let (mut value, offset) = parse_lxmf_msgpack_value(bytes, 0, 0, true)?;
    if offset != bytes.len() {
        return None;
    }
    if let Value::Map(entries) = &mut value {
        for (key, reading) in entries {
            if (matches!(key, Value::U64(128) | Value::I64(128))
                || matches!(key,Value::String(v) if v=="128"))
                && !finite(reading)
            {
                *reading = Value::Nil;
            }
        }
    }
    finite(&value).then(|| value_to_json(value))
}

/// Original encoded sensor value, allowing consumers to enforce its byte ceiling.
#[must_use]
pub fn telemetry_sensor_bytes(bytes: &[u8], sid: u8) -> Option<&[u8]> {
    let (count, mut offset) = match *bytes.first()? {
        tag @ 0x80..=0x8f => (usize::from(tag & 15), 1),
        0xde => (usize::from(read_be_u16_at(bytes, 1)?), 3),
        0xdf => (usize::try_from(read_be_u32_at(bytes, 1)?).ok()?, 5),
        _ => return None,
    };
    if count > bytes.len() / 2 {
        return None;
    }
    for _ in 0..count {
        let (key, next) = parse_lxmf_msgpack_value(bytes, offset, 1, false)?;
        let end = skip_value(bytes, next)?;
        if matches!(key,Value::U64(v) if v==u64::from(sid))
            || matches!(key,Value::I64(v) if v==i64::from(sid))
        {
            return bytes.get(next..end);
        }
        offset = end;
    }
    None
}

/// Parses `bytes` as exactly one value and converts it to JSON. Byte strings
/// become arrays of byte values; binary map keys become `base64:` keys.
#[must_use]
pub fn to_json(bytes: &[u8]) -> Option<JsonValue> {
    let (value, offset) = parse_value(bytes)?;
    (offset == bytes.len()).then(|| value_to_json(value))
}

fn parse_lxmf_msgpack_value(
    bytes: &[u8],
    offset: usize,
    depth: usize,
    telemetry: bool,
) -> Option<(Value, usize)> {
    if depth > 32 {
        return None;
    }
    let marker = *bytes.get(offset)?;
    let next = offset + 1;
    match marker {
        0x00..=0x7f => Some((Value::U64(u64::from(marker)), next)),
        0x80..=0x8f => {
            parse_lxmf_msgpack_map(bytes, next, usize::from(marker & 0x0f), depth, telemetry)
        }
        0x90..=0x9f => {
            parse_lxmf_msgpack_array(bytes, next, usize::from(marker & 0x0f), depth, telemetry)
        }
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
            telemetry,
        ),
        0xdd => parse_lxmf_msgpack_array(
            bytes,
            next + 4,
            usize::try_from(read_be_u32_at(bytes, next)?).ok()?,
            depth,
            telemetry,
        ),
        0xde => parse_lxmf_msgpack_map(
            bytes,
            next + 2,
            usize::from(read_be_u16_at(bytes, next)?),
            depth,
            telemetry,
        ),
        0xdf => parse_lxmf_msgpack_map(
            bytes,
            next + 4,
            usize::try_from(read_be_u32_at(bytes, next)?).ok()?,
            depth,
            telemetry,
        ),
        0xe0..=0xff => Some((Value::I64(i64::from(i8::from_be_bytes([marker]))), next)),
        _ => None,
    }
}

fn parse_lxmf_msgpack_number(bytes: &[u8], next: usize, marker: u8) -> Option<(Value, usize)> {
    match marker {
        0xca => {
            let value = f64::from(f32::from_bits(read_be_u32_at(bytes, next)?));
            Some((Value::F64(value), next + 4))
        }
        0xcb => {
            let value = f64::from_bits(read_be_u64_at(bytes, next)?);
            Some((Value::F64(value), next + 8))
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
    telemetry: bool,
) -> Option<(Value, usize)> {
    if len > bytes.len().saturating_sub(offset) {
        return None;
    }
    let mut items = Vec::with_capacity(len);
    for _ in 0..len {
        let (value, next) = parse_lxmf_msgpack_value(bytes, offset, depth + 1, telemetry)?;
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
    telemetry: bool,
) -> Option<(Value, usize)> {
    if len > bytes.len().saturating_sub(offset) / 2 {
        return None;
    }
    let mut keys = std::collections::HashSet::new();
    let mut items = Vec::with_capacity(len);
    for _ in 0..len {
        let (key, next) = parse_lxmf_msgpack_value(bytes, offset, depth + 1, telemetry)?;
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
        let (value, next) = if telemetry
            && depth == 0
            && (matches!(&key, Value::U64(128) | Value::I64(128))
                || matches!(&key,Value::String(v) if v=="128"))
        {
            let end = skip_value(bytes, next)?;
            let value = parse_lxmf_msgpack_value(bytes, next, depth + 1, false)
                .filter(|(_, offset)| *offset == end)
                .map_or(Value::Nil, |(value, _)| value);
            (value, end)
        } else {
            parse_lxmf_msgpack_value(bytes, next, depth + 1, telemetry)?
        };
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

// Advance over an optional value without allocating or recursing. Its typed
// decoder diagnoses unsupported shapes; malformed geometry cannot erase SID 2.
fn skip_value(bytes: &[u8], mut offset: usize) -> Option<usize> {
    let mut pending = 1usize;
    while pending > 0 {
        let tag = *bytes.get(offset)?;
        offset += 1;
        pending -= 1;
        let (extra, children) = match tag {
            0x00..=0x7f | 0xc0..=0xc3 | 0xe0..=0xff => (0, 0),
            0x80..=0x8f => (0, usize::from(tag & 15) * 2),
            0x90..=0x9f => (0, usize::from(tag & 15)),
            0xa0..=0xbf => (usize::from(tag & 31), 0),
            0xcc | 0xd0 => (1, 0),
            0xcd | 0xd1 => (2, 0),
            0xca | 0xce | 0xd2 => (4, 0),
            0xcb | 0xcf | 0xd3 => (8, 0),
            0xc4 | 0xd9 | 0xc7 => {
                let len = usize::from(*bytes.get(offset)?);
                offset += 1;
                (len + usize::from(tag == 0xc7), 0)
            }
            0xc5 | 0xda | 0xc8 => {
                let len = usize::from(read_be_u16_at(bytes, offset)?);
                offset += 2;
                (len + usize::from(tag == 0xc8), 0)
            }
            0xc6 | 0xdb | 0xc9 => {
                let len = usize::try_from(read_be_u32_at(bytes, offset)?).ok()?;
                offset += 4;
                (len.checked_add(usize::from(tag == 0xc9))?, 0)
            }
            0xd4..=0xd8 => (1 + (1usize << (tag - 0xd4)), 0),
            0xdc | 0xde => {
                let len = usize::from(read_be_u16_at(bytes, offset)?);
                offset += 2;
                (0, len * if tag == 0xde { 2 } else { 1 })
            }
            0xdd | 0xdf => {
                let len = usize::try_from(read_be_u32_at(bytes, offset)?).ok()?;
                offset += 4;
                (0, len.checked_mul(if tag == 0xdf { 2 } else { 1 })?)
            }
        };
        offset = offset.checked_add(extra)?;
        pending = pending.checked_add(children)?;
        if offset > bytes.len() || pending > bytes.len() - offset {
            return None;
        }
    }
    Some(offset)
}

mod sensor_values;
pub use sensor_values::{replace_sensor, without_sensor};
