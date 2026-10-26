use super::{
    ApiError, AppState, MarkerRecord, iso8601_from_unix_ms, marker_not_found,
    normalize_optional_text, record_marker_activity_after_commit, unix_now_ms,
    with_required_core_store_write,
};
use axum::{
    Json,
    extract::{Path, State},
};
use serde::Deserialize;
use serde_json::{Value, json};

#[derive(Debug, Deserialize)]
pub struct MarkerPositionPayload {
    pub lat: f64,
    pub lon: f64,
    #[serde(rename = "type", alias = "marker_type", alias = "markerType")]
    pub marker_type: Option<String>,
    pub symbol: Option<String>,
    pub notes: Option<String>,
}

pub(super) async fn patch_marker_position(
    Path(object_destination_hash): Path<String>,
    State(state): State<AppState>,
    Json(payload): Json<MarkerPositionPayload>,
) -> Result<Json<Value>, ApiError> {
    let position = r3akt_map_core::Position::new(payload.lat, payload.lon)
        .map_err(|error| ApiError::Unprocessable(error.to_string()))?;
    let unprocessable =
        |error: r3akt_map_core::MarkerError| ApiError::Unprocessable(error.to_string());
    let marker_type = payload
        .marker_type
        .as_deref()
        .map(r3akt_map_core::marker::marker_type)
        .transpose()
        .map_err(unprocessable)?;
    let symbol = payload
        .symbol
        .as_deref()
        .map(r3akt_map_core::marker::marker_symbol)
        .transpose()
        .map_err(unprocessable)?;
    let updated_at = unix_now_ms();
    let update = |marker: &mut MarkerRecord| {
        marker.move_to(position, updated_at);
        if let Some(marker_type) = marker_type {
            marker.marker_type = marker_type;
        }
        if let Some(symbol) = symbol {
            marker.symbol = symbol;
        }
        if let Some(notes) = payload.notes {
            marker.notes = normalize_optional_text(Some(notes));
        }
    };
    let marker = {
        let mut markers = state
            .markers
            .write()
            .map_err(|error| ApiError::Internal(error.to_string()))?;
        let marker = if state.sqlite_path.is_some() {
            with_required_core_store_write(&state, |store| {
                store.update_marker(&object_destination_hash, update)
            })?
            .ok_or_else(|| marker_not_found(&object_destination_hash))?
        } else {
            let mut marker = markers
                .get(&object_destination_hash)
                .cloned()
                .ok_or_else(|| marker_not_found(&object_destination_hash))?;
            update(&mut marker);
            marker
        };
        markers.insert(object_destination_hash.clone(), marker.clone());
        marker
    };
    record_marker_activity_after_commit(&state, "marker.updated", &marker);
    Ok(Json(json!({
        "status": "ok",
        "updated_at": iso8601_from_unix_ms(updated_at)
    })))
}
