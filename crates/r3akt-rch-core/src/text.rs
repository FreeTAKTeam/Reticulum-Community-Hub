pub(super) fn decode_utf8_ignoring_errors(bytes: &[u8]) -> String {
    let mut decoded = String::new();
    let mut remaining = bytes;
    while !remaining.is_empty() {
        match std::str::from_utf8(remaining) {
            Ok(valid) => {
                decoded.push_str(valid);
                break;
            }
            Err(error) => {
                let valid_up_to = error.valid_up_to();
                if valid_up_to > 0 {
                    decoded.push_str(&String::from_utf8_lossy(&remaining[..valid_up_to]));
                }
                let skip = error.error_len().unwrap_or(1);
                remaining = &remaining[(valid_up_to + skip).min(remaining.len())..];
            }
        }
    }
    decoded
}
