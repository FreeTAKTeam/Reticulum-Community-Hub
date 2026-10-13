//! Stages inbound topic attachments, restoring the media typing the hub has
//! always applied: an explicit type wins, image bytes are sniffed, and other
//! files are typed from their extension. Stored names gain a matching
//! extension so `/Image` and `/File` downloads open correctly.

use super::{
    ApiError, ChatAttachmentRecord, FileAttachmentRecord, ProtocolEnvelope, RchCommandTransaction,
    chat_attachment_from_file_record, infer_inbound_image_media_type,
    normalized_inbound_attachment_category, sanitize_attachment_filename, storage,
};
use std::path::Path;

pub(super) fn stage(
    unit: &RchCommandTransaction<'_>,
    envelope: &ProtocolEnvelope,
    attachments: &[r3akt_protocol::TopicAttachment],
) -> Result<Vec<ChatAttachmentRecord>, ApiError> {
    let mut staged = Vec::new();
    for attachment in attachments {
        let category = normalized_inbound_attachment_category(&attachment.category);
        let name = sanitize_attachment_filename(&attachment.name);
        let media_type = attachment
            .media_type
            .as_deref()
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_string)
            .or_else(|| {
                (category == "image")
                    .then(|| infer_inbound_image_media_type(&attachment.data))
                    .flatten()
                    .map(str::to_string)
            })
            .unwrap_or_else(|| guess_media_type(&name, category).to_string());
        let name = with_media_extension(name, &media_type);
        let record = unit
            .stage_attachment(
                FileAttachmentRecord {
                    file_id: 0,
                    name,
                    path: String::new(),
                    category: category.into(),
                    size: attachment.data.len() as u64,
                    media_type: Some(media_type),
                    topic_id: Some(envelope.topic.to_string()),
                    created_ts_ms: envelope.timestamp.timestamp_millis(),
                    updated_ts_ms: envelope.timestamp.timestamp_millis(),
                },
                &attachment.data,
            )
            .map_err(storage)?;
        staged.push(chat_attachment_from_file_record(&record));
    }
    Ok(staged)
}

fn guess_media_type(name: &str, category: &str) -> &'static str {
    match Path::new(name)
        .extension()
        .and_then(|value| value.to_str())
        .map(str::to_ascii_lowercase)
        .as_deref()
    {
        Some("txt" | "log" | "csv") => "text/plain",
        Some("json") => "application/json",
        Some("png") => "image/png",
        Some("jpg" | "jpeg") => "image/jpeg",
        Some("gif") => "image/gif",
        Some("bmp") => "image/bmp",
        Some("webp") => "image/webp",
        _ if category == "image" => "image/octet-stream",
        _ => "application/octet-stream",
    }
}

fn with_media_extension(name: String, media_type: &str) -> String {
    if Path::new(&name).extension().is_some() {
        return name;
    }
    let extension = match media_type.trim().to_ascii_lowercase().as_str() {
        "image/png" => ".png",
        "image/jpeg" => ".jpg",
        "image/gif" => ".gif",
        "image/bmp" => ".bmp",
        "image/webp" => ".webp",
        "text/plain" => ".txt",
        "application/json" => ".json",
        _ => return name,
    };
    format!("{name}{extension}")
}
