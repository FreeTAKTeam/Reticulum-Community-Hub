"""Tests for the rch CLI helpers."""

import argparse
import sys
from pathlib import Path

import httpx
import pytest

from reticulum_telemetry_hub.cli.rch import ControlClient
from reticulum_telemetry_hub.cli.rch import ControlState
from reticulum_telemetry_hub.cli.rch import _build_gateway_command
from reticulum_telemetry_hub.cli.rch import _build_parser
from reticulum_telemetry_hub.cli.rch import _control_port
from reticulum_telemetry_hub.cli.rch import _load_state
from reticulum_telemetry_hub.cli.rch import _resolve_api_key
from reticulum_telemetry_hub.cli.rch import _resolve_data_dir
from reticulum_telemetry_hub.cli.rch import _spawn_gateway_process
from reticulum_telemetry_hub.cli.rch import _start_command
from reticulum_telemetry_hub.cli.rch import _status_command
from reticulum_telemetry_hub.cli.rch import _stop_with_signal
from reticulum_telemetry_hub.cli.rch import _stop_command
from reticulum_telemetry_hub.cli.rch import _write_state
from reticulum_telemetry_hub.cli import rch


def test_write_and_load_state_round_trip(tmp_path) -> None:
    """Persist and reload control state."""

    state = ControlState(
        pid=1234,
        port=8001,
        data_dir=str(tmp_path),
        log_level="info",
        started_at="2026-01-23T00:00:00+00:00",
    )
    _write_state(tmp_path, state)

    loaded = _load_state(tmp_path)

    assert loaded == state


def test_load_state_missing_file_returns_none(tmp_path) -> None:
    """Return None when the state file is missing."""

    assert _load_state(tmp_path) is None


def test_load_state_invalid_payload_returns_none(tmp_path) -> None:
    """Return None when the state file is corrupt."""

    state_path = tmp_path / "rch_state.json"
    state_path.write_text("{not json", encoding="utf-8")

    assert _load_state(tmp_path) is None


def test_build_gateway_command_includes_args(tmp_path) -> None:
    """Build the gateway command with expected flags."""

    command = _build_gateway_command(tmp_path, 8123, "debug")

    assert "--data-dir" in command
    assert str(tmp_path) in command
    assert "--port" in command
    assert "8123" in command
    assert "--log-level" in command
    assert "debug" in command


def test_build_gateway_command_frozen_uses_gateway(tmp_path, monkeypatch) -> None:
    """Use the gateway subcommand when running in frozen mode."""

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "rch-backend.exe", raising=False)

    command = _build_gateway_command(tmp_path, 8124, "info")

    assert "gateway" in command
    assert "-m" not in command


def test_control_client_status_success() -> None:
    """Return status JSON for a healthy endpoint."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/Control/Status":
            return httpx.Response(200, json={"status": "running"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = ControlClient(port=8000, transport=transport)

    payload = client.status()

    assert payload == {"status": "running"}


def test_control_client_status_failure() -> None:
    """Return None for an error response."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "error"})

    transport = httpx.MockTransport(handler)
    client = ControlClient(port=8000, transport=transport)

    assert client.status() is None


def test_control_client_start_and_stop() -> None:
    """Handle start/stop responses."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/Control/Start":
            return httpx.Response(200, json={"status": "running"})
        if request.url.path == "/Control/Stop":
            return httpx.Response(200, json={"status": "stopping"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = ControlClient(port=8000, transport=transport)

    assert client.start() == {"status": "running"}
    assert client.stop() is True


def test_control_client_request_error_returns_none() -> None:
    """Return None when the request fails."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.RequestError("boom", request=request)

    transport = httpx.MockTransport(handler)
    client = ControlClient(port=8000, transport=transport)

    assert client.status() is None


def test_control_client_sends_api_key() -> None:
    """Send API key headers when provided."""

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["header"] = request.headers.get("x-api-key")
        return httpx.Response(200, json={"status": "running"})

    transport = httpx.MockTransport(handler)
    client = ControlClient(port=8000, api_key="secret", transport=transport)

    client.status()

    assert captured["header"] == "secret"


def test_start_command_spawns_process(tmp_path, monkeypatch) -> None:
    """Spawn a gateway process and write state."""

    written = {}

    class DummyClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def status(self) -> None:
            return None

    class DummyProcess:
        pid = 4242

    def fake_write_state(data_dir: Path, state: ControlState) -> None:
        written["data_dir"] = data_dir
        written["state"] = state

    def fake_spawn(command, log_path):
        return DummyProcess()

    monkeypatch.setattr("reticulum_telemetry_hub.cli.rch.ControlClient", DummyClient)
    monkeypatch.setattr("reticulum_telemetry_hub.cli.rch._write_state", fake_write_state)
    monkeypatch.setattr("reticulum_telemetry_hub.cli.rch._spawn_gateway_process", fake_spawn)
    monkeypatch.setattr("reticulum_telemetry_hub.cli.rch._load_state", lambda _: None)

    args = argparse.Namespace(data_dir=str(tmp_path), port=8002, log_level="info")
    result = _start_command(args)

    assert result == 0
    assert written["state"].pid == 4242
    assert written["state"].port == 8002


def test_start_command_noop_when_running(tmp_path, monkeypatch) -> None:
    """Skip spawning when a running instance is detected."""

    state = ControlState(
        pid=1111,
        port=9001,
        data_dir=str(tmp_path),
        log_level="info",
        started_at="2026-01-23T00:00:00+00:00",
    )
    captured = {}

    class DummyClient:
        def __init__(self, *args, **kwargs) -> None:
            captured["port"] = kwargs.get("port")

        def status(self) -> dict[str, object]:
            return {"status": "running"}

    def fake_spawn(*_args, **_kwargs):
        raise AssertionError("spawn should not be called")

    monkeypatch.setattr("reticulum_telemetry_hub.cli.rch.ControlClient", DummyClient)
    monkeypatch.setattr("reticulum_telemetry_hub.cli.rch._load_state", lambda _: state)
    monkeypatch.setattr("reticulum_telemetry_hub.cli.rch._spawn_gateway_process", fake_spawn)

    args = argparse.Namespace(data_dir=str(tmp_path), port=None, log_level=None)

    assert _start_command(args) == 0
    assert captured["port"] == 9001


def test_stop_command_prefers_http(monkeypatch, tmp_path) -> None:
    """Stop via the control API when available."""

    class DummyClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def stop(self) -> bool:
            return True

    monkeypatch.setattr("reticulum_telemetry_hub.cli.rch.ControlClient", DummyClient)
    monkeypatch.setattr("reticulum_telemetry_hub.cli.rch._load_state", lambda _: None)

    args = argparse.Namespace(data_dir=str(tmp_path), port=8000, log_level=None)

    assert _stop_command(args) == 0


def test_stop_command_uses_signal_when_http_fails(monkeypatch, tmp_path) -> None:
    """Stop via SIGTERM when the control API is unavailable."""

    state = ControlState(
        pid=2222,
        port=8000,
        data_dir=str(tmp_path),
        log_level="info",
        started_at="2026-01-23T00:00:00+00:00",
    )

    class DummyClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def stop(self) -> bool:
            return False

    monkeypatch.setattr("reticulum_telemetry_hub.cli.rch.ControlClient", DummyClient)
    monkeypatch.setattr("reticulum_telemetry_hub.cli.rch._load_state", lambda _: state)
    monkeypatch.setattr("reticulum_telemetry_hub.cli.rch._stop_with_signal", lambda _: True)

    args = argparse.Namespace(data_dir=str(tmp_path), port=None, log_level=None)

    assert _stop_command(args) == 0


def test_status_command_reports_running(monkeypatch, tmp_path) -> None:
    """Return success when the backend responds."""

    class DummyClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def status(self) -> dict[str, object]:
            return {"status": "running", "pid": 1234}

    monkeypatch.setattr("reticulum_telemetry_hub.cli.rch.ControlClient", DummyClient)
    monkeypatch.setattr("reticulum_telemetry_hub.cli.rch._load_state", lambda _: None)

    args = argparse.Namespace(data_dir=str(tmp_path), port=8000, log_level=None)

    assert _status_command(args) == 0


def test_status_command_reports_stopped(monkeypatch, tmp_path) -> None:
    """Return failure when the backend is unavailable."""

    class DummyClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def status(self) -> None:
            return None

    monkeypatch.setattr("reticulum_telemetry_hub.cli.rch.ControlClient", DummyClient)
    monkeypatch.setattr("reticulum_telemetry_hub.cli.rch._load_state", lambda _: None)

    args = argparse.Namespace(data_dir=str(tmp_path), port=8000, log_level=None)

    assert _status_command(args) == 1


def test_control_port_defaults_to_default_port(tmp_path) -> None:
    """Use the default port when no overrides are available."""

    args = argparse.Namespace(data_dir=str(tmp_path), port=None, log_level=None)
    assert _control_port(args, None) == 8000


def test_resolve_data_dir_uses_env(monkeypatch, tmp_path) -> None:
    """Resolve the storage directory using environment variables."""

    monkeypatch.setenv("RTH_STORAGE_DIR", str(tmp_path))

    assert _resolve_data_dir(None) == tmp_path


def test_resolve_api_key_prefers_canonical_env(monkeypatch) -> None:
    """Prefer RTH_API_KEY when both canonical and alias keys are configured."""

    monkeypatch.setenv("RTH_API_KEY", "canonical")
    monkeypatch.setenv("RCH_API_KEY", "legacy")

    assert _resolve_api_key() == "canonical"


def test_resolve_api_key_supports_legacy_alias(monkeypatch) -> None:
    """Fall back to legacy RCH_API_KEY when canonical key is missing."""

    monkeypatch.delenv("RTH_API_KEY", raising=False)
    monkeypatch.setenv("RCH_API_KEY", "legacy")

    assert _resolve_api_key() == "legacy"


def test_stop_with_signal_handles_failure(monkeypatch) -> None:
    """Handle OS errors when sending SIGTERM."""

    def fake_kill(_pid, _sig):
        raise OSError("boom")

    monkeypatch.setattr(rch.os, "kill", fake_kill)

    assert _stop_with_signal(1234) is False


def test_stop_with_signal_success(monkeypatch) -> None:
    """Return True when the signal succeeds."""

    called = {}

    def fake_kill(pid, sig):
        called["pid"] = pid
        called["sig"] = sig

    monkeypatch.setattr(rch.os, "kill", fake_kill)

    assert _stop_with_signal(4321) is True
    assert called["pid"] == 4321


def test_spawn_gateway_process_writes_log(tmp_path, monkeypatch) -> None:
    """Spawn a gateway process with captured output."""

    recorded = {}

    class DummyProcess:
        pid = 9000

    def fake_popen(command, **kwargs):
        recorded["command"] = command
        recorded["kwargs"] = kwargs
        return DummyProcess()

    monkeypatch.setenv("_MEIPASS", "C:\\Temp\\_MEI123")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(rch.subprocess, "Popen", fake_popen)

    process = _spawn_gateway_process(["python", "-m", "rch"], tmp_path / "rch.log")

    assert process.pid == 9000
    assert recorded["kwargs"]["stdin"] == rch.subprocess.DEVNULL
    assert recorded["kwargs"]["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert "_MEIPASS" not in recorded["kwargs"]["env"]


def test_build_parser_parses_start_args() -> None:
    """Parse CLI arguments for the start subcommand."""

    parser = _build_parser()
    args = parser.parse_args(["--data-dir", "RTH_Store", "start", "--log-level", "info"])

    assert args.command == "start"
    assert args.data_dir == "RTH_Store"
    assert args.log_level == "info"


def test_main_routes_to_start(monkeypatch) -> None:
    """Route main to the start command handler."""

    monkeypatch.setattr(rch, "_start_command", lambda _args: 0)
    monkeypatch.setattr(sys, "argv", ["rch", "start"])

    with pytest.raises(SystemExit) as exc:
        rch.main()

    assert exc.value.code == 0


def test_main_routes_to_stop(monkeypatch) -> None:
    """Route main to the stop command handler."""

    monkeypatch.setattr(rch, "_stop_command", lambda _args: 0)
    monkeypatch.setattr(sys, "argv", ["rch", "stop"])

    with pytest.raises(SystemExit) as exc:
        rch.main()

    assert exc.value.code == 0


def test_main_routes_to_status(monkeypatch) -> None:
    """Route main to the status command handler."""

    monkeypatch.setattr(rch, "_status_command", lambda _args: 0)
    monkeypatch.setattr(sys, "argv", ["rch", "status"])

    with pytest.raises(SystemExit) as exc:
        rch.main()

    assert exc.value.code == 0


def test_main_normalizes_gateway_args(monkeypatch) -> None:
    """Normalize python -m gateway calls to the gateway subcommand."""

    called = {}

    def fake_gateway(_args) -> int:
        called["gateway"] = True
        return 0

    monkeypatch.setattr(rch, "_gateway_command", fake_gateway)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rch",
            "-m",
            "reticulum_telemetry_hub.northbound.gateway",
            "--data-dir",
            "RCH_Store",
            "--port",
            "8123",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        rch.main()

    assert exc.value.code == 0
    assert called["gateway"] is True
