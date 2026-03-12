from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone

import pytest

from reticulum_telemetry_hub.mission_domain import EmergencyActionMessageService
from reticulum_telemetry_hub.mission_domain import MissionDomainService


def _services(tmp_path) -> tuple[MissionDomainService, EmergencyActionMessageService]:
    db_path = tmp_path / "eam.sqlite"
    return MissionDomainService(db_path), EmergencyActionMessageService(db_path)


def _seed_team(
    domain: MissionDomainService,
    *,
    team_uid: str = "team-1",
    member_ids: tuple[str, ...] = ("member-1",),
) -> None:
    domain.upsert_team({"uid": team_uid, "team_name": "Orange"})
    for index, member_id in enumerate(member_ids, start=1):
        domain.upsert_team_member(
            {
                "uid": member_id,
                "team_uid": team_uid,
                "rns_identity": f"peer-{index}",
                "display_name": f"Peer {index}",
                "callsign": f"ORANGE-{index}",
            }
        )


def _payload(
    *,
    callsign: str = "ORANGE-1",
    subject_id: str = "member-1",
    team_id: str = "team-1",
    reported_at: datetime | None = None,
    ttl_seconds: int | None = None,
    security_status: str = "Green",
    capability_status: str = "Green",
    preparedness_status: str = "Green",
    medical_status: str = "Green",
    mobility_status: str = "Green",
    comms_status: str = "Green",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "callsign": callsign,
        "subjectType": "member",
        "subjectId": subject_id,
        "teamId": team_id,
        "reportedAt": (reported_at or datetime.now(timezone.utc)).isoformat(),
        "securityStatus": security_status,
        "capabilityStatus": capability_status,
        "preparednessStatus": preparedness_status,
        "medicalStatus": medical_status,
        "mobilityStatus": mobility_status,
        "commsStatus": comms_status,
    }
    if ttl_seconds is not None:
        payload["ttlSeconds"] = ttl_seconds
    return payload


def test_status_service_create_update_and_delete_snapshot(tmp_path) -> None:
    domain, status_service = _services(tmp_path)
    _seed_team(domain)

    created = status_service.upsert_message(_payload())
    updated = status_service.upsert_message(
        _payload(medical_status="Red", comms_status="Yellow")
    )
    listed = status_service.list_messages(team_id="team-1")

    assert created["callsign"] == "ORANGE-1"
    assert created["overallStatus"] == "Green"
    assert updated["id"] == created["id"]
    assert updated["medicalStatus"] == "Red"
    assert updated["overallStatus"] == "Red"
    assert listed[0]["id"] == created["id"]
    assert status_service.get_message_by_callsign("ORANGE-1")["medicalStatus"] == "Red"

    deleted = status_service.delete_message("ORANGE-1")

    assert deleted["id"] == created["id"]
    with pytest.raises(KeyError):
        status_service.get_message_by_callsign("ORANGE-1")


def test_status_service_rejects_invalid_subject_type_and_unknown_subject(tmp_path) -> None:
    domain, status_service = _services(tmp_path)
    _seed_team(domain)

    with pytest.raises(ValueError, match="subjectType"):
        status_service.upsert_message({**_payload(), "subjectType": "team"})

    with pytest.raises(ValueError, match="subjectId"):
        status_service.upsert_message(_payload(subject_id="missing-member"))


def test_status_service_rejects_team_mismatch_and_callsign_conflict(tmp_path) -> None:
    domain, status_service = _services(tmp_path)
    _seed_team(domain, member_ids=("member-1", "member-2"))
    domain.upsert_team({"uid": "team-2", "team_name": "Blue"})

    with pytest.raises(ValueError, match="teamId"):
        status_service.upsert_message(_payload(team_id="team-2"))

    status_service.upsert_message(_payload())
    with pytest.raises(ValueError, match="callsign"):
        status_service.upsert_message(
            _payload(callsign="ORANGE-1", subject_id="member-2")
        )


def test_status_service_supports_capability_alias_and_rejects_alias_conflict(tmp_path) -> None:
    domain, status_service = _services(tmp_path)
    _seed_team(domain)

    stored = status_service.upsert_message(
        {
            **_payload(),
            "capabilityStatus": "Yellow",
            "securityCapability": "Yellow",
        }
    )

    assert stored["capabilityStatus"] == "Yellow"
    assert stored["securityCapability"] == "Yellow"

    with pytest.raises(ValueError, match="capabilityStatus and securityCapability"):
        status_service.upsert_message(
            {
                **_payload(),
                "capabilityStatus": "Green",
                "securityCapability": "Red",
            }
        )


def test_status_service_team_summary_treats_expired_member_status_as_unknown(tmp_path) -> None:
    domain, status_service = _services(tmp_path)
    _seed_team(domain, member_ids=("member-1", "member-2"))

    expired_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    status_service.upsert_message(
        _payload(
            reported_at=expired_at,
            ttl_seconds=60,
            security_status="Red",
            capability_status="Red",
            preparedness_status="Red",
            medical_status="Red",
            mobility_status="Red",
            comms_status="Red",
        )
    )

    summary = status_service.get_team_summary("team-1")

    assert summary["memberCount"] == 2
    assert summary["securityStatus"] == "Unknown"
    assert summary["overallStatus"] == "Unknown"


def test_status_service_team_summary_uses_known_values_when_some_members_are_missing(tmp_path) -> None:
    domain, status_service = _services(tmp_path)
    _seed_team(domain, member_ids=("member-1", "member-2"))
    status_service.upsert_message(_payload())

    summary = status_service.get_team_summary("team-1")

    assert summary["securityStatus"] == "Green"
    assert summary["capabilityStatus"] == "Green"
    assert summary["overallStatus"] == "Green"


def test_status_service_team_orange_example_aggregates_to_red(tmp_path) -> None:
    domain, status_service = _services(tmp_path)
    _seed_team(
        domain,
        member_ids=("member-a", "member-b", "member-c", "member-d"),
        team_uid="team-orange",
    )

    status_service.upsert_message(
        _payload(
            callsign="A",
            subject_id="member-a",
            team_id="team-orange",
        )
    )
    status_service.upsert_message(
        _payload(
            callsign="B",
            subject_id="member-b",
            team_id="team-orange",
            security_status="Yellow",
            preparedness_status="Yellow",
            comms_status="Yellow",
        )
    )
    status_service.upsert_message(
        _payload(
            callsign="C",
            subject_id="member-c",
            team_id="team-orange",
            capability_status="Red",
            preparedness_status="Red",
            medical_status="Yellow",
            mobility_status="Yellow",
        )
    )

    summary = status_service.get_team_summary("team-orange")

    assert summary["securityStatus"] == "Yellow"
    assert summary["capabilityStatus"] == "Red"
    assert summary["preparednessStatus"] == "Red"
    assert summary["medicalStatus"] == "Yellow"
    assert summary["mobilityStatus"] == "Yellow"
    assert summary["commsStatus"] == "Yellow"
    assert summary["overallStatus"] == "Red"
