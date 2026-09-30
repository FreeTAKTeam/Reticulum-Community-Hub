use super::{
    Arc, AtomicBool, ChatEventInput, CotUrl, DateTime, Instant, LocationSnapshot, Mutex, Ordering,
    StdDuration, TakConnectionConfig, TakConnector, TakConnectorError, TakCotSender,
    TakOutboundQueue, TakQueueStats, Utc, drain_queue_until, tak_worker_interval_after_report,
    thread,
};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TakServiceState {
    Stopped,
    Running,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TakServiceStatus {
    pub state: TakServiceState,
    pub queue: TakQueueStats,
    pub total_sent: u64,
    pub total_failed: u64,
    pub last_error: Option<String>,
    pub tls_enabled: bool,
    pub tls_verification_enabled: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TakServiceDispatchReport {
    pub enqueued: bool,
    pub sent: usize,
    pub status: TakServiceStatus,
    pub error: Option<String>,
}

#[derive(Debug, Clone)]
pub struct TakService<S> {
    connector: TakConnector,
    queue: TakOutboundQueue,
    sender: S,
    state: TakServiceState,
    total_sent: u64,
    total_failed: u64,
    last_error: Option<String>,
}

impl<S: TakCotSender> TakService<S> {
    #[must_use]
    pub fn new(config: TakConnectionConfig, queue_capacity: usize, sender: S) -> Self {
        Self {
            connector: TakConnector::new(config),
            queue: TakOutboundQueue::new(queue_capacity.max(1)),
            sender,
            state: TakServiceState::Stopped,
            total_sent: 0,
            total_failed: 0,
            last_error: None,
        }
    }

    pub fn start(&mut self) {
        self.state = TakServiceState::Running;
    }

    pub fn stop(&mut self) {
        self.state = TakServiceState::Stopped;
    }

    #[must_use]
    pub fn is_running(&self) -> bool {
        self.state == TakServiceState::Running
    }

    #[must_use]
    pub fn status(&self) -> TakServiceStatus {
        TakServiceStatus {
            state: self.state,
            queue: self.queue.stats(),
            total_sent: self.total_sent,
            total_failed: self.total_failed,
            last_error: self.last_error.clone(),
            tls_enabled: CotUrl::parse(&self.connector.config().cot_url)
                .is_ok_and(|url| matches!(url.scheme.as_str(), "tls" | "ssl")),
            tls_verification_enabled: !self.connector.config().tls_insecure
                && self.connector.config().pytak_tls_dont_verify == 0,
        }
    }

    #[must_use]
    pub fn config(&self) -> &TakConnectionConfig {
        self.connector.config()
    }

    /// Admit a location into the existing retry queue without attempting I/O.
    pub fn queue_location(
        &mut self,
        snapshot: &LocationSnapshot,
        now: DateTime<Utc>,
        identity_label: Option<&str>,
    ) -> Result<(), TakConnectorError> {
        self.ensure_running()?;
        let result = self
            .queue
            .enqueue_location(&self.connector, snapshot, now, identity_label);
        self.record_admission(result)
    }

    /// Admit chat into the existing retry queue without attempting I/O.
    pub fn queue_chat(&mut self, input: &ChatEventInput) -> Result<(), TakConnectorError> {
        self.ensure_running()?;
        let result = self.queue.enqueue_chat(&self.connector, input);
        self.record_admission(result)
    }

    fn record_admission(
        &mut self,
        result: Result<(), TakConnectorError>,
    ) -> Result<(), TakConnectorError> {
        if let Err(error) = &result {
            self.total_failed = self.total_failed.saturating_add(1);
            self.last_error = Some(error.to_string());
        }
        result
    }

    pub fn enqueue_chat(
        &mut self,
        input: &ChatEventInput,
    ) -> Result<TakServiceDispatchReport, TakConnectorError> {
        self.ensure_running()?;
        let enqueue_result = self.queue.enqueue_chat(&self.connector, input);
        Ok(self.flush_after_enqueue(enqueue_result))
    }

    pub fn enqueue_location(
        &mut self,
        snapshot: &LocationSnapshot,
        now: DateTime<Utc>,
        identity_label: Option<&str>,
    ) -> Result<TakServiceDispatchReport, TakConnectorError> {
        self.ensure_running()?;
        let enqueue_result =
            self.queue
                .enqueue_location(&self.connector, snapshot, now, identity_label);
        Ok(self.flush_after_enqueue(enqueue_result))
    }

    pub fn enqueue_ping(
        &mut self,
        now: DateTime<Utc>,
    ) -> Result<TakServiceDispatchReport, TakConnectorError> {
        self.ensure_running()?;
        let enqueue_result = self.queue.enqueue_ping(&self.connector, now);
        Ok(self.flush_after_enqueue(enqueue_result))
    }

    pub fn enqueue_keepalive(
        &mut self,
        now: DateTime<Utc>,
    ) -> Result<TakServiceDispatchReport, TakConnectorError> {
        self.ensure_running()?;
        let enqueue_result = self.queue.enqueue_keepalive(&self.connector, now);
        Ok(self.flush_after_enqueue(enqueue_result))
    }

    pub fn flush_once(&mut self) -> Result<TakServiceDispatchReport, TakConnectorError> {
        self.ensure_running()?;
        Ok(self.flush_after_enqueue(Ok(())))
    }

    fn ensure_running(&self) -> Result<(), TakConnectorError> {
        if self.is_running() {
            Ok(())
        } else {
            Err(TakConnectorError::ServiceStopped)
        }
    }

    fn flush_after_enqueue(
        &mut self,
        enqueue_result: Result<(), TakConnectorError>,
    ) -> TakServiceDispatchReport {
        self.flush_until(enqueue_result, &|| false)
    }

    fn flush_until(
        &mut self,
        enqueue_result: Result<(), TakConnectorError>,
        cancelled: &impl Fn() -> bool,
    ) -> TakServiceDispatchReport {
        if let Err(error) = enqueue_result {
            self.total_failed = self.total_failed.saturating_add(1);
            self.last_error = Some(error.to_string());
            return TakServiceDispatchReport {
                enqueued: false,
                sent: 0,
                status: self.status(),
                error: Some(error.to_string()),
            };
        }

        let (sent, error) = drain_queue_until(&mut self.queue, &self.sender, cancelled);
        self.total_sent = self.total_sent.saturating_add(sent as u64);
        self.last_error = error.as_ref().map(ToString::to_string);
        if error.is_some() {
            self.total_failed = self.total_failed.saturating_add(1);
        }
        TakServiceDispatchReport {
            enqueued: true,
            sent,
            status: self.status(),
            error: self.last_error.clone(),
        }
    }
}

pub struct TakServiceWorker<S> {
    service: Arc<Mutex<TakService<S>>>,
    stop: Arc<AtomicBool>,
    handle: Option<thread::JoinHandle<()>>,
}

impl<S> TakServiceWorker<S>
where
    S: TakCotSender + Send + 'static,
{
    pub fn spawn(
        mut service: TakService<S>,
        retry_interval: StdDuration,
    ) -> Result<Self, TakConnectorError> {
        let seconds = service.connector.config().keepalive_interval_seconds;
        if !seconds.is_finite() || seconds <= 0.0 {
            return Err(TakConnectorError::Worker(
                "keepalive interval must be finite and positive".to_string(),
            ));
        }
        let keepalive_interval =
            StdDuration::try_from_secs_f64(seconds.max(1.0)).map_err(|error| {
                TakConnectorError::Worker(format!("invalid keepalive interval: {error}"))
            })?;
        service.start();
        let service = Arc::new(Mutex::new(service));
        let stop = Arc::new(AtomicBool::new(false));
        let worker_service = Arc::clone(&service);
        let worker_stop = Arc::clone(&stop);
        let interval = retry_interval.max(StdDuration::from_millis(1));
        let handle = thread::spawn(move || {
            let mut last_ping: Option<Instant> = None;
            let mut last_keepalive: Option<Instant> = None;
            let mut current_interval = interval;
            while !worker_stop.load(Ordering::SeqCst) {
                match worker_service.lock() {
                    Ok(mut guard) => {
                        let service = &mut *guard;
                        let mut send_failed = false;
                        if service.is_running() && !service.queue.is_empty() {
                            {
                                let report = service
                                    .flush_until(Ok(()), &|| worker_stop.load(Ordering::SeqCst));
                                current_interval = tak_worker_interval_after_report(
                                    current_interval,
                                    interval,
                                    &report,
                                );
                                send_failed = report.error.is_some();
                            }
                        }
                        if service.is_running()
                            && !send_failed
                            && !worker_stop.load(Ordering::SeqCst)
                        {
                            let now = Instant::now();
                            if last_ping
                                .is_none_or(|last| now.duration_since(last) >= keepalive_interval)
                            {
                                {
                                    let enqueue =
                                        service.queue.enqueue_ping(&service.connector, Utc::now());
                                    let report = service.flush_until(enqueue, &|| {
                                        worker_stop.load(Ordering::SeqCst)
                                    });
                                    current_interval = tak_worker_interval_after_report(
                                        current_interval,
                                        interval,
                                        &report,
                                    );
                                    send_failed = report.error.is_some();
                                }
                                last_ping = Some(now);
                            }
                            if !send_failed
                                && !worker_stop.load(Ordering::SeqCst)
                                && last_keepalive.is_none_or(|last| {
                                    now.duration_since(last) >= keepalive_interval
                                })
                            {
                                {
                                    let enqueue = service
                                        .queue
                                        .enqueue_keepalive(&service.connector, Utc::now());
                                    let report = service.flush_until(enqueue, &|| {
                                        worker_stop.load(Ordering::SeqCst)
                                    });
                                    current_interval = tak_worker_interval_after_report(
                                        current_interval,
                                        interval,
                                        &report,
                                    );
                                }
                                last_keepalive = Some(now);
                            }
                        }
                    }
                    Err(error) => {
                        eprintln!("TAK outbound worker service lock poisoned: {error}");
                        break;
                    }
                }
                thread::park_timeout(current_interval);
            }
        });

        Ok(Self {
            service,
            stop,
            handle: Some(handle),
        })
    }

    #[must_use]
    pub fn service(&self) -> Arc<Mutex<TakService<S>>> {
        Arc::clone(&self.service)
    }

    pub fn request_shutdown(&self) {
        self.stop.store(true, Ordering::SeqCst);
        if let Some(handle) = &self.handle {
            handle.thread().unpark();
        }
    }

    pub fn shutdown(&mut self) -> Result<TakServiceStatus, TakConnectorError> {
        self.request_shutdown();
        if let Some(handle) = self.handle.take() {
            handle.thread().unpark();
            handle
                .join()
                .map_err(|_| TakConnectorError::Worker("outbound worker panicked".to_string()))?;
        }
        let mut service = self.service.lock().map_err(|error| {
            TakConnectorError::Worker(format!("outbound service lock: {error}"))
        })?;
        service.stop();
        Ok(service.status())
    }
}

impl<S> Drop for TakServiceWorker<S> {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::SeqCst);
        if let Some(handle) = self.handle.take() {
            handle.thread().unpark();
            if handle.join().is_err() {
                eprintln!("TAK outbound worker panicked during drop");
            }
        }
    }
}
