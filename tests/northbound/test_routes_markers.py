"""Marker route coverage for northbound API."""
# pylint: disable=import-error

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from pathlib import Path

from fastapi.testclient import TestClient

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.api.storage import HubStorage
from reticulum_telemetry_hub.config.manager import HubConfigurationManager
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.northbound.app import create_app
from reticulum_telemetry_hub.northbound.auth import ApiAuth
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog


def _build_client(tmp_path: Path) -> tuple[TestClient, list[dict]]:
    config_manager = HubConfigurationManager(storage_path=tmp_path)
    storage = HubStorage(tmp_path / "rth_api.sqlite")
    api = ReticulumTelemetryHubAPI(config_manager=config_manager, storage=storage)
    event_log = EventLog()
    telemetry = TelemetryController(
        db_path=tmp_path / "telemetry.db",
        api=api,
        event_log=event_log,
    )
    dispatched: list[dict] = []

    def _dispatch(payload: dict) -> bool:
        dispatched.append(dict(payload))
        return True

    app = create_app(
        api=api,
        telemetry_controller=telemetry,
        event_log=event_log,
        auth=ApiAuth(api_key="secret"),
        marker_dispatcher=_dispatch,
        started_at=datetime.now(timezone.utc),
    )
    return TestClient(app), dispatched


def test_marker_routes_create_and_update(tmp_path: Path) -> None:
    client, dispatched = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    create_response = client.post(
        "/api/markers",
        headers=headers,
        json={"name": "Alpha", "category": "fire", "lat": 1.0, "lon": 2.0},
    )

    assert create_response.status_code == 201
    payload = create_response.json()
    marker_id = payload["marker_id"]

    list_response = client.get("/api/markers", headers=headers)
    assert list_response.status_code == 200
    assert any(item["marker_id"] == marker_id for item in list_response.json())

    update_response = client.patch(
        f"/api/markers/{marker_id}/position",
        headers=headers,
        json={"lat": 3.0, "lon": 4.0},
    )

    assert update_response.status_code == 200
    assert update_response.json()["status"] == "ok"

    noop_response = client.patch(
        f"/api/markers/{marker_id}/position",
        headers=headers,
        json={"lat": 3.0, "lon": 4.0},
    )

    assert noop_response.status_code == 200
    assert len(dispatched) == 2
    assert dispatched[0]["event_type"] == "marker.created"
    assert dispatched[1]["event_type"] == "marker.updated"
