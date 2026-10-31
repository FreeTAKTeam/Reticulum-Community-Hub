use super::{
    ApiError, AppState, ReticulumdAnnounceRecord, Value, ensure_kill_switch_persistence_unlocked,
    import_reticulumd_announce_batch, plane,
};
use std::sync::Mutex;

pub(super) fn poll(state: &AppState, cursor: &Mutex<Option<String>>) -> Result<bool, ApiError> {
    let _quiescence = state
        .broker_work_gate
        .read()
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    ensure_kill_switch_persistence_unlocked(state)?;
    let mut cursor = cursor
        .lock()
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    let result = plane(state)?
        .broker_announce_page(cursor.clone())
        .map_err(|error| ApiError::ServiceUnavailable(error.to_string()))?;
    apply_page(state, &result, &mut cursor)
}

fn apply_page(
    state: &AppState,
    result: &Value,
    cursor: &mut Option<String>,
) -> Result<bool, ApiError> {
    // Old daemons silently ignore additional request fields. Fail visibly instead
    // of accepting another lossy latest-32 snapshot as a completed sweep.
    if result.get("projection").and_then(Value::as_str) != Some("latest_per_peer_v1") {
        return Err(ApiError::ServiceUnavailable(
            "daemon lacks latest-per-peer announce paging".into(),
        ));
    }
    let records: Vec<ReticulumdAnnounceRecord> = serde_json::from_value(
        result
            .get("announces")
            .cloned()
            .ok_or_else(|| ApiError::Internal("SDK projection lacks announces".into()))?,
    )
    .map_err(|error| ApiError::Internal(error.to_string()))?;
    if records.len() > 32 {
        return Err(ApiError::ServiceUnavailable(
            "SDK announce projection exceeds count bound".into(),
        ));
    }
    let next = match result.get("next_peer") {
        Some(Value::Null) if records.len() < 32 => None,
        Some(Value::String(peer))
            if records.len() == 32 && records.last().is_some_and(|record| &record.peer == peer) =>
        {
            Some(peer.clone())
        }
        _ => {
            return Err(ApiError::ServiceUnavailable(
                "invalid announce projection cursor".into(),
            ));
        }
    };
    let mut previous = cursor.as_deref().unwrap_or("");
    for record in &records {
        if record.peer.as_str() <= previous {
            return Err(ApiError::ServiceUnavailable(
                "announce projection did not advance".into(),
            ));
        }
        previous = &record.peer;
    }
    import_reticulumd_announce_batch(state, &records, false)?;
    // Advance only after import succeeds. A crash/restart safely replays a sweep.
    *cursor = next;
    Ok(cursor.is_some())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn failed_or_legacy_projection_does_not_advance_cursor() {
        let state = AppState::default();
        let mut cursor = Some("peer".into());
        for result in [
            json!({"announces":[]}),
            json!({"projection":"latest_per_peer_v1","announces":[],"next_peer":"peer"}),
            json!({"projection":"latest_per_peer_v1","announces":"bad","next_peer":null}),
        ] {
            assert!(apply_page(&state, &result, &mut cursor).is_err());
            assert_eq!(cursor.as_deref(), Some("peer"));
        }
    }
}
