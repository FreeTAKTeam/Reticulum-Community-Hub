"""Extended REST route coverage for northbound API."""
# pylint: disable=import-error

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
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

    join_alias_response = client.post("/RCH", params={"identity": "dest-2"})
    assert join_alias_response.status_code == 200

    leave_alias_response = client.put("/RCH", params={"identity": "dest-2"})
    assert leave_alias_response.status_code == 200

    capability_response = client.put(
        "/api/r3akt/capabilities/dest-1/mission.join",
        json={"granted_by": "tester"},
        headers=headers,
    )
    assert capability_response.status_code == 200

    missions_response = client.post(
        "/api/r3akt/missions",
        json={"mission_name": "Mission Alpha"},
        headers=headers,
    )
    assert missions_response.status_code == 200
    mission_uid = missions_response.json()["uid"]

    mission_get_response = client.get(
        f"/api/r3akt/missions/{mission_uid}",
        headers=headers,
    )
    assert mission_get_response.status_code == 200

    template_response = client.post(
        "/checklists/templates",
        json={
            "template": {
                "template_name": "Template Alpha",
                "description": "Template",
                "created_by_team_member_rns_identity": "dest-1",
                "columns": [
                    {
                        "column_name": "Due",
                        "display_order": 1,
                        "column_type": "RELATIVE_TIME",
                        "column_editable": False,
                        "is_removable": False,
                        "system_key": "DUE_RELATIVE_DTG",
                    },
                    {
                        "column_name": "Task",
                        "display_order": 2,
                        "column_type": "SHORT_STRING",
                        "column_editable": True,
                        "is_removable": True,
                    },
                ],
            }
        },
        headers=headers,
    )
    assert template_response.status_code == 200
    template_uid = template_response.json()["uid"]

    checklist_response = client.post(
        "/checklists",
        json={
            "template_uid": template_uid,
            "name": "Checklist Alpha",
            "description": "Checklist",
            "start_time": datetime.now(timezone.utc).isoformat(),
            "source_identity": "dest-1",
        },
        headers=headers,
    )
    assert checklist_response.status_code == 200
    checklist_uid = checklist_response.json()["uid"]

    task_add_response = client.post(
        f"/checklists/{checklist_uid}/tasks",
        json={"number": 1, "due_relative_minutes": 10},
        headers=headers,
    )
    assert task_add_response.status_code == 200

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

def test_r3akt_registry_routes_matrix(tmp_path: Path) -> None:
    client, _, _, _ = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    invalid_grant = client.put(
        "/api/r3akt/capabilities/peer-a/mission.join",
        json={"expires_at": "not-iso"},
        headers=headers,
    )
    assert invalid_grant.status_code == 400

    grant = client.put(
        "/api/r3akt/capabilities/peer-a/mission.join",
        json={
            "granted_by": "admin",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
        headers=headers,
    )
    assert grant.status_code == 200

    capabilities = client.get("/api/r3akt/capabilities/peer-a", headers=headers)
    assert capabilities.status_code == 200
    assert "mission.join" in capabilities.json()["capabilities"]

    revoke = client.delete(
        "/api/r3akt/capabilities/peer-a/mission.join",
        headers=headers,
    )
    assert revoke.status_code == 200

    mission = client.post(
        "/api/r3akt/missions",
        json={"uid": "mission-1", "mission_name": "Mission One"},
        headers=headers,
    )
    assert mission.status_code == 200
    mission_uid = mission.json()["uid"]

    mission_get = client.get(f"/api/r3akt/missions/{mission_uid}", headers=headers)
    assert mission_get.status_code == 200

    mission_missing = client.get("/api/r3akt/missions/missing", headers=headers)
    assert mission_missing.status_code == 404

    mission_change_invalid = client.post(
        "/api/r3akt/mission-changes",
        json={"name": "bad"},
        headers=headers,
    )
    assert mission_change_invalid.status_code == 400

    mission_change = client.post(
        "/api/r3akt/mission-changes",
        json={"uid": "change-1", "mission_uid": mission_uid, "name": "Updated"},
        headers=headers,
    )
    assert mission_change.status_code == 200

    team = client.post(
        "/api/r3akt/teams",
        json={"uid": "team-1", "mission_uid": mission_uid, "team_name": "Ops"},
        headers=headers,
    )
    assert team.status_code == 200

    member_invalid = client.post("/api/r3akt/team-members", json={}, headers=headers)
    assert member_invalid.status_code == 400

    member = client.post(
        "/api/r3akt/team-members",
        json={
            "uid": "member-1",
            "team_uid": "team-1",
            "rns_identity": "peer-a",
            "display_name": "Peer A",
        },
        headers=headers,
    )
    assert member.status_code == 200

    asset = client.post(
        "/api/r3akt/assets",
        json={
            "asset_uid": "asset-1",
            "team_member_uid": "member-1",
            "name": "Radio",
            "asset_type": "COMM",
        },
        headers=headers,
    )
    assert asset.status_code == 200

    skill = client.post(
        "/api/r3akt/skills",
        json={"skill_uid": "skill-1", "name": "Navigation"},
        headers=headers,
    )
    assert skill.status_code == 200

    member_skill_invalid = client.post(
        "/api/r3akt/team-member-skills",
        json={"team_member_rns_identity": "peer-a"},
        headers=headers,
    )
    assert member_skill_invalid.status_code == 400

    member_skill = client.post(
        "/api/r3akt/team-member-skills",
        json={
            "uid": "member-skill-1",
            "team_member_rns_identity": "peer-a",
            "skill_uid": "skill-1",
            "level": 3,
        },
        headers=headers,
    )
    assert member_skill.status_code == 200

    req_invalid = client.post(
        "/api/r3akt/task-skill-requirements",
        json={"task_uid": "task-1"},
        headers=headers,
    )
    assert req_invalid.status_code == 400

    requirement = client.post(
        "/api/r3akt/task-skill-requirements",
        json={
            "uid": "req-1",
            "task_uid": "task-1",
            "skill_uid": "skill-1",
            "minimum_level": 2,
        },
        headers=headers,
    )
    assert requirement.status_code == 200

    assignment_invalid = client.post(
        "/api/r3akt/assignments",
        json={"mission_uid": mission_uid},
        headers=headers,
    )
    assert assignment_invalid.status_code == 400

    assignment = client.post(
        "/api/r3akt/assignments",
        json={
            "assignment_uid": "assignment-1",
            "mission_uid": mission_uid,
            "task_uid": "task-1",
            "team_member_rns_identity": "peer-a",
            "assets": ["asset-1"],
        },
        headers=headers,
    )
    assert assignment.status_code == 200

    assert client.get("/api/r3akt/missions", headers=headers).status_code == 200
    assert client.get("/api/r3akt/mission-changes", headers=headers).status_code == 200
    assert client.get("/api/r3akt/teams", headers=headers).status_code == 200
    assert client.get("/api/r3akt/team-members", headers=headers).status_code == 200
    assert client.get("/api/r3akt/assets", headers=headers).status_code == 200
    assert client.get("/api/r3akt/skills", headers=headers).status_code == 200
    assert client.get("/api/r3akt/team-member-skills", headers=headers).status_code == 200
    assert client.get("/api/r3akt/task-skill-requirements", headers=headers).status_code == 200
    assert client.get("/api/r3akt/assignments", headers=headers).status_code == 200

    events = client.get("/api/r3akt/events", headers=headers)
    snapshots = client.get("/api/r3akt/snapshots", headers=headers)
    assert events.status_code == 200
    assert snapshots.status_code == 200
    assert events.json()


def test_checklist_routes_matrix_and_errors(tmp_path: Path) -> None:
    client, _, _, _ = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    template_bad_payload = client.post(
        "/checklists/templates",
        json={"template": "invalid"},
        headers=headers,
    )
    assert template_bad_payload.status_code == 400

    template = client.post(
        "/checklists/templates",
        json={
            "template": {
                "template_name": "Template Alpha",
                "description": "Template",
                "created_by_team_member_rns_identity": "peer-a",
                "columns": [
                    {
                        "column_name": "Due",
                        "display_order": 1,
                        "column_type": "RELATIVE_TIME",
                        "column_editable": False,
                        "is_removable": False,
                        "system_key": "DUE_RELATIVE_DTG",
                    },
                    {
                        "column_name": "Task",
                        "display_order": 2,
                        "column_type": "SHORT_STRING",
                        "column_editable": True,
                        "is_removable": True,
                    },
                ],
            }
        },
        headers=headers,
    )
    assert template.status_code == 200
    template_uid = template.json()["uid"]

    list_templates = client.get("/checklists/templates", headers=headers)
    assert list_templates.status_code == 200

    patch_bad_payload = client.patch(
        f"/checklists/templates/{template_uid}",
        json={"patch": "invalid"},
        headers=headers,
    )
    assert patch_bad_payload.status_code == 400

    patch_template = client.patch(
        f"/checklists/templates/{template_uid}",
        json={"patch": {"template_name": "Template Beta"}},
        headers=headers,
    )
    assert patch_template.status_code == 200

    clone_missing_name = client.post(
        f"/checklists/templates/{template_uid}/clone",
        json={},
        headers=headers,
    )
    assert clone_missing_name.status_code == 400

    clone_template = client.post(
        f"/checklists/templates/{template_uid}/clone",
        json={"template_name": "Template Clone", "description": "Clone"},
        headers=headers,
    )
    assert clone_template.status_code == 200
    clone_uid = clone_template.json()["uid"]

    delete_missing_template = client.delete(
        "/checklists/templates/missing-template",
        headers=headers,
    )
    assert delete_missing_template.status_code == 404

    checklist_online_bad = client.post(
        "/checklists",
        json={"name": "Missing template"},
        headers=headers,
    )
    assert checklist_online_bad.status_code == 400

    checklist_online = client.post(
        "/checklists",
        json={
            "template_uid": template_uid,
            "name": "Checklist Online",
            "description": "Online checklist",
            "start_time": datetime.now(timezone.utc).isoformat(),
            "source_identity": "peer-a",
        },
        headers=headers,
    )
    assert checklist_online.status_code == 200
    checklist_uid = checklist_online.json()["uid"]

    checklist_offline = client.post(
        "/checklists/offline",
        json={
            "name": "Checklist Offline",
            "description": "Offline checklist",
            "source_identity": "peer-a",
            "origin_type": "BLANK_TEMPLATE",
        },
        headers=headers,
    )
    assert checklist_offline.status_code == 200
    offline_uid = checklist_offline.json()["uid"]

    list_checklists = client.get("/checklists", headers=headers)
    assert list_checklists.status_code == 200

    join_missing = client.post("/checklists/missing/join", json={}, headers=headers)
    assert join_missing.status_code == 404

    join_checklist = client.post(
        f"/checklists/{checklist_uid}/join",
        json={"source_identity": "peer-a"},
        headers=headers,
    )
    assert join_checklist.status_code == 200

    get_checklist = client.get(f"/checklists/{checklist_uid}", headers=headers)
    assert get_checklist.status_code == 200

    upload_missing = client.post("/checklists/missing/upload", json={}, headers=headers)
    assert upload_missing.status_code == 404

    upload_checklist = client.post(
        f"/checklists/{offline_uid}/upload",
        json={"source_identity": "peer-a"},
        headers=headers,
    )
    assert upload_checklist.status_code == 200

    publish_missing = client.post(
        "/checklists/missing/feeds/feed-1",
        json={},
        headers=headers,
    )
    assert publish_missing.status_code == 404

    publish_feed = client.post(
        f"/checklists/{offline_uid}/feeds/feed-1",
        json={"source_identity": "peer-a"},
        headers=headers,
    )
    assert publish_feed.status_code == 200

    task_add = client.post(
        f"/checklists/{checklist_uid}/tasks",
        json={"number": 1, "due_relative_minutes": 10},
        headers=headers,
    )
    assert task_add.status_code == 200
    task_uid = task_add.json()["tasks"][0]["task_uid"]
    column_uid = next(
        item["column_uid"]
        for item in task_add.json()["columns"]
        if item["column_type"] == "SHORT_STRING"
    )

    task_status_invalid = client.post(
        f"/checklists/{checklist_uid}/tasks/{task_uid}/status",
        json={"user_status": "INVALID"},
        headers=headers,
    )
    assert task_status_invalid.status_code == 400

    task_status = client.post(
        f"/checklists/{checklist_uid}/tasks/{task_uid}/status",
        json={"user_status": "COMPLETE", "changed_by_team_member_rns_identity": "peer-a"},
        headers=headers,
    )
    assert task_status.status_code == 200

    task_style = client.patch(
        f"/checklists/{checklist_uid}/tasks/{task_uid}/row-style",
        json={"row_background_color": "#112233", "line_break_enabled": True},
        headers=headers,
    )
    assert task_style.status_code == 200

    task_cell_missing = client.patch(
        f"/checklists/{checklist_uid}/tasks/{task_uid}/cells/missing",
        json={"value": "x"},
        headers=headers,
    )
    assert task_cell_missing.status_code == 404

    task_cell = client.patch(
        f"/checklists/{checklist_uid}/tasks/{task_uid}/cells/{column_uid}",
        json={"value": "Inspect", "updated_by_team_member_rns_identity": "peer-a"},
        headers=headers,
    )
    assert task_cell.status_code == 200

    task_delete = client.delete(
        f"/checklists/{checklist_uid}/tasks/{task_uid}",
        headers=headers,
    )
    assert task_delete.status_code == 200

    task_delete_missing = client.delete(
        f"/checklists/{checklist_uid}/tasks/{task_uid}",
        headers=headers,
    )
    assert task_delete_missing.status_code == 404

    import_missing_csv = client.post(
        "/checklists/import/csv",
        json={},
        headers=headers,
    )
    assert import_missing_csv.status_code == 400

    encoded_csv = base64.b64encode(b"10,Task 1\n20,Task 2\n").decode("ascii")
    import_csv = client.post(
        "/checklists/import/csv",
        json={"csv_filename": "import.csv", "csv_base64": encoded_csv},
        headers=headers,
    )
    assert import_csv.status_code == 200

    delete_clone = client.delete(f"/checklists/templates/{clone_uid}", headers=headers)
    assert delete_clone.status_code == 200
