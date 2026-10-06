use super::{
    ApiError, AppState, OutboundMessageRecord, Value, clear_success_superseded_delivery_metadata,
    delivery_state_clears_error_metadata, merge_delivery_metadata, normalized_delivery_state,
    persist_outbound_message_row,
};
use std::ops::{Deref, DerefMut};

/// A receipt or terminal queue decision cannot be replaced by dispatch callbacks.
pub(super) fn dispatch_update_allowed(message: &OutboundMessageRecord) -> bool {
    !(matches!(
        normalized_delivery_state(message).as_str(),
        "delivered" | "dropped" | "expired"
    ) || (normalized_delivery_state(message) == "propagated"
        && message
            .delivery_metadata
            .get("acked")
            .and_then(Value::as_bool)
            == Some(true)))
}

/// Stage one delivery transition while its existing projection write guard is held.
/// A failed commit leaves the published record intact; releasing the guard cannot
/// reorder a later accepted transition ahead of an older `SQLite` write.
pub(super) struct Update<'a> {
    state: &'a AppState,
    target: &'a mut OutboundMessageRecord,
    candidate: OutboundMessageRecord,
}

impl<'a> Update<'a> {
    pub fn new(state: &'a AppState, target: &'a mut OutboundMessageRecord) -> Self {
        let candidate = target.clone();
        Self {
            state,
            target,
            candidate,
        }
    }

    /// Validate against the current projection while its write guard is held.
    /// A receipt or a different dispatch attempt wins over an older result.
    pub fn for_attempt(
        state: &'a AppState,
        target: &'a mut OutboundMessageRecord,
        expected: &OutboundMessageRecord,
    ) -> Option<Self> {
        if target.delivery_method != expected.delivery_method
            || target.delivery_policy_reason != expected.delivery_policy_reason
            || target.delivery_metadata.get("last_attempt_at_ts_ms")
                != expected.delivery_metadata.get("last_attempt_at_ts_ms")
        {
            return None;
        }
        dispatch_update_allowed(target).then(|| Self::new(state, target))
    }

    pub fn commit(self) -> Result<OutboundMessageRecord, ApiError> {
        persist_outbound_message_row(self.state, &self.candidate)?;
        *self.target = self.candidate.clone();
        Ok(self.candidate)
    }
}

pub(super) fn transition(
    state: &AppState,
    message_id: &str,
    expected: Option<&OutboundMessageRecord>,
    delivery_state: &str,
    metadata: Value,
) -> Result<Option<OutboundMessageRecord>, ApiError> {
    let mut messages = state
        .messages
        .write()
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    let Some(target) = messages
        .iter_mut()
        .find(|message| message.message_id == message_id)
    else {
        return Ok(None);
    };
    let update = if let Some(expected) = expected {
        Update::for_attempt(state, target, expected)
    } else {
        Some(Update::new(state, target))
    };
    let Some(mut update) = update else {
        return Ok(None);
    };
    update.delivery_state = delivery_state.to_string();
    if delivery_state_clears_error_metadata(delivery_state) {
        clear_success_superseded_delivery_metadata(&mut update.delivery_metadata);
    }
    merge_delivery_metadata(&mut update.delivery_metadata, metadata);
    update.commit().map(Some)
}

pub(super) fn current(
    state: &AppState,
    message_id: &str,
) -> Result<OutboundMessageRecord, ApiError> {
    state
        .messages
        .read()
        .map_err(|error| ApiError::Internal(error.to_string()))?
        .iter()
        .find(|current| current.message_id == message_id)
        .cloned()
        .ok_or_else(|| ApiError::NotFound("Outbound message not found".to_string()))
}

impl Deref for Update<'_> {
    type Target = OutboundMessageRecord;
    fn deref(&self) -> &Self::Target {
        &self.candidate
    }
}

impl DerefMut for Update<'_> {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.candidate
    }
}
