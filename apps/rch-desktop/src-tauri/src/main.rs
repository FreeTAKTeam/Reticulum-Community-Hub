use std::sync::Mutex;

use tauri::Manager;
use tauri::WindowEvent;
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::process::CommandEvent;

#[derive(Default)]
struct BackendProcess {
    child: Mutex<Option<CommandChild>>,
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

    let args = vec![
        "--bind".to_string(),
        "127.0.0.1:8000".to_string(),
        "--db-path".to_string(),
        db_path.to_string_lossy().to_string(),
        "--api-key".to_string(),
        "local-desktop".to_string(),
    ];

    let (mut rx, child) = app
        .shell()
        .sidecar("r3akt-rch-server")?
        .args(args)
        .spawn()?;

    *app.state::<BackendProcess>()
        .child
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
        .child
        .lock()
        .expect("backend lock")
        .take()
    {
        let _ = child.kill();
    }
}
