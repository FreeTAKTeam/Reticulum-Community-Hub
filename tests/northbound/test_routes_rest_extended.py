"""Extended REST route coverage for northbound API."""
# pylint: disable=import-error

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.api.storage import HubStorage
from reticulum_telemetry_hub.config import HubConfigurationManager
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_enum import (
    SID_LOCATION,
    SID_TIME,
)
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.northbound.app import create_app
from reticulum_telemetry_hub.northbound.auth import ApiAuth
from reticulum_telemetry_hub.northbound.routes_rest import register_core_routes
from reticulum_telemetry_hub.northbound.services import NorthboundServices
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog
from tests.factories import build_location_payload


def _build_client(
    tmp_path: Path,
) -> tuple[TestClient, ReticulumTelemetryHubAPI, EventLog, TelemetryController]:
    config_manager = HubConfigurationManager(storage_path=tmp_path)
    storage = HubStorage(tmp_path / "hub.sqlite")
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
        routing_provider=lambda: ["dest-1"],
        message_dispatcher=lambda content, topic_id=None, destination=None, fields=None: None,
    )
    return TestClient(app), api, event_log, telemetry


def test_openapi_yaml_returns_payload(tmp_path: Path) -> None:
    client, _, _, _ = _build_client(tmp_path)

    response = client.get("/openapi.yaml")

    assert response.status_code == 200
    assert "openapi" in response.text.lower()


def test_openapi_yaml_missing_returns_404(tmp_path: Path) -> None:
    config_manager = HubConfigurationManager(storage_path=tmp_path)
    api = ReticulumTelemetryHubAPI(
        config_manager=config_manager,
        storage=HubStorage(tmp_path / "hub.sqlite"),
    )
    event_log = EventLog()
    telemetry = TelemetryController(
        db_path=tmp_path / "telemetry.db",
        api=api,
        event_log=event_log,
    )
    services = NorthboundServices(
        api=api,
        telemetry=telemetry,
        event_log=event_log,
        started_at=datetime.now(timezone.utc),
    )
    app = FastAPI()
    register_core_routes(
        app,
        services=services,
        api=api,
        telemetry_controller=telemetry,
        require_protected=lambda: None,
        resolve_openapi_spec=lambda: None,
    )
    client = TestClient(app)

    response = client.get("/openapi.yaml")

    assert response.status_code == 404


def test_core_routes_endpoints(tmp_path: Path) -> None:
    reticulum_path = tmp_path / "reticulum.conf"
    reticulum_path.write_text("[reticulum]\nshare_instance = yes\n", encoding="utf-8")
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        f"[hub]\nreticulum_config_path = {reticulum_path}\n", encoding="utf-8"
    )

    client, api, event_log, telemetry = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    help_response = client.get("/Help")
    examples_response = client.get("/Examples")

    assert help_response.status_code == 200
    assert examples_response.status_code == 200

    config_path = api._config_manager.config_path  # pylint: disable=protected-access
    config_path.write_text("[app]\nname=RTH\n", encoding="utf-8")

    status_response = client.get("/Status", headers=headers)
    assert status_response.status_code == 200

    event_log.add_event("test_event", "Event recorded")
    events_response = client.get("/Events", headers=headers)
    assert events_response.status_code == 200
    assert events_response.json()

    now = datetime.now(timezone.utc)
    telemetry_response = client.get(
        "/Telemetry",
        params={"since": int(now.timestamp())},
    )
    assert telemetry_response.status_code == 200

    config_response = client.get("/Config", headers=headers)
    assert config_response.status_code == 200

    validate_response = client.post(
        "/Config/Validate",
        data="[app]\nname=RTH\n",
        headers={**headers, "Content-Type": "text/plain"},
    )
    assert validate_response.status_code == 200

    apply_response = client.put(
        "/Config",
        data="[app]\nname=RTH\n",
        headers={**headers, "Content-Type": "text/plain"},
    )
    assert apply_response.status_code == 200

    rollback_response = client.post("/Config/Rollback", headers=headers)
    assert rollback_response.status_code == 200

    reticulum_response = client.get("/Reticulum/Config", headers=headers)
    assert reticulum_response.status_code == 200

    reticulum_validate_response = client.post(
        "/Reticulum/Config/Validate",
        data="[reticulum]\nenable_transport = yes\n",
        headers={**headers, "Content-Type": "text/plain"},
    )
    assert reticulum_validate_response.status_code == 200

    reticulum_apply_response = client.put(
        "/Reticulum/Config",
        data="[reticulum]\nenable_transport = yes\n",
        headers={**headers, "Content-Type": "text/plain"},
    )
    assert reticulum_apply_response.status_code == 200

    reticulum_rollback_response = client.post(
        "/Reticulum/Config/Rollback", headers=headers
    )
    assert reticulum_rollback_response.status_code == 200

    capabilities_response = client.get(
        "/Reticulum/Interfaces/Capabilities", headers=headers
    )
    assert capabilities_response.status_code == 200
    capabilities_payload = capabilities_response.json()
    assert "supported_interface_types" in capabilities_payload
    assert "unsupported_interface_types" in capabilities_payload
    assert "identity_hash_hex_length" in capabilities_payload

    discovery_response = client.get("/Reticulum/Discovery", headers=headers)
    assert discovery_response.status_code == 200
    discovery_payload = discovery_response.json()
    assert "runtime_active" in discovery_payload
    assert "discovered_interfaces" in discovery_payload
    assert "refreshed_at" in discovery_payload

    telemetry.save_telemetry(
        {
            SID_TIME: int(now.timestamp()),
            SID_LOCATION: build_location_payload(int(now.timestamp())),
        },
        "peer-1",
        timestamp=now,
    )

    flush_response = client.post("/Command/FlushTelemetry", headers=headers)
    assert flush_response.status_code == 200

    reload_response = client.post("/Command/ReloadConfig", headers=headers)
    assert reload_response.status_code == 200

    message_response = client.post(
        "/Message",
        json={"Content": "hello"},
        headers=headers,
    )
    assert message_response.status_code == 200

    routing_response = client.get("/Command/DumpRouting", headers=headers)
    assert routing_response.status_code == 200
    assert routing_response.json()["destinations"] == ["dest-1"]

    join_response = client.post("/RTH", params={"identity": "dest-1"})
    assert join_response.status_code == 200

    leave_response = client.put("/RTH", params={"identity": "dest-1"})
    assert leave_response.status_code == 200

    client_list = client.get("/Client", headers=headers)
    assert client_list.status_code == 200

    info_response = client.get("/api/v1/app/info")
    assert info_response.status_code == 200


def test_apply_config_rejects_invalid_payload(tmp_path: Path) -> None:
    """Return HTTP 400 when a config payload is invalid."""

    client, api, _, _ = _build_client(tmp_path)
    headers = {"X-API-Key": "secret", "Content-Type": "text/plain"}

    config_path = api._config_manager.config_path  # pylint: disable=protected-access
    config_path.write_text("[app]\nname=RTH\n", encoding="utf-8")
    original = api.get_config_text()

    response = client.put("/Config", data="hub]\nname=Broken\n", headers=headers)

    assert response.status_code == 400
    assert "Invalid configuration payload" in response.json().get("detail", "")
    assert api.get_config_text() == original


def test_apply_reticulum_config_rejects_invalid_payload(tmp_path: Path) -> None:
    """Return HTTP 400 when a Reticulum config payload is invalid."""

    reticulum_path = tmp_path / "reticulum.conf"
    reticulum_path.write_text("[reticulum]\nshare_instance = yes\n", encoding="utf-8")
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        f"[hub]\nreticulum_config_path = {reticulum_path}\n", encoding="utf-8"
    )

    client, api, _, _ = _build_client(tmp_path)
    headers = {"X-API-Key": "secret", "Content-Type": "text/plain"}

    original = api.get_reticulum_config_text()

    response = client.put("/Reticulum/Config", data="reticulum]\nnope", headers=headers)

    assert response.status_code == 400
    assert "Invalid Reticulum configuration payload" in response.json().get("detail", "")
    assert api.get_reticulum_config_text() == original


def test_identity_moderation_routes(tmp_path: Path) -> None:
    client, _, _, _ = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    ban_response = client.post("/Client/abc/Ban", headers=headers)
    assert ban_response.status_code == 200

    unban_response = client.post("/Client/abc/Unban", headers=headers)
    assert unban_response.status_code == 200

    blackhole_response = client.post("/Client/abc/Blackhole", headers=headers)
    assert blackhole_response.status_code == 200

    identities_response = client.get("/Identities", headers=headers)
    assert identities_response.status_code == 200


def test_reticulum_capabilities_route_runtime_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    """Return a safe capabilities response when runtime is unavailable."""

    client, _, _, _ = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}
    monkeypatch.setattr(
        "reticulum_telemetry_hub.northbound.services.get_interface_capabilities",
        lambda: {
            "runtime_active": False,
            "os": "windows",
            "identity_hash_hex_length": 0,
            "supported_interface_types": [],
            "unsupported_interface_types": ["TCPClientInterface"],
            "discoverable_interface_types": [],
            "autoconnect_interface_types": [],
            "rns_version": "unavailable",
        },
    )

    response = client.get("/Reticulum/Interfaces/Capabilities", headers=headers)

    assert response.status_code == 200
    assert response.json()["runtime_active"] is False


def test_reticulum_discovery_route_runtime_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    """Return a safe discovery response when runtime is unavailable."""

    client, _, _, _ = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}
    monkeypatch.setattr(
        "reticulum_telemetry_hub.northbound.services.get_discovery_snapshot",
        lambda: {
            "runtime_active": False,
            "should_autoconnect": False,
            "max_autoconnected_interfaces": None,
            "required_discovery_value": None,
            "interface_discovery_sources": [],
            "discovered_interfaces": [],
            "refreshed_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    response = client.get("/Reticulum/Discovery", headers=headers)

    assert response.status_code == 200
    assert response.json()["runtime_active"] is False
    assert response.json()["discovered_interfaces"] == []
