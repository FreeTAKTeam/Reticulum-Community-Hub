//! Logical command claims (issue #351).
//!
//! A command claim binds `(source, command_id)` to a fingerprint of the
//! command's logical content, so a replayed command is applied once and a
//! reused command ID carrying different content stops the ordered inbox.
//!
//! The transport adds `_lxmf_message_id` to picture-capable commands. That is
//! per-delivery metadata, not command content: a sender retrying the same
//! command under a new LXMF message must hit the existing claim. The current
//! fingerprint therefore excludes it. Claims written before this rule are
//! still recognised and rebound to the current fingerprint:
//!
//! - preview.40 and earlier fingerprinted the arguments without any
//!   transport-added `_lxmf_*` key;
//! - preview.41 fingerprinted them with `_lxmf_message_id` of the message
//!   that first carried the command. That message also wrote the source's
//!   outer `lxmf:<message id>` claim, so the candidates are those IDs.
//!
//! Content that differs from every scheme still fails with the original
//! recovery error.

use super::{ApiError, RchCommandTransaction, Value, json, normalize_identity_key, storage};
use r3akt_protocol::{Command, ProtocolEnvelope};

/// Transport-only per-delivery key; never part of the logical content.
const MESSAGE_ID_ARG: &str = "_lxmf_message_id";
/// Transport-added image; content, but absent from preview.40 claims.
const IMAGE_ARG: &str = "_lxmf_image";
/// Logical ID prefix of the outer per-message claim (see `application.rs`).
const LXMF_CLAIM_PREFIX: &str = "lxmf:";

/// The claim payload for `command` under the current fingerprint scheme.
fn claim_payload(command: &Command) -> Value {
    json!({"name": command.name, "args": without(&command.args, &[MESSAGE_ID_ARG])})
}

fn without(args: &Value, keys: &[&str]) -> Value {
    let mut args = args.clone();
    if let Some(map) = args.as_object_mut() {
        for key in keys {
            map.remove(*key);
        }
    }
    args
}

fn source_key(source: &str) -> String {
    normalize_identity_key(source).unwrap_or_else(|| source.trim().to_ascii_lowercase())
}

fn fingerprint(payload: &Value) -> Result<String, ApiError> {
    RchCommandTransaction::logical_input_fingerprint(payload).map_err(storage)
}

/// Claims the logical command input, first rebinding a matching claim written
/// by an older fingerprint scheme. Returns `true` when the command is new.
pub(super) fn claim_command(
    unit: &RchCommandTransaction<'_>,
    envelope: &ProtocolEnvelope,
    logical: &str,
    command: &Command,
) -> Result<bool, ApiError> {
    let source = envelope.source.as_str();
    let payload = claim_payload(command);
    if let Some(previous) = unit
        .claimed_logical_input(source, logical)
        .map_err(storage)?
        && previous != fingerprint(&payload)?
        && legacy_claim_matches(unit, source, command, &previous)?
    {
        unit.rebind_logical_input(source, logical, &previous, &payload)
            .map_err(storage)?;
        eprintln!(
            "durable broker: rebound legacy command claim {logical} of source {} to the current fingerprint",
            source_key(source)
        );
    }
    unit.claim_logical_input(source, logical, &payload)
        .map_err(storage)
}

fn legacy_claim_matches(
    unit: &RchCommandTransaction<'_>,
    source: &str,
    command: &Command,
    previous: &str,
) -> Result<bool, ApiError> {
    let shape = |args: Value| json!({"name": command.name, "args": args});
    // preview.40: no transport-added keys at all.
    if fingerprint(&shape(without(&command.args, &[MESSAGE_ID_ARG, IMAGE_ARG])))? == previous {
        return Ok(true);
    }
    // preview.41 only differs from the current scheme when it added a message ID.
    if command.args.get(MESSAGE_ID_ARG).is_none() {
        return Ok(false);
    }
    // preview.41 under an earlier message ID. The message that wrote the
    // claim also wrote this source's outer `lxmf:<message id>` claim, so
    // those IDs are the only candidates.
    let mut args = command.args.clone();
    for logical in unit
        .claimed_logical_inputs_with_prefix(source, LXMF_CLAIM_PREFIX)
        .map_err(storage)?
    {
        let id = &logical[LXMF_CLAIM_PREFIX.len()..];
        args[MESSAGE_ID_ARG] = Value::String(id.into());
        if fingerprint(&shape(args.clone()))? == previous {
            return Ok(true);
        }
    }
    Ok(false)
}
