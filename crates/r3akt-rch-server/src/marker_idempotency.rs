use super::{
    ApiError, AppState, HeaderMap, MarkerRecord, persist_marker_row, with_required_core_store_write,
};
use r3akt_map_core::idempotency;
use r3akt_rch_core::MarkerCreation;

/// Reads the single optional `Idempotency-Key` header.
pub(super) fn key(headers: &HeaderMap) -> Result<Option<String>, ApiError> {
    let mut values = headers.get_all("Idempotency-Key").iter();
    let Some(value) = values.next() else {
        return Ok(None);
    };
    if values.next().is_some() {
        return Err(ApiError::BadRequest(
            "Idempotency-Key must occur once".to_string(),
        ));
    }
    let value = value
        .to_str()
        .map_err(|_| ApiError::BadRequest("Idempotency-Key must be ASCII".to_string()))?;
    idempotency::validate_key(value).map_err(|error| ApiError::BadRequest(error.to_string()))?;
    Ok(Some(value.to_string()))
}

pub(super) fn persist(
    state: &AppState,
    marker: MarkerRecord,
    key: Option<&str>,
) -> Result<(MarkerRecord, bool), ApiError> {
    let mut markers = state
        .markers
        .write()
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    let (marker, created) = if let Some(key) = key {
        let command_id = idempotency::command_id(key);
        let fingerprint = idempotency::creation_fingerprint(&marker);
        match with_required_core_store_write(state, |store| {
            store.create_marker_once(&marker, &command_id, &fingerprint)
        })? {
            MarkerCreation::Created(record) => (record, true),
            MarkerCreation::Replayed(record) => (record, false),
            MarkerCreation::KeyConflict => {
                return Err(ApiError::Conflict(
                    "Idempotency-Key was already used with a different marker payload".to_string(),
                ));
            }
        }
    } else {
        persist_marker_row(state, &marker)?;
        (marker, true)
    };
    // A replay returns its original creation response without restoring old
    // marker fields or reviving a subsequently deleted marker in a projection.
    if created {
        markers.insert(marker.object_destination_hash.clone(), marker.clone());
    }
    Ok((marker, created))
}
