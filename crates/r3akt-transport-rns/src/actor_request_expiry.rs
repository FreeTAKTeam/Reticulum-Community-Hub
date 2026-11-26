use std::sync::mpsc;
use std::time::{Duration, Instant};

use super::*;

#[test]
fn zmq_data_plane_reports_expired_requests_before_session_startup() {
    let (send_tx, send_rx) = mpsc::sync_channel(1);
    let (control_tx, control_rx) = mpsc::sync_channel(1);
    let (response_tx, response_rx) = mpsc::channel();
    send_tx
        .send(ZmqSdkActorRequest {
            payload: ZmqSdkActorPayload::Status("stale-status".to_string()),
            response: response_tx,
            queued_at: Instant::now()
                .checked_sub(Duration::from_secs(2))
                .expect("instant subtraction"),
        })
        .expect("queue stale request");
    drop(send_tx);
    drop(control_tx);

    let mut config = rch_local_zmq_pipeline_config("tcp://127.0.0.1:1", "tcp://127.0.0.1:2");
    config.request_timeout = Duration::from_millis(50);
    let metrics = ZmqDataPlaneMetrics::default();
    run_zmq_data_plane_actor(&config, &send_rx, &control_rx, &metrics);

    let stats = metrics.snapshot();
    assert_eq!(stats.expired_total, 1);
    assert_eq!(stats.queue_depth, 0);
    assert!(matches!(
        response_rx.try_recv().expect("explicit expiry response"),
        Err(TransportError::NotSubmitted(message)) if message.contains("expired in the actor queue")
    ));
}

#[test]
fn zmq_data_plane_shutdown_joins_actor_within_deadline_while_work_is_queued() {
    // No daemon: the in-flight request blocks on the bounded SDK connect.
    let plane = Arc::new(
        ZmqDataPlane::new_with_timeout(
            "tcp://127.0.0.1:1",
            "tcp://127.0.0.1:2",
            Duration::from_millis(200),
        )
        .expect("data plane"),
    );
    let callers: Vec<_> = (0..32)
        .map(|index| {
            let plane = Arc::clone(&plane);
            std::thread::spawn(move || plane.poll_events(Some(index.to_string()), 1))
        })
        .collect();
    std::thread::sleep(Duration::from_millis(20));
    let deadline = actor_response_wait_timeout(&plane.config, 3);
    let started = Instant::now();
    plane.shutdown().expect("bounded shutdown");
    assert!(started.elapsed() < deadline, "{:?}", started.elapsed());
    assert!(
        plane.actor.lock().expect("actor handle").is_none(),
        "actor joined"
    );
    for caller in callers {
        caller
            .join()
            .expect("caller thread")
            .expect_err("work is not run after shutdown");
    }
    assert!(matches!(
        plane.poll_events(None, 1),
        Err(TransportError::NotSubmitted(_))
    ));
}
