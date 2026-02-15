"""Tests for gateway runtime helpers."""
# pylint: disable=import-error

import argparse
from datetime import datetime
from datetime import timezone
import sys
import threading

from fastapi import FastAPI
from fastapi.testclient import TestClient

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.config import HubConfigurationManager
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.northbound.auth import ApiAuth
from reticulum_telemetry_hub.northbound import gateway
from reticulum_telemetry_hub.northbound.gateway import DEFAULT_API_HOST
from reticulum_telemetry_hub.northbound.gateway import LOCAL_API_HOST
from reticulum_telemetry_hub.northbound.gateway import _build_gateway_config
from reticulum_telemetry_hub.northbound.gateway import _build_log_levels
from reticulum_telemetry_hub.northbound.gateway import _parse_args
from reticulum_telemetry_hub.northbound.gateway import _resolve_interval
from reticulum_telemetry_hub.northbound.gateway import _start_hub_thread
from reticulum_telemetry_hub.northbound.gateway import build_gateway_app
from reticulum_telemetry_hub.northbound.gateway import GatewayConfig
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog


class DummyHub:
    """Minimal hub stub for gateway app construction."""

    def __init__(self, api, telemetry, event_log) -> None:
        self.api = api
        self.tel_controller = telemetry
        self.event_log = event_log
        self.command_manager = None
        self.marker_service = None
        self.identities = {}
        self.connections = {}

    def dispatch_northbound_message(self, message, topic_id=None, destination=None, fields=None):
        """No-op dispatcher for tests."""

        return None

    def dispatch_marker_event(self, marker, event_type: str) -> bool:
        """No-op marker dispatcher for tests."""

        return True

    def register_message_listener(self, listener):
        """Return a no-op unsubscribe."""

        return lambda: None


def test_resolve_interval_prefers_value() -> None:
    """Use explicit values and fall back to defaults."""

    assert _resolve_interval(5, 10) == 5
    assert _resolve_interval(None, 10) == 10


def test_build_log_levels_contains_defaults() -> None:
    """Include standard log levels."""

    levels = _build_log_levels()
    assert "info" in levels
    assert "debug" in levels


def test_parse_args_accepts_data_dir(monkeypatch) -> None:
    """Accept data-dir and port arguments."""

    monkeypatch.setattr(
        sys,
        "argv",
        ["prog", "--data-dir", "RTH_Store", "--port", "8123", "--log-level", "info"],
    )
    args = _parse_args()
    assert args.storage_dir == "RTH_Store"
    assert args.api_port == 8123
    assert args.log_level == "info"


def test_build_gateway_config_respects_requested_host(tmp_path) -> None:
    """Use the requested API host in gateway config."""

    args = argparse.Namespace(
        storage_dir=str(tmp_path),
        config_path=None,
        display_name=None,
        announce_interval=None,
        hub_telemetry_interval=None,
        service_telemetry_interval=None,
        log_level=None,
        embedded=None,
        daemon=False,
        services=[],
        api_port=8123,
        api_host="0.0.0.0",
    )
    config = _build_gateway_config(args)

    assert config.api_host == "0.0.0.0"
    assert config.api_port == 8123


def test_build_gateway_config_defaults_to_public_host(tmp_path) -> None:
    """Default API host is 0.0.0.0 when no host is provided."""

    args = argparse.Namespace(
        storage_dir=str(tmp_path),
        config_path=None,
        display_name=None,
        announce_interval=None,
        hub_telemetry_interval=None,
        service_telemetry_interval=None,
        log_level=None,
        embedded=None,
        daemon=False,
        services=[],
        api_port=8123,
        api_host=None,
    )

    config = _build_gateway_config(args)

    assert config.api_host == DEFAULT_API_HOST


def test_start_hub_thread_invokes_run() -> None:
    """Start the hub thread and invoke the run loop."""

    called = threading.Event()

    class DummyHubRunner:
        def run(self, *, daemon_mode, services):
            called.set()

    hub = DummyHubRunner()
    thread = _start_hub_thread(hub, daemon_mode=False, services=[])
    thread.join(timeout=1)

    assert called.is_set()


def test_build_gateway_app_sets_state(tmp_path) -> None:
    """Attach the hub to app state."""

    config_manager = HubConfigurationManager(storage_path=tmp_path)
    api = ReticulumTelemetryHubAPI(config_manager=config_manager)
    telemetry = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)
    hub = DummyHub(api, telemetry, EventLog())

    app = build_gateway_app(hub, started_at=datetime.now(timezone.utc))

    assert isinstance(app, FastAPI)
    assert app.state.hub is hub


def test_build_gateway_app_routes_include_destination_identity_and_name(tmp_path) -> None:
    """Expose destination hash, identity hash, and display names in routing snapshots."""

    config_manager = HubConfigurationManager(storage_path=tmp_path)
    api = ReticulumTelemetryHubAPI(config_manager=config_manager)
    telemetry = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)
    hub = DummyHub(api, telemetry, EventLog())

    class DummyConnection:
        def __init__(self, destination_hash: bytes, identity_hash: bytes) -> None:
            self.hash = destination_hash
            self.identity = type("DummyIdentity", (), {"hash": identity_hash})()

    destination_one = b"\x11" * 16
    destination_two = b"\x22" * 16
    identity_one = b"\xaa" * 16
    identity_two = b"\xbb" * 16
    hub.connections = {
        identity_one: DummyConnection(destination_one, identity_one),
        identity_two: DummyConnection(destination_two, identity_two),
    }
    hub.identities = {
        identity_one.hex(): "Field Team Alpha",
        destination_two.hex(): "Field Team Bravo",
    }

    app = build_gateway_app(
        hub,
        started_at=datetime.now(timezone.utc),
        auth=ApiAuth(api_key="secret"),
    )
    client = TestClient(app)

    response = client.get("/Command/DumpRouting", headers={"X-API-Key": "secret"})

    assert response.status_code == 200
    assert response.json()["destinations"] == [
        {
            "destination": destination_one.hex(),
            "identity": identity_one.hex(),
            "display_name": "Field Team Alpha",
        },
        {
            "destination": destination_two.hex(),
            "identity": identity_two.hex(),
            "display_name": "Field Team Bravo",
        },
    ]


def test_gateway_main_runs_server(monkeypatch, tmp_path) -> None:
    """Run the gateway main loop with stubbed dependencies."""

    state = {}
    config = GatewayConfig(
        storage_path=tmp_path,
        identity_path=tmp_path / "identity",
        config_path=tmp_path / "config.ini",
        display_name="RCH",
        announce_interval=1,
        hub_telemetry_interval=1,
        service_telemetry_interval=1,
        loglevel=1,
        embedded=False,
        daemon_mode=False,
        services=[],
        api_host=LOCAL_API_HOST,
        api_port=8123,
    )

    class DummyConfigManager:
        def __init__(self, storage_path, config_path) -> None:
            state["config_manager"] = (storage_path, config_path)

    class DummyHub:
        def __init__(self, *args, **kwargs) -> None:
            state["hub"] = self

        def shutdown(self) -> None:
            state["shutdown_called"] = True

        def run(self, *, daemon_mode, services) -> None:
            return None

    class DummyThread:
        def join(self, timeout=None) -> None:
            state["joined"] = True

    class DummyConfig:
        def __init__(self, app, host, port, log_level) -> None:
            state["server_config"] = (host, port, log_level)

    class DummyServer:
        def __init__(self, config) -> None:
            self.config = config
            self.should_exit = False

        def run(self) -> None:
            state["server_run"] = True

    monkeypatch.setattr(gateway, "_parse_args", lambda: object())
    monkeypatch.setattr(gateway, "_build_gateway_config", lambda _args: config)
    monkeypatch.setattr(gateway, "HubConfigurationManager", DummyConfigManager)
    monkeypatch.setattr(gateway, "ReticulumTelemetryHub", DummyHub)
    monkeypatch.setattr(gateway, "_start_hub_thread", lambda *_args, **_kwargs: DummyThread())
    monkeypatch.setattr(gateway, "build_gateway_app", lambda *_args, **_kwargs: FastAPI())
    monkeypatch.setattr(gateway.uvicorn, "Config", DummyConfig)
    monkeypatch.setattr(gateway.uvicorn, "Server", DummyServer)

    gateway.main()

    assert state["server_run"] is True
    assert state["shutdown_called"] is True
    assert state["joined"] is True
