#![allow(clippy::float_cmp, clippy::single_match_else)]

use std::env;
use std::fs;
use std::future::Future;
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::Duration as StdDuration;

const DEFAULT_HOST: &str = "127.0.0.1";
const DEFAULT_PORT: u16 = 8000;
const DEFAULT_MANAGED_RETICULUMD_TRANSPORT: &str = "127.0.0.1:0";
const DEFAULT_STORAGE_PATH: &str = "RTH_Store";
const DEFAULT_LOG_LEVEL_NAME: &str = "debug";
const STATE_FILENAME: &str = "rch_state.json";
const LOG_FILENAME: &str = "rch.log";
const RUST_STATE_DB_FILENAME: &str = "rch_state.sqlite3";

#[derive(Debug)]
struct ServerArgs {
    bind: SocketAddr,
    db_path: Option<PathBuf>,
    config_path: Option<PathBuf>,
    reticulum_config_path: Option<PathBuf>,
    reticulumd_rpc: Option<String>,
    reticulumd_source: Option<String>,
    reticulumd_exe: Option<PathBuf>,
    reticulumd_db_path: Option<PathBuf>,
    reticulumd_transport: Option<String>,
    ui_dist_path: Option<PathBuf>,
    api_key: Option<String>,
    system_status_fanout_mode: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ControlState {
    pid: u32,
    port: u16,
    data_dir: String,
    log_level: String,
    started_at: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
struct ControlArgs {
    data_dir: Option<String>,
    port: Option<u16>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct StartArgs {
    control: ControlArgs,
    log_level: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct GatewayArgs {
    data_dir: Option<String>,
    port: Option<u16>,
    api_host: String,
    log_level: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum CliCommand {
    Start(StartArgs),
    Stop(ControlArgs),
    Status(ControlArgs),
    Gateway(GatewayArgs),
}

#[derive(Debug)]
struct ManagedReticulumdLaunch {
    exe: Option<PathBuf>,
    rpc: Option<String>,
    db_path: Option<PathBuf>,
    config_path: Option<PathBuf>,
    transport: Option<String>,
}

impl ManagedReticulumdLaunch {
    fn from_args(args: &ServerArgs) -> Self {
        Self {
            exe: args.reticulumd_exe.clone(),
            rpc: args.reticulumd_rpc.clone(),
            db_path: args.reticulumd_db_path.clone(),
            config_path: args.reticulum_config_path.clone(),
            transport: args.reticulumd_transport.clone().or_else(|| {
                args.reticulumd_exe
                    .is_some()
                    .then(|| DEFAULT_MANAGED_RETICULUMD_TRANSPORT.to_string())
            }),
        }
    }
}

#[tokio::main]
async fn main() {
    if let Err(error) = run().await {
        eprintln!("{error}");
        std::process::exit(1);
    }
}

async fn run() -> Result<(), Box<dyn std::error::Error>> {
    let raw_args: Vec<String> = env::args().skip(1).collect();
    if let Some(command) = parse_cli_args(raw_args.clone())? {
        match command {
            CliCommand::Gateway(args) => {
                return run_server(gateway_args_to_server_args(&args)?).await;
            }
            CliCommand::Start(args) => {
                let code = start_command(&args)?;
                if code != 0 {
                    std::process::exit(code);
                }
                return Ok(());
            }
            CliCommand::Stop(args) => {
                let code = stop_command(&args);
                if code != 0 {
                    std::process::exit(code);
                }
                return Ok(());
            }
            CliCommand::Status(args) => {
                let code = status_command(&args);
                if code != 0 {
                    std::process::exit(code);
                }
                return Ok(());
            }
        }
    }
    let args = parse_args(raw_args)?;
    run_server(args).await
}

async fn run_server(args: ServerArgs) -> Result<(), Box<dyn std::error::Error>> {
    run_server_with_shutdown(args, wait_for_shutdown_signal()).await
}

async fn run_server_with_shutdown<S>(
    args: ServerArgs,
    shutdown_signal: S,
) -> Result<(), Box<dyn std::error::Error>>
where
    S: Future<Output = ()> + Send + 'static,
{
    let listener = tokio::net::TcpListener::bind(args.bind).await?;
    let managed_reticulumd_launch = ManagedReticulumdLaunch::from_args(&args);
    let ui_dist_path = args.ui_dist_path.clone().or_else(env_ui_dist_path);
    let state = build_runtime_state(&args, &managed_reticulumd_launch)?;
    state.start_managed_reticulumd()?;
    let app = create_app_for_runtime(state.clone(), ui_dist_path.as_ref());
    let outbound_worker = r3akt_rch_server::spawn_outbound_delivery_worker(state.clone());
    let inbound_worker = r3akt_rch_server::spawn_reticulumd_inbound_worker(state.clone());
    println!("r3akt-rch-server listening on http://{}", args.bind);
    let serve_result = axum::serve(
        listener,
        app.into_make_service_with_connect_info::<SocketAddr>(),
    )
    .with_graceful_shutdown(shutdown_signal)
    .await;
    if let Err(error) = r3akt_rch_server::shutdown_runtime_for_exit(&state) {
        eprintln!("r3akt-rch-server shutdown warning: {error}");
    }
    outbound_worker.abort();
    let _ = outbound_worker.await;
    inbound_worker.abort();
    let _ = inbound_worker.await;
    serve_result?;
    Ok(())
}

fn build_runtime_state(
    args: &ServerArgs,
    managed_reticulumd_launch: &ManagedReticulumdLaunch,
) -> Result<r3akt_rch_server::AppState, Box<dyn std::error::Error>> {
    let api_key = args
        .api_key
        .clone()
        .or_else(r3akt_rch_server::AppState::env_api_key);
    let system_status_fanout_mode = args
        .system_status_fanout_mode
        .clone()
        .or_else(r3akt_rch_server::AppState::env_system_status_fanout_mode);
    let mut state = match args.db_path {
        Some(ref path) => {
            println!("r3akt-rch-server using SQLite state at {}", path.display());
            let mut state = r3akt_rch_server::AppState::from_sqlite_path(path)?
                .with_optional_api_key(api_key)
                .with_optional_system_status_fanout_mode(system_status_fanout_mode);
            if let Some(path) = &args.config_path {
                state = state.with_config_path(path);
            }
            if let Some(path) = &args.reticulum_config_path {
                state = state.with_reticulum_config_path(path);
            }
            if let Some(endpoint) = &args.reticulumd_rpc {
                let source = args
                    .reticulumd_source
                    .as_deref()
                    .ok_or("--reticulumd-source is required with --reticulumd-rpc")?;
                state = state.with_reticulumd_rpc(endpoint.as_str(), source);
            }
            state
        }
        None => {
            let mut state = r3akt_rch_server::AppState::default()
                .with_optional_api_key(api_key)
                .with_optional_system_status_fanout_mode(system_status_fanout_mode);
            if let Some(path) = &args.config_path {
                state = state.with_config_path(path);
            }
            if let Some(path) = &args.reticulum_config_path {
                state = state.with_reticulum_config_path(path);
            }
            if let Some(endpoint) = &args.reticulumd_rpc {
                let source = args
                    .reticulumd_source
                    .as_deref()
                    .ok_or("--reticulumd-source is required with --reticulumd-rpc")?;
                state = state.with_reticulumd_rpc(endpoint.as_str(), source);
            }
            state
        }
    };
    if let Some(endpoint) = managed_reticulumd_launch.rpc.clone() {
        if let Some(exe) = managed_reticulumd_launch.exe.as_ref() {
            state = state
                .with_managed_reticulumd(
                    exe,
                    endpoint,
                    managed_reticulumd_launch
                        .db_path
                        .as_ref()
                        .map(|path| path.to_string_lossy().to_string()),
                    managed_reticulumd_launch.config_path.as_ref(),
                )
                .with_managed_reticulumd_transport(managed_reticulumd_launch.transport.clone());
        }
    }
    Ok(state)
}

async fn wait_for_shutdown_signal() {
    if let Err(error) = tokio::signal::ctrl_c().await {
        eprintln!("failed to install Ctrl-C shutdown handler: {error}");
        std::future::pending::<()>().await;
    }
}

fn env_ui_dist_path() -> Option<PathBuf> {
    env::var_os("R3AKT_UI_DIST_PATH").map(PathBuf::from)
}

fn state_path(data_dir: &Path) -> PathBuf {
    data_dir.join(STATE_FILENAME)
}

fn rust_state_db_path(data_dir: &Path) -> PathBuf {
    data_dir.join(RUST_STATE_DB_FILENAME)
}

fn home_dir() -> Option<PathBuf> {
    env::var_os("HOME")
        .or_else(|| env::var_os("USERPROFILE"))
        .map(PathBuf::from)
}

fn expand_user_path(value: impl AsRef<str>) -> PathBuf {
    let home = home_dir();
    expand_user_path_with_home(value, home.as_deref())
}

fn expand_user_path_with_home(value: impl AsRef<str>, home: Option<&Path>) -> PathBuf {
    let value = value.as_ref();
    if let Some(tail) = value.strip_prefix('~') {
        if let Some(home) = home {
            let tail = tail.trim_start_matches(['/', '\\']);
            return home.join(tail);
        }
    }
    PathBuf::from(value)
}

fn resolve_data_dir(data_dir: Option<&str>) -> PathBuf {
    data_dir
        .map(expand_user_path)
        .or_else(|| env::var("RTH_STORAGE_DIR").ok().map(expand_user_path))
        .unwrap_or_else(|| expand_user_path(DEFAULT_STORAGE_PATH))
}

fn resolve_api_key() -> Option<String> {
    r3akt_rch_server::AppState::env_api_key()
}

fn load_state(data_dir: &Path) -> Option<ControlState> {
    let content = fs::read_to_string(state_path(data_dir)).ok()?;
    let payload: serde_json::Value = serde_json::from_str(&content).ok()?;
    let pid = payload
        .get("pid")
        .and_then(serde_json::Value::as_u64)
        .and_then(|value| u32::try_from(value).ok())?;
    let port = payload
        .get("port")
        .and_then(serde_json::Value::as_u64)
        .and_then(|value| u16::try_from(value).ok())?;
    let data_dir_value = payload
        .get("data_dir")
        .and_then(serde_json::Value::as_str)
        .filter(|value| !value.is_empty())
        .map_or_else(|| data_dir.to_string_lossy().to_string(), ToOwned::to_owned);
    let log_level = payload
        .get("log_level")
        .and_then(serde_json::Value::as_str)
        .filter(|value| !value.is_empty())
        .unwrap_or(DEFAULT_LOG_LEVEL_NAME)
        .to_string();
    let started_at = payload
        .get("started_at")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default()
        .to_string();
    Some(ControlState {
        pid,
        port,
        data_dir: data_dir_value,
        log_level,
        started_at,
    })
}

fn write_state(data_dir: &Path, state: &ControlState) -> Result<(), Box<dyn std::error::Error>> {
    fs::create_dir_all(data_dir)?;
    let payload = serde_json::json!({
        "pid": state.pid,
        "port": state.port,
        "data_dir": state.data_dir,
        "log_level": state.log_level,
        "started_at": state.started_at
    });
    fs::write(
        state_path(data_dir),
        serde_json::to_string_pretty(&payload)?,
    )?;
    Ok(())
}

fn build_gateway_command(
    executable: &Path,
    data_dir: &Path,
    port: u16,
    log_level: Option<&str>,
) -> Vec<String> {
    let mut command = vec![
        executable.to_string_lossy().to_string(),
        "gateway".to_string(),
        "--data-dir".to_string(),
        data_dir.to_string_lossy().to_string(),
        "--port".to_string(),
        port.to_string(),
        "--api-host".to_string(),
        DEFAULT_HOST.to_string(),
    ];
    if let Some(log_level) = log_level {
        command.extend(["--log-level".to_string(), log_level.to_string()]);
    }
    command
}

fn spawn_gateway_process(
    command: &[String],
    log_path: &Path,
) -> Result<Child, Box<dyn std::error::Error>> {
    if command.is_empty() {
        return Err("gateway command is empty".into());
    }
    if let Some(parent) = log_path.parent() {
        fs::create_dir_all(parent)?;
    }
    let stdout = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_path)?;
    let stderr = stdout.try_clone()?;
    let mut process = Command::new(&command[0]);
    process
        .args(&command[1..])
        .stdin(Stdio::null())
        .stdout(stdout)
        .stderr(stderr);
    configure_detached_process(&mut process);
    Ok(process.spawn()?)
}

#[cfg(windows)]
fn configure_detached_process(command: &mut Command) {
    use std::os::windows::process::CommandExt;

    const CREATE_NEW_PROCESS_GROUP: u32 = 0x0000_0200;
    const DETACHED_PROCESS: u32 = 0x0000_0008;
    command.creation_flags(CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS);
}

#[cfg(not(windows))]
fn configure_detached_process(_command: &mut Command) {}

fn current_timestamp_rfc3339() -> String {
    time::OffsetDateTime::now_utc()
        .format(&time::format_description::well_known::Rfc3339)
        .unwrap_or_else(|_| time::OffsetDateTime::now_utc().unix_timestamp().to_string())
}

fn control_port(args: &ControlArgs, state: Option<&ControlState>) -> u16 {
    args.port
        .or_else(|| state.map(|state| state.port))
        .unwrap_or(DEFAULT_PORT)
}

fn is_api_port_available(host: &str, port: u16) -> bool {
    let Ok(address) = format!("{host}:{port}").parse::<SocketAddr>() else {
        return false;
    };
    TcpListener::bind(address).is_ok()
}

fn start_command(args: &StartArgs) -> Result<i32, Box<dyn std::error::Error>> {
    let data_dir = resolve_data_dir(args.control.data_dir.as_deref());
    let state = load_state(&data_dir);
    let port = control_port(&args.control, state.as_ref());
    let client = ControlClient::new(port, resolve_api_key());
    if state.is_some() && client.status().is_some() {
        println!("RCH already running on port {port}.");
        return Ok(0);
    }
    if !is_api_port_available(DEFAULT_HOST, port) {
        eprintln!("RCH API port {port} is already in use.");
        return Ok(1);
    }

    let executable = env::current_exe()?;
    let command = build_gateway_command(&executable, &data_dir, port, args.log_level.as_deref());
    let child = spawn_gateway_process(&command, &data_dir.join(LOG_FILENAME))?;
    let log_level = args
        .log_level
        .clone()
        .unwrap_or_else(|| DEFAULT_LOG_LEVEL_NAME.to_string());
    write_state(
        &data_dir,
        &ControlState {
            pid: child.id(),
            port,
            data_dir: data_dir.to_string_lossy().to_string(),
            log_level,
            started_at: current_timestamp_rfc3339(),
        },
    )?;
    println!("RCH started (pid={}) on port {port}.", child.id());
    Ok(0)
}

fn stop_command(args: &ControlArgs) -> i32 {
    let data_dir = resolve_data_dir(args.data_dir.as_deref());
    let state = load_state(&data_dir);
    let port = control_port(args, state.as_ref());
    let client = ControlClient::new(port, resolve_api_key());
    if client.stop() {
        println!("RCH stop requested.");
        return 0;
    }
    if let Some(state) = state {
        if stop_with_signal(state.pid) {
            println!("RCH stop signal sent.");
            return 0;
        }
    }
    println!("RCH is not running.");
    1
}

fn status_command(args: &ControlArgs) -> i32 {
    let data_dir = resolve_data_dir(args.data_dir.as_deref());
    let state = load_state(&data_dir);
    let port = control_port(args, state.as_ref());
    let client = ControlClient::new(port, resolve_api_key());
    let Some(payload) = client.status() else {
        println!("RCH is not running.");
        return 1;
    };
    let status = payload
        .get("status")
        .and_then(serde_json::Value::as_str)
        .unwrap_or("running");
    let pid = payload
        .get("pid")
        .map_or_else(|| "null".to_string(), serde_json::Value::to_string);
    println!("RCH status: {status} (pid={pid}, port={port})");
    0
}

fn stop_with_signal(pid: u32) -> bool {
    #[cfg(windows)]
    let status = Command::new("taskkill")
        .args(["/PID", &pid.to_string(), "/T"])
        .status();
    #[cfg(not(windows))]
    let status = Command::new("kill")
        .args(["-TERM", &pid.to_string()])
        .status();
    status.is_ok_and(|status| status.success())
}

struct ControlClient {
    port: u16,
    api_key: Option<String>,
    timeout: StdDuration,
}

struct ControlResponse {
    status_code: u16,
    body: String,
}

impl ControlClient {
    fn new(port: u16, api_key: Option<String>) -> Self {
        Self {
            port,
            api_key,
            timeout: StdDuration::from_secs(2),
        }
    }

    fn status(&self) -> Option<serde_json::Value> {
        let response = self.request("GET", "/Control/Status")?;
        if response.status_code != 200 {
            return None;
        }
        serde_json::from_str(&response.body).ok()
    }

    fn stop(&self) -> bool {
        self.request("POST", "/Control/Stop")
            .is_some_and(|response| response.status_code == 200)
    }

    fn request(&self, method: &str, path: &str) -> Option<ControlResponse> {
        let address = format!("{DEFAULT_HOST}:{}", self.port).parse().ok()?;
        let mut stream = TcpStream::connect_timeout(&address, self.timeout).ok()?;
        let _ = stream.set_read_timeout(Some(self.timeout));
        let _ = stream.set_write_timeout(Some(self.timeout));
        let api_key_header = self
            .api_key
            .as_deref()
            .map(|api_key| format!("X-API-Key: {api_key}\r\n"))
            .unwrap_or_default();
        let request = format!(
            "{method} {path} HTTP/1.1\r\nHost: {DEFAULT_HOST}:{}\r\n{api_key_header}Connection: close\r\nContent-Length: 0\r\n\r\n",
            self.port
        );
        stream.write_all(request.as_bytes()).ok()?;
        let mut response = String::new();
        stream.read_to_string(&mut response).ok()?;
        parse_http_response(&response)
    }
}

fn parse_http_response(response: &str) -> Option<ControlResponse> {
    let (head, body) = response.split_once("\r\n\r\n")?;
    let status_code = head
        .lines()
        .next()?
        .split_whitespace()
        .nth(1)?
        .parse::<u16>()
        .ok()?;
    Some(ControlResponse {
        status_code,
        body: body.to_string(),
    })
}

fn create_app_for_runtime(
    state: r3akt_rch_server::AppState,
    ui_dist_path: Option<&PathBuf>,
) -> axum::Router {
    if let Some(path) = ui_dist_path {
        println!("r3akt-rch-server serving UI bundle from {}", path.display());
        r3akt_rch_server::create_app_with_state_and_ui_dist_path(state, path.clone())
    } else {
        r3akt_rch_server::create_app_with_state(state)
    }
}

fn gateway_args_to_server_args(
    args: &GatewayArgs,
) -> Result<ServerArgs, Box<dyn std::error::Error>> {
    let data_dir = resolve_data_dir(args.data_dir.as_deref());
    let _accepted_log_level = args.log_level.as_deref();
    let bind: SocketAddr = format!("{}:{}", args.api_host, args.port.unwrap_or(DEFAULT_PORT))
        .parse()
        .map_err(|error| format!("invalid gateway bind address: {error}"))?;
    Ok(ServerArgs {
        bind,
        db_path: Some(rust_state_db_path(&data_dir)),
        config_path: None,
        reticulum_config_path: None,
        reticulumd_rpc: None,
        reticulumd_source: None,
        reticulumd_exe: None,
        reticulumd_db_path: None,
        reticulumd_transport: None,
        ui_dist_path: None,
        api_key: None,
        system_status_fanout_mode: None,
    })
}

fn parse_cli_args<I, S>(args: I) -> Result<Option<CliCommand>, Box<dyn std::error::Error>>
where
    I: IntoIterator<Item = S>,
    S: Into<String>,
{
    let args: Vec<String> = args.into_iter().map(Into::into).collect();
    let mut index = 0;
    let mut control = ControlArgs::default();
    while index < args.len() {
        match args[index].as_str() {
            "--data-dir" => {
                index += 1;
                control.data_dir = Some(required_arg(&args, index, "--data-dir")?.to_string());
                index += 1;
            }
            "--port" => {
                index += 1;
                control.port = Some(parse_port(required_arg(&args, index, "--port")?)?);
                index += 1;
            }
            "start" => {
                let (control, log_level) = parse_start_tail(control, &args[index + 1..])?;
                return Ok(Some(CliCommand::Start(StartArgs { control, log_level })));
            }
            "stop" => {
                let control = parse_control_tail(control, &args[index + 1..])?;
                return Ok(Some(CliCommand::Stop(control)));
            }
            "status" => {
                let control = parse_control_tail(control, &args[index + 1..])?;
                return Ok(Some(CliCommand::Status(control)));
            }
            "gateway" => {
                return Ok(Some(CliCommand::Gateway(parse_gateway_tail(
                    control,
                    &args[index + 1..],
                )?)));
            }
            "-m" => {
                index += 1;
                let module = required_arg(&args, index, "-m")?;
                index += 1;
                if module == "reticulum_telemetry_hub.northbound.gateway" {
                    return Ok(Some(CliCommand::Gateway(parse_gateway_tail(
                        control,
                        &args[index..],
                    )?)));
                }
                return Ok(None);
            }
            _ => return Ok(None),
        }
    }
    Ok(None)
}

fn parse_control_tail(
    mut control: ControlArgs,
    args: &[String],
) -> Result<ControlArgs, Box<dyn std::error::Error>> {
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--data-dir" => {
                index += 1;
                control.data_dir = Some(required_arg(args, index, "--data-dir")?.to_string());
                index += 1;
            }
            "--port" => {
                index += 1;
                control.port = Some(parse_port(required_arg(args, index, "--port")?)?);
                index += 1;
            }
            other => return Err(format!("unsupported argument {other}").into()),
        }
    }
    Ok(control)
}

fn parse_start_tail(
    control: ControlArgs,
    args: &[String],
) -> Result<(ControlArgs, Option<String>), Box<dyn std::error::Error>> {
    let mut control = control;
    let mut log_level = None;
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--data-dir" => {
                index += 1;
                control.data_dir = Some(required_arg(args, index, "--data-dir")?.to_string());
                index += 1;
            }
            "--port" => {
                index += 1;
                control.port = Some(parse_port(required_arg(args, index, "--port")?)?);
                index += 1;
            }
            "--log-level" => {
                index += 1;
                log_level = Some(parse_log_level(required_arg(args, index, "--log-level")?)?);
                index += 1;
            }
            other => return Err(format!("unsupported argument {other}").into()),
        }
    }
    Ok((control, log_level))
}

fn parse_gateway_tail(
    control: ControlArgs,
    args: &[String],
) -> Result<GatewayArgs, Box<dyn std::error::Error>> {
    let mut data_dir = control.data_dir;
    let mut port = control.port;
    let mut api_host = DEFAULT_HOST.to_string();
    let mut log_level = None;
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--data-dir" => {
                index += 1;
                data_dir = Some(required_arg(args, index, "--data-dir")?.to_string());
                index += 1;
            }
            "--port" => {
                index += 1;
                port = Some(parse_port(required_arg(args, index, "--port")?)?);
                index += 1;
            }
            "--api-host" => {
                index += 1;
                api_host = required_arg(args, index, "--api-host")?.to_string();
                index += 1;
            }
            "--log-level" => {
                index += 1;
                log_level = Some(parse_log_level(required_arg(args, index, "--log-level")?)?);
                index += 1;
            }
            other => return Err(format!("unsupported argument {other}").into()),
        }
    }
    Ok(GatewayArgs {
        data_dir,
        port,
        api_host,
        log_level,
    })
}

fn required_arg<'a>(
    args: &'a [String],
    index: usize,
    flag: &str,
) -> Result<&'a str, Box<dyn std::error::Error>> {
    args.get(index)
        .map(String::as_str)
        .ok_or_else(|| format!("{flag} requires a value").into())
}

fn parse_port(value: &str) -> Result<u16, Box<dyn std::error::Error>> {
    Ok(value.parse::<u16>()?)
}

fn parse_log_level(value: &str) -> Result<String, Box<dyn std::error::Error>> {
    match value {
        "error" | "warning" | "info" | "debug" => Ok(value.to_string()),
        other => Err(format!("invalid log level {other}").into()),
    }
}

fn parse_args<I, S>(args: I) -> Result<ServerArgs, Box<dyn std::error::Error>>
where
    I: IntoIterator<Item = S>,
    S: Into<String>,
{
    let mut args = args.into_iter().map(Into::into);
    let mut bind = "127.0.0.1:8080".to_string();
    let mut db_path = None;
    let mut config_path = None;
    let mut reticulum_config_path = None;
    let mut reticulumd_rpc = None;
    let mut reticulumd_source = None;
    let mut reticulumd_exe = None;
    let mut reticulumd_db_path = None;
    let mut reticulumd_transport = None;
    let mut ui_dist_path = None;
    let mut api_key = None;
    let mut system_status_fanout_mode = None;
    while let Some(arg) = args.next() {
        match (arg.as_str(), args.next()) {
            ("--bind", Some(value)) => bind = value,
            ("--db-path", Some(value)) => db_path = Some(PathBuf::from(value)),
            ("--config-path", Some(value)) => config_path = Some(PathBuf::from(value)),
            ("--reticulum-config-path", Some(value)) => {
                reticulum_config_path = Some(PathBuf::from(value));
            }
            ("--reticulumd-rpc", Some(value)) => reticulumd_rpc = Some(value),
            ("--reticulumd-source", Some(value)) => reticulumd_source = Some(value),
            ("--reticulumd-exe", Some(value)) => reticulumd_exe = Some(PathBuf::from(value)),
            ("--reticulumd-db-path", Some(value)) => {
                reticulumd_db_path = Some(PathBuf::from(value));
            }
            ("--reticulumd-transport", Some(value)) => reticulumd_transport = Some(value),
            ("--ui-dist-path", Some(value)) => ui_dist_path = Some(PathBuf::from(value)),
            ("--api-key", Some(value)) => api_key = Some(value),
            ("--system-status-fanout-mode", Some(value)) => system_status_fanout_mode = Some(value),
            _ => return Err(format!("unsupported argument {arg}").into()),
        }
    }
    if reticulumd_rpc.is_some() && reticulumd_source.is_none() {
        return Err("--reticulumd-source is required with --reticulumd-rpc".into());
    }
    if reticulumd_source.is_some() && reticulumd_rpc.is_none() {
        return Err("--reticulumd-rpc is required with --reticulumd-source".into());
    }
    if reticulumd_exe.is_some() && reticulumd_rpc.is_none() {
        return Err("--reticulumd-rpc is required with --reticulumd-exe".into());
    }
    if reticulumd_db_path.is_some() && reticulumd_exe.is_none() {
        return Err("--reticulumd-db-path is only valid with --reticulumd-exe".into());
    }
    if reticulumd_transport.is_some() && reticulumd_exe.is_none() {
        return Err("--reticulumd-transport is only valid with --reticulumd-exe".into());
    }
    Ok(ServerArgs {
        bind: bind.parse()?,
        db_path,
        config_path,
        reticulum_config_path,
        reticulumd_rpc,
        reticulumd_source,
        reticulumd_exe,
        reticulumd_db_path,
        reticulumd_transport,
        ui_dist_path,
        api_key,
        system_status_fanout_mode,
    })
}

#[cfg(test)]
mod tests {
    use std::io::{Read, Write};

    use uuid::Uuid;

    #[test]
    fn write_and_load_control_state_round_trip() {
        let data_dir = std::env::temp_dir().join(format!("r3akt-rch-cli-{}", Uuid::new_v4()));
        let state = super::ControlState {
            pid: 1234,
            port: 8001,
            data_dir: data_dir.to_string_lossy().to_string(),
            log_level: "info".to_string(),
            started_at: "2026-01-23T00:00:00+00:00".to_string(),
        };

        super::write_state(&data_dir, &state).expect("write state");
        let loaded = super::load_state(&data_dir).expect("load state");

        assert_eq!(loaded, state);
        std::fs::remove_dir_all(data_dir).expect("cleanup");
    }

    #[test]
    fn load_control_state_invalid_payload_returns_none() {
        let data_dir = std::env::temp_dir().join(format!("r3akt-rch-cli-{}", Uuid::new_v4()));
        std::fs::create_dir_all(&data_dir).expect("data dir");
        std::fs::write(super::state_path(&data_dir), "{not json").expect("state");

        assert!(super::load_state(&data_dir).is_none());
        std::fs::remove_dir_all(data_dir).expect("cleanup");
    }

    #[test]
    fn build_gateway_command_matches_python_cli_shape() {
        let command = super::build_gateway_command(
            std::path::Path::new("rch-backend.exe"),
            std::path::Path::new("RTH_Store"),
            8124,
            Some("info"),
        );

        assert_eq!(command[0], "rch-backend.exe");
        assert!(command.contains(&"gateway".to_string()));
        assert!(command.contains(&"--data-dir".to_string()));
        assert!(command.contains(&"RTH_Store".to_string()));
        assert!(command.contains(&"--port".to_string()));
        assert!(command.contains(&"8124".to_string()));
        assert!(command.contains(&"--api-host".to_string()));
        assert!(command.contains(&super::DEFAULT_HOST.to_string()));
        assert!(command.contains(&"--log-level".to_string()));
        assert!(command.contains(&"info".to_string()));
    }

    #[test]
    fn expand_user_path_matches_python_config_manager_home_resolution() {
        let home = std::path::Path::new("C:\\Users\\Field");

        assert_eq!(
            super::expand_user_path_with_home("~/rth_store", Some(home)),
            home.join("rth_store")
        );
        assert_eq!(
            super::expand_user_path_with_home("C:\\RCH", Some(home)),
            std::path::PathBuf::from("C:\\RCH")
        );
    }

    #[test]
    fn parse_cli_start_args_match_python_ordering() {
        let command = super::parse_cli_args([
            "--data-dir",
            "RTH_Store",
            "--port",
            "8123",
            "start",
            "--log-level",
            "debug",
        ])
        .expect("parse")
        .expect("cli command");

        match command {
            super::CliCommand::Start(args) => {
                assert_eq!(args.control.data_dir.as_deref(), Some("RTH_Store"));
                assert_eq!(args.control.port, Some(8123));
                assert_eq!(args.log_level.as_deref(), Some("debug"));
            }
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parse_cli_gateway_args_convert_to_server_bind_and_db_path() {
        let data_dir = std::env::temp_dir().join(format!("r3akt-rch-cli-{}", Uuid::new_v4()));
        let command = super::parse_cli_args([
            "gateway",
            "--data-dir",
            data_dir.to_str().expect("data dir"),
            "--port",
            "8125",
            "--api-host",
            "127.0.0.1",
        ])
        .expect("parse")
        .expect("cli command");

        match command {
            super::CliCommand::Gateway(args) => {
                let server_args = super::gateway_args_to_server_args(&args).expect("server args");
                assert_eq!(server_args.bind.to_string(), "127.0.0.1:8125");
                assert_eq!(
                    server_args.db_path.as_deref(),
                    Some(super::rust_state_db_path(&data_dir).as_path())
                );
            }
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parse_cli_normalizes_python_module_gateway_invocation() {
        let command = super::parse_cli_args([
            "-m",
            "reticulum_telemetry_hub.northbound.gateway",
            "--data-dir",
            "RCH_Store",
            "--port",
            "8123",
            "--log-level",
            "info",
        ])
        .expect("parse")
        .expect("cli command");

        match command {
            super::CliCommand::Gateway(args) => {
                assert_eq!(args.data_dir.as_deref(), Some("RCH_Store"));
                assert_eq!(args.port, Some(8123));
                assert_eq!(args.log_level.as_deref(), Some("info"));
            }
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[tokio::test]
    async fn gateway_server_boots_runtime_and_shuts_down_like_python_main() {
        let data_dir = std::env::temp_dir().join(format!("r3akt-rch-gateway-{}", Uuid::new_v4()));
        std::fs::create_dir_all(&data_dir).expect("data dir");
        let db_path = data_dir.join(super::RUST_STATE_DB_FILENAME);
        let args = super::ServerArgs {
            bind: "127.0.0.1:0".parse().expect("bind"),
            db_path: Some(db_path.clone()),
            config_path: None,
            reticulum_config_path: None,
            reticulumd_rpc: None,
            reticulumd_source: None,
            reticulumd_exe: None,
            reticulumd_db_path: None,
            reticulumd_transport: None,
            ui_dist_path: None,
            api_key: Some("secret".to_string()),
            system_status_fanout_mode: None,
        };

        super::run_server_with_shutdown(args, async {
            tokio::time::sleep(std::time::Duration::from_millis(10)).await;
        })
        .await
        .expect("gateway server boot");

        assert!(db_path.exists());
        std::fs::remove_dir_all(data_dir).expect("cleanup");
    }

    #[test]
    fn parse_cli_ignores_existing_server_args() {
        assert!(
            super::parse_cli_args(["--bind", "127.0.0.1:9000"])
                .expect("parse")
                .is_none()
        );
    }

    #[test]
    fn control_port_prefers_args_then_state_then_default() {
        let state = super::ControlState {
            pid: 1,
            port: 9001,
            data_dir: "RTH_Store".to_string(),
            log_level: "debug".to_string(),
            started_at: String::new(),
        };

        assert_eq!(
            super::control_port(
                &super::ControlArgs {
                    data_dir: None,
                    port: Some(9002)
                },
                Some(&state)
            ),
            9002
        );
        assert_eq!(
            super::control_port(
                &super::ControlArgs {
                    data_dir: None,
                    port: None
                },
                Some(&state)
            ),
            9001
        );
        assert_eq!(
            super::control_port(
                &super::ControlArgs {
                    data_dir: None,
                    port: None
                },
                None
            ),
            super::DEFAULT_PORT
        );
    }

    #[test]
    fn api_port_availability_reports_busy_port_like_python_gateway() {
        let listener = std::net::TcpListener::bind((super::DEFAULT_HOST, 0)).expect("listener");
        let port = listener.local_addr().expect("local addr").port();

        assert!(!super::is_api_port_available(super::DEFAULT_HOST, port));

        drop(listener);
        assert!(super::is_api_port_available(super::DEFAULT_HOST, port));
    }

    #[test]
    fn control_client_status_success_sends_api_key() {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("listener");
        let port = listener.local_addr().expect("local addr").port();
        let handle = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("accept");
            let mut buffer = [0_u8; 2048];
            let size = stream.read(&mut buffer).expect("read request");
            let request = String::from_utf8_lossy(&buffer[..size]);
            assert!(request.starts_with("GET /Control/Status HTTP/1.1"));
            assert!(request.contains("X-API-Key: secret"));
            let body = r#"{"status":"running","pid":1234}"#;
            write!(
                stream,
                "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                body.len(),
                body
            )
            .expect("write response");
        });

        let payload = super::ControlClient::new(port, Some("secret".to_string()))
            .status()
            .expect("status payload");

        assert_eq!(payload["status"], "running");
        assert_eq!(payload["pid"], 1234);
        handle.join().expect("server thread");
    }

    #[test]
    fn parse_args_accepts_bind_and_db_path() {
        let args = super::parse_args([
            "--bind",
            "127.0.0.1:9000",
            "--db-path",
            "state.db",
            "--config-path",
            "config.ini",
            "--reticulum-config-path",
            "reticulum-config",
            "--reticulumd-rpc",
            "127.0.0.1:4242",
            "--reticulumd-source",
            "source-destination",
            "--reticulumd-exe",
            "reticulumd.exe",
            "--reticulumd-db-path",
            "reticulumd.db",
            "--reticulumd-transport",
            "127.0.0.1:0",
            "--ui-dist-path",
            "ui-dist",
            "--api-key",
            "secret",
            "--system-status-fanout-mode",
            "event_plus_periodic",
        ])
        .expect("args");

        assert_eq!(args.bind.to_string(), "127.0.0.1:9000");
        assert_eq!(
            args.db_path.as_deref(),
            Some(std::path::Path::new("state.db"))
        );
        assert_eq!(
            args.config_path.as_deref(),
            Some(std::path::Path::new("config.ini"))
        );
        assert_eq!(
            args.reticulum_config_path.as_deref(),
            Some(std::path::Path::new("reticulum-config"))
        );
        assert_eq!(args.reticulumd_rpc.as_deref(), Some("127.0.0.1:4242"));
        assert_eq!(
            args.reticulumd_source.as_deref(),
            Some("source-destination")
        );
        assert_eq!(
            args.reticulumd_exe.as_deref(),
            Some(std::path::Path::new("reticulumd.exe"))
        );
        assert_eq!(
            args.reticulumd_db_path.as_deref(),
            Some(std::path::Path::new("reticulumd.db"))
        );
        assert_eq!(args.reticulumd_transport.as_deref(), Some("127.0.0.1:0"));
        assert_eq!(
            args.ui_dist_path.as_deref(),
            Some(std::path::Path::new("ui-dist"))
        );
        assert_eq!(args.api_key.as_deref(), Some("secret"));
        assert_eq!(
            args.system_status_fanout_mode.as_deref(),
            Some("event_plus_periodic")
        );
    }

    #[test]
    fn parse_args_rejects_reticulumd_rpc_without_source() {
        let error = super::parse_args(["--reticulumd-rpc", "127.0.0.1:4242"]).expect_err("error");

        assert_eq!(
            error.to_string(),
            "--reticulumd-source is required with --reticulumd-rpc"
        );
    }

    #[test]
    fn parse_args_rejects_managed_reticulumd_without_rpc_endpoint() {
        let error = super::parse_args(["--reticulumd-exe", "reticulumd.exe"]).expect_err("error");

        assert_eq!(
            error.to_string(),
            "--reticulumd-rpc is required with --reticulumd-exe"
        );
    }

    #[test]
    fn parse_args_rejects_reticulumd_db_path_without_managed_daemon() {
        let error = super::parse_args([
            "--reticulumd-rpc",
            "127.0.0.1:4242",
            "--reticulumd-source",
            "source-destination",
            "--reticulumd-db-path",
            "reticulumd.db",
        ])
        .expect_err("error");

        assert_eq!(
            error.to_string(),
            "--reticulumd-db-path is only valid with --reticulumd-exe"
        );
    }

    #[test]
    fn parse_args_rejects_reticulumd_transport_without_managed_daemon() {
        let error = super::parse_args([
            "--reticulumd-rpc",
            "127.0.0.1:4242",
            "--reticulumd-source",
            "source-destination",
            "--reticulumd-transport",
            "127.0.0.1:0",
        ])
        .expect_err("error");

        assert_eq!(
            error.to_string(),
            "--reticulumd-transport is only valid with --reticulumd-exe"
        );
    }
}
