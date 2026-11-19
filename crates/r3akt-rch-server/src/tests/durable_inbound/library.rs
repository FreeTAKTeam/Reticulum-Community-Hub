//! Mission Library over LXMF (RCH #354/#355): mission-scoped listing, no
//! disclosure to unauthorized callers, publish right for linking.

use super::pictures::{result_of, send};
use super::*;

const READER_ID: &str = "44444444444444444444444444444444";
const READER: &str = "dddddddddddddddddddddddddddddddd";
const EDITOR_ID: &str = "55555555555555555555555555555555";
const EDITOR: &str = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee";
const OUTSIDER_ID: &str = "66666666666666666666666666666666";
const OUTSIDER: &str = "ffffffffffffffffffffffffffffffff";

fn attachment(
    file_id: u64,
    name: &str,
    category: &str,
    media: &str,
    created: i64,
) -> FileAttachmentRecord {
    FileAttachmentRecord {
        file_id,
        name: name.into(),
        path: format!("/tmp/{name}"),
        category: category.into(),
        size: 100,
        media_type: Some(media.into()),
        topic_id: None,
        created_ts_ms: created,
        updated_ts_ms: created,
    }
}

fn state() -> crate::AppState {
    let setup = |command_type: &str, args: Value| r3akt_profile_rch::MissionCommandEnvelope {
        command_id: format!("setup-{command_type}-{args}"),
        source: r3akt_profile_rch::RchSource::new("setup-source"),
        timestamp: "2026-11-19T12:00:00Z".to_string(),
        command_type: command_type.to_string(),
        args,
        correlation_id: None,
        topics: Vec::new(),
    };
    let mut core = RchCore::new();
    core.set_authorization_required(true);
    for uid in ["alpha", "bravo"] {
        core.handle_command(&setup(
            "mission.registry.mission.upsert",
            json!({"uid": uid, "mission_name": uid}),
        ));
    }
    // RCH authorizes the LXMF source hash a command arrives from.
    for (identity, role) in [
        (READER, "MISSION_READONLY_SUBSCRIBER"),
        (EDITOR, "MISSION_SUBSCRIBER"),
    ] {
        core.handle_command(&setup(
            "mission.registry.rights.mission_access.assign",
            json!({"mission_uid": "alpha", "subject_type": "identity", "subject_id": identity, "role": role}),
        ));
    }
    for (identity, destination) in [
        (READER_ID, READER),
        (EDITOR_ID, EDITOR),
        (OUTSIDER_ID, OUTSIDER),
    ] {
        core.record_identity_announce(
            destination,
            Some(identity.to_string()),
            Some(identity.to_string()),
            Some("destination".to_string()),
            vec!["r3akt".to_string(), "EmergencyMessages".to_string()],
        )
        .expect("announce");
    }
    let db = std::env::temp_dir().join(format!("r3akt-library-{}.db", Uuid::new_v4()));
    let mut store = RchSqliteStore::open(&db).expect("store");
    store.save_snapshot(&core.snapshot()).expect("snapshot");
    for record in [
        attachment(1, "plan.pdf", "file", "application/pdf", 10),
        attachment(2, "site.jpg", "image", "image/jpeg", 20),
        attachment(3, "secret.pdf", "file", "application/pdf", 30),
        attachment(4, "unlinked.txt", "file", "text/plain", 40),
    ] {
        store.upsert_file_attachment(&record).expect("attachment");
    }
    drop(store);
    let connection = rusqlite::Connection::open(&db).expect("db");
    connection
        .execute_batch(
            "INSERT INTO rch_library_mission_files VALUES('alpha',1,1),('alpha',2,1),('bravo',3,1);",
        )
        .expect("links");
    let mut state = crate::AppState::from_sqlite_path(&db)
        .expect("state")
        .with_test_reticulumd_source("local-destination");
    state.enable_durable_consumer().expect("durable consumer");
    state
}

fn command(state: &crate::AppState, id: &str, who: (&str, &str), kind: &str, args: Value) -> Value {
    let requests = send(state, id, who.0, who.1, kind, args, json!({}));
    assert!(
        requests.iter().all(|r| r["destination"] == who.0),
        "reply to sender only: {requests:#?}"
    );
    result_of(&requests, who.0)["10"].clone()
}

fn names(result: &Value) -> Vec<String> {
    result["result"]["items"]
        .as_array()
        .expect("items")
        .iter()
        .map(|item| item["name"].as_str().expect("name").to_string())
        .collect()
}

#[test]
fn library_list_is_mission_scoped_and_metadata_only() {
    let state = state();
    let reader = (READER, READER_ID);
    let listed = command(&state, "l1", reader, "mission.library.list", json!({}));
    assert_eq!(listed["result"]["status"], "ok", "{listed:#}");
    assert_eq!(
        names(&listed),
        ["site.jpg", "plan.pdf"],
        "bravo and unlinked items are hidden"
    );
    assert_eq!(listed["result"]["total"], 2);
    let item = &listed["result"]["items"][0];
    assert_eq!(
        (item["item_id"].as_str(), item["kind"].as_str()),
        (Some("rch:2"), Some("image"))
    );
    assert!(item.get("path").is_none(), "no server path or bytes leak");

    let images = command(
        &state,
        "l2",
        reader,
        "mission.library.list",
        json!({"kind": "file", "search": "PLAN"}),
    );
    assert_eq!(names(&images), ["plan.pdf"]);
    let bravo = command(
        &state,
        "l3",
        reader,
        "mission.library.list",
        json!({"mission_uid": "bravo"}),
    );
    assert_eq!(bravo["result"]["total"], 0);

    let outsider = command(
        &state,
        "l4",
        (OUTSIDER, OUTSIDER_ID),
        "mission.library.list",
        json!({}),
    );
    assert_eq!(
        outsider["result"]["total"], 0,
        "no rights, nothing enumerated"
    );
    let bad = command(
        &state,
        "l5",
        reader,
        "mission.library.list",
        json!({"per_page": 500}),
    );
    assert_eq!(
        (bad["status"].as_str(), bad["reason_code"].as_str()),
        (Some("rejected"), Some("invalid_payload"))
    );
}

#[test]
fn item_get_hides_unauthorized_items_and_link_needs_publish() {
    let state = state();
    let reader = (READER, READER_ID);
    let got = command(
        &state,
        "g1",
        reader,
        "mission.library.item.get",
        json!({"item_id": "rch:1"}),
    );
    assert_eq!(got["result"]["item"]["mission_uids"], json!(["alpha"]));
    for (id, args) in [
        ("g2", json!({"item_id": "rch:3"})),
        ("g3", json!({"file_id": 99})),
    ] {
        let hidden = command(&state, id, reader, "mission.library.item.get", args);
        assert_eq!(
            hidden["reason_code"], "not_found",
            "unknown and unauthorized look alike"
        );
    }

    let link = json!({"item_id": "rch:1", "mission_uid": "alpha"});
    let denied = command(
        &state,
        "k1",
        reader,
        "mission.library.item.link",
        link.clone(),
    );
    assert_eq!(
        denied["reason_code"], "unauthorized",
        "read-only cannot publish"
    );
    let editor = (EDITOR, EDITOR_ID);
    let linked = command(&state, "k2", editor, "mission.library.item.link", link);
    assert_eq!(linked["result"]["status"], "linked", "{linked:#}");
    let cross = command(
        &state,
        "k3",
        editor,
        "mission.library.item.link",
        json!({"item_id": "rch:2", "mission_uid": "bravo"}),
    );
    assert_eq!(cross["reason_code"], "unauthorized", "no write on bravo");
}

#[tokio::test]
async fn rest_library_shares_the_catalog_and_keeps_legacy_routes() {
    use axum::body::Body;
    use axum::http::{Method, Request, StatusCode};
    use http_body_util::BodyExt;
    use tower::ServiceExt;

    let app = crate::create_app_with_state(state().with_api_key("secret"));
    let get = |uri: &str| {
        Request::builder()
            .method(Method::GET)
            .uri(uri)
            .header("X-API-Key", "secret")
            .body(Body::empty())
            .expect("request")
    };
    let response = app
        .clone()
        .oneshot(get("/Library?kind=file&per_page=2"))
        .await
        .expect("response");
    assert_eq!(response.status(), StatusCode::OK);
    let body = response
        .into_body()
        .collect()
        .await
        .expect("body")
        .to_bytes();
    let page: Value = serde_json::from_slice(&body).expect("json");
    assert_eq!(
        (page["total"].as_u64(), page["has_next"].as_bool()),
        (Some(3), Some(true))
    );
    assert_eq!(
        page["items"][0]["name"], "unlinked.txt",
        "operators see every item, newest first"
    );
    let bad = app
        .clone()
        .oneshot(get("/Library?per_page=0"))
        .await
        .expect("response");
    assert_eq!(bad.status(), StatusCode::BAD_REQUEST);
    let legacy = app.oneshot(get("/File")).await.expect("response");
    let body = legacy.into_body().collect().await.expect("body").to_bytes();
    let legacy: Value = serde_json::from_slice(&body).expect("json");
    assert_eq!(legacy[0]["FileID"], 1, "legacy bare array sorted by FileID");
}
