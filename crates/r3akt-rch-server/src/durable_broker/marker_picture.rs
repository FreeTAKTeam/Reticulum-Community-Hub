//! Picture markers (r3akt-uas #19) within inbox custody: the thumbnail of a
//! `mission.marker.create`, the reduced-image upload (stored, never relayed)
//! and retrieval answered to the requester only.
use super::envelope::outgoing;
use super::{
    ApiError, FileAttachmentRecord, InboxEvent, OutboundMessageRecord, ProtocolEnvelope,
    RchCommandTransaction, Value, json, rem_team_routing, storage,
};
use base64::Engine as _;
use base64::engine::general_purpose::STANDARD as BASE64_STANDARD;
use r3akt_map_core::marker_picture as picture;
use r3akt_profile_rch::{CommandResultEnvelope, CommandResultStatus, MissionCommandEnvelope};
use serde::{Serialize, Serializer};
use std::collections::BTreeMap;

/// Field 6 as `[format, bytes]`.
pub(super) type Image = (String, Vec<u8>);

/// Packs `fields` with field 6 as `MessagePack` binary. As JSON, image bytes
/// become one array element per byte, and any image over 64 KiB exceeds the
/// daemon's 65,536-node `ZeroMQ` decode budget, which stalls the dispatch lane.
pub(super) fn with_image(fields: &Value, (format, bytes): &Image) -> Result<Value, ApiError> {
    struct Bytes<'a>(&'a [u8]);
    impl Serialize for Bytes<'_> {
        fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
            serializer.serialize_bytes(self.0)
        }
    }
    #[derive(Serialize)]
    #[serde(untagged)]
    enum Field<'a> {
        Json(&'a Value),
        Image(&'a str, Bytes<'a>),
    }
    let mut map = BTreeMap::new();
    for (key, value) in fields.as_object().into_iter().flatten() {
        let key: i64 = key
            .parse()
            .map_err(|_| ApiError::Internal(format!("LXMF field key {key:?} is not numeric")))?;
        map.insert(key, Field::Json(value));
    }
    map.insert(6, Field::Image(format, Bytes(bytes)));
    let packed = rmp_serde::to_vec(&map).map_err(|error| {
        ApiError::Internal(format!("failed to pack picture LXMF fields: {error}"))
    })?;
    Ok(json!({"_lxmf_fields_msgpack_b64": BASE64_STANDARD.encode(packed)}))
}

/// The transport's `_lxmf_image`: field 6 as `[format, "base64:..."]`.
fn image_arg(args: &Value) -> Option<Image> {
    picture::image_field(args.get("_lxmf_image")?)
}

fn text(args: &Value, key: &str) -> Option<String> {
    args.get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
}

fn stage_image(
    unit: &RchCommandTransaction<'_>,
    envelope: &ProtocolEnvelope,
    name: String,
    media_type: &str,
    bytes: &[u8],
) -> Result<u64, ApiError> {
    let now = envelope.timestamp.timestamp_millis();
    let record = unit
        .stage_attachment(
            FileAttachmentRecord {
                file_id: 0,
                name,
                path: String::new(),
                category: "image".into(),
                size: bytes.len() as u64,
                media_type: Some(media_type.into()),
                topic_id: None,
                created_ts_ms: now,
                updated_ts_ms: now,
            },
            bytes,
        )
        .map_err(storage)?;
    Ok(record.file_id)
}

/// After a fresh picture-marker create: stores the thumbnail under the
/// picture ID and returns field 6 for the team relay. The core has already
/// rejected a thumbnail that does not match `picture.thumbnail.sha256`.
pub(super) fn stage_thumbnail(
    unit: &RchCommandTransaction<'_>,
    envelope: &ProtocolEnvelope,
    mission: &MissionCommandEnvelope,
    marker_id: &str,
) -> Result<Option<Image>, ApiError> {
    let args = &mission.args;
    let Some(meta) = args.get("picture").filter(|value| !value.is_null()) else {
        return Ok(None);
    };
    // The core already accepted these; parse again for the typed values.
    let meta = picture::MarkerPicture::parse(meta).map_err(ApiError::BadRequest)?;
    let message_id = text(args, "_lxmf_message_id")
        .map(|id| picture::message_id(&id))
        .transpose()
        .map_err(ApiError::BadRequest)?;
    let image = image_arg(args);
    if let Some(message_id) = &message_id {
        let file_id = image
            .as_ref()
            .map(|(format, bytes)| {
                stage_image(
                    unit,
                    envelope,
                    format!("picture-{message_id}-thumbnail.{format}"),
                    &meta.thumbnail.media_type,
                    bytes,
                )
            })
            .transpose()?;
        unit.stage_marker_picture(message_id, marker_id, file_id)
            .map_err(storage)?;
    }
    Ok(image)
}

fn result(
    mission: &MissionCommandEnvelope,
    status: CommandResultStatus,
    reason_code: Option<&str>,
    reason: Option<String>,
    result: Value,
) -> r3akt_rch_core::MissionSyncResponse {
    r3akt_rch_core::MissionSyncResponse::results(CommandResultEnvelope {
        command_id: mission.command_id.clone(),
        status,
        detail: None,
        reason_code: reason_code.map(str::to_string),
        reason,
        required_capabilities: vec![],
        accepted_at: None,
        by_identity: None,
        correlation_id: mission.correlation_id.clone(),
        result,
    })
}

fn rejected(mission: &MissionCommandEnvelope, code: &str, reason: &str) -> Answer {
    let status = if code == "unauthorized" {
        "unauthorized"
    } else {
        "rejected"
    };
    (
        result(
            mission,
            CommandResultStatus::Rejected,
            Some(code),
            Some(reason.into()),
            json!({"status": status}),
        ),
        None,
    )
}

fn completed(mission: &MissionCommandEnvelope, value: Value, image: Option<Image>) -> Answer {
    (
        result(mission, CommandResultStatus::Completed, None, None, value),
        image,
    )
}

/// Answers `mission.marker.picture.upload` and `.get` to the sender only.
pub(super) fn handle(
    unit: &mut RchCommandTransaction<'_>,
    event: &InboxEvent,
    envelope: &ProtocolEnvelope,
    mission: &MissionCommandEnvelope,
    reply_allowed: bool,
    published: &mut Vec<OutboundMessageRecord>,
) -> Result<(), ApiError> {
    let (response, image) = match mission.command_type.as_str() {
        picture::UPLOAD_COMMAND => upload(unit, envelope, mission)?,
        picture::GET_COMMAND => get(unit, mission)?,
        _ => rejected(mission, "unknown_command", "Unsupported picture command"),
    };
    if !reply_allowed {
        return Ok(());
    }
    let mut fields = rem_team_routing::mission_response_fields(&response, None)?;
    if let Some(image) = &image {
        fields = with_image(&fields, image)?;
    }
    published.push(outgoing(
        unit,
        event,
        envelope.source.as_str(),
        &response.content,
        fields,
        envelope.timestamp.timestamp_millis(),
    )?);
    Ok(())
}

type Answer = (r3akt_rch_core::MissionSyncResponse, Option<Image>);

fn upload(
    unit: &RchCommandTransaction<'_>,
    envelope: &ProtocolEnvelope,
    mission: &MissionCommandEnvelope,
) -> Result<Answer, ApiError> {
    let args = &mission.args;
    let Some(message_id) = text(args, "message_id").and_then(|id| picture::message_id(&id).ok())
    else {
        return Ok(rejected(
            mission,
            "invalid_payload",
            "message_id is required",
        ));
    };
    let Some(marker_id) = text(args, "object_destination_hash")
        .and_then(|id| r3akt_map_core::marker::object_destination_hash(&id).ok())
    else {
        return Ok(rejected(
            mission,
            "invalid_payload",
            "object_destination_hash is required",
        ));
    };
    let mut meta = picture::PictureImage {
        media_type: text(args, "media_type").unwrap_or_default(),
        width: args
            .get("width")
            .and_then(Value::as_u64)
            .and_then(|v| u32::try_from(v).ok())
            .unwrap_or(0),
        height: args
            .get("height")
            .and_then(Value::as_u64)
            .and_then(|v| u32::try_from(v).ok())
            .unwrap_or(0),
        sha256: text(args, "sha256").unwrap_or_default(),
    };
    if let Err(reason) = meta.validate() {
        return Ok(rejected(mission, "invalid_payload", &reason));
    }
    let Some((format, bytes)) = image_arg(args) else {
        return Ok(rejected(
            mission,
            "invalid_payload",
            "FIELD_IMAGE (0x06) is required",
        ));
    };
    // Refused before the marker message is stored, so it can never attach to the wrong marker.
    let Some(row) = unit.marker_picture(&message_id).map_err(storage)? else {
        return Ok(rejected(
            mission,
            "unknown_picture",
            "no picture marker with this message_id",
        ));
    };
    if row.object_destination_hash != marker_id {
        return Ok(rejected(
            mission,
            "invalid_payload",
            "message_id belongs to another marker",
        ));
    }
    if unit.marker_writer(&marker_id).map_err(storage)?.as_deref() != Some(envelope.source.as_str())
    {
        return Ok(rejected(
            mission,
            "unauthorized",
            "only the marker's writer may upload its picture",
        ));
    }
    if picture::sha256_hex(&bytes) != meta.sha256 {
        return Ok(rejected(
            mission,
            "invalid_payload",
            "image does not match sha256",
        ));
    }
    let stored = json!({"status": "stored", "message_id": message_id, "sha256": meta.sha256, "size": bytes.len()});
    if let Some(existing) = &row.image_sha256 {
        return Ok(if *existing == meta.sha256 {
            completed(mission, stored, None)
        } else {
            rejected(mission, "conflict", "a different image is already stored")
        });
    }
    let file_id = stage_image(
        unit,
        envelope,
        format!("picture-{message_id}.{format}"),
        &meta.media_type,
        &bytes,
    )?;
    unit.stage_marker_picture_image(
        &message_id,
        file_id,
        &format,
        &meta.sha256,
        &meta.media_type,
        meta.width,
        meta.height,
    )
    .map_err(storage)?;
    Ok(completed(mission, stored, None))
}

fn get(
    unit: &mut RchCommandTransaction<'_>,
    mission: &MissionCommandEnvelope,
) -> Result<Answer, ApiError> {
    let Some(message_id) =
        text(&mission.args, "message_id").and_then(|id| picture::message_id(&id).ok())
    else {
        return Ok(rejected(
            mission,
            "invalid_payload",
            "message_id is required",
        ));
    };
    // Same rules as reading markers: gate the requester as a marker list.
    let read = MissionCommandEnvelope {
        command_type: "mission.marker.list".into(),
        ..mission.clone()
    };
    unit.prepare_command(&read).map_err(storage)?;
    if unit.core_mut().mission_command_rejection(&read).is_some() {
        return Ok(rejected(
            mission,
            "unauthorized",
            "not authorized to read markers",
        ));
    }
    let status = |status: &str| json!({"status": status, "message_id": message_id});
    let Some(row) = unit.marker_picture(&message_id).map_err(storage)? else {
        return Ok(completed(mission, status("unavailable"), None));
    };
    let (Some(file_id), Some(format), Some(sha256)) =
        (row.image_file_id, &row.image_format, &row.image_sha256)
    else {
        // A recorded hash without a file means the image was uploaded, then deleted (#365).
        let state = if row.image_sha256.is_some() {
            "unavailable"
        } else {
            "pending"
        };
        return Ok(completed(mission, status(state), None));
    };
    let Some(bytes) = unit.attachment_bytes(file_id).map_err(storage)? else {
        return Ok(completed(mission, status("unavailable"), None));
    };
    let value = json!({
        "status": "ok",
        "message_id": message_id,
        "object_destination_hash": row.object_destination_hash,
        "media_type": row.image_media_type,
        "width": row.image_width,
        "height": row.image_height,
        "sha256": sha256,
        "size": bytes.len(),
    });
    Ok(completed(mission, value, Some((format.clone(), bytes))))
}
