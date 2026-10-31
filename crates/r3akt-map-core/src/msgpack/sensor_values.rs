use super::{
    Value, parse_lxmf_msgpack_value, parse_value, read_be_u16_at, read_be_u32_at, skip_value,
};
/// Removes an optional numeric sensor while retaining every other encoded value verbatim.
/// # Errors
/// Rejects invalid outer maps or malformed sensor entries.
pub fn without_sensor(bytes: &[u8], sid: u8) -> Result<Vec<u8>, &'static str> {
    let (count, mut offset) = match bytes.first().copied() {
        Some(tag @ 0x80..=0x8f) => (usize::from(tag & 15), 1),
        Some(0xde) => (
            usize::from(read_be_u16_at(bytes, 1).ok_or("invalid sensor map")?),
            3,
        ),
        Some(0xdf) => (
            usize::try_from(read_be_u32_at(bytes, 1).ok_or("invalid sensor map")?)
                .map_err(|_| "sensor map overflow")?,
            5,
        ),
        _ => return Err("invalid sensor map"),
    };
    if bytes.len() > crate::telemetry::MAX_SENSOR_BYTES || count > bytes.len() / 2 {
        return Err("sensor map limit exceeded");
    }
    let mut entries = Vec::new();
    let mut kept = 0_u32;
    for _ in 0..count {
        let start = offset;
        let (key, next) =
            parse_lxmf_msgpack_value(bytes, offset, 1, false).ok_or("invalid sensor key")?;
        offset = skip_value(bytes, next).ok_or("invalid sensor value")?;
        if matches!(key,Value::U64(v) if v==u64::from(sid))
            || matches!(key,Value::I64(v) if v==i64::from(sid))
            || matches!(key,Value::String(ref s) if s==&sid.to_string())
        {
            continue;
        }
        entries.extend_from_slice(bytes.get(start..offset).ok_or("invalid sensor entry")?);
        kept += 1;
    }
    if offset != bytes.len() {
        return Err("trailing sensor bytes");
    }
    let mut output = if kept < 16 {
        vec![0x80 + u8::try_from(kept).map_err(|_| "sensor count overflow")?]
    } else if let Ok(count) = u16::try_from(kept) {
        let mut header = vec![0xde];
        header.extend_from_slice(&count.to_be_bytes());
        header
    } else {
        let mut header = vec![0xdf];
        header.extend_from_slice(&kept.to_be_bytes());
        header
    };
    output.extend(entries);
    Ok(output)
}

/// Replaces a numeric sensor while keeping other encoded sensor values intact.
/// # Errors
/// Rejects invalid sensor bytes, malformed maps or count overflow.
pub fn replace_sensor(
    bytes: &[u8],
    sid: u8,
    value: Option<&[u8]>,
) -> Result<Vec<u8>, &'static str> {
    let stripped = without_sensor(bytes, sid)?;
    let Some(value) = value else {
        return Ok(stripped);
    };
    let (_, consumed) = parse_value(value).ok_or("invalid replacement sensor")?;
    if consumed != value.len() {
        return Err("trailing replacement sensor bytes");
    }
    let (count, offset) = match stripped[0] {
        tag @ 0x80..=0x8f => (u32::from(tag & 15), 1),
        0xde => (
            u32::from(read_be_u16_at(&stripped, 1).ok_or("invalid sensor map")?),
            3,
        ),
        0xdf => (read_be_u32_at(&stripped, 1).ok_or("invalid sensor map")?, 5),
        _ => return Err("invalid sensor map"),
    };
    let count = count.checked_add(1).ok_or("sensor count overflow")?;
    let mut output = if let Some(n) = u8::try_from(count).ok().filter(|n| *n < 16) {
        vec![0x80 + n]
    } else if let Ok(n) = u16::try_from(count) {
        let mut h = vec![0xde];
        h.extend_from_slice(&n.to_be_bytes());
        h
    } else {
        let mut h = vec![0xdf];
        h.extend_from_slice(&count.to_be_bytes());
        h
    };
    output.extend_from_slice(&stripped[offset..]);
    if sid < 128 {
        output.push(sid);
    } else {
        output.extend_from_slice(&[0xcc, sid]);
    }
    output.extend_from_slice(value);
    if output.len() > crate::telemetry::MAX_SENSOR_BYTES {
        return Err("sensor packet limit exceeded");
    }
    Ok(output)
}
