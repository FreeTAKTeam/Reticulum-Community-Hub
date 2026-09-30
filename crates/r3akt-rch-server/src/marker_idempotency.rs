use super::{
    ApiError, AppState, CoreMarkerRecord, HeaderMap, MarkerRecord, json, persist_marker_row,
    with_required_core_store_write,
};
use sha2::{Digest, Sha256};

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
    if value.is_empty() || value.len() > 128 || !value.bytes().all(|byte| byte.is_ascii_graphic()) {
        return Err(ApiError::BadRequest(
            "Idempotency-Key must contain 1 to 128 visible ASCII characters".to_string(),
        ));
    }
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
        let command_id = format!("rch/http/marker/{}", digest(key.as_bytes()));
        // Bind the key to the validated, normalized creation fields, excluding
        // newly minted identifiers/timestamps and all authentication material.
        let payload = json!({"marker_type": marker.marker_type, "symbol": marker.symbol,
            "name": marker.name, "category": marker.category, "lat": marker.lat,
            "lon": marker.lon, "notes": marker.notes});
        let fingerprint = digest(
            &serde_json::to_vec(&payload).map_err(|error| ApiError::Internal(error.to_string()))?,
        );
        let record = CoreMarkerRecord::from(marker);
        match with_required_core_store_write(state, |store| {
            store.create_marker_once(&record, &command_id, &fingerprint)
        })? {
            r3akt_rch_core::MarkerCreation::Created(record) => (MarkerRecord::from(record), true),
            r3akt_rch_core::MarkerCreation::Replayed(record) => (MarkerRecord::from(record), false),
            r3akt_rch_core::MarkerCreation::KeyConflict => {
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

fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
