"""Marker route coverage for northbound API."""
# pylint: disable=import-error

from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
import subprocess
from typing import Callable
from typing import Optional

from fastapi.testclient import TestClient
import pytest

from reticulum_telemetry_hub.api.marker_service import MarkerUpdateResult
from reticulum_telemetry_hub.api.models import Marker
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.api.storage import HubStorage
from reticulum_telemetry_hub.config.manager import HubConfigurationManager
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.northbound.app import create_app
from reticulum_telemetry_hub.northbound.auth import ApiAuth
from reticulum_telemetry_hub.mission_sync.rust_bridge import RustMissionSyncBridge
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandEnvelope
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog


_UNSET = object()
FIELD_RESULTS = 10
FIELD_GROUP = 11
FIELD_EVENT = 13


class RustMarkerService:
    """Marker service subset backed by the Rust RCH bridge."""

    def __init__(self, db_path: Path) -> None:
        self._bridge = _bridge(db_path)
        self._next_command = 0

    def list_markers(self) -> list[Marker]:
        result = self._result("mission.marker.list", {})
        markers = result.get("markers")
        assert isinstance(markers, list)
        return [_marker_from_payload(dict(marker)) for marker in markers if isinstance(marker, dict)]

    def create_marker(
        self,
        *,
        name: str | None,
        marker_type: str,
        symbol: str,
        category: str,
        lat: float,
        lon: float,
        origin_rch: str,
        notes: str | None = None,
        ttl_seconds: int | None = None,
    ) -> Marker:
        return _marker_from_payload(
            self._result(
                "mission.marker.create",
                {
                    "name": name,
                    "marker_type": marker_type,
                    "symbol": symbol,
                    "category": category,
                    "lat": lat,
                    "lon": lon,
                    "origin_rch": origin_rch,
                    "notes": notes,
                    "ttl_seconds": ttl_seconds,
                },
            )
        )

    def update_marker_position(
        self,
        object_destination_hash: str,
        *,
        lat: float,
        lon: float,
    ) -> MarkerUpdateResult:
        current = self._get_marker(object_destination_hash)
        if current.lat == float(lat) and current.lon == float(lon):
            return MarkerUpdateResult(marker=current, changed=False)
        marker = _marker_from_payload(
            self._result(
                "mission.marker.position.patch",
                {
                    "object_destination_hash": object_destination_hash,
                    "lat": lat,
                    "lon": lon,
                },
            )
        )
        return MarkerUpdateResult(marker=marker, changed=True)

    def update_marker_name(
        self,
        object_destination_hash: str,
        *,
        name: str,
    ) -> MarkerUpdateResult:
        current = self._get_marker(object_destination_hash)
        if current.name == name.strip():
            return MarkerUpdateResult(marker=current, changed=False)
        marker = _marker_from_payload(
            self._result(
                "mission.marker.patch",
                {"object_destination_hash": object_destination_hash, "name": name},
            )
        )
        return MarkerUpdateResult(marker=marker, changed=True)

    def delete_marker(self, object_destination_hash: str) -> Marker:
        return _marker_from_payload(
            self._result(
                "mission.marker.delete",
                {"object_destination_hash": object_destination_hash},
            )
        )

    def _get_marker(self, object_destination_hash: str) -> Marker:
        for marker in self.list_markers():
            if marker.object_destination_hash == object_destination_hash:
                return marker
        raise KeyError(f"Marker '{object_destination_hash}' not found")

    def _result(self, command_type: str, args: dict[str, object]) -> dict[str, object]:
        self._next_command += 1
        responses = self._bridge.handle_command(
            MissionCommandEnvelope.model_validate(
                {
                    "command_id": f"cmd-rust-marker-route-{self._next_command}",
                    "source": {"rns_identity": "peer-a"},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "command_type": command_type,
                    "args": args,
                }
            ),
            source_identity="peer-a",
        )
        payload = responses[-1].fields[FIELD_RESULTS]
        if not isinstance(payload, dict) or payload.get("status") != "result":
            raise KeyError(command_type)
        result = payload.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"Rust marker command returned non-object result: {command_type}")
        return result


def _runtime_root() -> Path:
    candidates = [
        Path(__file__).resolve().parents[4] / "New project" / "R3AKT-Runtime",
        Path(r"C:\Users\broth\Documents\New project\R3AKT-Runtime"),
    ]
    for candidate in candidates:
        if (candidate / "Cargo.toml").exists():
            return candidate
    pytest.fail("R3AKT-Runtime workspace not found for Rust marker route parity tests")


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


def _marker_from_payload(payload: dict[str, object]) -> Marker:
    position = payload.get("position")
    if not isinstance(position, dict):
        position = {"lat": payload.get("lat"), "lon": payload.get("lon")}
    updated_at = _parse_datetime(payload.get("updated_at") or payload.get("time"))
    created_at = _parse_datetime(payload.get("created_at") or updated_at)
    stale_at = _parse_datetime(payload.get("stale_at") or updated_at)
    if stale_at <= datetime.now(timezone.utc):
        stale_at = updated_at + timedelta(hours=24)
    return Marker(
        local_id=str(payload.get("local_id") or payload.get("object_destination_hash") or ""),
        object_destination_hash=str(payload.get("object_destination_hash") or ""),
        origin_rch=str(payload.get("origin_rch") or ""),
        object_identity_storage_key=None,
        marker_type=str(payload.get("type") or payload.get("marker_type") or "marker"),
        symbol=str(payload.get("symbol") or "marker"),
        name=str(payload.get("name") or "Marker"),
        category=str(payload.get("category") or "marker"),
        lat=float(position.get("lat") or 0.0),
        lon=float(position.get("lon") or 0.0),
        notes=payload.get("notes") if isinstance(payload.get("notes"), str) else None,
        time=_parse_datetime(payload.get("time") or updated_at),
        stale_at=stale_at,
        created_at=created_at,
        updated_at=updated_at,
    )


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


def _build_client(
    tmp_path: Path,
    *,
    marker_dispatcher: Optional[Callable[[object, str], bool]] | object = _UNSET,
    backend: str = "python",
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
    marker_service = (
        RustMarkerService(tmp_path / "r3akt-marker-routes.sqlite")
        if backend == "rust"
        else None
    )
    app = create_app(
        api=api,
        telemetry_controller=telemetry,
        event_log=event_log,
        auth=ApiAuth(api_key="secret"),
        marker_dispatcher=dispatcher,
        marker_service=marker_service,
        started_at=datetime.now(timezone.utc),
    )
    return TestClient(app), dispatched


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_marker_routes_create_update_and_delete(
    tmp_path: Path,
    monkeypatch,
    backend: str,
) -> None:
    monkeypatch.setenv("RTH_MARKER_IDENTITY_KEY", "11" * 32)
    client, dispatched = _build_client(tmp_path, backend=backend)
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

    rename_response = client.patch(
        f"/api/markers/{marker_id}",
        headers=headers,
        json={"name": "Renamed Alpha"},
    )

    assert rename_response.status_code == 200
    refreshed = client.get("/api/markers", headers=headers)
    assert refreshed.status_code == 200
    renamed = next(
        item for item in refreshed.json() if item["object_destination_hash"] == marker_id
    )
    assert renamed["name"] == "Renamed Alpha"

    delete_response = client.delete(f"/api/markers/{marker_id}", headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "ok"

    after_delete = client.get("/api/markers", headers=headers)
    assert after_delete.status_code == 200
    assert all(
        item["object_destination_hash"] != marker_id for item in after_delete.json()
    )

    missing_delete = client.delete(f"/api/markers/{marker_id}", headers=headers)
    assert missing_delete.status_code == 404

    assert len(dispatched) == 4
    assert dispatched[0] == "marker.created"
    assert dispatched[1] == "marker.updated"
    assert dispatched[2] == "marker.updated"
    assert dispatched[3] == "marker.deleted"


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
    telemetry_response = client.get(
        "/Telemetry",
        params={"since": since},
        headers={"X-API-Key": "secret"},
    )

    assert telemetry_response.status_code == 200
    entries = telemetry_response.json().get("entries", [])
    assert any(entry["peer_destination"] == marker_id for entry in entries)
