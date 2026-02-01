"""Tests for gateway control routes."""
# pylint: disable=import-error

from pathlib import Path

from fastapi.testclient import TestClient

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.config import HubConfigurationManager
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.northbound.app import create_app
from reticulum_telemetry_hub.northbound.auth import ApiAuth
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog


class DummyControl:
    """Control stub with start/stop hooks."""

    def __init__(self) -> None:
        self.shutdown_called = False
        self.start_called = False

    def status(self) -> dict[str, object]:
        """Return a fixed status payload."""

        return {"status": "running"}

    def request_shutdown(self) -> None:
        """Record shutdown requests."""

        self.shutdown_called = True

    def request_start(self) -> None:
        """Record start requests."""

        self.start_called = True


class DummyControlNoStart:
    """Control stub without a start hook."""

    def __init__(self) -> None:
        self.shutdown_called = False

    def status(self) -> dict[str, object]:
        """Return a fixed status payload."""

        return {"status": "running"}

    def request_shutdown(self) -> None:
        """Record shutdown requests."""

        self.shutdown_called = True


def _build_app(tmp_path: Path, control) -> TestClient:
    """Create a test client wired to the control routes."""

    config_manager = HubConfigurationManager(storage_path=tmp_path)
    api = ReticulumTelemetryHubAPI(config_manager=config_manager)
    telemetry = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)
    app = create_app(
        api=api,
        telemetry_controller=telemetry,
        event_log=EventLog(),
        auth=ApiAuth(api_key="secret"),
        control=control,
    )
    return TestClient(app)


def test_control_status_and_stop(tmp_path) -> None:
    """Return status and accept stop requests."""

    control = DummyControl()
    client = _build_app(tmp_path, control)

    status_response = client.get("/Control/Status", headers={"X-API-Key": "secret"})
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "running"

    stop_response = client.post("/Control/Stop", headers={"X-API-Key": "secret"})
    assert stop_response.status_code == 200
    assert control.shutdown_called is True


def test_control_start_without_start_hook(tmp_path) -> None:
    """Allow start when a control hook is missing."""

    control = DummyControlNoStart()
    client = _build_app(tmp_path, control)

    response = client.post("/Control/Start", headers={"X-API-Key": "secret"})
    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_control_routes_missing_when_disabled(tmp_path) -> None:
    """Return 404 when control routes are not registered."""

    config_manager = HubConfigurationManager(storage_path=tmp_path)
    api = ReticulumTelemetryHubAPI(config_manager=config_manager)
    telemetry = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)
    app = create_app(
        api=api,
        telemetry_controller=telemetry,
        event_log=EventLog(),
        auth=ApiAuth(api_key="secret"),
    )
    client = TestClient(app)

    response = client.get("/Control/Status", headers={"X-API-Key": "secret"})
    assert response.status_code == 404
