use std::collections::BTreeMap;

use serde::{Serializer, ser::SerializeMap};

use crate::{FIELD_COMMANDS, FIELD_GROUP, MissionCommandEnvelope, RchProfileError};

pub fn encode_commands(commands: &[MissionCommandEnvelope]) -> Result<Vec<u8>, RchProfileError> {
    let fields = BTreeMap::from([(FIELD_COMMANDS, commands)]);
    rmp_serde::to_vec_named(&fields).map_err(|error| RchProfileError::Encode(error.to_string()))
}

/// Encodes commands with an optional TEAM UID for RCH fanout.
/// RCH validates the UID and the sender's team membership on receipt.
///
/// # Errors
/// Returns an error if the supplied team UID is blank or encoding fails.
pub fn encode_commands_for_team(
    commands: &[MissionCommandEnvelope],
    team_uid: Option<&str>,
) -> Result<Vec<u8>, RchProfileError> {
    let Some(team_uid) = team_uid else {
        return encode_commands(commands);
    };
    if team_uid.trim().is_empty() {
        return Err(RchProfileError::Encode("team UID must not be empty".into()));
    }

    let mut bytes = Vec::new();
    let mut serializer = rmp_serde::Serializer::new(&mut bytes).with_struct_map();
    let encode_error = |error: rmp_serde::encode::Error| RchProfileError::Encode(error.to_string());
    let mut fields = (&mut serializer)
        .serialize_map(Some(2))
        .map_err(encode_error)?;
    fields
        .serialize_entry(&FIELD_COMMANDS, commands)
        .map_err(encode_error)?;
    fields
        .serialize_entry(&FIELD_GROUP, team_uid)
        .map_err(encode_error)?;
    fields.end().map_err(encode_error)?;
    Ok(bytes)
}
