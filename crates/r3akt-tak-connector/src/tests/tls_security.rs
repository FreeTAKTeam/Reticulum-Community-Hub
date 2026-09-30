use super::*;

#[test]
fn default_tls_sender_rejects_an_untrusted_local_server() {
    let identity =
        Identity::from_pkcs8(TEST_TLS_CERT.as_bytes(), TEST_TLS_KEY.as_bytes()).expect("identity");
    let acceptor = native_tls::TlsAcceptor::new(identity).expect("acceptor");
    let listener = TcpListener::bind("127.0.0.1:0").expect("listener");
    let address = listener.local_addr().expect("address");
    let server = thread::spawn(move || {
        let (stream, _) = listener.accept().expect("accept");
        stream
            .set_read_timeout(Some(StdDuration::from_secs(2)))
            .expect("timeout");
        match acceptor.accept(stream) {
            Ok(mut stream) => {
                let mut data = Vec::new();
                let _ = stream.read_to_end(&mut data);
                true
            }
            Err(_) => false,
        }
    });
    let sender = TakClearSender::new(&format!("tls://{address}")).expect("sender");
    let result = sender.send(&CotPayload {
        kind: CotPayloadKind::Ping,
        xml: "<event/>".to_string(),
    });
    let accepted = server.join().expect("server");
    assert!(
        result.is_err(),
        "untrusted certificate must fail by default"
    );
    assert!(!accepted, "no authenticated session with untrusted server");
}

#[test]
fn trusted_ca_does_not_allow_a_wrong_hostname() {
    let identity =
        Identity::from_pkcs8(TEST_TLS_CERT.as_bytes(), TEST_TLS_KEY.as_bytes()).expect("identity");
    let acceptor = native_tls::TlsAcceptor::new(identity).expect("acceptor");
    let listener = TcpListener::bind("127.0.0.1:0").expect("listener");
    let address = listener.local_addr().expect("address");
    let server = thread::spawn(move || {
        let (stream, _) = listener.accept().expect("accept");
        stream
            .set_read_timeout(Some(StdDuration::from_secs(2)))
            .expect("timeout");
        acceptor.accept(stream).is_ok()
    });
    let ca_path = std::env::temp_dir().join(format!("rch-tak-hostname-{}.pem", Uuid::new_v4()));
    std::fs::write(&ca_path, TEST_TLS_CERT).expect("CA");
    let sender = TakClearSender::from_config(&TakConnectionConfig {
        tls_ca: Some(ca_path.display().to_string()),
        ..TakConnectionConfig::default()
    })
    .expect("sender");
    let stream = TcpStream::connect(address).expect("connect");
    stream
        .set_read_timeout(Some(StdDuration::from_secs(2)))
        .expect("timeout");
    assert!(
        sender
            .tls_connector()
            .expect("connector")
            .connect("wrong-host.invalid", stream)
            .is_err()
    );
    assert!(!server.join().expect("server"));
    std::fs::remove_file(ca_path).expect("cleanup");
}

#[test]
fn default_tls_receiver_rejects_an_untrusted_server() {
    let identity =
        Identity::from_pkcs8(TEST_TLS_CERT.as_bytes(), TEST_TLS_KEY.as_bytes()).expect("identity");
    let acceptor = native_tls::TlsAcceptor::new(identity).expect("acceptor");
    let listener = TcpListener::bind("127.0.0.1:0").expect("listener");
    let address = listener.local_addr().expect("address");
    let server = thread::spawn(move || {
        let (stream, _) = listener.accept().expect("accept");
        stream
            .set_read_timeout(Some(StdDuration::from_secs(2)))
            .expect("timeout");
        acceptor.accept(stream).is_ok()
    });
    let mut receiver = TakSocketReceiver::new(&format!("tls://{address}")).expect("receiver");
    assert!(receiver.receive().is_err());
    assert!(!server.join().expect("server"));
}

#[test]
fn stalled_tls_handshake_has_an_io_deadline() {
    let listener = TcpListener::bind("127.0.0.1:0").expect("listener");
    let address = listener.local_addr().expect("address");
    let (release, wait) = mpsc::channel();
    let server = thread::spawn(move || {
        let (_stream, _) = listener.accept().expect("accept");
        wait.recv_timeout(StdDuration::from_secs(3))
            .expect("release");
    });
    let sender = TakClearSender::new(&format!("tls://{address}"))
        .expect("sender")
        .with_io_timeout(StdDuration::from_millis(80));
    let started = Instant::now();
    assert!(
        sender
            .send(&CotPayload {
                kind: CotPayloadKind::Ping,
                xml: "<event/>".to_string()
            })
            .is_err()
    );
    assert!(
        started.elapsed() < StdDuration::from_secs(2),
        "handshake must finish before server releases its socket"
    );
    release.send(()).expect("release");
    server.join().expect("server");
}

#[test]
fn explicit_insecure_configuration_is_visible_in_service_status() {
    let config = TakConnectionConfig {
        tls_insecure: true,
        ..TakConnectionConfig::default()
    };
    let sender = TakClearSender::from_config(&config).expect("sender");
    let service = TakService::new(config, 2, sender);
    assert!(!service.status().tls_verification_enabled);
    let config = TakConnectionConfig::default();
    let service = TakService::new(
        config.clone(),
        2,
        TakClearSender::from_config(&config).expect("sender"),
    );
    assert!(service.status().tls_verification_enabled);
}
