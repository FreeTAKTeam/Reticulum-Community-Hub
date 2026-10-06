use super::{
    JsonValue, PropagationPeerSyncRequest, PropagationRemoteRequest, RnsSdkTransport,
    RnsTransportOperation, SdkControlRequest, TransportError, ZmqSdkActorPayload,
    ZmqSdkActorResponse, ZmqSdkActorSession, transport_sdk_error,
};

pub(super) fn resolve_zmq_actor_path(
    session: &ZmqSdkActorSession,
    destination: &str,
) -> Result<JsonValue, TransportError> {
    let status = session
        .client
        .rns_transport(SdkControlRequest::new(
            RnsTransportOperation::PathStatus,
            serde_json::json!({"destination": destination}),
        ))
        .map_err(transport_sdk_error)?;
    if !status.accepted {
        return Err(TransportError::Receive(
            "Daemon rejected SDK path status query".to_string(),
        ));
    }
    let known = status
        .value
        .get("path_found")
        .and_then(JsonValue::as_bool)
        .ok_or_else(|| {
            TransportError::Receive("Daemon path status is missing boolean path_found".to_string())
        })?;
    if known {
        return Ok(status.value);
    }
    let requested = session
        .client
        .rns_transport(SdkControlRequest::new(
            RnsTransportOperation::RequestPath,
            serde_json::json!({"destination": destination, "timeout_secs": 0}),
        ))
        .map_err(transport_sdk_error)?;
    if !requested.accepted
        || requested
            .value
            .get("path_found")
            .and_then(JsonValue::as_bool)
            .is_none()
    {
        return Err(TransportError::Receive(
            "Daemon returned invalid or rejected SDK path request".to_string(),
        ));
    }
    Ok(requested.value)
}

pub(super) fn sync_zmq_actor_selected_node(
    session: &ZmqSdkActorSession,
) -> Result<JsonValue, TransportError> {
    let backend = session.client.backend();
    let selected = backend
        .propagation_node_get()
        .map_err(transport_sdk_error)?;
    let peer = selected
        .peer
        .filter(|peer| !peer.trim().is_empty())
        .ok_or_else(|| {
            TransportError::Send("No propagation node selected in daemon".to_string())
        })?;
    let sync: PropagationPeerSyncRequest =
        serde_json::from_value(serde_json::json!({"peer": peer}))
            .map_err(|error| TransportError::Send(format!("Invalid SDK sync request: {error}")))?;
    let sync_result = backend
        .propagation_peer_sync(sync)
        .map_err(transport_sdk_error)?;
    let fetch: PropagationRemoteRequest = serde_json::from_value(
        serde_json::json!({"remote": peer, "timeout_secs": 30.0, "transfer_limit_kb": 10240.0}),
    )
    .map_err(|error| TransportError::Send(format!("Invalid SDK fetch request: {error}")))?;
    let fetch_result = backend
        .propagation_remote_fetch(fetch)
        .map_err(transport_sdk_error)?;
    Ok(
        serde_json::json!({"status":"sync_requested", "reason":"manual", "propagation_node":peer, "rpc_result":sync_result, "fetch_result":fetch_result}),
    )
}

impl super::ZmqDataPlane {
    /// Consult the daemon's active path table and request discovery if unknown.
    /// Returns its authoritative path metadata without retaining a local route cache.
    pub fn resolve_path(
        &self,
        destination: impl Into<String>,
    ) -> Result<JsonValue, TransportError> {
        match self.request(ZmqSdkActorPayload::ResolvePath(destination.into()))? {
            ZmqSdkActorResponse::Control(value) => Ok(value),
            _ => Err(TransportError::Receive(
                "SDK path lookup returned non-control response".to_string(),
            )),
        }
    }

    /// Sync using the daemon-selected propagation node, without changing selection.
    pub fn sync_selected_propagation_node(&self) -> Result<JsonValue, TransportError> {
        match self.request(ZmqSdkActorPayload::SyncSelectedNode)? {
            ZmqSdkActorResponse::Control(value) => Ok(value),
            _ => Err(TransportError::Receive(
                "SDK sync returned non-control response".to_string(),
            )),
        }
    }
}
