use super::{
    BTreeMap, LxmfSdkOutboundBatch, LxmfSdkOutboundBatchError, LxmfSdkOutboundBatchResult,
    TransportError, ZmqSdkActorSession, lxmf_sdk_batch_send_request, transport_sdk_error,
};

pub(super) fn send_lxmf_zmq_actor_batch(
    session: &mut ZmqSdkActorSession,
    batch: LxmfSdkOutboundBatch,
) -> Result<Vec<LxmfSdkOutboundBatchResult>, TransportError> {
    let mut destinations = batch
        .messages
        .iter()
        .map(|message| (message.correlation_id.clone(), message.destination.clone()))
        .collect::<BTreeMap<_, _>>();
    if destinations.len() != batch.messages.len() {
        return Err(TransportError::Encode(
            "Duplicate SDK batch correlation IDs".to_string(),
        ));
    }
    let request = lxmf_sdk_batch_send_request(batch)?;
    let result = session
        .client
        .backend()
        .send_batch(request)
        .map_err(transport_sdk_error)?;
    if result.results.len() != destinations.len() {
        return Err(TransportError::Receive(
            "SDK batch response does not cover every requested recipient".to_string(),
        ));
    }
    let mut output = Vec::with_capacity(result.results.len());
    for item in result.results {
        let message_id = item.message_id.unwrap_or_default();
        if item.accepted && message_id.is_empty() {
            return Err(TransportError::Send(
                "LXMF-rs ZeroMQ SDK accepted batch item missing message_id".to_string(),
            ));
        }
        let destination = destinations.remove(&item.id).ok_or_else(|| {
            TransportError::Receive(
                "SDK batch response has a duplicate or unknown recipient ID".to_string(),
            )
        })?;
        output.push(LxmfSdkOutboundBatchResult {
            id: item.id,
            message_id,
            destination,
            accepted: item.accepted,
            error: item.error.map(|error| LxmfSdkOutboundBatchError {
                code: error.code,
                message: error.message,
                category: error.category,
                retryable: error.retryable,
            }),
        });
    }
    Ok(output)
}
