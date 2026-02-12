"""Zone route coverage for northbound API."""
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


def _build_client(tmp_path: Path) -> TestClient:
    config_manager = HubConfigurationManager(storage_path=tmp_path)
    storage = HubStorage(tmp_path / "rth_api.sqlite")
    api = ReticulumTelemetryHubAPI(config_manager=config_manager, storage=storage)
    event_log = EventLog()
    telemetry = TelemetryController(
        db_path=tmp_path / "telemetry.db",
        api=api,
        event_log=event_log,
    )
    app = create_app(
        api=api,
        telemetry_controller=telemetry,
        event_log=event_log,
        auth=ApiAuth(api_key="secret"),
        started_at=datetime.now(timezone.utc),
    )
    return TestClient(app)


def _polygon(points: list[tuple[float, float]]) -> list[dict[str, float]]:
    return [{"lat": lat, "lon": lon} for lat, lon in points]


def test_zone_routes_create_list_update_delete(tmp_path: Path) -> None:
    client = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    create_response = client.post(
        "/api/zones",
        headers=headers,
        json={
            "name": "Alpha Zone",
            "points": _polygon([(1.0, 2.0), (1.1, 2.0), (1.1, 2.1)]),
        },
    )

    assert create_response.status_code == 201
    zone_id = create_response.json()["zone_id"]

    list_response = client.get("/api/zones", headers=headers)
    assert list_response.status_code == 200
    zones = list_response.json()
    assert any(zone["zone_id"] == zone_id for zone in zones)

    update_response = client.patch(
        f"/api/zones/{zone_id}",
        headers=headers,
        json={
            "name": "Bravo Zone",
            "points": _polygon([(1.0, 2.0), (1.2, 2.0), (1.2, 2.2)]),
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["status"] == "ok"

    refreshed = client.get("/api/zones", headers=headers)
    assert refreshed.status_code == 200
    updated = next(zone for zone in refreshed.json() if zone["zone_id"] == zone_id)
    assert updated["name"] == "Bravo Zone"
    assert len(updated["points"]) == 3

    delete_response = client.delete(f"/api/zones/{zone_id}", headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "ok"

    missing_delete = client.delete(f"/api/zones/{zone_id}", headers=headers)
    assert missing_delete.status_code == 404


def test_zone_routes_reject_invalid_geometry(tmp_path: Path) -> None:
    client = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    # bow-tie/self-intersecting polygon
    response = client.post(
        "/api/zones",
        headers=headers,
        json={
            "name": "Invalid Zone",
            "points": _polygon([(0.0, 0.0), (1.0, 1.0), (0.0, 1.0), (1.0, 0.0)]),
        },
    )

    assert response.status_code == 400
    assert "self-intersect" in response.json()["detail"]
