//! Issue #351: a marker command replayed under a new LXMF message ID must hit
//! its existing command claim, whichever release wrote that claim, and must
//! not stall the ordered inbox for the events queued behind it.

use super::pictures::{
    DRONE, DRONE_ID, MARKER, MATE, TEAM, THUMB, create_args, sha, state as picture_state,
};
use super::*;

const COMMAND_ID: &str = "marker-cmd-351";
// LXMF message IDs double as picture IDs, so they are 64 hex characters.
const FIRST: &str = "1111111111111111111111111111111111111111111111111111111111111111";
const REPLAY: &str = "2222222222222222222222222222222222222222222222222222222222222222";
const CHANGED: &str = "3333333333333333333333333333333333333333333333333333333333333333";

fn plain_args() -> Value {
    json!({"object_destination_hash": MARKER, "name": "Ridge", "lat": 44.5, "lon": -1.25})
}

fn marker_message(id: &str, args: &Value, extra: &Value) -> Value {
    let mut fields = json!({ crate::FIELD_COMMANDS.to_string(): [{
        "command_id": COMMAND_ID,
        "command_type": "mission.marker.create",
        "source": { "rns_identity": DRONE_ID },
        "timestamp": "2026-11-18T14:03:30Z",
        "args": args
    }] });
    for (key, value) in extra.as_object().expect("extra fields") {
        fields[key] = value.clone();
    }
    json!({"id": id, "source": DRONE, "destination": "local-destination", "direction": "in", "fields": fields})
}

fn chat_message(id: &str) -> Value {
    json!({"id": id, "source": DRONE, "destination": "local-destination", "direction": "in",
           "content": "still here after the replay", "fields": {}})
}

fn claim_fingerprint(args: Value) -> String {
    r3akt_rch_core::RchCommandTransaction::logical_input_fingerprint(
        &json!({"name": "mission.marker.create", "args": args}),
    )
    .expect("fingerprint")
}

fn claim(state: &crate::AppState) -> String {
    rusqlite::Connection::open(state_db(state))
        .expect("db")
        .query_row(
            "SELECT fingerprint FROM rch_broker_claims WHERE logical_id=?1",
            [format!("command:{COMMAND_ID}")],
            |r| r.get(0),
        )
        .expect("command claim")
}

/// Rewrites the committed claim as an earlier release would have written it.
fn write_legacy_claim(state: &crate::AppState, fingerprint: &str) {
    let changed = rusqlite::Connection::open(state_db(state))
        .expect("db")
        .execute(
            "UPDATE rch_broker_claims SET fingerprint=?1 WHERE logical_id=?2",
            rusqlite::params![fingerprint, format!("command:{COMMAND_ID}")],
        )
        .expect("rewrite claim");
    assert_eq!(changed, 1);
}

fn markers(state: &crate::AppState) -> usize {
    state.markers.read().expect("markers").len()
}

fn assert_drained(state: &crate::AppState) {
    let mut store = RchSqliteStore::open(state_db(state)).expect("store");
    let consumer = store.durable_consumer_id().expect("consumer");
    let checkpoint = store.inbox_checkpoint(&consumer).expect("checkpoint");
    assert_eq!(checkpoint.applied, checkpoint.stored, "{checkpoint:?}");
}

/// Replays the marker under a new message ID followed by an unrelated chat
/// message in the same batch, then checks the effects.
fn replay_then_chat(state: &crate::AppState, args: &Value, extra: &Value) {
    let markers_before = markers(state);
    let requests_before = pending_broker_requests(&state_db(state)).len();
    apply_daemon_messages(
        state,
        json!([
            marker_message(REPLAY, args, extra),
            chat_message("lxmf-chat")
        ]),
    );
    assert_drained(state);
    assert_eq!(markers(state), markers_before, "one marker effect");
    let new_requests = pending_broker_requests(&state_db(state))
        .into_iter()
        .skip(requests_before)
        .collect::<Vec<_>>();
    assert!(
        new_requests
            .iter()
            .all(|r| r["fields"].get("13").is_none() && r["fields"].get("10").is_none()),
        "no duplicate marker relay or result: {new_requests:#?}"
    );
    assert!(
        state
            .messages
            .read()
            .expect("messages")
            .iter()
            .any(|m| m.content.contains("still here after the replay")),
        "chat after the replay is visible"
    );
    assert_eq!(
        claim(state),
        claim_fingerprint(without_message_id(args, extra)),
        "claim rebound to the current fingerprint"
    );
}

/// The current claim content: the decoded args minus the per-delivery ID.
fn without_message_id(args: &Value, extra: &Value) -> Value {
    let mut args = args.clone();
    if let Some(team) = extra.get("11") {
        args["_rem_team_uid"] = team.clone();
    }
    if let Some(image) = extra.get("6") {
        let bytes = image[1]
            .as_array()
            .expect("image bytes")
            .iter()
            .map(|b| u8::try_from(b.as_u64().expect("byte")).expect("byte"))
            .collect::<Vec<_>>();
        args["_lxmf_image"] = json!([
            image[0],
            format!("base64:{}", BASE64_STANDARD.encode(bytes))
        ]);
    }
    args
}

fn first_create(state: &crate::AppState, args: &Value, extra: &Value) {
    apply_daemon_messages(state, json!([marker_message(FIRST, args, extra)]));
    assert_drained(state);
    assert_eq!(markers(state), 1);
}

#[test]
fn plain_marker_replay_under_new_message_id_is_applied_once() {
    let state = picture_state();
    let args = plain_args();
    let extra = json!({});
    first_create(&state, &args, &extra);
    replay_then_chat(&state, &args, &extra);
}

#[test]
fn plain_marker_replay_matches_a_preview40_claim() {
    let state = picture_state();
    let args = plain_args();
    let extra = json!({});
    first_create(&state, &args, &extra);
    write_legacy_claim(&state, &claim_fingerprint(args.clone()));
    replay_then_chat(&state, &args, &extra);
}

#[test]
fn plain_marker_replay_matches_a_preview41_claim() {
    let state = picture_state();
    let args = plain_args();
    let extra = json!({});
    first_create(&state, &args, &extra);
    let mut preview41 = args.clone();
    preview41["_lxmf_message_id"] = json!(FIRST);
    write_legacy_claim(&state, &claim_fingerprint(preview41));
    replay_then_chat(&state, &args, &extra);
}

#[test]
fn picture_marker_replay_matches_preview40_and_preview41_claims() {
    for preview41 in [false, true] {
        let state = picture_state();
        let args = create_args(&sha(THUMB));
        let extra = json!({"11": TEAM, "6": ["jpg", THUMB]});
        first_create(&state, &args, &extra);
        let mut legacy = without_message_id(&args, &extra);
        if preview41 {
            legacy["_lxmf_message_id"] = json!(FIRST);
        } else {
            legacy.as_object_mut().expect("args").remove("_lxmf_image");
        }
        write_legacy_claim(&state, &claim_fingerprint(legacy));
        replay_then_chat(&state, &args, &extra);
        assert!(
            pending_broker_requests(&state_db(&state))
                .iter()
                .filter(|r| r["destination"] == MATE && r["fields"].get("13").is_some())
                .count()
                == 1,
            "the team saw the picture marker exactly once"
        );
    }
}

#[test]
fn reused_marker_command_id_with_different_content_still_conflicts() {
    for preview41 in [false, true] {
        let state = picture_state();
        let args = plain_args();
        first_create(&state, &args, &json!({}));
        if preview41 {
            let mut legacy = args.clone();
            legacy["_lxmf_message_id"] = json!(FIRST);
            write_legacy_claim(&state, &claim_fingerprint(legacy));
        }
        let mut changed = args.clone();
        changed["name"] = json!("Valley");
        let error = crate::durable_broker::apply_inbound_messages_for_test(
            &state,
            &[marker_message(CHANGED, &changed, &json!({}))],
        )
        .expect_err("different content under the same command ID");
        assert!(
            error
                .to_string()
                .contains("conflicts with committed content"),
            "{error}"
        );
    }
}
