//! Allocation-free structural validation before `MessagePack` deserialization.
use super::{DecodeError, MAX_APP_DATA_BYTES, MAX_DEPTH, MAX_ITEMS};

struct Cursor<'a> {
    bytes: &'a [u8],
    offset: usize,
    remaining: usize,
}

impl<'a> Cursor<'a> {
    fn new(bytes: &'a [u8]) -> Self {
        Self {
            bytes,
            offset: 0,
            remaining: MAX_ITEMS,
        }
    }

    fn take(&mut self, len: usize) -> Result<&'a [u8], DecodeError> {
        let end = self.offset.checked_add(len).ok_or(DecodeError::Malformed)?;
        let value = self
            .bytes
            .get(self.offset..end)
            .ok_or(DecodeError::Malformed)?;
        self.offset = end;
        Ok(value)
    }

    fn length(&mut self, width: usize) -> Result<usize, DecodeError> {
        self.take(width)?.iter().try_fold(0_usize, |value, byte| {
            value
                .checked_mul(256)
                .and_then(|value| value.checked_add(usize::from(*byte)))
                .ok_or(DecodeError::Malformed)
        })
    }

    fn sequence(&mut self, count: usize, depth: usize) -> Result<(), DecodeError> {
        if count > self.remaining {
            return Err(DecodeError::Items);
        }
        // Every item needs at least one byte; reject impossible claims before looping.
        if count > self.bytes.len().saturating_sub(self.offset) {
            return Err(DecodeError::Malformed);
        }
        for _ in 0..count {
            self.item(depth)?;
        }
        Ok(())
    }

    fn item(&mut self, depth: usize) -> Result<(), DecodeError> {
        if depth > MAX_DEPTH {
            return Err(DecodeError::Depth);
        }
        self.remaining = self.remaining.checked_sub(1).ok_or(DecodeError::Items)?;
        let marker = self.take(1)?[0];
        match marker {
            0x00..=0x7f | 0xc0 | 0xc2 | 0xc3 | 0xe0..=0xff => {}
            0xcc | 0xd0 => {
                self.take(1)?;
            }
            0xcd | 0xd1 => {
                self.take(2)?;
            }
            0xca | 0xce | 0xd2 => {
                self.take(4)?;
            }
            0xcb | 0xcf | 0xd3 => {
                self.take(8)?;
            }
            0xa0..=0xbf => {
                self.take(usize::from(marker & 0x1f))?;
            }
            0xc4..=0xc6 | 0xd9..=0xdb => {
                let width = match marker {
                    0xc4 | 0xd9 => 1,
                    0xc5 | 0xda => 2,
                    _ => 4,
                };
                let len = self.length(width)?;
                self.take(len)?;
            }
            0x90..=0x9f => self.sequence(usize::from(marker & 0x0f), depth + 1)?,
            0xdc | 0xdd => {
                let count = self.length(if marker == 0xdc { 2 } else { 4 })?;
                self.sequence(count, depth + 1)?;
            }
            0x80..=0x8f => self.sequence(usize::from(marker & 0x0f) * 2, depth + 1)?,
            0xde | 0xdf => {
                let count = self.length(if marker == 0xde { 2 } else { 4 })?;
                self.sequence(count.checked_mul(2).ok_or(DecodeError::Items)?, depth + 1)?;
            }
            // Extension values have one type byte in addition to the payload.
            0xd4..=0xd8 => {
                self.take((1_usize << (marker - 0xd4)) + 1)?;
            }
            0xc7..=0xc9 => {
                let len = self.length(1_usize << (marker - 0xc7))?;
                self.take(len.checked_add(1).ok_or(DecodeError::Malformed)?)?;
            }
            _ => return Err(DecodeError::Malformed),
        }
        Ok(())
    }
}

pub(super) fn validate(bytes: &[u8]) -> Result<(), DecodeError> {
    if bytes.len() > MAX_APP_DATA_BYTES {
        return Err(DecodeError::TooLarge);
    }
    let mut cursor = Cursor::new(bytes);
    cursor.item(0)?;
    if cursor.offset != bytes.len() {
        return Err(DecodeError::Malformed);
    }
    Ok(())
}

pub(super) fn array_items(bytes: &[u8]) -> Result<Option<Vec<&[u8]>>, DecodeError> {
    validate(bytes)?;
    let mut cursor = Cursor::new(bytes);
    let count = match cursor.take(1)?[0] {
        marker @ 0x90..=0x9f => usize::from(marker & 0x0f),
        0xdc => cursor.length(2)?,
        0xdd => cursor.length(4)?,
        _ => return Ok(None),
    };
    let mut slots = Vec::new();
    for _ in 0..count {
        let start = cursor.offset;
        cursor.item(1)?;
        slots.push(&bytes[start..cursor.offset]);
    }
    Ok(Some(slots))
}

pub(super) fn byte_payload(bytes: &[u8]) -> Result<Option<(&[u8], bool)>, DecodeError> {
    validate(bytes)?;
    let mut cursor = Cursor::new(bytes);
    let marker = cursor.take(1)?[0];
    let (len, binary) = match marker {
        0xa0..=0xbf => (usize::from(marker & 0x1f), false),
        0xc4 | 0xd9 => (cursor.length(1)?, marker == 0xc4),
        0xc5 | 0xda => (cursor.length(2)?, marker == 0xc5),
        0xc6 | 0xdb => (cursor.length(4)?, marker == 0xc6),
        _ => return Ok(None),
    };
    Ok(Some((cursor.take(len)?, binary)))
}
