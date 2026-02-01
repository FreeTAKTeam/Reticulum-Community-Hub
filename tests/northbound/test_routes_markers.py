"""Marker route coverage for northbound API."""
# pylint: disable=import-error

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Callable
from typing import Optional

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


_UNSET = object()


def _build_client(
    tmp_path: Path,
    *,
    marker_dispatcher: Optional[Callable[[object, str], bool]] | object = _UNSET,
) -> tuple[TestClient, list[str]]:
    config_manager = HubConfigurationManager(storage_path=tmp_path)
    storage = HubStorage(tmp_path / "rth_api.sqlite")
    api = ReticulumTelemetryHubAPI(config_manager=config_manager, storage=storage)
    event_log = EventLog()
    telemetry = TelemetryController(
        db_path=tmp_path / "telemetry.db",
        api=api,
        event_log=event_log,
    )
    dispatched: list[str] = []

    def _dispatch(marker, event_type: str) -> bool:
        dispatched.append(event_type)
        return True

    dispatcher = _dispatch if marker_dispatcher is _UNSET else marker_dispatcher
    app = create_app(
        api=api,
        telemetry_controller=telemetry,
        event_log=event_log,
        auth=ApiAuth(api_key="secret"),
        marker_dispatcher=dispatcher,
        started_at=datetime.now(timezone.utc),
    )
    return TestClient(app), dispatched


def test_marker_routes_create_and_update(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("RTH_MARKER_IDENTITY_KEY", "11" * 32)
    client, dispatched = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    create_response = client.post(
        "/api/markers",
        headers=headers,
        json={
            "name": "Alpha",
            "type": "fire",
            "symbol": "fire",
            "category": "napsg",
            "lat": 1.0,
            "lon": 2.0,
        },
    )

    assert create_response.status_code == 201
    payload = create_response.json()
    marker_id = payload["object_destination_hash"]

    list_response = client.get("/api/markers", headers=headers)
    assert list_response.status_code == 200
    assert any(
        item["object_destination_hash"] == marker_id for item in list_response.json()
    )

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
    assert dispatched[0] == "marker.created"
    assert dispatched[1] == "marker.updated"


def test_marker_symbols_route(tmp_path: Path) -> None:
    client, _ = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    response = client.get("/api/markers/symbols", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert any(item.get("id") == "marker" and item.get("set") == "mdi" for item in payload)
    assert any(item.get("id") == "vehicle" and item.get("set") == "mdi" for item in payload)


def test_marker_routes_accept_mdi_symbols(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("RTH_MARKER_IDENTITY_KEY", "22" * 32)
    client, _ = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    create_response = client.post(
        "/api/markers",
        headers=headers,
        json={
            "name": "Vehicle",
            "type": "vehicle",
            "symbol": "vehicle",
            "category": "vehicle",
            "lat": 10.0,
            "lon": 11.0,
        },
    )

    assert create_response.status_code == 201
    marker_id = create_response.json()["object_destination_hash"]
    list_response = client.get("/api/markers", headers=headers)
    assert list_response.status_code == 200
    marker = next(
        item for item in list_response.json() if item["object_destination_hash"] == marker_id
    )
    assert marker["symbol"] == "vehicle"


def test_marker_routes_normalize_alias_symbols(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("RTH_MARKER_IDENTITY_KEY", "33" * 32)
    client, _ = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    create_response = client.post(
        "/api/markers",
        headers=headers,
        json={
            "name": "Community",
            "type": "Group / Community",
            "symbol": "Group / Community",
            "category": "Group / Community",
            "lat": 12.0,
            "lon": 13.0,
        },
    )

    assert create_response.status_code == 201
    marker_id = create_response.json()["object_destination_hash"]
    list_response = client.get("/api/markers", headers=headers)
    assert list_response.status_code == 200
    marker = next(
        item for item in list_response.json() if item["object_destination_hash"] == marker_id
    )
    assert marker["symbol"] == "group"


def test_marker_telemetry_recorded_without_dispatcher(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("RTH_MARKER_IDENTITY_KEY", "44" * 32)
    client, _ = _build_client(tmp_path, marker_dispatcher=None)
    headers = {"X-API-Key": "secret"}

    create_response = client.post(
        "/api/markers",
        headers=headers,
        json={
            "name": "Telemetry Marker",
            "type": "marker",
            "symbol": "marker",
            "category": "marker",
            "lat": 5.0,
            "lon": 6.0,
        },
    )

    assert create_response.status_code == 201
    marker_id = create_response.json()["object_destination_hash"]

    since = int(datetime.now(timezone.utc).timestamp()) - 60
    telemetry_response = client.get("/Telemetry", params={"since": since})

    assert telemetry_response.status_code == 200
    entries = telemetry_response.json().get("entries", [])
    assert any(entry["peer_destination"] == marker_id for entry in entries)
