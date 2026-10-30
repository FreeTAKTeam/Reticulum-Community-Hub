//! Explicit marker delivery through the existing durable outbound queue.
use axum::{
    Json,
    extract::{Path, State},
    http::StatusCode,
};
use base64::{Engine as _, engine::general_purpose::STANDARD};
use serde::Deserialize;
use serde_json::{Value, json};

use super::{
    ApiError, AppState, outbound_identity_allowed, record_outbound_message_deferred_async,
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct ShareRequest {
    destination: String,
}

pub(super) async fn share(
    Path(marker_id): Path<String>,
    State(state): State<AppState>,
    Json(request): Json<ShareRequest>,
) -> Result<(StatusCode, Json<Value>), ApiError> {
    let destination = r3akt_map_core::marker::object_destination_hash(&request.destination)
        .map_err(|_| {
            ApiError::Unprocessable(
                "destination must be a 32-character LXMF destination hash".into(),
            )
        })?;
    if !outbound_identity_allowed(&state, &destination, &destination) {
        return Err(ApiError::Forbidden(
            "destination is not permitted by outbound policy".into(),
        ));
    }
    let marker = state
        .markers
        .read()
        .map_err(|error| ApiError::Internal(error.to_string()))?
        .get(&marker_id)
        .cloned()
        .ok_or_else(|| ApiError::NotFound("Marker not found".into()))?;
    let source = state
        .reticulumd_source
        .as_deref()
        .map_or("r3akt-rch-server", String::as_str);
    let packed =
        r3akt_map_core::marker_wire::encode_fields("mission.marker.updated", &marker, source, None)
            .map_err(ApiError::Internal)?;
    let message = record_outbound_message_deferred_async(
        state,
        format!("Map marker: {}", marker.name),
        None,
        Some(destination),
        Vec::new(),
        false,
        json!({
            "fanout_kind": "marker_share",
            "marker_id": marker.object_destination_hash,
            "lxmf_fields": {"_lxmf_fields_msgpack_b64": STANDARD.encode(packed)},
        }),
    )
    .await?;
    Ok((
        StatusCode::ACCEPTED,
        Json(json!({
            "message_id": message.message_id,
            "marker_id": marker.object_destination_hash,
            "destination": message.destination,
            "delivery_state": message.delivery_state,
        })),
    ))
}
