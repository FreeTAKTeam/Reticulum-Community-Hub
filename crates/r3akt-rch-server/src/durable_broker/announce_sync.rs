use super::{
    ApiError, AppState, RchSqliteStore, ReticulumdAnnounceRecord, Value,
    import_reticulumd_announce_batch_in, plane,
};
use std::collections::HashMap;
use std::hash::{DefaultHasher, Hash, Hasher};
use std::sync::Mutex;

/// Sweep progress plus the daemon record last imported per peer (#242). The
/// daemon re-serves every peer each 30-second sweep; pages whose records are
/// unchanged are skipped without opening the RCH store. One u64 pair per peer.
#[derive(Default)]
pub(super) struct AnnounceSweep {
    pub(super) cursor: Option<String>,
    imported: HashMap<u64, u64>,
}

fn fingerprint(value: impl Hash) -> u64 {
    let mut hasher = DefaultHasher::new();
    value.hash(&mut hasher);
    hasher.finish()
}

/// Caller holds the broker work gate, checked the kill switch and owns `store`.
pub(super) fn poll(
    state: &AppState,
    sweep: &Mutex<AnnounceSweep>,
    store: &mut RchSqliteStore,
) -> Result<bool, ApiError> {
    let mut sweep = sweep
        .lock()
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    let result = plane(state)?
        .broker_announce_page(sweep.cursor.clone())
        .map_err(|error| ApiError::ServiceUnavailable(error.to_string()))?;
    apply_page(state, &result, &mut sweep, Some(store))
}

fn apply_page(
    state: &AppState,
    result: &Value,
    sweep: &mut AnnounceSweep,
    store: Option<&mut RchSqliteStore>,
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
    let mut previous = sweep.cursor.as_deref().unwrap_or("");
    for record in &records {
        if record.peer.as_str() <= previous {
            return Err(ApiError::ServiceUnavailable(
                "announce projection did not advance".into(),
            ));
        }
        previous = &record.peer;
    }
    let keyed: Vec<_> = records
        .iter()
        .map(|r| {
            (
                fingerprint(&r.peer),
                fingerprint((&r.id, r.timestamp, r.seen_count)),
            )
        })
        .collect();
    let changed: Vec<ReticulumdAnnounceRecord> = records
        .into_iter()
        .zip(&keyed)
        .filter(|(_, (peer, record))| sweep.imported.get(peer) != Some(record))
        .map(|(record, _)| record)
        .collect();
    if !changed.is_empty() {
        import_reticulumd_announce_batch_in(state, store, &changed, false)?;
    }
    // Advance only after import succeeds. A crash/restart safely replays a sweep.
    sweep.imported.extend(keyed);
    sweep.cursor = next;
    Ok(sweep.cursor.is_some())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn failed_or_legacy_projection_does_not_advance_cursor() {
        let state = AppState::default();
        let mut sweep = AnnounceSweep {
            cursor: Some("peer".into()),
            ..Default::default()
        };
        for result in [
            json!({"announces":[]}),
            json!({"projection":"latest_per_peer_v1","announces":[],"next_peer":"peer"}),
            json!({"projection":"latest_per_peer_v1","announces":"bad","next_peer":null}),
        ] {
            assert!(apply_page(&state, &result, &mut sweep, None).is_err());
            assert_eq!(sweep.cursor.as_deref(), Some("peer"));
        }
    }
}
