use std::io::{Read, Write};

use uuid::Uuid;

#[test]
#[cfg(unix)]
fn failed_stop_does_not_signal_process_from_saved_pid() {
    let mut unrelated = std::process::Command::new("cat")
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .spawn()
        .expect("unrelated process");
    let data_dir = std::env::temp_dir().join(format!("r3akt-rch-stop-{}", Uuid::new_v4()));
    let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("listener");
    let port = listener.local_addr().expect("local addr").port();
    super::write_state(
        &data_dir,
        &super::ControlState {
            pid: unrelated.id(),
            port,
            data_dir: data_dir.to_string_lossy().to_string(),
            log_level: "info".to_string(),
            started_at: "2026-01-23T00:00:00Z".to_string(),
        },
    )
    .expect("write stale state");
    let handle = std::thread::spawn(move || {
        let (mut stream, _) = listener.accept().expect("accept");
        let mut buffer = [0_u8; 2048];
        let size = stream.read(&mut buffer).expect("request");
        assert!(String::from_utf8_lossy(&buffer[..size]).starts_with("POST /Control/Stop "));
        stream
            .write_all(
                b"HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
            )
            .expect("deny stop");
    });
    let args = super::ControlArgs {
        data_dir: Some(data_dir.to_string_lossy().to_string()),
        port: None,
    };

    let rejected_stop = super::stop_command(&args);
    handle.join().expect("server thread");
    let unreachable_stop = super::stop_command(&args);
    let mut echoed = [0_u8; 6];
    let alive = unrelated
        .stdin
        .as_mut()
        .expect("child stdin")
        .write_all(b"alive\n")
        .and_then(|()| {
            unrelated
                .stdout
                .as_mut()
                .expect("child stdout")
                .read_exact(&mut echoed)
        });
    if unrelated.try_wait().expect("process state").is_none() {
        unrelated.kill().expect("clean up child");
    }
    unrelated.wait().expect("reap child");
    std::fs::remove_dir_all(data_dir).expect("cleanup");

    assert_eq!(rejected_stop, 1);
    assert_eq!(unreachable_stop, 1);
    alive.expect("saved PID must not be signalled after a failed stop request");
    assert_eq!(&echoed, b"alive\n");
}
