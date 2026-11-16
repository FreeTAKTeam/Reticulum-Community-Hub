//! Operator switch for R3AKT command authorization.
//!
//! When enabled, R3AKT mission and checklist commands arriving over LXMF,
//! including `join`, are accepted only from identities that hold the matching
//! capability. The setting lives in `rch_settings` and every command
//! transaction reads it, so a change applies to the next command without a
//! restart.

use super::{
    ApiError, AppState, Json, State, Value, json, open_r3akt_read_store,
    record_system_event_best_effort, with_required_core_store_write,
};

const FIELD: &str = "authorization_required";

fn payload(required: bool) -> Value {
    json!({ FIELD: required })
}

fn requested_value(body: &Value) -> Result<bool, ApiError> {
    body.get(FIELD)
        .and_then(Value::as_bool)
        .ok_or_else(|| ApiError::BadRequest(format!("'{FIELD}' must be provided as a boolean")))
}

pub(super) async fn get_setting(State(state): State<AppState>) -> Result<Json<Value>, ApiError> {
    let required = open_r3akt_read_store(&state)?
        .authorization_required()
        .map_err(|error| ApiError::Internal(format!("cannot read {FIELD}: {error}")))?;
    Ok(Json(payload(required)))
}

pub(super) async fn put_setting(
    State(state): State<AppState>,
    Json(body): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let required = requested_value(&body)?;
    with_required_core_store_write(&state, |store| store.set_authorization_required(required))?;
    record_system_event_best_effort(
        &state,
        "authorization_required_changed",
        if required {
            "R3AKT command authorization enabled"
        } else {
            "R3AKT command authorization disabled"
        },
        payload(required),
    );
    Ok(Json(payload(required)))
}

#[cfg(test)]
mod tests;
