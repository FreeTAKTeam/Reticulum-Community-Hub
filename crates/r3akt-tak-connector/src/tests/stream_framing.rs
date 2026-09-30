use super::*;

const FIRST: &[u8] = br#"<event uid="first"><point lat="1" lon="2" /></event>"#;
const SECOND: &[u8] = br#"<event uid="second"><point lat="3" lon="4" /></event>"#;

#[test]
fn incomplete_or_multiple_xml_events_cannot_parse_as_one_event() {
    for bytes in [
        br#"<event uid="first"><point lat="1" lon="2" />"#.to_vec(),
        [FIRST, SECOND].concat(),
    ] {
        assert!(matches!(
            parse_inbound_cot_payload(&bytes, true),
            TakInboundCotResult::Raw(_)
        ));
    }
}

#[test]
fn tcp_receiver_keeps_partial_bytes_across_a_timeout_and_reuses_the_connection() {
    let listener = TcpListener::bind("127.0.0.1:0").expect("listener");
    let address = listener.local_addr().expect("address");
    let (release, wait) = mpsc::channel();
    let server = thread::spawn(move || {
        let (mut stream, _) = listener.accept().expect("accept");
        stream.write_all(&FIRST[..20]).expect("partial write");
        wait.recv_timeout(StdDuration::from_secs(3))
            .expect("release");
        // The defective receiver closes this connection after its first read.
        let _ = stream.write_all(&FIRST[20..]);
    });
    let mut receiver = TakSocketReceiver::new(&format!("tcp://{address}"))
        .expect("receiver")
        .with_read_timeout(StdDuration::from_millis(50));
    let partial = receiver.receive();
    release.send(()).expect("release");
    let complete = receiver.receive();
    server.join().expect("server");
    assert_eq!(partial.expect("partial timeout"), None);
    assert_eq!(complete.expect("complete frame"), Some(FIRST.to_vec()));
}

#[test]
fn tcp_receiver_separates_coalesced_frames_including_cdata_and_comments() {
    let listener = TcpListener::bind("127.0.0.1:0").expect("listener");
    let address = listener.local_addr().expect("address");
    let first = br#"<event uid="first"><detail><![CDATA[</event>]]><!-- </event> --></detail><point lat="1" lon="2" /></event>"#;
    let server = thread::spawn(move || {
        let (mut stream, _) = listener.accept().expect("accept");
        stream
            .write_all(&[first.as_slice(), SECOND].concat())
            .expect("write");
    });
    let mut receiver = TakSocketReceiver::new(&format!("tcp://{address}"))
        .expect("receiver")
        .with_read_timeout(StdDuration::from_millis(50));
    let one = receiver.receive();
    let two = receiver.receive();
    server.join().expect("server");
    assert_eq!(one.expect("first"), Some(first.to_vec()));
    assert_eq!(two.expect("second"), Some(SECOND.to_vec()));
}

#[test]
fn truncated_eof_and_oversized_frames_are_errors_and_reconnect_cleanly() {
    for invalid in [
        br#"<event uid="unfinished">"#.to_vec(),
        [b"<event uid=\"".as_slice(), vec![b'x'; 512].as_slice()].concat(),
    ] {
        let listener = TcpListener::bind("127.0.0.1:0").expect("listener");
        let address = listener.local_addr().expect("address");
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("first accept");
            stream.write_all(&invalid).expect("invalid write");
            drop(stream);
            let (mut stream, _) = listener.accept().expect("reconnect");
            stream.write_all(FIRST).expect("valid write");
        });
        let mut receiver = TakSocketReceiver::new(&format!("tcp://{address}"))
            .expect("receiver")
            .with_read_timeout(StdDuration::from_millis(50))
            .with_max_bytes(128);
        let invalid = receiver.receive();
        let recovered = receiver.receive();
        server.join().expect("server");
        assert!(
            invalid.is_err(),
            "invalid bytes must not become a partial successful payload"
        );
        assert_eq!(recovered.expect("recovery"), Some(FIRST.to_vec()));
    }
}

#[test]
fn verified_tls_receiver_separates_split_and_coalesced_frames() {
    let identity =
        Identity::from_pkcs8(TEST_TLS_CERT.as_bytes(), TEST_TLS_KEY.as_bytes()).expect("identity");
    let acceptor = native_tls::TlsAcceptor::new(identity).expect("acceptor");
    let listener = TcpListener::bind("127.0.0.1:0").expect("listener");
    let address = listener.local_addr().expect("address");
    let (release, wait) = mpsc::channel();
    let server = thread::spawn(move || {
        let (stream, _) = listener.accept().expect("accept");
        stream
            .set_read_timeout(Some(StdDuration::from_secs(2)))
            .expect("timeout");
        let mut stream = acceptor.accept(stream).expect("verified handshake");
        stream.write_all(&FIRST[..20]).expect("partial");
        wait.recv_timeout(StdDuration::from_secs(3))
            .expect("release");
        stream
            .write_all(&[&FIRST[20..], SECOND].concat())
            .expect("remaining frames");
    });
    let ca = std::env::temp_dir().join(format!("rch-framing-{}.pem", Uuid::new_v4()));
    std::fs::write(&ca, TEST_TLS_CERT).expect("CA");
    let mut receiver = TakSocketReceiver::from_config(&TakConnectionConfig {
        cot_url: format!("tls://{address}"),
        tls_ca: Some(ca.to_string_lossy().to_string()),
        ..TakConnectionConfig::default()
    })
    .expect("receiver")
    .with_read_timeout(StdDuration::from_millis(200));
    let partial = receiver.receive();
    release.send(()).expect("release");
    let first = receiver.receive();
    let second = receiver.receive();
    server.join().expect("server");
    std::fs::remove_file(ca).expect("cleanup");
    assert_eq!(partial.expect("partial timeout"), None);
    assert_eq!(first.expect("first frame"), Some(FIRST.to_vec()));
    assert_eq!(second.expect("second frame"), Some(SECOND.to_vec()));
}

#[test]
fn protobuf_input_is_rejected_with_an_explicit_configuration_error() {
    let mut buffer = vec![TAK_PROTO_MAGIC_BYTE, 1, 0];
    assert!(
        inbound_frames::take_frame(&mut buffer, 64)
            .expect_err("unsupported input")
            .to_string()
            .contains("protobuf")
    );
}
