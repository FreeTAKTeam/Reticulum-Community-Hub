"""REM-compatible route coverage for EmergencyActionMessage endpoints."""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path

from fastapi.testclient import TestClient

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.api.storage import HubStorage
from reticulum_telemetry_hub.config import HubConfigurationManager
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.mission_domain import MissionDomainService
from reticulum_telemetry_hub.mission_domain.canonical_teams import CANONICAL_COLOR_TEAM_UIDS
from reticulum_telemetry_hub.northbound.app import create_app
from reticulum_telemetry_hub.northbound.auth import ApiAuth
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog


def _build_client(
    tmp_path: Path,
    *,
    client_host: tuple[str, int] = ("testclient", 50000),
) -> tuple[TestClient, ReticulumTelemetryHubAPI, MissionDomainService]:
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
    domain = MissionDomainService(config_manager.config.hub_database_path)
    return TestClient(app, client=client_host), api, domain


def _seed_team(domain: MissionDomainService, *, team_uid: str = "team-1") -> None:
    domain.upsert_team({"uid": team_uid, "team_name": "Ops"})
    domain.upsert_team_member(
        {
            "uid": "member-1",
            "team_uid": team_uid,
            "rns_identity": "peer-a",
            "display_name": "Peer A",
            "callsign": "ORANGE-1",
        }
    )


def test_eam_routes_require_auth_and_support_crud(tmp_path: Path) -> None:
    client, _, domain = _build_client(tmp_path, client_host=("198.51.100.10", 50000))
    _seed_team(domain)
    headers = {"X-API-Key": "secret"}
    payload = {
        "callsign": "ORANGE-1",
        "eam_uid": "eam-1",
        "team_member_uid": "member-1",
        "team_uid": "team-1",
        "reported_by": "Peer A",
        "reported_at": datetime.now(timezone.utc).isoformat(),
        "security_status": "Green",
        "capability_status": "Yellow",
        "preparedness_status": "Green",
        "medical_status": "Green",
        "mobility_status": "Green",
        "comms_status": "Green",
        "notes": "Holding position",
        "confidence": 0.9,
        "ttl_seconds": 3600,
        "source": {"rns_identity": "peer-a", "display_name": "Peer A"},
    }

    unauthorized = client.get("/api/EmergencyActionMessage")
    created = client.post("/api/EmergencyActionMessage", json=payload, headers=headers)
    listed = client.get("/api/EmergencyActionMessage", headers=headers)
    fetched = client.get("/api/EmergencyActionMessage/ORANGE-1", headers=headers)
    latest = client.get(
        "/api/EmergencyActionMessage/latest/member-1",
        headers=headers,
    )
    mismatch = client.put(
        "/api/EmergencyActionMessage/ORANGE-1",
        json={**payload, "callsign": "WRONG"},
        headers=headers,
    )
    updated = client.put(
        "/api/EmergencyActionMessage/ORANGE-1",
        json={**payload, "medical_status": "Red"},
        headers=headers,
    )
    deleted = client.delete("/api/EmergencyActionMessage/ORANGE-1", headers=headers)
    missing = client.get("/api/EmergencyActionMessage/ORANGE-1", headers=headers)

    assert unauthorized.status_code == 401
    assert created.status_code == 200
    assert created.json()["eam_uid"] == "eam-1"
    assert created.json()["group_name"] == "Ops"
    assert created.json()["capability_status"] == "Yellow"
    assert created.json()["source"] == {"rns_identity": "peer-a", "display_name": "Peer A"}
    assert listed.status_code == 200
    assert listed.json()[0]["group_name"] == "Ops"
    assert listed.json()[0]["callsign"] == "ORANGE-1"
    assert fetched.status_code == 200
    assert fetched.json()["team_member_uid"] == "member-1"
    assert latest.status_code == 200
    assert latest.json()["eam_uid"] == "eam-1"
    assert mismatch.status_code == 400
    assert updated.status_code == 200
    assert updated.json()["overall_status"] == "Red"
    assert deleted.status_code == 200
    assert missing.status_code == 404


def test_eam_routes_auto_provision_canonical_team_and_member(tmp_path: Path) -> None:
    client, _, domain = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}
    team_uid = CANONICAL_COLOR_TEAM_UIDS["ORANGE"]

    created = client.post(
        "/api/EmergencyActionMessage",
        json={
            "eam_uid": "eam-auto-1",
            "callsign": "ORANGE-1",
            "group_name": "ORANGE",
            "team_member_uid": "member-auto-1",
            "team_uid": team_uid,
            "reported_by": "Relay Operator",
            "security_status": "Green",
            "capability_status": "Green",
            "preparedness_status": "Green",
            "medical_status": "Green",
            "mobility_status": "Green",
            "comms_status": "Green",
            "source": {"rns_identity": "peer-auto-1", "display_name": "Peer Auto"},
        },
        headers=headers,
    )

    assert created.status_code == 200
    assert created.json()["eam_uid"] == "eam-auto-1"
    assert created.json()["group_name"] == "ORANGE"
    assert created.json()["team_uid"] == team_uid

    team = domain.get_team(team_uid)
    member = domain.get_team_member("member-auto-1")
    assert team["uid"] == team_uid
    assert team["color"] == "ORANGE"
    assert team["team_name"] == "ORANGE"
    assert member["team_uid"] == team_uid
    assert member["rns_identity"] == "peer-auto-1"
    assert member["display_name"] == "Relay Operator"
    assert member["callsign"] == "ORANGE-1"


def test_eam_routes_reject_legacy_http_fields(tmp_path: Path) -> None:
    client, _, _domain = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    response = client.post(
        "/api/EmergencyActionMessage",
        json={
            "callsign": "ORANGE-1",
            "subjectType": "member",
            "subjectId": "member-1",
            "teamId": "team-1",
            "securityCapability": "Red",
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_eam_team_summary_route_handles_missing_and_expired_reports(tmp_path: Path) -> None:
    client, _, domain = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    domain.upsert_team({"uid": "team-1", "team_name": "Ops"})
    domain.upsert_team_member(
        {
            "uid": "member-1",
            "team_uid": "team-1",
            "rns_identity": "peer-a",
            "display_name": "Peer A",
            "callsign": "ORANGE-1",
        }
    )
    domain.upsert_team_member(
        {
            "uid": "member-2",
            "team_uid": "team-1",
            "rns_identity": "peer-b",
            "display_name": "Peer B",
            "callsign": "ORANGE-2",
        }
    )
    client.post(
        "/api/EmergencyActionMessage",
        json={
            "callsign": "ORANGE-1",
            "team_member_uid": "member-1",
            "team_uid": "team-1",
            "reported_at": (
                datetime.now(timezone.utc) - timedelta(minutes=10)
            ).isoformat(),
            "ttl_seconds": 60,
            "security_status": "Red",
            "capability_status": "Red",
            "preparedness_status": "Red",
            "medical_status": "Red",
            "mobility_status": "Red",
            "comms_status": "Red",
            "source": {"rns_identity": "peer-a"},
        },
        headers=headers,
    )

    summary = client.get("/api/EmergencyActionMessage/team/team-1/summary", headers=headers)
    missing_team = client.get(
        "/api/EmergencyActionMessage/team/missing-team/summary",
        headers=headers,
    )

    assert summary.status_code == 200
    assert summary.json()["team_uid"] == "team-1"
    assert summary.json()["total"] == 1
    assert summary.json()["active_total"] == 0
    assert summary.json()["deleted_total"] == 1
    assert summary.json()["overall_status"] is None
    assert missing_team.status_code == 404


def test_eam_routes_hide_expired_snapshots_from_list_and_latest(tmp_path: Path) -> None:
    client, _, domain = _build_client(tmp_path)
    _seed_team(domain)
    headers = {"X-API-Key": "secret"}

    created = client.post(
        "/api/EmergencyActionMessage",
        json={
            "callsign": "ORANGE-1",
            "team_member_uid": "member-1",
            "team_uid": "team-1",
            "reported_at": (
                datetime.now(timezone.utc) - timedelta(minutes=10)
            ).isoformat(),
            "ttl_seconds": 60,
            "security_status": "Red",
            "capability_status": "Red",
            "preparedness_status": "Red",
            "medical_status": "Red",
            "mobility_status": "Red",
            "comms_status": "Red",
            "source": {"rns_identity": "peer-a"},
        },
        headers=headers,
    )
    listed = client.get("/api/EmergencyActionMessage", headers=headers)
    latest = client.get(
        "/api/EmergencyActionMessage/latest/member-1",
        headers=headers,
    )

    assert created.status_code == 200
    assert listed.status_code == 200
    assert listed.json() == []
    assert latest.status_code == 404


def test_eam_routes_allow_recreate_after_delete(tmp_path: Path) -> None:
    client, _, domain = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    domain.upsert_team({"uid": "team-1", "team_name": "Ops"})
    domain.upsert_team_member(
        {
            "uid": "member-1",
            "team_uid": "team-1",
            "rns_identity": "peer-a",
            "display_name": "Peer A",
            "callsign": "OPS-1",
        }
    )
    domain.upsert_team_member(
        {
            "uid": "member-2",
            "team_uid": "team-1",
            "rns_identity": "peer-b",
            "display_name": "Peer B",
            "callsign": "OPS-2",
        }
    )

    created = client.post(
        "/api/EmergencyActionMessage",
        json={
            "eam_uid": "eam-1",
            "callsign": "OPS-1",
            "team_member_uid": "member-1",
            "team_uid": "team-1",
            "source": {"rns_identity": "peer-a"},
        },
        headers=headers,
    )
    deleted = client.delete("/api/EmergencyActionMessage/OPS-1", headers=headers)
    recreated = client.post(
        "/api/EmergencyActionMessage",
        json={
            "eam_uid": "eam-2",
            "callsign": "OPS-1",
            "team_member_uid": "member-2",
            "team_uid": "team-1",
            "source": {"rns_identity": "peer-b"},
        },
        headers=headers,
    )

    assert created.status_code == 200
    assert deleted.status_code == 200
    assert recreated.status_code == 200
    assert recreated.json()["eam_uid"] == "eam-2"
    assert recreated.json()["team_member_uid"] == "member-2"
    assert recreated.json()["callsign"] == "OPS-1"


def test_eam_team_summary_route_matches_team_orange_example(tmp_path: Path) -> None:
    client, _, domain = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    domain.upsert_team({"uid": "team-orange", "team_name": "Ops"})
    for member_uid, callsign in (
        ("member-a", "A"),
        ("member-b", "B"),
        ("member-c", "C"),
        ("member-d", "D"),
    ):
        domain.upsert_team_member(
            {
                "uid": member_uid,
                "team_uid": "team-orange",
                "rns_identity": f"peer-{member_uid}",
                "display_name": member_uid,
                "callsign": callsign,
            }
        )

    payloads = [
        {
            "callsign": "A",
            "team_member_uid": "member-a",
            "team_uid": "team-orange",
            "security_status": "Green",
            "capability_status": "Green",
            "preparedness_status": "Green",
            "medical_status": "Green",
            "mobility_status": "Green",
            "comms_status": "Green",
        },
        {
            "callsign": "B",
            "team_member_uid": "member-b",
            "team_uid": "team-orange",
            "security_status": "Yellow",
            "capability_status": "Green",
            "preparedness_status": "Yellow",
            "medical_status": "Green",
            "mobility_status": "Green",
            "comms_status": "Yellow",
        },
        {
            "callsign": "C",
            "team_member_uid": "member-c",
            "team_uid": "team-orange",
            "security_status": "Green",
            "capability_status": "Red",
            "preparedness_status": "Red",
            "medical_status": "Yellow",
            "mobility_status": "Yellow",
            "comms_status": "Green",
        },
    ]
    for payload in payloads:
        response = client.post("/api/EmergencyActionMessage", json=payload, headers=headers)
        assert response.status_code == 200

    summary = client.get(
        "/api/EmergencyActionMessage/team/team-orange/summary",
        headers=headers,
    )

    assert summary.status_code == 200
    assert summary.json()["team_uid"] == "team-orange"
    assert summary.json()["total"] == 3
    assert summary.json()["active_total"] == 3
    assert summary.json()["green_total"] == 1
    assert summary.json()["yellow_total"] == 1
    assert summary.json()["red_total"] == 1
    assert summary.json()["overall_status"] == "Red"
