use serde_json::Value;

pub(super) fn parse_ws_json(payload: &str) -> Result<Value, serde_json::Error> {
    let parsed = serde_json::from_str::<Value>(payload)?;
    if parsed.is_object() {
        Ok(parsed)
    } else {
        Err(serde_json::Error::io(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "WebSocket payload must be a JSON object",
        )))
    }
}
