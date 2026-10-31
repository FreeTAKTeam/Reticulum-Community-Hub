use super::{pending_broker_requests, test_client};
use crate::*;

const REM: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const GENERIC: &str = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

fn fixture(peers: &[(&str, bool)]) -> (AppState, std::path::PathBuf, MarkerRecord) {
    let directory = std::env::temp_dir().join(format!("rch-marker-delivery-{}", Uuid::new_v4()));
    std::fs::create_dir(&directory).unwrap();
    let db = directory.join("state.db");
    let now = unix_now_ms();
    let mut snapshot = r3akt_rch_core::RchCore::new().snapshot();
    snapshot.clients = peers.iter().map(|(id, _)| test_client(id, now)).collect();
    snapshot.identity_announces = peers
        .iter()
        .map(|(id, rem)| r3akt_rch_core::IdentityAnnounceRecord {
            destination_hash: (*id).into(),
            announced_identity_hash: None,
            display_name: None,
            source_interface: Some("identity".into()),
            announce_capabilities: if *rem {
                vec!["r3akt".into(), "emergencymessages".into()]
            } else {
                vec!["group_chat".into()]
            },
            client_type: if *rem { "rem" } else { "generic_lxmf" }.into(),
            first_seen_ts_ms: now,
            last_seen_ts_ms: now,
        })
        .collect();
    RchSqliteStore::open(&db)
        .unwrap()
        .save_snapshot(&snapshot)
        .unwrap();
    let state = AppState::from_sqlite_path(&db)
        .unwrap()
        .with_test_reticulumd_source("cccccccccccccccccccccccccccccccc");
    let marker = MarkerRecord::create(
        r3akt_map_core::MarkerDraft {
            marker_type: "fire".into(),
            symbol: "fire".into(),
            name: "Ridge".into(),
            category: "incident".into(),
            notes: None,
            origin_rch: "rch".into(),
            position: r3akt_map_core::Position::new(44.5, -1.25).unwrap(),
        },
        "local".into(),
        now,
    );
    (state, directory, marker)
}

#[test]
fn automatic_marker_delivery_honors_roster_preferences_and_identity_policy() {
    let paused = "11111111111111111111111111111111";
    let text_only = "22222222222222222222222222222222";
    let banned = "33333333333333333333333333333333";
    let blackholed = "44444444444444444444444444444444";
    let denied = "55555555555555555555555555555555";
    let (state, directory, marker) = fixture(&[
        (REM, true),
        (GENERIC, false),
        (paused, false),
        (text_only, false),
        (banned, false),
        (blackholed, false),
        (denied, false),
    ]);
    let mut state = state
        .with_outbound_identity_allowlist([REM, GENERIC, paused, text_only, banned, blackholed]);
    // A runtime restart must not remove offline roster members or bypass policy.
    state.reticulumd_rpc_endpoint = Some(Arc::new("unused-test-endpoint".into()));
    state.runtime_control.write().unwrap().last_start_ts_ms =
        Some(unix_now_ms() + REM_PEER_RUNTIME_START_GRACE_MS + 60_000);
    {
        let mut clients = state.clients.write().unwrap();
        clients.get_mut(paused).unwrap().paused = true;
        clients.get_mut(text_only).unwrap().text_only = true;
    }
    for (identity, is_banned, is_blackholed) in [(banned, true, false), (blackholed, false, true)] {
        state.identity_states.write().unwrap().insert(
            identity.into(),
            IdentityStatusRecord {
                identity: identity.into(),
                is_banned,
                is_blackholed,
                updated_ts_ms: unix_now_ms(),
            },
        );
    }
    let result =
        marker_fanout::fanout_marker_activity_to_recipients(&state, "marker.created", &marker)
            .unwrap();
    assert_eq!(result["sent"], 2);
    assert_eq!(result["failed"], 0);
    assert_eq!(result["skipped"], 5);
    assert_eq!(
        result["skipped_reasons"],
        json!({"paused":1, "text_only":1, "outbound_policy":3})
    );
    let requests = pending_broker_requests(&directory.join("state.db"));
    assert_eq!(requests.len(), 2);
    assert!(
        requests
            .iter()
            .all(|request| request["options"]["try_propagation_on_fail"] == true)
    );
    assert!(
        requests
            .iter()
            .all(|r| r["destination"] == REM || r["destination"] == GENERIC)
    );
    let messages = state.messages.read().unwrap();
    let generic = messages
        .iter()
        .find(|m| m.destination.as_deref() == Some(GENERIC))
        .unwrap();
    assert_eq!(
        generic.delivery_metadata["fanout_channel"],
        "marker_telemetry"
    );
    let packed = BASE64_STANDARD
        .decode(
            generic.delivery_metadata["lxmf_fields"]["_lxmf_fields_msgpack_b64"]
                .as_str()
                .unwrap(),
        )
        .unwrap();
    let (r3akt_map_core::msgpack::Value::Map(fields), _) =
        r3akt_map_core::msgpack::parse_value(&packed).unwrap()
    else {
        panic!("fields map")
    };
    let r3akt_map_core::msgpack::Value::Array(stream) = &fields[0].1 else {
        panic!("stream")
    };
    let r3akt_map_core::msgpack::Value::Array(entry) = &stream[0] else {
        panic!("stream entry")
    };
    assert!(matches!(&entry[0], r3akt_map_core::msgpack::Value::Bytes(hash) if hash.len() == 16));
    assert!(matches!(
        &entry[2],
        r3akt_map_core::msgpack::Value::Bytes(_)
    ));
    drop(messages);
    std::fs::remove_dir_all(directory).unwrap();
}

#[test]
fn marker_deletes_and_mission_links_remain_rem_only_with_explicit_skip_reasons() {
    let (state, directory, marker) = fixture(&[(REM, true), (GENERIC, false)]);
    let deleted =
        marker_fanout::fanout_marker_activity_to_recipients(&state, "marker.deleted", &marker)
            .unwrap();
    assert_eq!(deleted["sent"], 1);
    assert_eq!(
        deleted["skipped_recipients"],
        json!([{
            "destination": GENERIC, "reason": "standard_marker_delete_unsupported"
        }])
    );
    assert_eq!(
        deleted["skipped_reasons"]["standard_marker_delete_unsupported"],
        1
    );
    for event in [
        "mission.registry.mission.marker.linked",
        "mission.registry.mission.marker.unlinked",
    ] {
        let linked = marker_fanout::fanout_mission_marker_link_to_recipients(
            &state,
            event,
            "mission",
            &marker.object_destination_hash,
            &json!({}),
        )
        .unwrap();
        assert_eq!(linked["sent"], 1);
        assert_eq!(linked["skipped_reasons"]["rem_command_required"], 1);
    }
    let requests = pending_broker_requests(&directory.join("state.db"));
    assert_eq!(requests.len(), 3);
    assert!(requests.iter().all(|r| r["destination"] == REM));
    assert!(requests[0]["fields"].get("3").is_none());
    assert_eq!(
        requests[0]["fields"]["13"]["event_type"],
        "mission.marker.deleted"
    );
    std::fs::remove_dir_all(directory).unwrap();
}

#[test]
fn offline_roster_markers_are_durable_with_propagation_but_announced_only_peers_are_excluded() {
    let (mut state, directory, marker) = fixture(&[(REM, true), (GENERIC, false)]);
    state.clients.write().unwrap().remove(REM);
    // The remaining roster peer announced before the current runtime window.
    state.reticulumd_rpc_endpoint = Some(Arc::new("unused-test-endpoint".into()));
    state.runtime_control.write().unwrap().last_start_ts_ms =
        Some(unix_now_ms() + REM_PEER_RUNTIME_START_GRACE_MS + 60_000);
    let result =
        marker_fanout::fanout_marker_activity_to_recipients(&state, "marker.created", &marker)
            .unwrap();
    assert_eq!(result["sent"], 1);
    let requests = pending_broker_requests(&directory.join("state.db"));
    assert_eq!(requests.len(), 1);
    assert_eq!(requests[0]["destination"], GENERIC);
    assert_eq!(requests[0]["options"]["method"], "direct");
    assert_eq!(requests[0]["options"]["try_propagation_on_fail"], true);
    drop(state);
    std::fs::remove_dir_all(directory).unwrap();
}
