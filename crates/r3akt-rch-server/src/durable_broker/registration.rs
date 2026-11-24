//! Admission gate for inbound LXMF traffic.
//!
//! Banned or blackholed senders are dropped silently. With the operator's authorization switch on, only registered members may
//! chat with the hub or send it commands. Registration is roster membership,
//! which operators grant in the UI (Users → Add User); an LXMF `join` from an
//! unregistered identity does not register it. Refused senders are not added
//! to the roster, and their messages are neither stored nor relayed.

use super::{
    ApiError, InboxEvent, OutboundMessageRecord, ProtocolEnvelope, RchCommandTransaction,
    normalize_identity_key,
};
use r3akt_protocol::Payload;

pub(crate) const NOT_REGISTERED_REPLY: &str =
    "This hub only accepts registered members. Ask an operator to add you.";

/// Returns `false` after dropping a blocked sender or refusing an unregistered
/// sender's chat or command.
pub(super) fn admitted(
    unit: &mut RchCommandTransaction<'_>,
    event: &InboxEvent,
    envelope: &ProtocolEnvelope,
    bootstrap: bool,
    published: &mut Vec<OutboundMessageRecord>,
) -> Result<bool, ApiError> {
    let source = normalize_identity_key(envelope.source.as_str());
    if !bootstrap
        && unit.core_mut().identity_states().iter().any(|s| {
            normalize_identity_key(&s.identity) == source && (s.is_banned || s.is_blackholed)
        })
    {
        unit.diagnose_rejection("inbound identity is banned or blackholed");
        return Ok(false);
    }
    let user_action = matches!(
        envelope.payload,
        Payload::Command(_) | Payload::TopicMessage(_)
    );
    let core = unit.core_mut();
    if !user_action
        || !core.authorization_required()
        || core.is_registered_member(envelope.source.as_str())
    {
        return Ok(true);
    }
    unit.diagnose_rejection("inbound identity is not a registered member");
    if !bootstrap {
        super::chat_presentation::reply(unit, event, envelope, NOT_REGISTERED_REPLY, published)?;
    }
    Ok(false)
}
