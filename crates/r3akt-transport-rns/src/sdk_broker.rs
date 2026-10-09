use super::{
    JsonValue, TransportError, ZmqDataPlane, ZmqSdkActorPayload, ZmqSdkActorResponse,
    ZmqSdkActorSession, durable_broker,
};

pub(super) fn transport_requires_session_restore(error: &TransportError) -> bool {
    matches!(error,TransportError::Sdk {code,..} if matches!(code.as_str(),"SDK_BROKER_SESSION_REQUIRED"|"SDK_BROKER_NEGOTIATION_REQUIRED"|"SDK_RUNTIME_IDENTITY_NOT_FOUND"))
}

impl ZmqDataPlane {
    pub fn broker_resume(
        &self,
        request: durable_broker::ResumeRequest,
    ) -> Result<durable_broker::BrokerCheckpoint, TransportError> {
        match self.request(ZmqSdkActorPayload::BrokerResume(request))? {
            ZmqSdkActorResponse::BrokerCheckpoint(value) => Ok(value),
            _ => Err(TransportError::Receive("expected broker checkpoint".into())),
        }
    }
    pub fn broker_fetch(
        &self,
        request: durable_broker::FetchRequest,
    ) -> Result<durable_broker::BrokerBatch, TransportError> {
        match self.request(ZmqSdkActorPayload::BrokerFetch(request))? {
            ZmqSdkActorResponse::BrokerBatch(value) => Ok(value),
            _ => Err(TransportError::Receive("expected broker batch".into())),
        }
    }
    pub fn broker_ack_stored(
        &self,
        request: durable_broker::AckStoredRequest,
    ) -> Result<durable_broker::EventPosition, TransportError> {
        match self.request(ZmqSdkActorPayload::BrokerAck(request))? {
            ZmqSdkActorResponse::BrokerStored(value) => Ok(value),
            _ => Err(TransportError::Receive(
                "expected broker custody checkpoint".into(),
            )),
        }
    }
}

pub(super) fn broker_identity(session: &ZmqSdkActorSession) -> Result<String, TransportError> {
    session
        .identity
        .as_ref()
        .map(|i| i.bundle.identity.0.clone())
        .ok_or_else(|| TransportError::Sdk {
            code: "SDK_RUNTIME_IDENTITY_NOT_FOUND".into(),
            category: Some("Runtime".into()),
            retryable: false,
            message: "RCH service identity must be registered before durable broker use".into(),
        })
}
impl ZmqDataPlane {
    pub fn broker_announces(&self) -> Result<JsonValue, TransportError> {
        match self.request(ZmqSdkActorPayload::BrokerAnnounces(
            durable_broker::AnnounceProjectionRequest {
                identity: String::new(),
            },
        ))? {
            ZmqSdkActorResponse::Control(value) => Ok(value),
            _ => Err(TransportError::Receive(
                "unexpected announce projection response".into(),
            )),
        }
    }
    pub fn broker_admit(
        &self,
        request: durable_broker::AdmitRequest,
    ) -> Result<durable_broker::OperationReceipt, TransportError> {
        match self.request(ZmqSdkActorPayload::BrokerAdmit(request))? {
            ZmqSdkActorResponse::BrokerOperation(Some(value)) => Ok(value),
            _ => Err(TransportError::Receive(
                "expected durable operation receipt".into(),
            )),
        }
    }
    pub fn broker_reconcile(
        &self,
        request: durable_broker::ReconcileRequest,
    ) -> Result<Option<durable_broker::OperationReceipt>, TransportError> {
        match self.request(ZmqSdkActorPayload::BrokerReconcile(request))? {
            ZmqSdkActorResponse::BrokerOperation(value) => Ok(value),
            _ => Err(TransportError::Receive(
                "expected durable reconciliation".into(),
            )),
        }
    }
}
