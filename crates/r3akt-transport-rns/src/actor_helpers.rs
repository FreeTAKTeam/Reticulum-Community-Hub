use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
use std::sync::mpsc;
use std::time::Duration;

use super::{TransportError, ZmqSdkActorRequest, ZmqSdkActorResponse};

pub(super) fn atomic_max_usize(target: &AtomicUsize, candidate: usize) {
    let _result = target.fetch_update(Ordering::Relaxed, Ordering::Relaxed, |current| {
        (candidate > current).then_some(candidate)
    });
}

pub(super) fn atomic_max_u64(target: &AtomicU64, candidate: u64) {
    let _result = target.fetch_update(Ordering::Relaxed, Ordering::Relaxed, |current| {
        (candidate > current).then_some(candidate)
    });
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
        if *send_burst >= 32 {
            if let Ok(request) = control_receiver.try_recv() {
                *send_burst = 0;
                return Some(request);
            }
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
