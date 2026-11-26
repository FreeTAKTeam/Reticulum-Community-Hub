use std::sync::atomic::Ordering;
use std::sync::mpsc;
use std::time::{Duration, Instant};

use super::{
    TransportError, ZmqDataPlane, ZmqDataPlaneMetrics, ZmqSdkActorPayload, ZmqSdkActorRequest,
    ZmqSdkActorResponse, actor_helpers::send_actor_response, actor_response_wait_timeout,
};

impl ZmqDataPlane {
    /// Stops admission, returns queued work unsent (`NotSubmitted`, so durable
    /// jobs stay queued for retry), and joins the actor. The wait is bounded by
    /// one in-flight operation's response budget; on timeout the actor thread
    /// is left detached and an error is returned.
    pub fn shutdown(&self) -> Result<(), TransportError> {
        self.metrics.stopping.store(true, Ordering::Release);
        let (response, _receiver) = mpsc::channel();
        // A full control lane still wakes the actor, which then drains everything.
        if let Err(mpsc::TrySendError::Full(_)) = self.control_sender.try_send(ZmqSdkActorRequest {
            payload: ZmqSdkActorPayload::Shutdown,
            response,
            queued_at: Instant::now(),
        }) {
            eprintln!("ZeroMQ control queue full during shutdown; actor drains on wake");
        }
        let actor = self
            .actor
            .lock()
            .map_err(|error| TransportError::Send(format!("ZeroMQ actor handle: {error}")))?
            .take();
        let Some(actor) = actor else {
            return Err(TransportError::NotSubmitted(
                "LXMF-rs ZeroMQ data-plane actor already stopped".to_string(),
            ));
        };
        let deadline = Instant::now() + actor_response_wait_timeout(&self.config, 3);
        while !actor.is_finished() {
            if Instant::now() >= deadline {
                return Err(TransportError::Send(
                    "LXMF-rs ZeroMQ data-plane actor did not stop before the shutdown deadline"
                        .to_string(),
                ));
            }
            std::thread::sleep(Duration::from_millis(10));
        }
        actor.join().map_err(|_| {
            TransportError::Send("LXMF-rs ZeroMQ data-plane actor panicked".to_string())
        })
    }
}

impl Drop for ZmqDataPlane {
    fn drop(&mut self) {
        let (response, receiver) = mpsc::channel();
        drop(receiver);
        self.metrics.stopping.store(true, Ordering::Release);
        if let Err(error) = self.control_sender.try_send(ZmqSdkActorRequest {
            payload: ZmqSdkActorPayload::Shutdown,
            response,
            queued_at: Instant::now(),
        }) {
            eprintln!("failed to enqueue best-effort ZeroMQ shutdown during drop: {error}");
        }
    }
}

pub(super) fn reject_queued_on_shutdown(
    first: ZmqSdkActorRequest,
    send_receiver: &mpsc::Receiver<ZmqSdkActorRequest>,
    control_receiver: &mpsc::Receiver<ZmqSdkActorRequest>,
    metrics: &ZmqDataPlaneMetrics,
) {
    let rest = send_receiver.try_iter().chain(control_receiver.try_iter());
    for (index, request) in std::iter::once(first).chain(rest).enumerate() {
        if index > 0 {
            metrics.record_dequeued(request.queued_at, request.payload.is_send_lane());
        }
        let result = if matches!(request.payload, ZmqSdkActorPayload::Shutdown) {
            Ok(ZmqSdkActorResponse::Shutdown)
        } else {
            Err(TransportError::NotSubmitted(
                "LXMF-rs ZeroMQ data plane shut down before this request ran".to_string(),
            ))
        };
        send_actor_response(&request.response, result, "shutdown drain");
    }
}
