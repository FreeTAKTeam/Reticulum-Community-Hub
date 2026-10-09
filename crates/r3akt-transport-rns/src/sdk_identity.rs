//! Keep RCH service announcements bound to the identity returned by the SDK.
use super::{RchServiceIdentityConfig, TransportError, ZmqSdkActorSession, transport_sdk_error};
use base64::Engine;
use lxmf_sdk::{
    Client, IdentityAnnounceRequest, IdentityBundle, IdentityImportRequest, LxmfSdkIdentity,
    ZmqPipelineBackendClient,
};
use std::collections::BTreeMap;

pub(super) struct RegisteredZmqIdentity {
    config: RchServiceIdentityConfig,
    pub(super) bundle: IdentityBundle,
}

pub(super) fn register_zmq_actor_identity(
    session: &mut ZmqSdkActorSession,
    config: RchServiceIdentityConfig,
) -> Result<IdentityBundle, TransportError> {
    let identity = session
        .client
        .identity_import(IdentityImportRequest {
            bundle_base64: base64::engine::general_purpose::STANDARD.encode(&config.private_key),
            passphrase: None,
            display_name: Some(config.display_name.clone()),
            capabilities: config.capabilities.clone(),
            metadata: config.metadata.clone(),
            extensions: BTreeMap::new(),
        })
        .map_err(transport_sdk_error)?;
    if identity.identity.0.trim().is_empty()
        || identity
            .delivery_destination
            .as_deref()
            .is_none_or(|destination| destination.trim().is_empty())
    {
        return Err(TransportError::Send(
            "LXMF SDK imported RCH identity without an identity or delivery destination".into(),
        ));
    }
    let activated = session
        .client
        .identity_activate(identity.identity.clone())
        .map_err(transport_sdk_error)?;
    if !activated.accepted {
        return Err(TransportError::Send(
            "LXMF SDK rejected activation of the imported RCH service identity".into(),
        ));
    }
    announce_registered_identity(&session.client, &config, &identity)?;
    // Publish the configuration and SDK binding together only after all checks.
    session.identity = Some(RegisteredZmqIdentity {
        config,
        bundle: identity.clone(),
    });
    Ok(identity)
}

pub(super) fn update_zmq_actor_identity(
    session: &mut ZmqSdkActorSession,
    display_name: String,
    capabilities: Vec<String>,
    metadata: BTreeMap<String, serde_json::Value>,
) -> Result<IdentityBundle, TransportError> {
    let Some(registered) = session.identity.as_ref() else {
        return Err(TransportError::Send(
            "RCH service identity is not registered".to_string(),
        ));
    };
    let mut config = registered.config.clone();
    config.display_name = display_name;
    config.capabilities = capabilities;
    config.metadata = metadata;
    register_zmq_actor_identity(session, config)
}

pub(super) fn send_lxmf_zmq_actor_announce(
    session: &mut ZmqSdkActorSession,
) -> Result<Option<String>, TransportError> {
    if let Some(registered) = session.identity.as_ref() {
        announce_registered_identity(&session.client, &registered.config, &registered.bundle)?;
    } else {
        return session
            .client
            .identity_announce_now()
            .map(|_| None)
            .map_err(transport_sdk_error);
    }
    Ok(None)
}

fn announce_registered_identity(
    client: &Client<ZmqPipelineBackendClient>,
    config: &RchServiceIdentityConfig,
    identity: &IdentityBundle,
) -> Result<(), TransportError> {
    let announced = client
        .identity_announce(IdentityAnnounceRequest {
            identity: Some(identity.identity.clone()),
            display_name: Some(config.display_name.clone()),
            capabilities: config.capabilities.clone(),
            metadata: config.metadata.clone(),
            extensions: BTreeMap::new(),
        })
        .map_err(transport_sdk_error)?;
    if !announced.accepted
        || announced.identity.as_ref() != Some(&identity.identity)
        || announced.delivery_destination != identity.delivery_destination
    {
        return Err(TransportError::Send(format!(
            "LXMF SDK announce did not accept the registered RCH identity/destination: expected identity={} destination={:?}, accepted={} identity={:?} destination={:?}",
            identity.identity.0,
            identity.delivery_destination,
            announced.accepted,
            announced.identity,
            announced.delivery_destination,
        )));
    }
    Ok(())
}
