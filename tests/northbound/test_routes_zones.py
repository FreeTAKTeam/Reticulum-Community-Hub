"""Zone route coverage for northbound API."""
# pylint: disable=import-error

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from pathlib import Path
import subprocess

from fastapi.testclient import TestClient
import pytest

from reticulum_telemetry_hub.api.models import Zone
from reticulum_telemetry_hub.api.models import ZonePoint
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.api.storage import HubStorage
from reticulum_telemetry_hub.api.zone_service import ZoneUpdateResult
from reticulum_telemetry_hub.config.manager import HubConfigurationManager
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.mission_sync.rust_bridge import RustMissionSyncBridge
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandEnvelope
from reticulum_telemetry_hub.northbound.app import create_app
from reticulum_telemetry_hub.northbound.auth import ApiAuth
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog


FIELD_RESULTS = 10
FIELD_GROUP = 11
FIELD_EVENT = 13


class RustZoneService:
    """Zone service subset backed by the Rust RCH bridge."""

    def __init__(self, db_path: Path) -> None:
        self._bridge = _bridge(db_path)
        self._next_command = 0

    def list_zones(self) -> list[Zone]:
        result = self._result("mission.zone.list", {})
        zones = result.get("zones")
        assert isinstance(zones, list)
        return [_zone_from_payload(dict(zone)) for zone in zones if isinstance(zone, dict)]

    def create_zone(self, *, name: str, points: list[ZonePoint]) -> Zone:
        return _zone_from_payload(
            self._result(
                "mission.zone.create",
                {
                    "name": name,
                    "points": [point.to_dict() for point in points],
                },
            )
        )

    def update_zone(
        self,
        zone_id: str,
        *,
        name: str | None = None,
        points: list[ZonePoint] | None = None,
    ) -> ZoneUpdateResult:
        zone = _zone_from_payload(
            self._result(
                "mission.zone.patch",
                {
                    "zone_id": zone_id,
                    "name": name,
                    "points": [point.to_dict() for point in points] if points else None,
                },
            )
        )
        return ZoneUpdateResult(zone=zone)

    def delete_zone(self, zone_id: str) -> Zone:
        return _zone_from_payload(
            self._result("mission.zone.delete", {"zone_id": zone_id})
        )

    def _result(self, command_type: str, args: dict[str, object]) -> dict[str, object]:
        self._next_command += 1
        responses = self._bridge.handle_command(
            MissionCommandEnvelope.model_validate(
                {
                    "command_id": f"cmd-rust-zone-route-{self._next_command}",
                    "source": {"rns_identity": "peer-a"},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "command_type": command_type,
                    "args": args,
                }
            ),
            source_identity="peer-a",
        )
        payload = responses[-1].fields[FIELD_RESULTS]
        if not isinstance(payload, dict):
            raise KeyError(command_type)
        if payload.get("status") == "rejected":
            reason = str(payload.get("reason") or payload.get("detail") or command_type)
            if payload.get("reason_code") == "invalid_payload":
                raise ValueError(reason)
            raise KeyError(reason)
        if payload.get("status") != "result":
            raise KeyError(command_type)
        result = payload.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"Rust zone command returned non-object result: {command_type}")
        return result


def _runtime_root() -> Path:
    candidates = [
        Path(__file__).resolve().parents[4] / "New project" / "R3AKT-Runtime",
        Path(r"C:\Users\broth\Documents\New project\R3AKT-Runtime"),
    ]
    for candidate in candidates:
        if (candidate / "Cargo.toml").exists():
            return candidate
    pytest.fail("R3AKT-Runtime workspace not found for Rust zone route parity tests")


def _bridge(db_path: Path) -> RustMissionSyncBridge:
    runtime_root = _runtime_root()

    def runner(args, **kwargs):  # type: ignore[no-untyped-def]
        request_db_path = args[args.index("--db") + 1]
        return subprocess.run(
            ["cargo", "run", "-q", "-p", "r3akt-rch-bridge", "--", "--db", request_db_path],
            cwd=runtime_root,
            input=kwargs["input"],
            text=True,
            capture_output=True,
            check=False,
        )

    return RustMissionSyncBridge(
        binary_path="cargo-run-r3akt-rch-bridge",
        db_path=str(db_path),
        field_results=FIELD_RESULTS,
        field_event=FIELD_EVENT,
        field_group=FIELD_GROUP,
        runner=runner,
    )


def _zone_from_payload(payload: dict[str, object]) -> Zone:
    points = payload.get("points")
    assert isinstance(points, list)
    updated_at = _parse_datetime(payload.get("updated_at"))
    return Zone(
        zone_id=str(payload.get("zone_id") or ""),
        name=str(payload.get("name") or ""),
        points=[
            ZonePoint(lat=float(point.get("lat")), lon=float(point.get("lon")))
            for point in points
            if isinstance(point, dict)
        ],
        created_at=_parse_datetime(payload.get("created_at") or updated_at),
        updated_at=updated_at,
    )


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


def _build_client(tmp_path: Path, *, backend: str = "python") -> TestClient:
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
        zone_service=(
            RustZoneService(tmp_path / "r3akt-zone-routes.sqlite")
            if backend == "rust"
            else None
        ),
        started_at=datetime.now(timezone.utc),
    )
    return TestClient(app)


def _polygon(points: list[tuple[float, float]]) -> list[dict[str, float]]:
    return [{"lat": lat, "lon": lon} for lat, lon in points]


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_zone_routes_create_list_update_delete(tmp_path: Path, backend: str) -> None:
    client = _build_client(tmp_path, backend=backend)
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


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_zone_routes_reject_invalid_geometry(tmp_path: Path, backend: str) -> None:
    client = _build_client(tmp_path, backend=backend)
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
