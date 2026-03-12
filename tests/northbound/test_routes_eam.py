"""Compatibility route coverage for EmergencyActionMessage endpoints."""

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
    domain.upsert_team({"uid": team_uid, "team_name": "Orange"})
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
        "subjectType": "member",
        "subjectId": "member-1",
        "teamId": "team-1",
        "securityStatus": "Green",
        "securityCapability": "Yellow",
        "preparednessStatus": "Green",
        "medicalStatus": "Green",
        "mobilityStatus": "Green",
        "commsStatus": "Green",
    }

    unauthorized = client.get("/api/EmergencyActionMessage")
    created = client.post("/api/EmergencyActionMessage", json=payload, headers=headers)
    listed = client.get("/api/EmergencyActionMessage", headers=headers)
    fetched = client.get("/api/EmergencyActionMessage/ORANGE-1", headers=headers)
    latest = client.get(
        "/api/EmergencyActionMessage/latest/member/member-1",
        headers=headers,
    )
    mismatch = client.put(
        "/api/EmergencyActionMessage/ORANGE-1",
        json={**payload, "callsign": "WRONG"},
        headers=headers,
    )
    updated = client.put(
        "/api/EmergencyActionMessage/ORANGE-1",
        json={**payload, "medicalStatus": "Red"},
        headers=headers,
    )
    deleted = client.delete("/api/EmergencyActionMessage/ORANGE-1", headers=headers)
    missing = client.get("/api/EmergencyActionMessage/ORANGE-1", headers=headers)

    assert unauthorized.status_code == 401
    assert created.status_code == 200
    assert created.json()["capabilityStatus"] == "Yellow"
    assert created.json()["securityCapability"] == "Yellow"
    assert listed.status_code == 200
    assert listed.json()[0]["callsign"] == "ORANGE-1"
    assert fetched.status_code == 200
    assert latest.status_code == 200
    assert mismatch.status_code == 400
    assert updated.status_code == 200
    assert updated.json()["overallStatus"] == "Red"
    assert deleted.status_code == 200
    assert missing.status_code == 404


def test_eam_team_summary_route_handles_missing_and_expired_reports(tmp_path: Path) -> None:
    client, _, domain = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    domain.upsert_team({"uid": "team-1", "team_name": "Orange"})
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
            "subjectId": "member-1",
            "teamId": "team-1",
            "reportedAt": (
                datetime.now(timezone.utc) - timedelta(minutes=10)
            ).isoformat(),
            "ttlSeconds": 60,
            "securityStatus": "Red",
            "capabilityStatus": "Red",
            "preparednessStatus": "Red",
            "medicalStatus": "Red",
            "mobilityStatus": "Red",
            "commsStatus": "Red",
        },
        headers=headers,
    )

    summary = client.get(
        "/api/EmergencyActionMessage/team/team-1/summary",
        headers=headers,
    )
    missing_team = client.get(
        "/api/EmergencyActionMessage/team/missing-team/summary",
        headers=headers,
    )

    assert summary.status_code == 200
    assert summary.json()["memberCount"] == 2
    assert summary.json()["securityStatus"] == "Unknown"
    assert summary.json()["overallStatus"] == "Unknown"
    assert missing_team.status_code == 404


def test_eam_team_summary_route_matches_team_orange_example(tmp_path: Path) -> None:
    client, _, domain = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    domain.upsert_team({"uid": "team-orange", "team_name": "Orange"})
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
            "subjectId": "member-a",
            "teamId": "team-orange",
            "securityStatus": "Green",
            "capabilityStatus": "Green",
            "preparednessStatus": "Green",
            "medicalStatus": "Green",
            "mobilityStatus": "Green",
            "commsStatus": "Green",
        },
        {
            "callsign": "B",
            "subjectId": "member-b",
            "teamId": "team-orange",
            "securityStatus": "Yellow",
            "capabilityStatus": "Green",
            "preparednessStatus": "Yellow",
            "medicalStatus": "Green",
            "mobilityStatus": "Green",
            "commsStatus": "Yellow",
        },
        {
            "callsign": "C",
            "subjectId": "member-c",
            "teamId": "team-orange",
            "securityStatus": "Green",
            "capabilityStatus": "Red",
            "preparednessStatus": "Red",
            "medicalStatus": "Yellow",
            "mobilityStatus": "Yellow",
            "commsStatus": "Green",
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
    assert summary.json()["securityStatus"] == "Yellow"
    assert summary.json()["capabilityStatus"] == "Red"
    assert summary.json()["preparednessStatus"] == "Red"
    assert summary.json()["medicalStatus"] == "Yellow"
    assert summary.json()["mobilityStatus"] == "Yellow"
    assert summary.json()["commsStatus"] == "Yellow"
    assert summary.json()["overallStatus"] == "Red"
