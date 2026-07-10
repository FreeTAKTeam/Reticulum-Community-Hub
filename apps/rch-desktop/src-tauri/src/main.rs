use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::Manager;
use tauri::WindowEvent;
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::process::CommandEvent;

#[derive(Default)]
struct BackendProcess {
    server: Mutex<Option<CommandChild>>,
    reticulumd: Mutex<Option<CommandChild>>,
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(BackendProcess::default())
        .setup(|app| {
            start_backend(app.handle()).map_err(|error| error.to_string())?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, WindowEvent::CloseRequested { .. }) {
                stop_backend(window.app_handle());
            }
        })
        .run(tauri::generate_context!())
        .expect("failed to run RCH desktop");
}

fn start_backend(app: &tauri::AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let data_dir = app.path().app_data_dir()?;
    std::fs::create_dir_all(&data_dir)?;
    let db_path = data_dir.join("rch_state.sqlite3");
    let reticulumd_db_path = data_dir.join("reticulum.db");
    ensure_loopback_port_available(8000)?;
    let zmq_command_port = unused_loopback_port()?;
    let zmq_response_port = unused_loopback_port()?;
    let zmq_command = format!("tcp://127.0.0.1:{zmq_command_port}");
    let zmq_response = format!("tcp://127.0.0.1:{zmq_response_port}");

    let (mut reticulumd_rx, reticulumd_child) = app
        .shell()
        .sidecar("reticulumd")?
        .args(vec![
            "--db".to_string(),
            reticulumd_db_path.to_string_lossy().to_string(),
            "--zmq-rpc-command".to_string(),
            zmq_command.clone(),
            "--rpc".to_string(),
            "127.0.0.1:0".to_string(),
        ])
        .spawn()?;
    *app.state::<BackendProcess>()
        .reticulumd
        .lock()
        .expect("reticulumd lock") = Some(reticulumd_child);

    if let Err(error) = wait_for_loopback_port(zmq_command_port, Duration::from_secs(10)) {
        stop_backend(app);
        return Err(error.into());
    }

    tauri::async_runtime::spawn(async move {
        while let Some(event) = reticulumd_rx.recv().await {
            match event {
                CommandEvent::Stdout(bytes) => {
                    println!("reticulumd: {}", String::from_utf8_lossy(&bytes).trim_end());
                }
                CommandEvent::Stderr(bytes) => {
                    eprintln!("reticulumd: {}", String::from_utf8_lossy(&bytes).trim_end());
                }
                CommandEvent::Terminated(status) => eprintln!("reticulumd exited: {status:?}"),
                _ => {}
            }
        }
    });

    let args = vec![
        "--bind".to_string(),
        "127.0.0.1:8000".to_string(),
        "--db-path".to_string(),
        db_path.to_string_lossy().to_string(),
        "--api-key".to_string(),
        "local-desktop".to_string(),
        "--lxmf-zmq-command".to_string(),
        zmq_command,
        "--lxmf-zmq-response".to_string(),
        zmq_response,
        "--reticulumd-source".to_string(),
        "rch-desktop".to_string(),
    ];

    let server = app.shell().sidecar("r3akt-rch-server")?.args(args).spawn();
    let (mut rx, child) = match server {
        Ok(server) => server,
        Err(error) => {
            stop_backend(app);
            return Err(error.into());
        }
    };

    *app.state::<BackendProcess>()
        .server
        .lock()
        .expect("backend lock") = Some(child);

    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(bytes) => {
                    println!("rch-server: {}", String::from_utf8_lossy(&bytes).trim_end());
                }
                CommandEvent::Stderr(bytes) => {
                    eprintln!("rch-server: {}", String::from_utf8_lossy(&bytes).trim_end());
                }
                CommandEvent::Terminated(status) => {
                    eprintln!("rch-server exited: {status:?}");
                }
                _ => {}
            }
        }
    });

    Ok(())
}

fn stop_backend(app: &tauri::AppHandle) {
    if let Some(child) = app
        .state::<BackendProcess>()
        .server
        .lock()
        .expect("backend lock")
        .take()
    {
        let _ = child.kill();
    }
    if let Some(child) = app
        .state::<BackendProcess>()
        .reticulumd
        .lock()
        .expect("reticulumd lock")
        .take()
    {
        let _ = child.kill();
    }
}

fn unused_loopback_port() -> std::io::Result<u16> {
    let listener = std::net::TcpListener::bind((std::net::Ipv4Addr::LOCALHOST, 0))?;
    listener.local_addr().map(|address| address.port())
}

fn ensure_loopback_port_available(port: u16) -> std::io::Result<()> {
    std::net::TcpListener::bind((std::net::Ipv4Addr::LOCALHOST, port)).map(|_| ())
}

fn wait_for_loopback_port(port: u16, timeout: Duration) -> std::io::Result<()> {
    let deadline = Instant::now() + timeout;
    loop {
        if std::net::TcpStream::connect((std::net::Ipv4Addr::LOCALHOST, port)).is_ok() {
            return Ok(());
        }
        if Instant::now() >= deadline {
            return Err(std::io::Error::new(
                std::io::ErrorKind::TimedOut,
                format!("reticulumd ZeroMQ command port {port} did not become ready"),
            ));
        }
        std::thread::sleep(Duration::from_millis(50));
    }
}
