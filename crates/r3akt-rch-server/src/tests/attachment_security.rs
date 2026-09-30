use super::*;
use std::path::PathBuf;

fn fixture() -> (crate::AppState, PathBuf) {
    let directory =
        std::env::temp_dir().join(format!("rch-attachment-security-{}", Uuid::new_v4()));
    std::fs::create_dir_all(&directory).expect("directory");
    let state = crate::AppState::from_sqlite_path(directory.join("state.db"))
        .expect("state")
        .with_api_key("secret");
    (state, directory)
}

fn multipart(content: &[u8], media_type: &str, extra: &str) -> Vec<u8> {
    let mut body = format!("--rch-test\r\nContent-Disposition: form-data; name=\"category\"\r\n\r\nfile\r\n{extra}--rch-test\r\nContent-Disposition: form-data; name=\"file\"; filename=\"upload.html\"\r\nContent-Type: {media_type}\r\n\r\n").into_bytes();
    body.extend_from_slice(content);
    body.extend_from_slice(b"\r\n--rch-test--\r\n");
    body
}

async fn upload(state: &crate::AppState, body: Body) -> axum::response::Response {
    crate::create_app_with_state(state.clone())
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/Chat/Attachment")
                .header("X-API-Key", "secret")
                .header("content-type", "multipart/form-data; boundary=rch-test")
                .body(body)
                .expect("request"),
        )
        .await
        .expect("response")
}

#[tokio::test]
async fn documented_eight_mebibyte_file_limit_is_usable_and_enforced() {
    let (state, directory) = fixture();
    for (length, expected) in [
        (3 * 1024 * 1024, StatusCode::OK),
        (8 * 1024 * 1024, StatusCode::OK),
        (8 * 1024 * 1024 + 1, StatusCode::PAYLOAD_TOO_LARGE),
    ] {
        let response = upload(
            &state,
            Body::from(multipart(
                &vec![b'x'; length],
                "application/octet-stream",
                "",
            )),
        )
        .await;
        assert_eq!(response.status(), expected, "length {length}");
    }
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[tokio::test]
async fn metadata_field_is_bounded_before_it_is_fully_read() {
    let (state, directory) = fixture();
    let extra = format!(
        "--rch-test\r\nContent-Disposition: form-data; name=\"TopicID\"\r\n\r\n{}\r\n",
        "x".repeat(65 * 1024)
    );
    let response = upload(&state, Body::from(multipart(b"file", "text/plain", &extra))).await;
    assert_eq!(response.status(), StatusCode::PAYLOAD_TOO_LARGE);
    assert_eq!(
        crate::load_attachment_records(&state, "file")
            .expect("records")
            .len(),
        0
    );
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[tokio::test]
async fn active_and_spoofed_content_is_downloaded_without_sniffing() {
    let (state, directory) = fixture();
    for media_type in ["text/html", "image/svg+xml", "image/png"] {
        let response = upload(
            &state,
            Body::from(multipart(
                b"<script>alert('active')</script>",
                media_type,
                "",
            )),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let payload: Value = serde_json::from_slice(
            &response
                .into_body()
                .collect()
                .await
                .expect("body")
                .to_bytes(),
        )
        .expect("JSON");
        let response = crate::create_app_with_state(state.clone())
            .oneshot(
                Request::builder()
                    .uri(format!(
                        "/File/{}/raw",
                        payload["FileID"].as_u64().expect("ID")
                    ))
                    .header("X-API-Key", "secret")
                    .body(Body::empty())
                    .expect("request"),
            )
            .await
            .expect("response");
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response.headers().get("content-type").expect("type"),
            "application/octet-stream"
        );
        assert_eq!(
            response
                .headers()
                .get("x-content-type-options")
                .expect("sniff policy"),
            "nosniff"
        );
        assert!(
            response
                .headers()
                .get("content-disposition")
                .expect("disposition")
                .to_str()
                .expect("header")
                .starts_with("attachment;")
        );
    }
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[tokio::test]
async fn chunked_metadata_rejection_stops_consuming_the_body_early() {
    use std::sync::{
        Arc,
        atomic::{AtomicUsize, Ordering},
    };
    let (state, directory) = fixture();
    let extra = format!(
        "--rch-test\r\nContent-Disposition: form-data; name=\"TopicID\"\r\n\r\n{}\r\n",
        "x".repeat(4 * 1024 * 1024)
    );
    let data = multipart(b"file", "text/plain", &extra);
    let chunks: Vec<_> = data
        .chunks(16 * 1024)
        .map(axum::body::Bytes::copy_from_slice)
        .collect();
    let consumed = Arc::new(AtomicUsize::new(0));
    let observed = consumed.clone();
    let stream = futures_util::StreamExt::map(futures_util::stream::iter(chunks), move |chunk| {
        observed.fetch_add(chunk.len(), Ordering::SeqCst);
        Ok::<_, std::io::Error>(chunk)
    });
    let response = upload(&state, Body::from_stream(stream)).await;
    assert_eq!(response.status(), StatusCode::PAYLOAD_TOO_LARGE);
    assert!(
        consumed.load(Ordering::SeqCst) <= 128 * 1024,
        "consumed {} bytes",
        consumed.load(Ordering::SeqCst)
    );
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[tokio::test]
async fn raster_type_is_determined_from_content_and_raw_bytes_survive_restart() {
    let (state, directory) = fixture();
    let png = b"\x89PNG\r\n\x1a\nfixture raster bytes";
    let response = upload(&state, Body::from(multipart(png, "text/html", ""))).await;
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value = serde_json::from_slice(
        &response
            .into_body()
            .collect()
            .await
            .expect("body")
            .to_bytes(),
    )
    .expect("JSON");
    let restarted = crate::AppState::from_sqlite_path(directory.join("state.db"))
        .expect("restart")
        .with_api_key("secret");
    let response = crate::create_app_with_state(restarted)
        .oneshot(
            Request::builder()
                .uri(format!(
                    "/File/{}/raw",
                    payload["FileID"].as_u64().expect("ID")
                ))
                .header("X-API-Key", "secret")
                .body(Body::empty())
                .expect("request"),
        )
        .await
        .expect("response");
    assert_eq!(
        response.headers().get("content-type").expect("type"),
        "image/png"
    );
    assert!(
        response
            .headers()
            .get("content-disposition")
            .expect("disposition")
            .to_str()
            .expect("header")
            .starts_with("inline;")
    );
    assert_eq!(
        &response
            .into_body()
            .collect()
            .await
            .expect("body")
            .to_bytes()[..],
        png
    );
    std::fs::remove_dir_all(directory).expect("cleanup");
}

#[tokio::test]
async fn failed_attachment_database_insert_removes_the_uncommitted_file() {
    let (state, directory) = fixture();
    let connection = rusqlite::Connection::open(directory.join("state.db")).expect("DB");
    connection.execute_batch("CREATE TRIGGER reject_upload BEFORE INSERT ON rch_file_attachments BEGIN SELECT RAISE(ABORT, 'injected upload failure'); END;").expect("fault");
    let response = upload(&state, Body::from(multipart(b"file", "text/plain", ""))).await;
    assert_eq!(response.status(), StatusCode::INTERNAL_SERVER_ERROR);
    assert!(
        crate::load_attachment_records(&state, "file")
            .expect("records")
            .is_empty()
    );
    let storage = state.attachment_storage_path("file").expect("storage");
    assert_eq!(std::fs::read_dir(storage).expect("files").count(), 0);
    std::fs::remove_dir_all(directory).expect("cleanup");
}
