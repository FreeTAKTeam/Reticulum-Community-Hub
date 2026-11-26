use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
use std::sync::mpsc;
use std::time::Duration;

use super::{
    LXMF_ZMQ_SEND_QUEUE_MAX_BYTES, TransportError, ZmqDataPlaneMetrics, ZmqPipelineBackendConfig,
    ZmqSdkActorPayload, ZmqSdkActorRequest, ZmqSdkActorResponse, actor_response_wait_timeout,
};

pub(super) fn atomic_max_usize(target: &AtomicUsize, candidate: usize) {
    target.fetch_max(candidate, Ordering::Relaxed);
}

pub(super) fn atomic_max_u64(target: &AtomicU64, candidate: u64) {
    target.fetch_max(candidate, Ordering::Relaxed);
}

pub(super) fn send_actor_response(
    response: &mpsc::Sender<Result<ZmqSdkActorResponse, TransportError>>,
    result: Result<ZmqSdkActorResponse, TransportError>,
    context: &str,
) {
    if response.send(result).is_err() {
        eprintln!("ZeroMQ actor response receiver dropped during {context}");
    }
}

pub(super) fn recv_prioritized_actor_request(
    send_receiver: &mpsc::Receiver<ZmqSdkActorRequest>,
    control_receiver: &mpsc::Receiver<ZmqSdkActorRequest>,
    send_burst: &mut usize,
) -> Option<ZmqSdkActorRequest> {
    loop {
        if *send_burst >= 32
            && let Ok(request) = control_receiver.try_recv()
        {
            *send_burst = 0;
            return Some(request);
        }
        match send_receiver.try_recv() {
            Ok(request) => {
                *send_burst = send_burst.saturating_add(1);
                return Some(request);
            }
            Err(mpsc::TryRecvError::Empty) => {}
            Err(mpsc::TryRecvError::Disconnected) => return control_receiver.recv().ok(),
        }
        match control_receiver.try_recv() {
            Ok(request) => {
                *send_burst = 0;
                return Some(request);
            }
            Err(mpsc::TryRecvError::Empty) => {}
            Err(mpsc::TryRecvError::Disconnected) => return send_receiver.recv().ok(),
        }
        match send_receiver.recv_timeout(Duration::from_millis(5)) {
            Ok(request) => {
                *send_burst = send_burst.saturating_add(1);
                return Some(request);
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {}
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                return control_receiver.recv().ok();
            }
        }
    }
}

impl ZmqSdkActorPayload {
    pub(super) fn response_wait_timeout(&self, config: &ZmqPipelineBackendConfig) -> Duration {
        let operation_rpcs = match self {
            Self::RegisterIdentity(_) | Self::UpdateIdentity { .. } | Self::SyncSelectedNode => 3,
            Self::ResolvePath(_) => 2,
            _ => 1,
        };
        actor_response_wait_timeout(config, operation_rpcs)
    }

    /// Estimated retained bytes; only send-lane payloads count toward the byte budget.
    pub(super) fn retained_bytes(&self) -> usize {
        // An unserializable value cannot be encoded for the wire either, so it never fits.
        fn json_len(value: &impl serde::Serialize) -> usize {
            serde_json::to_vec(value).map_or(usize::MAX, |bytes| bytes.len())
        }
        fn message(title: &str, content: &str, fields: &serde_json::Value) -> usize {
            title
                .len()
                .saturating_add(content.len())
                .saturating_add(json_len(fields))
        }
        match self {
            Self::Single(m) => message(&m.title, &m.content, &m.fields),
            Self::Batch(batch) => batch.messages.iter().fold(0, |total, m| {
                total.saturating_add(message(&m.title, &m.content, &m.fields))
            }),
            Self::BrokerAdmit(request) => json_len(request),
            _ => 0,
        }
    }

    pub(super) fn batch_size(&self) -> usize {
        match self {
            Self::Single(_) => 1,
            Self::Batch(batch) => batch.messages.len(),
            Self::Status(_)
            | Self::ResolvePath(_)
            | Self::SyncSelectedNode
            | Self::RegisterIdentity(_)
            | Self::UpdateIdentity { .. }
            | Self::Announce
            | Self::PollEvents { .. }
            | Self::MessageHistory(_)
            | Self::BrokerAnnounces(_)
            | Self::BrokerAdmit(_)
            | Self::BrokerReconcile(_)
            | Self::BrokerResume(_)
            | Self::BrokerFetch(_)
            | Self::BrokerAck(_)
            | Self::Shutdown => 0,
        }
    }

    pub(super) fn is_send_lane(&self) -> bool {
        matches!(
            self,
            Self::Single(_) | Self::Batch(_) | Self::BrokerAdmit(_)
        )
    }
}

impl ZmqDataPlaneMetrics {
    #[allow(deprecated, reason = "`try_update` needs Rust 1.95; the MSRV is 1.89")]
    pub(super) fn reserve_send_bytes(&self, bytes: usize) -> bool {
        self.send_queue_bytes
            .fetch_update(Ordering::AcqRel, Ordering::Acquire, |queued| {
                queued
                    .checked_add(bytes)
                    .filter(|total| *total <= LXMF_ZMQ_SEND_QUEUE_MAX_BYTES)
            })
            .is_ok()
    }

    #[allow(deprecated, reason = "`try_update` needs Rust 1.95; the MSRV is 1.89")]
    pub(super) fn release_send_bytes(&self, bytes: usize) {
        match self
            .send_queue_bytes
            .fetch_update(Ordering::AcqRel, Ordering::Acquire, |queued| {
                Some(queued.saturating_sub(bytes))
            }) {
            Ok(_) | Err(_) => {}
        }
    }
}
