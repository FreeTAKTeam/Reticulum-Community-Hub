//! Picture markers (r3akt-uas #19): thumbnail relay with the marker, reduced
//! image upload kept on RCH, retrieval answered to the requester only.

use super::*;

pub(super) const TEAM: &str = "d6b6e188b910d6bdd24d04b7a7ec5444";
const OTHER_TEAM: &str = "43341e5c822d99857fa6e8641f2ca9c0";
pub(super) const DRONE_ID: &str = "11111111111111111111111111111111";
pub(super) const DRONE: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const MATE_ID: &str = "22222222222222222222222222222222";
pub(super) const MATE: &str = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
const OUTSIDER_ID: &str = "33333333333333333333333333333333";
const OUTSIDER: &str = "cccccccccccccccccccccccccccccccc";
pub(super) const MARKER: &str = "0123456789abcdef0123456789abcdef";
const PICTURE: &str = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff";
pub(super) const THUMB: &[u8] = &[0xff, 0xd8, 0xff, 0xe0, 1, 2, 3];
const REDUCED: &[u8] = &[0xff, 0xd8, 0xff, 0xe0, 9, 8, 7, 6, 5];

pub(super) fn sha(bytes: &[u8]) -> String {
    r3akt_map_core::marker_picture::sha256_hex(bytes)
}

pub(super) fn state() -> crate::AppState {
    let setup = |command_type: &str, args: Value| r3akt_profile_rch::MissionCommandEnvelope {
        command_id: format!("setup-{command_type}-{args}"),
        source: r3akt_profile_rch::RchSource::new("setup-source"),
        timestamp: "2026-11-17T12:00:00Z".to_string(),
        command_type: command_type.to_string(),
        args,
        correlation_id: None,
        topics: Vec::new(),
    };
    let mut core = RchCore::new();
    for (uid, name) in [(TEAM, "Yellow"), (OTHER_TEAM, "Blue")] {
        core.handle_command(&setup(
            "mission.registry.team.upsert",
            json!({ "uid": uid, "team_name": name }),
        ));
    }
    for (uid, team, identity) in [
        ("member-drone", TEAM, DRONE_ID),
        ("member-mate", TEAM, MATE_ID),
        ("member-outsider", OTHER_TEAM, OUTSIDER_ID),
    ] {
        core.handle_command(&setup(
            "mission.registry.team_member.upsert",
            json!({"uid": uid, "team_uid": team, "rns_identity": identity, "display_name": uid}),
        ));
    }
    for (identity, destination) in [(DRONE_ID, DRONE), (MATE_ID, MATE), (OUTSIDER_ID, OUTSIDER)] {
        core.record_identity_announce(
            destination,
            Some(identity.to_string()),
            Some(identity.to_string()),
            Some("destination".to_string()),
            vec!["r3akt".to_string(), "EmergencyMessages".to_string()],
        )
        .expect("announce");
    }
    let db = std::env::temp_dir().join(format!("r3akt-picture-marker-{}.db", Uuid::new_v4()));
    RchSqliteStore::open(&db)
        .expect("store")
        .save_snapshot(&core.snapshot())
        .expect("snapshot");
    let mut state = crate::AppState::from_sqlite_path(&db)
        .expect("state")
        .with_test_reticulumd_source("local-destination");
    state.enable_durable_consumer().expect("durable consumer");
    state
}

/// Sends one command message and returns the broker requests it produced.
fn send(
    state: &crate::AppState,
    id: &str,
    source: &str,
    identity: &str,
    command_type: &str,
    args: Value,
    extra: Value,
) -> Vec<Value> {
    let before = pending_broker_requests(&state_db(state)).len();
    let mut fields = json!({ crate::FIELD_COMMANDS.to_string(): [{
        "command_id": format!("cmd-{id}"),
        "command_type": command_type,
        "source": { "rns_identity": identity },
        "timestamp": "2026-11-17T12:00:00Z",
        "args": args
    }] });
    for (key, value) in extra.as_object().expect("extra fields") {
        fields[key] = value.clone();
    }
    apply_daemon_messages(
        state,
        json!([{"id": id, "source": source, "destination": "local-destination", "fields": fields}]),
    );
    pending_broker_requests(&state_db(state))
        .into_iter()
        .skip(before)
        .collect()
}

fn result_of(requests: &[Value], destination: &str) -> Value {
    requests
        .iter()
        .filter(|r| r["destination"] == destination)
        .map(|r| r["fields"].clone())
        .find(|f| f["10"]["status"] != "accepted")
        .unwrap_or_else(|| panic!("no result for {destination}: {requests:#?}"))
}

pub(super) fn create_args(thumbnail_sha: &str) -> Value {
    json!({
        "object_destination_hash": MARKER,
        "marker_type": "picture", "symbol": "picture", "category": "picture",
        "name": "Picture", "lat": 44.5, "lon": -1.25,
        "picture": {
            "thumbnail": {"media_type": "image/jpeg", "width": 160, "height": 120, "sha256": thumbnail_sha},
            "captured_at": "2026-11-17T12:00:00Z",
            "camera": {"lat": 44.5001, "lon": -1.2501, "altitude_m": 50.0, "altitude_reference": "takeoff"},
            "crop": "centre"
        }
    })
}

fn upload_args(sha256: &str) -> Value {
    json!({"object_destination_hash": MARKER, "message_id": PICTURE, "media_type": "image/jpeg",
           "width": 1600, "height": 1200, "sha256": sha256})
}

fn get(state: &crate::AppState, id: &str, source: &str, identity: &str, message_id: &str) -> Value {
    let requests = send(
        state,
        id,
        source,
        identity,
        "mission.marker.picture.get",
        json!({ "message_id": message_id }),
        json!({ "11": TEAM }),
    );
    assert!(
        requests.iter().all(|r| r["destination"] == source),
        "{requests:#?}"
    );
    result_of(&requests, source)
}

#[test]
fn picture_marker_thumbnail_relays_and_reduced_image_is_fetched_on_demand() {
    let state = state();
    let thumb = json!(["jpg", THUMB]);

    let created = send(
        &state,
        PICTURE,
        DRONE,
        DRONE_ID,
        "mission.marker.create",
        create_args(&sha(THUMB)),
        json!({"11": TEAM, "6": thumb}),
    );
    let relay = created
        .iter()
        .find(|r| r["destination"] == MATE)
        .unwrap_or_else(|| panic!("team relay: {created:#?}"));
    assert_eq!(relay["fields"]["6"], thumb);
    let payload = &relay["fields"]["13"]["payload"];
    assert_eq!(payload["type"], "picture");
    assert_eq!(payload["picture"]["message_id"], PICTURE);
    assert_eq!(payload["picture"]["crop"], "centre");
    assert!(payload["picture"]["camera"].get("heading_deg").is_none());
    let received = r3akt_map_core::marker_picture::decode_relay(&relay["fields"], "rem".into())
        .expect("decode");
    assert_eq!(received.expect("picture").thumbnail.as_deref(), Some(THUMB));
    assert!(
        created
            .iter()
            .filter(|r| r["destination"] == DRONE)
            .all(|r| r["fields"].get("6").is_none())
    );
    assert!(created.iter().all(|r| r["destination"] != OUTSIDER));

    assert_eq!(
        get(&state, "get-1", MATE, MATE_ID, PICTURE)["10"]["result"]["status"],
        "pending"
    );

    // Only the marker's writer may upload, and only bytes matching the hash.
    let upload = |id: &str, source: &str, identity: &str, args: Value| {
        send(
            &state,
            id,
            source,
            identity,
            "mission.marker.picture.upload",
            args,
            json!({"6": ["jpg", REDUCED]}),
        )
    };
    let denied = upload("up-1", MATE, MATE_ID, upload_args(&sha(REDUCED)));
    assert_eq!(
        result_of(&denied, MATE)["10"]["reason_code"],
        "unauthorized"
    );
    let mismatch = upload("up-2", DRONE, DRONE_ID, upload_args(&sha(THUMB)));
    assert_eq!(result_of(&mismatch, DRONE)["10"]["status"], "rejected");
    let mut unknown = upload_args(&sha(REDUCED));
    unknown["message_id"] = json!("ff".repeat(32));
    let unknown = upload("up-3", DRONE, DRONE_ID, unknown);
    assert_eq!(
        result_of(&unknown, DRONE)["10"]["reason_code"],
        "unknown_picture"
    );

    let stored = upload("up-4", DRONE, DRONE_ID, upload_args(&sha(REDUCED)));
    assert!(
        stored.iter().all(|r| r["destination"] == DRONE),
        "never relayed: {stored:#?}"
    );
    assert_eq!(
        result_of(&stored, DRONE)["10"]["result"]["status"],
        "stored"
    );

    let fetched = get(&state, "get-2", MATE, MATE_ID, PICTURE);
    assert_eq!(fetched["10"]["result"]["status"], "ok");
    assert_eq!(fetched["10"]["result"]["sha256"], sha(REDUCED));
    assert_eq!(fetched["6"], json!(["jpg", REDUCED]));

    let outsider = get(&state, "get-3", OUTSIDER, OUTSIDER_ID, PICTURE);
    assert_eq!(outsider["10"]["result"]["status"], "unauthorized");
    assert!(outsider.get("6").is_none());
    let missing = get(&state, "get-4", MATE, MATE_ID, &"ee".repeat(32));
    assert_eq!(missing["10"]["result"]["status"], "unavailable");
}

#[test]
fn picture_marker_with_mismatched_thumbnail_is_rejected() {
    let state = state();
    let created = send(
        &state,
        PICTURE,
        DRONE,
        DRONE_ID,
        "mission.marker.create",
        create_args(&sha(REDUCED)),
        json!({"11": TEAM, "6": ["jpg", THUMB]}),
    );
    assert!(created.iter().all(|r| r["destination"] == DRONE));
    assert_eq!(result_of(&created, DRONE)["10"]["status"], "rejected");
}
