use super::{
    ApiError, AppState, Body, CHAT_ATTACHMENT_MAX_BYTES, Digest, FileAttachmentRecord, FsPath,
    HashSet, Json, Next, Request, Response, Sha256, State, StatusCode, Uuid, Value,
    attachment_not_found, attachment_persistence, attachment_to_python_value,
    get_attachment_record, header, infer_inbound_image_media_type, normalize_optional_text,
    sanitize_attachment_filename, unix_now_ms,
};
use axum::extract::Multipart;
use axum::extract::multipart::{Field, MultipartError};
use futures_util::StreamExt;
use tokio::io::{AsyncReadExt, AsyncSeekExt};

pub(super) const MAX_REQUEST_BYTES: usize = CHAT_ATTACHMENT_MAX_BYTES + 64 * 1024;
const MAX_METADATA_BYTES: usize = 8 * 1024;
const MAX_FIELDS: usize = 8;

pub(super) async fn bound_upload_prefetch(request: Request, next: Next) -> Response {
    let (parts, body) = request.into_parts();
    let stream = futures_util::stream::try_unfold(
        (body.into_data_stream(), axum::body::Bytes::new()),
        |(mut source, mut pending)| async move {
            tokio::task::yield_now().await;
            if pending.is_empty() {
                match source.next().await {
                    Some(Ok(bytes)) => pending = bytes,
                    Some(Err(error)) => return Err(error),
                    None => return Ok(None),
                }
            }
            // Multipart greedily polls ready streams before parsing a field. Yield between
            // bounded slices so field limits can reject input before the next source read.
            let bytes = pending.split_to(pending.len().min(16 * 1024));
            Ok(Some((bytes, (source, pending))))
        },
    );
    next.run(Request::from_parts(parts, Body::from_stream(stream)))
        .await
}

fn multipart_error(error: MultipartError) -> ApiError {
    if error.status() == StatusCode::PAYLOAD_TOO_LARGE {
        ApiError::PayloadTooLarge("Attachment request exceeds size limit".to_string())
    } else {
        ApiError::BadRequest(format!("Invalid attachment multipart data: {error}"))
    }
}

async fn bounded_field(
    mut field: Field<'_>,
    limit: usize,
    total: &mut usize,
) -> Result<Vec<u8>, ApiError> {
    let mut bytes = Vec::new();
    while let Some(chunk) = field.chunk().await.map_err(multipart_error)? {
        *total = total.saturating_add(chunk.len());
        if chunk.len() > limit.saturating_sub(bytes.len()) || *total > MAX_REQUEST_BYTES {
            return Err(ApiError::PayloadTooLarge(
                "Attachment field exceeds size limit".to_string(),
            ));
        }
        bytes.extend_from_slice(&chunk);
    }
    Ok(bytes)
}

async fn bounded_text(field: Field<'_>, total: &mut usize) -> Result<String, ApiError> {
    String::from_utf8(bounded_field(field, MAX_METADATA_BYTES, total).await?).map_err(|error| {
        ApiError::BadRequest(format!("Attachment metadata must be UTF-8: {error}"))
    })
}

pub(super) async fn upload_chat_attachment(
    State(state): State<AppState>,
    mut multipart: Multipart,
) -> Result<Json<Value>, ApiError> {
    let mut category: Option<String> = None;
    let mut sha256: Option<String> = None;
    let mut topic_id: Option<String> = None;
    let mut filename: Option<String> = None;
    let mut media_type: Option<String> = None;
    let mut content: Option<Vec<u8>> = None;

    let mut fields = HashSet::new();
    let mut total = 0;
    while let Some(field) = multipart.next_field().await.map_err(multipart_error)? {
        let name = field.name().unwrap_or("").to_string();
        let canonical_name = if matches!(name.as_str(), "topic_id" | "TopicID" | "topicId") {
            "topic_id"
        } else {
            &name
        };
        if !fields.insert(canonical_name.to_string()) {
            return Err(ApiError::BadRequest(
                "Duplicate attachment field".to_string(),
            ));
        }
        if fields.len() > MAX_FIELDS {
            return Err(ApiError::PayloadTooLarge(
                "Too many attachment fields".to_string(),
            ));
        }
        match canonical_name {
            "category" => category = Some(bounded_text(field, &mut total).await?),
            "sha256" => sha256 = Some(bounded_text(field, &mut total).await?),
            "topic_id" => topic_id = Some(bounded_text(field, &mut total).await?),
            "file" => {
                filename = Some(
                    field
                        .file_name()
                        .filter(|value| !value.trim().is_empty())
                        .unwrap_or("upload.bin")
                        .to_string(),
                );
                if filename
                    .as_ref()
                    .is_some_and(|name| name.len() > 255 || name.chars().any(char::is_control))
                {
                    return Err(ApiError::BadRequest(
                        "Attachment filename must be 255 bytes or fewer without control characters"
                            .to_string(),
                    ));
                }
                media_type = field.content_type().map(ToString::to_string);
                content = Some(bounded_field(field, CHAT_ATTACHMENT_MAX_BYTES, &mut total).await?);
            }
            _ => {
                bounded_field(field, MAX_METADATA_BYTES, &mut total).await?;
            }
        }
    }

    let category = category
        .map(|value| value.trim().to_ascii_lowercase())
        .filter(|value| !value.is_empty())
        .ok_or_else(|| {
            ApiError::BadRequest("Attachment category must be file or image".to_string())
        })?;
    if !matches!(category.as_str(), "file" | "image") {
        return Err(ApiError::BadRequest(
            "Attachment category must be file or image".to_string(),
        ));
    }
    let content =
        content.ok_or_else(|| ApiError::BadRequest("field `file` is required".to_string()))?;
    if content.is_empty() {
        return Err(ApiError::BadRequest(
            "Attachment content is empty".to_string(),
        ));
    }
    if content.len() > CHAT_ATTACHMENT_MAX_BYTES {
        return Err(ApiError::PayloadTooLarge(
            "Attachment exceeds size limit".to_string(),
        ));
    }
    if category == "image" {
        let media_type_value = media_type.as_deref().unwrap_or_default();
        if !media_type_value.starts_with("image/") {
            return Err(ApiError::BadRequest(
                "Image attachments must use an image content type".to_string(),
            ));
        }
    }
    if let Some(expected_hash) = sha256
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        let digest = Sha256::digest(&content);
        let actual_hash = digest
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>();
        if actual_hash != expected_hash.to_ascii_lowercase() {
            return Err(ApiError::BadRequest("Attachment hash mismatch".to_string()));
        }
    }

    let safe_name = sanitize_attachment_filename(filename.as_deref().unwrap_or("upload.bin"));
    let suffix = FsPath::new(&safe_name)
        .extension()
        .and_then(|value| value.to_str())
        .map(|value| format!(".{value}"))
        .unwrap_or_default();
    let stored_name = format!("{}{}", Uuid::new_v4().simple(), suffix);
    let base_path = state.attachment_storage_path(&category)?;
    let target_path = base_path.join(stored_name);
    let now = unix_now_ms();
    let record = FileAttachmentRecord {
        file_id: 0,
        name: safe_name,
        path: target_path.display().to_string(),
        category,
        size: content.len() as u64,
        media_type,
        topic_id: normalize_optional_text(topic_id),
        created_ts_ms: now,
        updated_ts_ms: now,
    };
    // The blocking owner keeps file cleanup and persistence together even if the
    // HTTP request is dropped. Async filesystem writes otherwise detach on drop.
    let record = tokio::task::spawn_blocking(move || {
        attachment_persistence::persist(&state, record, &content)
    })
    .await
    .map_err(|error| {
        ApiError::Internal(format!("Attachment persistence task failed: {error}"))
    })??;

    Ok(Json(attachment_to_python_value(&record)))
}

pub(super) async fn retrieve_attachment_raw(
    state: &AppState,
    file_id: u64,
    category: &str,
) -> Result<Response, ApiError> {
    let attachment = get_attachment_record(state, file_id, category)?;
    if attachment.path.starts_with("rch-db:") {
        let bytes = super::with_required_core_store_write(state, |store| {
            store.broker_attachment_bytes(file_id)
        })?
        .ok_or_else(|| attachment_not_found(file_id))?;
        let media = infer_inbound_image_media_type(&bytes).unwrap_or("application/octet-stream");
        let name = sanitize_attachment_filename(&attachment.name).replace(['"', '\r', '\n'], "_");
        return Response::builder()
            .status(StatusCode::OK)
            .header(header::CONTENT_TYPE, media)
            .header(
                header::CONTENT_DISPOSITION,
                format!("attachment; filename=\"{name}\""),
            )
            .header(header::CONTENT_LENGTH, bytes.len())
            .header("X-Content-Type-Options", "nosniff")
            .body(Body::from(bytes))
            .map_err(|e| ApiError::Internal(e.to_string()));
    }
    let mut file = tokio::fs::File::open(&attachment.path)
        .await
        .map_err(|error| {
            if error.kind() == std::io::ErrorKind::NotFound {
                attachment_not_found(file_id)
            } else {
                ApiError::Internal(format!("Cannot open attachment {file_id}: {error}"))
            }
        })?;
    let length = file
        .metadata()
        .await
        .map_err(|error| {
            ApiError::Internal(format!("Cannot inspect attachment {file_id}: {error}"))
        })?
        .len();
    let mut prefix = [0u8; 64];
    let prefix_length = file.read(&mut prefix).await.map_err(|error| {
        ApiError::Internal(format!("Cannot read attachment {file_id}: {error}"))
    })?;
    file.seek(std::io::SeekFrom::Start(0))
        .await
        .map_err(|error| {
            ApiError::Internal(format!("Cannot seek attachment {file_id}: {error}"))
        })?;
    let raster_type = infer_inbound_image_media_type(&prefix[..prefix_length]);
    let disposition = if raster_type.is_some() {
        "inline"
    } else {
        "attachment"
    };
    let filename: String = sanitize_attachment_filename(&attachment.name)
        .chars()
        .take(255)
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || matches!(ch, '.' | '-' | '_' | ' ') {
                ch
            } else {
                '_'
            }
        })
        .collect();
    let stream = futures_util::stream::try_unfold(file.take(length), move |mut file| async move {
        let mut bytes = vec![0u8; 64 * 1024];
        match file.read(&mut bytes).await {
            Ok(0) => Ok(None),
            Ok(count) => {
                bytes.truncate(count);
                Ok(Some((bytes, file)))
            }
            Err(error) => {
                eprintln!("attachment {file_id} stream failed: {error}");
                Err(error)
            }
        }
    });
    Response::builder()
        .status(StatusCode::OK)
        .header(
            header::CONTENT_TYPE,
            raster_type.unwrap_or("application/octet-stream"),
        )
        .header(
            header::CONTENT_DISPOSITION,
            format!("{disposition}; filename=\"{filename}\""),
        )
        .header(header::CONTENT_LENGTH, length)
        .header("X-Content-Type-Options", "nosniff")
        .header("Content-Security-Policy", "default-src 'none'; sandbox")
        .body(Body::from_stream(stream))
        .map_err(|error| ApiError::Internal(error.to_string()))
}
