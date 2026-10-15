#![deny(
    clippy::expect_used,
    clippy::let_underscore_must_use,
    clippy::panic,
    clippy::unwrap_used
)]

use std::path::Path;
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
    if let Err(error) = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(BackendProcess::default())
        .setup(|app| {
            start_backend(app.handle()).map_err(|error| error.to_string())?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, WindowEvent::CloseRequested { .. }) {
                if let Err(error) = stop_backend(window.app_handle()) {
                    eprintln!("failed to stop RCH desktop sidecars cleanly: {error}");
                }
            }
        })
        .run(tauri::generate_context!())
    {
        eprintln!("failed to run RCH desktop: {error}");
        std::process::exit(1);
    }
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
        .args(reticulumd_sidecar_args(&reticulumd_db_path, &zmq_command))
        .spawn()?;
    store_process(
        &app.state::<BackendProcess>().reticulumd,
        reticulumd_child,
        "reticulumd",
    )?;

    if let Err(error) = wait_for_loopback_port(zmq_command_port, Duration::from_secs(10)) {
        if let Err(stop_error) = stop_backend(app) {
            eprintln!("failed to clean up sidecars after reticulumd startup error: {stop_error}");
        }
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

    let server_args = rch_server_sidecar_args(&db_path, &zmq_command, &zmq_response);
    let server = app
        .shell()
        .sidecar("r3akt-rch-server")?
        .args(server_args)
        .spawn();
    let (mut rx, child) = match server {
        Ok(server) => server,
        Err(error) => {
            if let Err(stop_error) = stop_backend(app) {
                eprintln!("failed to clean up reticulumd after server startup error: {stop_error}");
            }
            return Err(error.into());
        }
    };

    if let Err(error) = store_process(&app.state::<BackendProcess>().server, child, "RCH server") {
        if let Err(stop_error) = stop_backend(app) {
            eprintln!("failed to clean up reticulumd after server tracking error: {stop_error}");
        }
        return Err(error);
    }

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

fn reticulumd_sidecar_args(db_path: &Path, zmq_command: &str) -> Vec<String> {
    vec![
        "--db".to_string(),
        db_path.to_string_lossy().to_string(),
        "--zmq-rpc-command".to_string(),
        zmq_command.to_string(),
        "--zmq-durable-broker".to_string(),
        "--rpc".to_string(),
        "127.0.0.1:0".to_string(),
    ]
}

fn rch_server_sidecar_args(db_path: &Path, zmq_command: &str, zmq_response: &str) -> Vec<String> {
    vec![
        "--bind".to_string(),
        "127.0.0.1:8000".to_string(),
        "--db-path".to_string(),
        db_path.to_string_lossy().to_string(),
        "--lxmf-zmq-command".to_string(),
        zmq_command.to_string(),
        "--lxmf-zmq-response".to_string(),
        zmq_response.to_string(),
    ]
}

fn store_process(
    slot: &Mutex<Option<CommandChild>>,
    child: CommandChild,
    label: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let mut process = match slot.lock() {
        Ok(process) => process,
        Err(error) => {
            let cleanup_detail = child.kill().err().map_or_else(String::new, |cleanup| {
                format!("; cleanup failed: {cleanup}")
            });
            return Err(std::io::Error::other(format!(
                "{label} process lock poisoned: {error}{cleanup_detail}"
            ))
            .into());
        }
    };
    if process.is_some() {
        let cleanup_detail = child.kill().err().map_or_else(String::new, |cleanup| {
            format!("; cleanup failed: {cleanup}")
        });
        return Err(std::io::Error::new(
            std::io::ErrorKind::AlreadyExists,
            format!("{label} process is already running{cleanup_detail}"),
        )
        .into());
    }
    *process = Some(child);
    Ok(())
}

fn stop_process(
    slot: &Mutex<Option<CommandChild>>,
    label: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let child = slot
        .lock()
        .map_err(|error| std::io::Error::other(format!("{label} process lock poisoned: {error}")))?
        .take();
    if let Some(child) = child {
        child
            .kill()
            .map_err(|error| std::io::Error::other(format!("failed to stop {label}: {error}")))?;
    }
    Ok(())
}

fn stop_backend(app: &tauri::AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let processes = app.state::<BackendProcess>();
    let server_result = stop_process(&processes.server, "RCH server");
    let reticulumd_result = stop_process(&processes.reticulumd, "reticulumd");
    server_result?;
    reticulumd_result?;
    Ok(())
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

#[cfg(test)]
mod tests {
    use super::{rch_server_sidecar_args, reticulumd_sidecar_args};
    use std::path::Path;

    #[test]
    fn managed_daemon_uses_durable_broker_for_zmq() {
        let args = reticulumd_sidecar_args(Path::new("reticulum.db"), "tcp://127.0.0.1:9100");

        assert_eq!(argument_value(&args, "--db"), Some("reticulum.db"));
        assert_eq!(
            argument_value(&args, "--zmq-rpc-command"),
            Some("tcp://127.0.0.1:9100")
        );
        assert!(args.iter().any(|arg| arg == "--zmq-durable-broker"));
        assert_eq!(argument_value(&args, "--rpc"), Some("127.0.0.1:0"));
        assert!(!args.iter().any(|arg| arg == "--transport"));
        assert!(!args.iter().any(|arg| arg == "--config"));
    }

    #[test]
    fn server_uses_derived_zmq_identity_without_source_assertion() {
        let args = rch_server_sidecar_args(
            Path::new("rch.db"),
            "tcp://127.0.0.1:9100",
            "tcp://127.0.0.1:9101",
        );

        assert_eq!(argument_value(&args, "--bind"), Some("127.0.0.1:8000"));
        assert_eq!(argument_value(&args, "--db-path"), Some("rch.db"));
        assert_eq!(
            argument_value(&args, "--lxmf-zmq-command"),
            Some("tcp://127.0.0.1:9100")
        );
        assert_eq!(
            argument_value(&args, "--lxmf-zmq-response"),
            Some("tcp://127.0.0.1:9101")
        );
        assert!(!args.iter().any(|arg| arg == "--reticulumd-source"));
    }

    fn argument_value<'a>(args: &'a [String], name: &str) -> Option<&'a str> {
        args.windows(2)
            .find(|pair| pair[0] == name)
            .map(|pair| pair[1].as_str())
    }
}
