from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone

import pytest

from reticulum_telemetry_hub.mission_domain import EmergencyActionMessageService
from reticulum_telemetry_hub.mission_domain import MissionDomainService
from reticulum_telemetry_hub.mission_domain.canonical_teams import CANONICAL_COLOR_TEAM_UIDS


def _services(tmp_path) -> tuple[MissionDomainService, EmergencyActionMessageService]:
    db_path = tmp_path / "eam.sqlite"
    return MissionDomainService(db_path), EmergencyActionMessageService(db_path)


def _seed_team(
    domain: MissionDomainService,
    *,
    team_uid: str = "team-1",
    team_name: str = "Team",
    member_ids: tuple[str, ...] = ("member-1",),
) -> None:
    domain.upsert_team({"uid": team_uid, "team_name": team_name})
    for index, member_id in enumerate(member_ids, start=1):
        domain.upsert_team_member(
            {
                "uid": member_id,
                "team_uid": team_uid,
                "rns_identity": f"peer-{index}",
                "display_name": f"Peer {index}",
                "callsign": f"{team_name}-{index}",
            }
        )


def _payload(
    *,
    eam_uid: str | None = None,
    callsign: str = "ORANGE-1",
    team_member_uid: str = "member-1",
    team_uid: str = "team-1",
    group_name: str | None = "ORANGE",
    reported_by: str | None = "Operator",
    source: dict[str, str | None] | None = None,
    reported_at: datetime | None = None,
    ttl_seconds: int | None = None,
    confidence: float | None = None,
    security_status: str = "Green",
    capability_status: str = "Green",
    preparedness_status: str = "Green",
    medical_status: str = "Green",
    mobility_status: str = "Green",
    comms_status: str = "Green",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "eam_uid": eam_uid,
        "callsign": callsign,
        "team_member_uid": team_member_uid,
        "team_uid": team_uid,
        "group_name": group_name,
        "reported_by": reported_by,
        "reported_at": (reported_at or datetime.now(timezone.utc)).isoformat(),
        "security_status": security_status,
        "capability_status": capability_status,
        "preparedness_status": preparedness_status,
        "medical_status": medical_status,
        "mobility_status": mobility_status,
        "comms_status": comms_status,
    }
    if source is not None:
        payload["source"] = source
    if ttl_seconds is not None:
        payload["ttl_seconds"] = ttl_seconds
    if confidence is not None:
        payload["confidence"] = confidence
    return payload


def test_status_service_auto_creates_canonical_team_and_team_member(tmp_path) -> None:
    domain, status_service = _services(tmp_path)
    team_uid = CANONICAL_COLOR_TEAM_UIDS["ORANGE"]
    source = {"rns_identity": "peer-1", "display_name": "Peer 1"}

    created = status_service.upsert_message(
        _payload(
            team_uid=team_uid,
            group_name="ORANGE",
            team_member_uid="member-1",
            source=source,
            reported_by="Relay Operator",
        )
    )

    assert created["eam_uid"]
    assert created["callsign"] == "ORANGE-1"
    assert created["group_name"] == "ORANGE"
    assert created["team_uid"] == team_uid
    assert created["team_member_uid"] == "member-1"
    assert created["reported_by"] == "Relay Operator"
    assert created["reported_at"] is not None
    assert created["overall_status"] == "Green"
    assert created["source"] == source

    team = domain.get_team(team_uid)
    member = domain.get_team_member("member-1")

    assert team["uid"] == team_uid
    assert team["color"] == "ORANGE"
    assert team["team_name"] == "ORANGE"
    assert member["uid"] == "member-1"
    assert member["team_uid"] == team_uid
    assert member["rns_identity"] == "peer-1"
    assert member["display_name"] == "Relay Operator"
    assert member["callsign"] == "ORANGE-1"

    listed = status_service.list_messages(team_uid=team_uid)
    assert len(listed) == 1
    assert listed[0]["eam_uid"] == created["eam_uid"]
    assert listed[0]["group_name"] == "ORANGE"
    assert listed[0]["source"] == source


def test_status_service_roundtrips_source_and_group_name(tmp_path) -> None:
    _, status_service = _services(tmp_path)
    team_uid = CANONICAL_COLOR_TEAM_UIDS["YELLOW"]
    source = {"rns_identity": "peer-9", "display_name": "Peer 9"}

    created = status_service.upsert_message(
        _payload(
            eam_uid="eam-123",
            callsign="YELLOW-9",
            team_member_uid="member-9",
            team_uid=team_uid,
            group_name="YELLOW",
            reported_by="Leader Nine",
            source=source,
            confidence=0.75,
        )
    )

    fetched = status_service.get_message_by_callsign("YELLOW-9")

    assert created["eam_uid"] == "eam-123"
    assert created["group_name"] == "YELLOW"
    assert created["source"] == source
    assert created["confidence"] == 0.75
    assert fetched["eam_uid"] == "eam-123"
    assert fetched["group_name"] == "YELLOW"
    assert fetched["source"] == source
    assert fetched["reported_by"] == "Leader Nine"


def test_status_service_rejects_member_on_wrong_team(tmp_path) -> None:
    domain, status_service = _services(tmp_path)
    _seed_team(domain, team_uid="team-a", team_name="Alpha Squad")
    _seed_team(domain, team_uid="team-b", team_name="Bravo Squad", member_ids=("member-b",))

    with pytest.raises(ValueError, match="does not belong to team_uid"):
        status_service.upsert_message(
            _payload(
                callsign="ALPHA-1",
                team_member_uid="member-1",
                team_uid="team-b",
                group_name="team-b",
                source={"rns_identity": "peer-1", "display_name": "Peer 1"},
            )
        )


def test_status_service_rejects_unknown_noncanonical_team(tmp_path) -> None:
    _, status_service = _services(tmp_path)

    with pytest.raises(ValueError, match="does not map to a team"):
        status_service.upsert_message(
            _payload(
                callsign="NOVEMBER-1",
                team_member_uid="member-1",
                team_uid="team-unknown",
                group_name="NOVEMBER",
                source={"rns_identity": "peer-1", "display_name": "Peer 1"},
            )
        )


def test_status_service_rejects_callsign_conflict(tmp_path) -> None:
    domain, status_service = _services(tmp_path)
    _seed_team(
        domain,
        team_uid="team-1",
        team_name="Orange Squad",
        member_ids=("member-1", "member-2"),
    )

    status_service.upsert_message(
        _payload(
            callsign="ORANGE-1",
            team_member_uid="member-1",
            team_uid="team-1",
            group_name="ORANGE",
            source={"rns_identity": "peer-1", "display_name": "Peer 1"},
        )
    )

    with pytest.raises(ValueError, match="already assigned"):
        status_service.upsert_message(
            _payload(
                callsign="ORANGE-1",
                team_member_uid="member-2",
                team_uid="team-1",
                group_name="ORANGE",
                source={"rns_identity": "peer-2", "display_name": "Peer 2"},
            )
        )


def test_status_service_ttl_overall_status_and_summary_shape(tmp_path) -> None:
    domain, status_service = _services(tmp_path)
    team_uid = "team-1"
    _seed_team(
        domain,
        team_uid=team_uid,
        team_name="Orange Squad",
        member_ids=("member-1", "member-2"),
    )

    expired_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    status_service.upsert_message(
        _payload(
            callsign="ORANGE-1",
            team_member_uid="member-1",
            team_uid=team_uid,
            group_name="ORANGE",
            reported_at=expired_at,
            ttl_seconds=60,
            security_status="Red",
            capability_status="Red",
            preparedness_status="Red",
            medical_status="Red",
            mobility_status="Red",
            comms_status="Red",
            source={"rns_identity": "peer-1", "display_name": "Peer 1"},
        )
    )
    active = status_service.upsert_message(
        _payload(
            callsign="ORANGE-2",
            team_member_uid="member-2",
            team_uid=team_uid,
            group_name="ORANGE",
            security_status="Green",
            capability_status="Green",
            preparedness_status="Green",
            medical_status="Green",
            mobility_status="Green",
            comms_status="Green",
            source={"rns_identity": "peer-2", "display_name": "Peer 2"},
        )
    )

    listed = status_service.list_messages(team_uid=team_uid, overall_status="Green")
    summary = status_service.get_team_summary(team_uid)

    assert len(listed) == 1
    assert listed[0]["eam_uid"] == active["eam_uid"]
    assert listed[0]["callsign"] == "ORANGE-2"
    assert listed[0]["overall_status"] == "Green"
    assert listed[0]["source"] == {"rns_identity": "peer-2", "display_name": "Peer 2"}
    assert summary == {
        "team_uid": team_uid,
        "total": 1,
        "active_total": 1,
        "deleted_total": 0,
        "overall_status": "Green",
        "green_total": 1,
        "yellow_total": 0,
        "red_total": 0,
        "updated_at_ms": summary["updated_at_ms"],
    }
    assert isinstance(summary["updated_at_ms"], int)
    assert summary["updated_at_ms"] > 0


def test_status_service_team_summary_prefers_worst_active_status(tmp_path) -> None:
    domain, status_service = _services(tmp_path)
    team_uid = "team-orange"
    _seed_team(
        domain,
        team_uid=team_uid,
        team_name="Orange Squad",
        member_ids=("member-a", "member-b", "member-c", "member-d"),
    )

    status_service.upsert_message(
        _payload(
            callsign="A",
            team_member_uid="member-a",
            team_uid=team_uid,
            group_name="ORANGE",
            source={"rns_identity": "peer-a", "display_name": "Peer A"},
        )
    )
    status_service.upsert_message(
        _payload(
            callsign="B",
            team_member_uid="member-b",
            team_uid=team_uid,
            group_name="ORANGE",
            security_status="Yellow",
            preparedness_status="Yellow",
            comms_status="Yellow",
            source={"rns_identity": "peer-b", "display_name": "Peer B"},
        )
    )
    status_service.upsert_message(
        _payload(
            callsign="C",
            team_member_uid="member-c",
            team_uid=team_uid,
            group_name="ORANGE",
            capability_status="Red",
            preparedness_status="Red",
            medical_status="Yellow",
            mobility_status="Yellow",
            source={"rns_identity": "peer-c", "display_name": "Peer C"},
        )
    )

    summary = status_service.get_team_summary(team_uid)

    assert summary["team_uid"] == team_uid
    assert summary["total"] == 3
    assert summary["active_total"] == 3
    assert summary["overall_status"] == "Red"
    assert summary["green_total"] == 1
    assert summary["yellow_total"] == 1
    assert summary["red_total"] == 1
