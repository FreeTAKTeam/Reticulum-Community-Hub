//! Optional event position on a log entry, e.g. from telemetry sent in the same LXMF message.

use serde_json::Value;

use crate::{LogEntryRecord, RchCoreError};

/// Reads `latitude`/`longitude` from command args. Without either, an update keeps the
/// current position; both must be numbers within range when given.
pub(crate) fn from_args(
    args: &Value,
    current: Option<&LogEntryRecord>,
) -> Result<(Option<f64>, Option<f64>), RchCoreError> {
    match (args.get("latitude"), args.get("longitude")) {
        (None, None) => Ok(current.map_or((None, None), |entry| (entry.latitude, entry.longitude))),
        (Some(lat), Some(lon)) => match (lat.as_f64(), lon.as_f64()) {
            (Some(lat), Some(lon))
                if (-90.0..=90.0).contains(&lat) && (-180.0..=180.0).contains(&lon) =>
            {
                Ok((Some(lat), Some(lon)))
            }
            _ => Err(RchCoreError::InvalidPayload(
                "latitude/longitude must be numbers within range".to_string(),
            )),
        },
        _ => Err(RchCoreError::InvalidPayload(
            "latitude and longitude must be sent together".to_string(),
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn position_requires_both_values_in_range() {
        assert_eq!(
            from_args(&json!({"latitude": 44.0, "longitude": -63.0}), None).unwrap(),
            (Some(44.0), Some(-63.0))
        );
        assert_eq!(from_args(&json!({}), None).unwrap(), (None, None));
        assert!(from_args(&json!({"latitude": 44.0}), None).is_err());
        assert!(from_args(&json!({"latitude": 95.0, "longitude": 0.0}), None).is_err());
    }
}
