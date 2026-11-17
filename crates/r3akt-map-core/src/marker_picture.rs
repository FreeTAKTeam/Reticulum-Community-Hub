//! Picture markers (r3akt-uas #19): a `picture` marker whose LXMF message
//! also carries a JPEG thumbnail in standard `FIELD_IMAGE` (0x06) as
//! `[format, bytes]`. The picture ID is the hex LXMF message ID of the
//! marker message; RCH records it as `picture.message_id`.

use serde::{Deserialize, Serialize};
use serde_json::Value as JsonValue;
use sha2::{Digest, Sha256};

use crate::{MarkerRecord, bytes, replica};

/// Catalog key used as marker type, symbol and category.
pub const MARKER_TYPE: &str = "picture";
/// Drone to RCH: the reduced image for a picture marker. Never relayed.
pub const UPLOAD_COMMAND: &str = "mission.marker.picture.upload";
/// REM to RCH: fetch the reduced image; answered to the requester only.
pub const GET_COMMAND: &str = "mission.marker.picture.get";
/// JSON-projection key of LXMF `FIELD_IMAGE`.
pub const FIELD_IMAGE_KEY: &str = "6";

/// Picture metadata carried on the marker record and its API value.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MarkerPicture {
    /// Picture ID (hex LXMF message ID); set by RCH, absent in the create args.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub message_id: Option<String>,
    pub thumbnail: PictureImage,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub captured_at: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub camera: Option<PictureCamera>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub crop: Option<PictureCrop>,
}

/// Description of an image tier (thumbnail or reduced image).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PictureImage {
    pub media_type: String,
    pub width: u32,
    pub height: u32,
    pub sha256: String,
}

/// Camera pose at capture. Unknown values are absent, never guessed.
#[derive(Debug, Clone, PartialEq, Default, Serialize, Deserialize)]
pub struct PictureCamera {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub lat: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub lon: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub altitude_m: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub altitude_reference: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub heading_deg: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub gimbal_pitch_deg: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub gimbal_yaw_deg: Option<f64>,
}

/// How the image was cropped around the aim point.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PictureCrop {
    Centre,
    AiBox,
}

impl MarkerPicture {
    /// Parses and validates a `picture` object received from the network.
    ///
    /// # Errors
    /// A description of the first invalid field.
    pub fn parse(value: &JsonValue) -> Result<Self, String> {
        let mut picture: Self =
            serde_json::from_value(value.clone()).map_err(|error| format!("picture: {error}"))?;
        picture.thumbnail.validate()?;
        if let Some(id) = &picture.message_id {
            picture.message_id = Some(message_id(id)?);
        }
        Ok(picture)
    }
}

impl PictureImage {
    /// Checks the media type, a non-zero size and a SHA-256 hex digest, and
    /// lowercases the digest.
    ///
    /// # Errors
    /// A description of the invalid field.
    pub fn validate(&mut self) -> Result<(), String> {
        if self.media_type.trim().is_empty() {
            return Err("picture media_type is required".into());
        }
        if self.width == 0 || self.height == 0 {
            return Err("picture width and height must be positive".into());
        }
        self.sha256 = self.sha256.trim().to_ascii_lowercase();
        if self.sha256.len() != 64 || !self.sha256.bytes().all(|b| b.is_ascii_hexdigit()) {
            return Err("picture sha256 must be 64 hexadecimal characters".into());
        }
        Ok(())
    }
}

/// Validates a hex LXMF message ID (the picture ID) and lowercases it.
///
/// # Errors
/// When it is not 64 hexadecimal characters (a SHA-256 message hash).
pub fn message_id(raw: &str) -> Result<String, String> {
    let id = raw.trim().to_ascii_lowercase();
    if id.len() == 64 && id.bytes().all(|b| b.is_ascii_hexdigit()) {
        Ok(id)
    } else {
        Err("message_id must be a hexadecimal LXMF message ID".into())
    }
}

/// Lowercase hex SHA-256 of `bytes`.
#[must_use]
pub fn sha256_hex(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

/// Reads the JSON projection of `FIELD_IMAGE` (`[format, bytes]`, bytes as
/// a byte array or `base64:` text). `None` unless both parts are present.
#[must_use]
pub fn image_field(value: &JsonValue) -> Option<(String, Vec<u8>)> {
    let [format, data] = value.as_array()?.as_slice() else {
        return None;
    };
    let format = format.as_str()?.trim().to_ascii_lowercase();
    let data = bytes::json_bytes(data);
    (!format.is_empty() && !data.is_empty()).then_some((format, data))
}

/// A picture marker as REM receives it from RCH's team relay.
#[derive(Debug, Clone, PartialEq)]
pub struct ReceivedPicture {
    pub marker: MarkerRecord,
    /// The thumbnail, only when it matches `picture.thumbnail.sha256`;
    /// `None` means draw the picture fallback marker.
    pub thumbnail: Option<Vec<u8>>,
}

/// Decodes a picture marker from the JSON projection of an RCH relay's LXMF
/// fields: a `mission.marker.*` upsert event in field 13 whose payload has
/// type `picture`, plus field 6. `Ok(None)` when the message holds no
/// picture marker. `local_id` is the receiver's own storage key.
///
/// # Errors
/// When the picture marker payload itself is invalid.
pub fn decode_relay(
    fields: &JsonValue,
    local_id: String,
) -> Result<Option<ReceivedPicture>, String> {
    let events = match fields.get("13") {
        Some(JsonValue::Array(events)) => events.iter().collect(),
        Some(event) => vec![event],
        None => Vec::new(),
    };
    let Some(payload) = events.into_iter().find_map(|event| {
        let kind = event.get("event_type").and_then(JsonValue::as_str)?;
        let payload = event.get("payload")?;
        (replica::UPSERT_EVENTS.contains(&kind)
            && payload.get("type").and_then(JsonValue::as_str) == Some(MARKER_TYPE))
        .then_some(payload)
    }) else {
        return Ok(None);
    };
    let marker = replica::from_api_value(payload, local_id).map_err(|error| error.to_string())?;
    let thumbnail = marker.picture.as_ref().and_then(|picture| {
        let (_, data) = image_field(fields.get(FIELD_IMAGE_KEY)?)?;
        (sha256_hex(&data) == picture.thumbnail.sha256).then_some(data)
    });
    Ok(Some(ReceivedPicture { marker, thumbnail }))
}
