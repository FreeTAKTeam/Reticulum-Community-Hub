"""CLI entrypoint for managing the Reticulum Community Hub runtime."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv as load_env

from reticulum_telemetry_hub.config.constants import DEFAULT_LOG_LEVEL_NAME
from reticulum_telemetry_hub.config.constants import DEFAULT_STORAGE_PATH
from reticulum_telemetry_hub.config.manager import _expand_user_path


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
STATE_FILENAME = "rch_state.json"
LOG_FILENAME = "rch.log"


@dataclass(frozen=True)
class ControlState:
    """Persisted state used by the rch CLI."""

    pid: int
    port: int
    data_dir: str
    log_level: str
    started_at: str


class ControlClient:
    """HTTP client for the local RCH control endpoints."""

    def __init__(
        self,
        *,
        port: int,
        api_key: Optional[str] = None,
        timeout: float = 2.0,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._base_url = f"http://{DEFAULT_HOST}:{port}"
        self._timeout = timeout
        self._transport = transport
        self._headers: dict[str, str] = {}
        if api_key:
            self._headers["X-API-Key"] = api_key

    def status(self) -> Optional[dict[str, object]]:
        """Return status payload from the running backend."""

        response = self._request("GET", "/Control/Status")
        if response is None:
            return None
        if response.status_code != 200:
            return None
        try:
            return response.json()
        except ValueError:
            return None

    def stop(self) -> bool:
        """Request a graceful stop from the running backend."""

        response = self._request("POST", "/Control/Stop")
        return bool(response and response.status_code == 200)

    def start(self) -> Optional[dict[str, object]]:
        """Return status after a start request."""

        response = self._request("POST", "/Control/Start")
        if response is None:
            return None
        if response.status_code != 200:
            return None
        try:
            return response.json()
        except ValueError:
            return None

    def _request(self, method: str, path: str) -> Optional[httpx.Response]:
        """Issue a request against the control API."""

        try:
            with httpx.Client(
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                return client.request(
                    method,
                    f"{self._base_url}{path}",
                    headers=self._headers,
                )
        except httpx.RequestError:
            return None


def _state_path(data_dir: Path) -> Path:
    """Return the state file path for a data directory."""

    return data_dir / STATE_FILENAME


def _resolve_data_dir(data_dir: Optional[str]) -> Path:
    """Return the resolved data directory for CLI operations."""

    if data_dir:
        return _expand_user_path(data_dir)
    env_dir = os.environ.get("RTH_STORAGE_DIR")
    return _expand_user_path(env_dir or DEFAULT_STORAGE_PATH)


def _load_state(data_dir: Path) -> Optional[ControlState]:
    """Load the persisted state from disk, if present."""

    state_path = _state_path(data_dir)
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return None

    try:
        pid = int(payload.get("pid"))
        port = int(payload.get("port"))
    except (TypeError, ValueError):
        return None

    data_dir_value = str(payload.get("data_dir") or data_dir)
    log_level = str(payload.get("log_level") or DEFAULT_LOG_LEVEL_NAME)
    started_at = str(payload.get("started_at") or "")
    return ControlState(
        pid=pid,
        port=port,
        data_dir=data_dir_value,
        log_level=log_level,
        started_at=started_at,
    )


def _write_state(data_dir: Path, state: ControlState) -> None:
    """Persist the CLI state to disk."""

    data_dir.mkdir(parents=True, exist_ok=True)
    state_path = _state_path(data_dir)
    payload = {
        "pid": state.pid,
        "port": state.port,
        "data_dir": state.data_dir,
        "log_level": state.log_level,
        "started_at": state.started_at,
    }
    state_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _build_gateway_command(
    data_dir: Path, port: int, log_level: Optional[str]
) -> list[str]:
    """Build the command used to spawn the gateway process."""

    command = [
        sys.executable,
        "-m",
        "reticulum_telemetry_hub.northbound.gateway",
        "--data-dir",
        str(data_dir),
        "--port",
        str(port),
        "--api-host",
        DEFAULT_HOST,
    ]
    if log_level:
        command.extend(["--log-level", log_level])
    return command


def _spawn_gateway_process(command: list[str], log_path: Path) -> subprocess.Popen:
    """Spawn the gateway process in the background."""

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("a", encoding="utf-8")
    creationflags = 0
    kwargs: dict[str, object] = {
        "stdout": log_file,
        "stderr": log_file,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0)
        kwargs["creationflags"] = creationflags
    else:
        kwargs["start_new_session"] = True
    process = subprocess.Popen(command, **kwargs)
    log_file.close()
    return process


def _control_port(args: argparse.Namespace, state: Optional[ControlState]) -> int:
    """Resolve the control port for stop/status calls."""

    if args.port is not None:
        return int(args.port)
    if state is not None:
        return int(state.port)
    return DEFAULT_PORT


def _stop_with_signal(pid: int) -> bool:
    """Attempt to stop a process with SIGTERM."""

    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except OSError:
        return False


def _start_command(args: argparse.Namespace) -> int:
    """Handle the rch start command."""

    data_dir = _resolve_data_dir(args.data_dir)
    state = _load_state(data_dir)
    port = (
        args.port
        if args.port is not None
        else int(state.port) if state is not None else DEFAULT_PORT
    )
    api_key = os.environ.get("RCH_API_KEY")
    client = ControlClient(port=port, api_key=api_key)

    if state is not None and client.status() is not None:
        print(f"RCH already running on port {port}.")
        return 0

    command = _build_gateway_command(data_dir, port, args.log_level)
    process = _spawn_gateway_process(command, data_dir / LOG_FILENAME)
    started_at = datetime.now(timezone.utc).isoformat()
    log_level = args.log_level or DEFAULT_LOG_LEVEL_NAME
    _write_state(
        data_dir,
        ControlState(
            pid=process.pid,
            port=port,
            data_dir=str(data_dir),
            log_level=log_level,
            started_at=started_at,
        ),
    )
    print(f"RCH started (pid={process.pid}) on port {port}.")
    return 0


def _stop_command(args: argparse.Namespace) -> int:
    """Handle the rch stop command."""

    data_dir = _resolve_data_dir(args.data_dir)
    state = _load_state(data_dir)
    port = _control_port(args, state)
    api_key = os.environ.get("RCH_API_KEY")
    client = ControlClient(port=port, api_key=api_key)

    if client.stop():
        print("RCH stop requested.")
    elif state is not None and _stop_with_signal(state.pid):
        print("RCH stop signal sent.")
    else:
        print("RCH is not running.")
        return 1

    return 0


def _status_command(args: argparse.Namespace) -> int:
    """Handle the rch status command."""

    data_dir = _resolve_data_dir(args.data_dir)
    state = _load_state(data_dir)
    port = _control_port(args, state)
    api_key = os.environ.get("RCH_API_KEY")
    client = ControlClient(port=port, api_key=api_key)

    payload = client.status()
    if payload is None:
        print("RCH is not running.")
        return 1
    status = payload.get("status", "running")
    pid = payload.get("pid")
    print(f"RCH status: {status} (pid={pid}, port={port})")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the CLI."""

    parser = argparse.ArgumentParser(prog="rch")
    parser.add_argument(
        "--data-dir",
        dest="data_dir",
        default=None,
        help="Storage directory for hub data.",
    )
    parser.add_argument(
        "--port",
        dest="port",
        type=int,
        default=None,
        help="Port to bind the northbound API.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start", help="Start the hub backend.")
    start_parser.add_argument(
        "--log-level",
        dest="log_level",
        choices=["error", "warning", "info", "debug"],
        default=None,
        help="Log verbosity for the hub runtime.",
    )

    subparsers.add_parser("stop", help="Stop the hub backend.")
    subparsers.add_parser("status", help="Show hub backend status.")
    return parser


def main() -> None:
    """Run the rch CLI entrypoint."""

    load_env()
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "start":
        raise SystemExit(_start_command(args))
    if args.command == "stop":
        raise SystemExit(_stop_command(args))
    if args.command == "status":
        raise SystemExit(_status_command(args))
    raise SystemExit(1)


if __name__ == "__main__":
    main()
