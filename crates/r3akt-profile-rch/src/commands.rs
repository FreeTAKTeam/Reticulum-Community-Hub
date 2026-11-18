use std::collections::BTreeMap;

use serde::{Serializer, ser::SerializeMap};

use crate::{FIELD_COMMANDS, FIELD_GROUP, FIELD_IMAGE, MissionCommandEnvelope, RchProfileError};

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
    encode_commands_for_team_with_image(commands, team_uid, None)
}

/// Like [`encode_commands_for_team`], plus standard LXMF `FIELD_IMAGE`
/// (0x06) as `[format, bytes]` when `image` is `Some((format, bytes))`,
/// e.g. `("jpg", thumbnail)` for a picture marker (r3akt-uas #19).
///
/// # Errors
/// Returns an error if the team UID or image format is blank, the image is
/// empty, or encoding fails.
pub fn encode_commands_for_team_with_image(
    commands: &[MissionCommandEnvelope],
    team_uid: Option<&str>,
    image: Option<(&str, &[u8])>,
) -> Result<Vec<u8>, RchProfileError> {
    if team_uid.is_none() && image.is_none() {
        return encode_commands(commands);
    }
    if team_uid.is_some_and(|team| team.trim().is_empty()) {
        return Err(RchProfileError::Encode("team UID must not be empty".into()));
    }
    if image.is_some_and(|(format, bytes)| format.trim().is_empty() || bytes.is_empty()) {
        return Err(RchProfileError::Encode(
            "image format and bytes must not be empty".into(),
        ));
    }

    let mut bytes = Vec::new();
    let mut serializer = rmp_serde::Serializer::new(&mut bytes).with_struct_map();
    let encode_error = |error: rmp_serde::encode::Error| RchProfileError::Encode(error.to_string());
    let mut fields = (&mut serializer)
        .serialize_map(Some(
            1 + usize::from(team_uid.is_some()) + usize::from(image.is_some()),
        ))
        .map_err(encode_error)?;
    fields
        .serialize_entry(&FIELD_COMMANDS, commands)
        .map_err(encode_error)?;
    if let Some(team_uid) = team_uid {
        fields
            .serialize_entry(&FIELD_GROUP, team_uid)
            .map_err(encode_error)?;
    }
    if let Some((format, data)) = image {
        fields
            .serialize_entry(&FIELD_IMAGE, &(format, Binary(data)))
            .map_err(encode_error)?;
    }
    fields.end().map_err(encode_error)?;
    Ok(bytes)
}

/// Serializes as a `MessagePack` `bin`, as LXMF expects for image bytes.
struct Binary<'a>(&'a [u8]);

impl serde::Serialize for Binary<'_> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.serialize_bytes(self.0)
    }
}
