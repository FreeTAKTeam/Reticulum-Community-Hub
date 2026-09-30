use super::*;

struct NotifyingSender(mpsc::Sender<()>);

impl TakCotSender for NotifyingSender {
    fn send(&self, _: &CotPayload) -> Result<(), TakConnectorError> {
        self.0.send(()).expect("worker observed");
        Err(TakConnectorError::Send("offline".to_string()))
    }
}

struct NotifyingReceiver(mpsc::Sender<()>);

impl TakCotReceiver for NotifyingReceiver {
    fn receive(&mut self) -> Result<Option<Vec<u8>>, TakConnectorError> {
        self.0.send(()).expect("worker observed");
        Err(TakConnectorError::Send("offline".to_string()))
    }
}

#[test]
fn outbound_shutdown_wakes_retry_backoff() {
    let (sender, observed) = mpsc::channel();
    let service = TakService::new(TakConnectionConfig::default(), 2, NotifyingSender(sender));
    let mut worker =
        TakServiceWorker::spawn(service, StdDuration::from_millis(200)).expect("worker");
    observed
        .recv_timeout(StdDuration::from_secs(2))
        .expect("first attempt");
    let started = Instant::now();
    worker.shutdown().expect("shutdown");
    assert!(
        started.elapsed() < StdDuration::from_millis(100),
        "shutdown must wake a sleeping worker"
    );
}

#[test]
fn invalid_keepalive_intervals_fail_without_starting_a_worker() {
    for seconds in [f64::NAN, f64::INFINITY, -1.0, 0.0, f64::MAX] {
        let (sender, _) = mpsc::channel();
        let config = TakConnectionConfig {
            keepalive_interval_seconds: seconds,
            ..TakConnectionConfig::default()
        };
        let service = TakService::new(config, 2, NotifyingSender(sender));
        assert!(TakServiceWorker::spawn(service, StdDuration::from_millis(1)).is_err());
    }
}

#[test]
fn inbound_shutdown_wakes_retry_backoff() {
    let (sender, observed) = mpsc::channel();
    let service = TakInboundService::new(NotifyingReceiver(sender), true);
    let mut worker = TakInboundWorker::spawn(service, StdDuration::from_millis(200));
    observed
        .recv_timeout(StdDuration::from_secs(2))
        .expect("first attempt");
    let started = Instant::now();
    worker.shutdown().expect("shutdown");
    assert!(
        started.elapsed() < StdDuration::from_millis(100),
        "shutdown must wake a sleeping worker"
    );
}

#[test]
fn cancelled_flush_retains_unsent_work_and_does_not_send_control_events() {
    struct BlockingSender {
        started: mpsc::Sender<()>,
        release: Mutex<mpsc::Receiver<()>>,
        sends: Arc<AtomicUsize>,
    }
    impl TakCotSender for BlockingSender {
        fn send(&self, _: &CotPayload) -> Result<(), TakConnectorError> {
            if self.sends.fetch_add(1, Ordering::SeqCst) == 0 {
                self.started.send(()).expect("started");
                self.release
                    .lock()
                    .expect("release lock")
                    .recv()
                    .expect("release");
            }
            Ok(())
        }
    }
    let (started, observed) = mpsc::channel();
    let (release, wait) = mpsc::channel();
    let sends = Arc::new(AtomicUsize::new(0));
    let mut service = TakService::new(
        TakConnectionConfig::default(),
        4,
        BlockingSender {
            started,
            release: Mutex::new(wait),
            sends: Arc::clone(&sends),
        },
    );
    service.start();
    for _ in 0..3 {
        service
            .queue_chat(&ChatEventInput {
                content: "fixture".to_string(),
                sender_label: "fixture".to_string(),
                topic_id: None,
                source_hash: None,
                timestamp: Utc::now(),
                message_uuid: None,
            })
            .expect("queue");
    }
    let mut worker = TakServiceWorker::spawn(service, StdDuration::from_millis(1)).expect("worker");
    observed
        .recv_timeout(StdDuration::from_secs(2))
        .expect("first send");
    worker.request_shutdown();
    release.send(()).expect("release");
    worker.shutdown().expect("join");
    assert_eq!(
        sends.load(Ordering::SeqCst),
        1,
        "cancel must stop between payloads and before keepalive/ping"
    );
    let status = worker.service().lock().expect("service").status();
    assert_eq!(status.queue.pending, 2);
    assert_eq!(status.total_sent, 1);
}

#[test]
fn partial_flush_counts_successes_before_a_later_send_failure() {
    struct PartialSender(AtomicUsize);
    impl TakCotSender for PartialSender {
        fn send(&self, _: &CotPayload) -> Result<(), TakConnectorError> {
            if self.0.fetch_add(1, Ordering::SeqCst) == 0 {
                Ok(())
            } else {
                Err(TakConnectorError::Send("second send fails".to_string()))
            }
        }
    }
    let mut service = TakService::new(
        TakConnectionConfig::default(),
        3,
        PartialSender(AtomicUsize::new(0)),
    );
    service.start();
    for _ in 0..2 {
        service
            .queue_chat(&ChatEventInput {
                content: "fixture".to_string(),
                sender_label: "fixture".to_string(),
                topic_id: None,
                source_hash: None,
                timestamp: Utc::now(),
                message_uuid: None,
            })
            .expect("queue");
    }
    let report = service.flush_once().expect("flush report");
    assert!(report.error.is_some());
    assert_eq!(report.sent, 1);
    assert_eq!(report.status.total_sent, 1);
    assert_eq!(report.status.queue.pending, 1);
}
