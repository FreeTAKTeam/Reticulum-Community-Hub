use super::*;
use rns_rpc::rpc::{
    OutboundBridge, OutboundDeliveryOptions, RpcDaemon, ServiceIdentityBridge,
    ServiceIdentityRecord, ServiceIdentitySpec,
};
use rns_rpc::{MessageRecord, MessagesStore};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use zeromq::{PullSocket, Socket, SocketRecv};

mod replies;

#[derive(Default)]
struct IdentityBridge(Mutex<Option<ServiceIdentityRecord>>);
impl ServiceIdentityBridge for IdentityBridge {
    fn list_service_identities(&self) -> std::io::Result<Vec<ServiceIdentityRecord>> {
        Ok(self.0.lock().unwrap().clone().into_iter().collect())
    }
    fn create_service_identity(
        &self,
        _: ServiceIdentitySpec,
    ) -> std::io::Result<ServiceIdentityRecord> {
        Err(std::io::Error::other(
            "fixture imports a persisted identity",
        ))
    }
    fn import_service_identity(
        &self,
        bytes: &[u8],
        spec: ServiceIdentitySpec,
    ) -> std::io::Result<ServiceIdentityRecord> {
        let identity =
            PrivateIdentity::from_private_key_bytes(bytes).map_err(std::io::Error::other)?;
        let hash = identity.address_hash().to_hex_string();
        let destination = rns_core::destination::new_in(identity, "lxmf", "delivery");
        let record = ServiceIdentityRecord {
            identity: hash,
            delivery_destination: destination.desc.address_hash.to_hex_string(),
            public_key: destination.desc.identity.to_hex_string(),
            display_name: spec.display_name,
            capabilities: spec.capabilities,
            metadata: spec.metadata,
        };
        *self.0.lock().unwrap() = Some(record.clone());
        Ok(record)
    }
    fn export_service_identity(&self, _: &str) -> std::io::Result<Vec<u8>> {
        Err(std::io::Error::other("not used"))
    }
    fn announce_service_identity(
        &self,
        identity: &str,
        _: ServiceIdentitySpec,
    ) -> std::io::Result<ServiceIdentityRecord> {
        let record = self.0.lock().unwrap().clone().unwrap();
        assert_eq!(identity, record.identity);
        Ok(record)
    }
}
struct NetworkBridge;
impl OutboundBridge for NetworkBridge {
    fn deliver(&self, _: &MessageRecord, _: &OutboundDeliveryOptions) -> std::io::Result<()> {
        Ok(())
    }
}
struct Fixture {
    daemon: Arc<RpcDaemon>,
    endpoint: String,
    response: String,
    stop: Arc<AtomicBool>,
    reply_failures: Arc<AtomicUsize>,
    worker: Option<std::thread::JoinHandle<()>>,
}
impl Fixture {
    fn open(path: &FsPath) -> Self {
        let store = MessagesStore::open(path).unwrap();
        store.enable_durable_broker(32 * 1024 * 1024).unwrap();
        let daemon = Arc::new(RpcDaemon::with_store_and_bridge(
            store,
            "fixture-daemon".into(),
            Arc::new(NetworkBridge),
        ));
        daemon.set_service_identity_bridge(Arc::new(IdentityBridge::default()));
        let response = endpoint();
        let endpoint = endpoint();
        let stop = Arc::new(AtomicBool::new(false));
        let reply_failures = Arc::new(AtomicUsize::new(0));
        let failures = reply_failures.clone();
        let (ready_tx, ready_rx) = std::sync::mpsc::channel();
        let d = daemon.clone();
        let ep = endpoint.clone();
        let ending = stop.clone();
        let worker = std::thread::spawn(move || {
            tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .unwrap()
                .block_on(async move {
                    let mut commands = PullSocket::new();
                    commands.bind(&ep).await.unwrap();
                    ready_tx.send(()).unwrap();
                    while !ending.load(Ordering::Acquire) {
                        let incoming =
                            match tokio::time::timeout(Duration::from_millis(50), commands.recv())
                                .await
                            {
                                Ok(Ok(value)) => value,
                                Err(_) => continue,
                                Ok(Err(error)) => panic!("{error}"),
                            };
                        let envelope =
                            rns_rpc::rpc::zmq::decode_envelope(incoming.get(0).unwrap()).unwrap();
                        let principal = d
                            .authorize_http_principal(&[], Some("127.0.0.1"), None)
                            .unwrap();
                        let payload = d
                            .handle_framed_request_for_zmq_session(
                                &envelope.session_id,
                                &principal,
                                &envelope.payload,
                            )
                            .unwrap();
                        if let Err(error) = replies::deliver(envelope, payload).await {
                            // A cancelled SDK attempt can close its reply endpoint. Keep serving
                            // the replay-safe retry, as the production response writer does.
                            failures.fetch_add(1, Ordering::Release);
                            eprintln!("fixture reply delivery failed: {error}");
                        }
                    }
                });
        });
        ready_rx.recv_timeout(Duration::from_secs(3)).unwrap();
        Self {
            daemon,
            endpoint,
            response,
            stop,
            reply_failures,
            worker: Some(worker),
        }
    }
    fn state(&self, path: &FsPath, identity_path: &FsPath) -> AppState {
        let mut state = AppState::from_sqlite_path(path)
            .unwrap()
            .with_lxmf_zmq_sdk_identity(
                self.endpoint.clone(),
                self.response.clone(),
                None,
                identity_path,
                "RCH",
            )
            .unwrap();
        state.enable_durable_consumer().unwrap();
        state.register_lxmf_zmq_service_identity().unwrap();
        state
    }
    fn inbound(&self, id: &str, destination: &str) {
        self.daemon
            .accept_inbound(MessageRecord {
                id: id.into(),
                source: "remote-peer".into(),
                destination: destination.into(),
                title: String::new(),
                content: "Test1234".into(),
                timestamp: 17,
                direction: "in".into(),
                fields: None,
                receipt_status: None,
            })
            .unwrap();
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Release);
        if let Err(error) = self.worker.take().unwrap().join() {
            if std::thread::panicking() {
                eprintln!("fixture worker panicked during cleanup: {error:?}");
            } else {
                panic!("fixture worker panicked: {error:?}");
            }
        }
        self.daemon.shutdown_outbound_workers();
    }
}
fn endpoint() -> String {
    let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    format!("tcp://{}", listener.local_addr().unwrap())
}
fn local(batch: &broker::BrokerBatch, consumer: &str) -> InboxBatch {
    InboxBatch {
        journal_id: batch.journal_id.0.clone(),
        consumer_id: consumer.into(),
        start: batch.start.0,
        end: batch.end.0,
        receipt: batch.receipt.0.clone(),
        events: batch
            .events
            .iter()
            .map(|e| InboxEvent {
                version: e.version,
                position: e.position.0,
                created_at: e.created_at,
                event_type: e.event_type.clone(),
                payload: e.payload.clone(),
            })
            .collect(),
    }
}
#[test]
fn paired_test1234_survives_lost_ack_and_both_restarts_before_application() {
    let dir = std::env::temp_dir().join(format!("rch-paired-{}", Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    let daemon_path = dir.join("daemon.db");
    let rch_path = dir.join("rch.db");
    let identity_path = dir.join("identity");
    let fixture = Fixture::open(&daemon_path);
    let state = fixture.state(&rch_path, &identity_path);
    let consumer = open(&state).unwrap().durable_consumer_id().unwrap();
    fixture.inbound(
        "logical-Test1234",
        state.reticulumd_source.as_deref().unwrap(),
    );
    let cp = plane(&state)
        .unwrap()
        .broker_resume(broker::ResumeRequest {
            consumer_id: broker::ConsumerId(consumer.clone()),
            identity: String::new(),
            journal_id: None,
            stored: broker::EventPosition(0),
        })
        .unwrap();
    let batch = plane(&state)
        .unwrap()
        .broker_fetch(broker::FetchRequest {
            consumer_id: cp.consumer_id,
            identity: String::new(),
            max_events: 128,
            max_bytes: broker::MAX_BATCH_BYTES,
        })
        .unwrap();
    open(&state)
        .unwrap()
        .store_inbox_batch(&local(&batch, &consumer))
        .unwrap();
    // Persist custody, lose ACK, restart both owners. The daemon must replay its issued receipt.
    plane(&state).unwrap().shutdown().unwrap();
    drop(state);
    drop(fixture);
    let fixture = Fixture::open(&daemon_path);
    let state = fixture.state(&rch_path, &identity_path);
    intake(&state, &consumer).unwrap();
    let cp = open(&state).unwrap().inbox_checkpoint(&consumer).unwrap();
    assert_eq!(cp.stored, 1);
    assert_eq!(cp.applied, 0);
    assert!(apply(&state, &consumer).unwrap());
    assert!(!apply(&state, &consumer).unwrap());
    fixture.inbound(
        "logical-Test1234",
        state.reticulumd_source.as_deref().unwrap(),
    );
    intake(&state, &consumer).unwrap();
    assert!(!apply(&state, &consumer).unwrap());
    assert_eq!(
        state
            .messages
            .read()
            .unwrap()
            .iter()
            .filter(|m| m.content == "Test1234")
            .count(),
        1
    );
    let conn = rusqlite::Connection::open(&rch_path).unwrap();
    assert_eq!(
        conn.query_row("SELECT COUNT(*) FROM rch_broker_inbox", [], |r| r
            .get::<_, i64>(0))
            .unwrap(),
        1
    );
    assert_eq!(
        conn.query_row("SELECT COUNT(*) FROM rch_broker_claims", [], |r| r
            .get::<_, i64>(0))
            .unwrap(),
        1
    );
    assert_eq!(
        open(&state)
            .unwrap()
            .inbox_checkpoint(&consumer)
            .unwrap()
            .applied,
        1
    );
    plane(&state).unwrap().shutdown().unwrap();
    drop(state);
    drop(fixture);
    drop(conn);
    std::fs::remove_dir_all(dir).unwrap();
}
#[test]
fn retry_backoff_is_finite_and_resets_on_success() {
    assert_eq!(retry_delay(1), Duration::from_millis(500));
    assert_eq!(retry_delay(2), Duration::from_secs(1));
    assert_eq!(retry_delay(100), Duration::from_secs(30));
}

#[test]
fn paired_replay_exceeds_old_event_window_and_keeps_every_logical_input() {
    let dir = std::env::temp_dir().join(format!("rch-window-{}", Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    let fixture = Fixture::open(&dir.join("daemon.db"));
    let state = fixture.state(&dir.join("rch.db"), &dir.join("identity"));
    let consumer = open(&state).unwrap().durable_consumer_id().unwrap();
    for index in 0..1280 {
        fixture.inbound(
            &format!("input-{index}"),
            state.reticulumd_source.as_deref().unwrap(),
        );
    }
    for _ in 0..10 {
        intake(&state, &consumer).unwrap();
    }
    assert_eq!(
        open(&state)
            .unwrap()
            .inbox_checkpoint(&consumer)
            .unwrap()
            .stored,
        1280
    );
    assert_eq!(
        open(&state).unwrap().durable_broker_diagnostics().unwrap()["pending"],
        1280
    );
    let conn = rusqlite::Connection::open(dir.join("rch.db")).unwrap();
    assert_eq!(
        conn.query_row("SELECT COUNT(*) FROM rch_broker_inbox", [], |r| r
            .get::<_, i64>(0))
            .unwrap(),
        1280
    );
    assert_eq!(
        open(&state)
            .unwrap()
            .inbox_checkpoint(&consumer)
            .unwrap()
            .applied,
        0
    );
    plane(&state).unwrap().shutdown().unwrap();
    drop(state);
    drop(fixture);
    drop(conn);
    std::fs::remove_dir_all(dir).unwrap();
}

#[test]
fn paired_outbound_reconciles_lost_admission_reply_and_applies_terminal_receipt() {
    let dir = std::env::temp_dir().join(format!("rch-outbox-{}", Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    let fixture = Fixture::open(&dir.join("daemon.db"));
    let state = fixture.state(&dir.join("rch.db"), &dir.join("identity"));
    let message = OutboundMessageRecord {
        message_id: "northbound".into(),
        topic_id: None,
        destination: Some("11223344556677889900aabbccddeeff".into()),
        sender: "operator".into(),
        content: "Test1234".into(),
        delivery_mode: DeliveryMode::Targeted,
        delivery_method: String::new(),
        delivery_policy_reason: String::new(),
        delivery_state: String::new(),
        delivery_metadata: json!({}),
        created_ts_ms: unix_now_ms(),
        attachments: vec![],
    };
    queue_northbound(&state, message).unwrap();
    let intent = open(&state)
        .unwrap()
        .pending_broker_intent()
        .unwrap()
        .unwrap();
    let admitted = plane(&state)
        .unwrap()
        .broker_admit(serde_json::from_value(intent.request.clone()).unwrap())
        .unwrap();
    // Daemon stored the operation, but RCH never recorded its reply. Dispatch must reconcile.
    assert!(dispatch(&state).unwrap());
    assert!(!dispatch(&state).unwrap());
    let same = plane(&state)
        .unwrap()
        .broker_admit(serde_json::from_value(intent.request).unwrap())
        .unwrap();
    assert_eq!(same.message_id, admitted.message_id);
    fixture
        .daemon
        .record_network_receipt(
            &admitted.message_id,
            "delivered",
            serde_json::Map::default(),
        )
        .unwrap();
    let consumer = open(&state).unwrap().durable_consumer_id().unwrap();
    intake(&state, &consumer).unwrap();
    while apply(&state, &consumer).unwrap() {}
    let messages = state.messages.read().unwrap();
    assert_eq!(messages.len(), 1);
    assert_eq!(messages[0].delivery_state, "delivered");
    drop(messages);
    let conn = rusqlite::Connection::open(dir.join("daemon.db")).unwrap();
    assert_eq!(
        conn.query_row("SELECT COUNT(*) FROM broker_operations", [], |r| r
            .get::<_, i64>(0))
            .unwrap(),
        1
    );
    plane(&state).unwrap().shutdown().unwrap();
    drop(state);
    drop(fixture);
    drop(conn);
    std::fs::remove_dir_all(dir).unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn paired_owning_workers_pause_resume_and_join_without_abandoning_custody() {
    let dir = std::env::temp_dir().join(format!("rch-owners-{}", Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    let fixture = Fixture::open(&dir.join("daemon.db"));
    let state = fixture.state(&dir.join("rch.db"), &dir.join("identity"));
    state.runtime_control.write().unwrap().shutdown_requested = true;
    let consumer = open(&state).unwrap().durable_consumer_id().unwrap();
    fixture.inbound("paused", state.reticulumd_source.as_deref().unwrap());
    let owner = spawn(state.clone(), Duration::from_millis(50));
    tokio::time::sleep(Duration::from_millis(150)).await;
    assert_eq!(
        open(&state)
            .unwrap()
            .inbox_checkpoint(&consumer)
            .unwrap()
            .stored,
        0
    );
    state.runtime_control.write().unwrap().shutdown_requested = false;
    tokio::time::timeout(Duration::from_secs(8), async {
        loop {
            if open(&state)
                .unwrap()
                .inbox_checkpoint(&consumer)
                .unwrap()
                .applied
                == 1
            {
                break;
            }
            tokio::time::sleep(Duration::from_millis(25)).await;
        }
    })
    .await
    .unwrap();
    request_runtime_exit(&state);
    tokio::time::timeout(Duration::from_secs(3), owner)
        .await
        .unwrap()
        .unwrap();
    assert_eq!(
        state
            .messages
            .read()
            .unwrap()
            .iter()
            .filter(|m| m.content == "Test1234")
            .count(),
        1
    );
    plane(&state).unwrap().shutdown().unwrap();
    drop(state);
    drop(fixture);
    std::fs::remove_dir_all(dir).unwrap();
}
