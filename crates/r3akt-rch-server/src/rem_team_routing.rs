use r3akt_profile_rch::FIELD_GROUP;
use serde_json::{Value, json};

use super::ApiError;

pub(super) fn mission_response_fields(
    response: &r3akt_rch_core::MissionSyncResponse,
    team_uid: Option<&str>,
) -> Result<Value, ApiError> {
    let mut fields = serde_json::to_value(&response.fields).map_err(|error| {
        ApiError::Internal(format!(
            "failed to serialize mission response LXMF fields: {error}"
        ))
    })?;
    if let (Some(team_uid), Some(fields)) = (team_uid, fields.as_object_mut()) {
        fields.insert(FIELD_GROUP.to_string(), json!(team_uid));
    }
    Ok(fields)
}
