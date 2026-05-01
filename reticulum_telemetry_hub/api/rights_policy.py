"""Mission rights policy constants and helper serializers."""

from __future__ import annotations

from typing import Any

from reticulum_telemetry_hub.mission_domain.enums import MissionRole

from .rights_storage_models import MissionAccessAssignmentRecord
from .rights_storage_models import SubjectOperationGrantRecord
from .storage_models import R3aktMissionTeamLinkRecord
from .storage_models import R3aktTeamMemberClientLinkRecord
from .storage_models import R3aktTeamRecord


MISSION_READONLY_OPERATIONS = {
    "mission.join",
    "mission.leave",
    "mission.audit.read",
    "topic.read",
    "mission.content.read",
    "mission.zone.read",
    "mission.registry.mission.read",
    "mission.registry.log.read",
    "mission.registry.status.read",
    "mission.registry.team.read",
    "mission.registry.asset.read",
    "mission.registry.skill.read",
    "mission.registry.assignment.read",
    "checklist.read",
    "checklist.join",
}

MISSION_WRITE_OPERATIONS = MISSION_READONLY_OPERATIONS | {
    "mission.message.send",
    "topic.subscribe",
    "mission.content.write",
    "mission.zone.write",
    "mission.registry.log.write",
    "mission.registry.status.write",
    "mission.registry.assignment.write",
    "checklist.write",
    "checklist.upload",
    "checklist.feed.publish",
}

MISSION_OWNER_OPERATIONS = MISSION_WRITE_OPERATIONS | {
    "topic.create",
    "topic.write",
    "topic.delete",
    "mission.zone.delete",
    "mission.registry.mission.write",
    "mission.registry.team.write",
    "mission.registry.asset.write",
    "mission.registry.skill.write",
}

MISSION_ROLE_BUNDLES: dict[str, set[str]] = {
    MissionRole.MISSION_READONLY_SUBSCRIBER.value: set(MISSION_READONLY_OPERATIONS),
    MissionRole.MISSION_SUBSCRIBER.value: set(MISSION_WRITE_OPERATIONS),
    MissionRole.MISSION_OWNER.value: set(MISSION_OWNER_OPERATIONS),
}

SUPPORTED_OPERATIONS = sorted(
    {
        "mission.join",
        "mission.leave",
        "mission.audit.read",
        "mission.message.send",
        "topic.read",
        "topic.create",
        "topic.write",
        "topic.delete",
        "topic.subscribe",
        "mission.content.read",
        "mission.content.write",
        "mission.zone.read",
        "mission.zone.write",
        "mission.zone.delete",
        "mission.registry.mission.read",
        "mission.registry.mission.write",
        "mission.registry.log.read",
        "mission.registry.log.write",
        "mission.registry.status.read",
        "mission.registry.status.write",
        "mission.registry.team.read",
        "mission.registry.team.write",
        "mission.registry.asset.read",
        "mission.registry.asset.write",
        "mission.registry.skill.read",
        "mission.registry.skill.write",
        "mission.registry.assignment.read",
        "mission.registry.assignment.write",
        "checklist.template.read",
        "checklist.template.write",
        "checklist.template.delete",
        "checklist.read",
        "checklist.write",
        "checklist.join",
        "checklist.upload",
        "checklist.feed.publish",
        "r3akt",
    }
)


def serialize_operation_right(record: SubjectOperationGrantRecord) -> dict[str, Any]:
    """Serialize an operation grant row for API responses."""

    return {
        "grant_uid": record.grant_uid,
        "subject_type": record.subject_type,
        "subject_id": record.subject_id,
        "operation": record.operation,
        "scope_type": record.scope_type,
        "scope_id": record.scope_id,
        "granted": bool(record.granted),
        "granted_by": record.granted_by,
        "granted_at": record.granted_at.isoformat() if record.granted_at else None,
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def serialize_mission_access_assignment(
    record: MissionAccessAssignmentRecord,
) -> dict[str, Any]:
    """Serialize a mission access assignment row for API responses."""

    return {
        "assignment_uid": record.assignment_uid,
        "mission_uid": record.mission_uid,
        "subject_type": record.subject_type,
        "subject_id": record.subject_id,
        "role": record.role,
        "operations": sorted(MISSION_ROLE_BUNDLES.get(record.role, set())),
        "assigned_by": record.assigned_by,
        "assigned_at": record.assigned_at.isoformat() if record.assigned_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def normalize_subject_type(subject_type: str) -> str:
    """Normalize and validate a rights subject type."""

    normalized_subject_type = str(subject_type or "").strip().lower()
    if normalized_subject_type not in {"identity", "team_member"}:
        raise ValueError("subject_type must be one of: identity, team_member")
    return normalized_subject_type


def normalize_subject_id(subject_type: str, subject_id: str) -> str:
    """Normalize a rights subject identifier."""

    normalized_subject_type = normalize_subject_type(subject_type)
    normalized_subject_id = str(subject_id or "").strip()
    if not normalized_subject_id:
        raise ValueError("subject_id is required")
    if normalized_subject_type == "identity":
        return normalized_subject_id.lower()
    return normalized_subject_id


def normalize_mission_role(role: str) -> str:
    """Normalize and validate a mission access role."""

    normalized_role = str(role or "").strip().upper()
    if normalized_role not in MISSION_ROLE_BUNDLES:
        allowed = ", ".join(sorted(MISSION_ROLE_BUNDLES))
        raise ValueError(f"role must be one of: {allowed}")
    return normalized_role


def team_map(session) -> dict[str, R3aktTeamRecord]:
    """Return teams keyed by UID."""

    return {
        str(record.uid): record
        for record in session.query(R3aktTeamRecord).all()
    }


def mission_team_uids(session, mission_uid: str) -> list[str]:
    """Return team UIDs linked to a mission."""

    linked_rows = (
        session.query(R3aktMissionTeamLinkRecord.team_uid)
        .filter(R3aktMissionTeamLinkRecord.mission_uid == mission_uid)
        .all()
    )
    legacy_rows = (
        session.query(R3aktTeamRecord.uid)
        .filter(R3aktTeamRecord.mission_uid == mission_uid)
        .all()
    )
    return sorted(
        {
            str(row[0]).strip()
            for row in [*linked_rows, *legacy_rows]
            if str(row[0]).strip()
        }
    )


def client_links_by_member(session) -> dict[str, set[str]]:
    """Return client identity links keyed by team-member UID."""

    payload: dict[str, set[str]] = {}
    for link in session.query(R3aktTeamMemberClientLinkRecord).all():
        payload.setdefault(str(link.team_member_uid), set()).add(
            str(link.client_identity)
        )
    return payload
