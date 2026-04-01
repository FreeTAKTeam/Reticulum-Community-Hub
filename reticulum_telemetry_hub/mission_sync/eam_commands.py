"""Helpers for southbound mission-sync Emergency Action Message commands."""

from __future__ import annotations

from typing import Any
from typing import Mapping

from reticulum_telemetry_hub.mission_domain import EmergencyActionMessageService


UPSERT_COMMAND = "mission.registry.eam.upsert"
LIST_COMMAND = "mission.registry.eam.list"
GET_COMMAND = "mission.registry.eam.get"
LATEST_COMMAND = "mission.registry.eam.latest"
DELETE_COMMAND = "mission.registry.eam.delete"
TEAM_SUMMARY_COMMAND = "mission.registry.eam.team.summary"

STATUS_FIELD_NAMES = (
    "security_status",
    "capability_status",
    "preparedness_status",
    "medical_status",
    "mobility_status",
    "comms_status",
)

DISALLOWED_FIELD_MESSAGES = {
    "subject_type": "subject_type is not supported southbound; EAM is member-scoped only",
    "subjectType": "subjectType is not supported southbound; EAM is member-scoped only",
    "subject_id": "subject_id is not supported southbound; use team_member_uid",
    "subjectId": "subjectId is not supported southbound; use team_member_uid",
    "teamId": "teamId is not supported southbound; use team_uid",
    "reportedAt": "reportedAt is not supported southbound; use reported_at",
    "reportedBy": "reportedBy is not supported southbound; use reported_by",
    "overall_status": "overall_status is computed server-side and is not accepted on writes",
    "overallStatus": "overallStatus is computed server-side and is not accepted on writes",
    "groupName": "groupName is not supported southbound; use group_name",
    "securityStatus": "securityStatus is not supported southbound; use security_status",
    "capabilityStatus": "capabilityStatus is not supported southbound; use capability_status",
    "preparednessStatus": "preparednessStatus is not supported southbound; use preparedness_status",
    "medicalStatus": "medicalStatus is not supported southbound; use medical_status",
    "mobilityStatus": "mobilityStatus is not supported southbound; use mobility_status",
    "commsStatus": "commsStatus is not supported southbound; use comms_status",
    "ttlSeconds": "ttlSeconds is not supported southbound; use ttl_seconds",
    "securityCapability": "securityCapability is not supported southbound; use capability_status",
}


class EmergencyActionMessageCommandError(Exception):
    """Raised when an EAM southbound command cannot be executed."""

    def __init__(self, reason_code: str, reason: str) -> None:
        """Initialize the error."""

        super().__init__(reason)
        self.reason_code = reason_code
        self.reason = reason


def execute_eam_command(
    command_type: str,
    args: Mapping[str, Any],
    *,
    status_service: EmergencyActionMessageService,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Execute an EAM mission-sync command."""

    if command_type == LIST_COMMAND:
        payload = _list_eams(args, status_service=status_service)
        return payload, "mission.registry.eam.listed", payload
    if command_type == UPSERT_COMMAND:
        payload = _upsert_eam(args, status_service=status_service)
        return payload, "mission.registry.eam.upserted", payload
    if command_type == GET_COMMAND:
        payload = _get_eam(args, status_service=status_service)
        return payload, "mission.registry.eam.retrieved", payload
    if command_type == LATEST_COMMAND:
        payload = _get_latest_eam(args, status_service=status_service)
        return payload, "mission.registry.eam.latest_retrieved", payload
    if command_type == DELETE_COMMAND:
        payload = _delete_eam(args, status_service=status_service)
        return payload, "mission.registry.eam.deleted", payload
    if command_type == TEAM_SUMMARY_COMMAND:
        payload = _team_summary(args, status_service=status_service)
        return payload, "mission.registry.eam.team_summary.retrieved", payload
    raise EmergencyActionMessageCommandError(
        "unsupported_operation",
        f"Unsupported Emergency Action Message command '{command_type}'",
    )


def _list_eams(
    args: Mapping[str, Any],
    *,
    status_service: EmergencyActionMessageService,
) -> dict[str, Any]:
    """List EAM snapshots."""

    _reject_disallowed_fields(args)
    team_uid = _optional_text(args, "team_uid")
    overall_status = _optional_text(args, "overall_status")
    snapshots = status_service.list_messages(
        team_uid=team_uid,
        overall_status=overall_status,
    )
    return {"eams": [dict(item) for item in snapshots]}


def _upsert_eam(
    args: Mapping[str, Any],
    *,
    status_service: EmergencyActionMessageService,
) -> dict[str, Any]:
    """Create or update an EAM snapshot."""

    _reject_disallowed_fields(args)
    payload: dict[str, Any] = {
        "callsign": _required_text(args, "callsign"),
        "eam_uid": _optional_text(args, "eam_uid"),
        "group_name": _optional_text(args, "group_name"),
        "team_member_uid": _required_text(args, "team_member_uid"),
        "team_uid": _required_text(args, "team_uid"),
    }
    reported_by = _optional_text(args, "reported_by")
    if reported_by is not None:
        payload["reported_by"] = reported_by
    reported_at = _optional_text(args, "reported_at")
    if reported_at is not None:
        payload["reported_at"] = reported_at
    notes = _optional_text(args, "notes")
    if notes is not None:
        payload["notes"] = notes
    source = args.get("source")
    if source is not None:
        payload["source"] = source

    confidence = args.get("confidence")
    if confidence is not None:
        payload["confidence"] = confidence
    ttl_seconds = args.get("ttl_seconds")
    if ttl_seconds is not None:
        payload["ttl_seconds"] = ttl_seconds

    for field_name in STATUS_FIELD_NAMES:
        if field_name in args:
            payload[field_name] = args.get(field_name)

    snapshot = status_service.upsert_message(payload)
    return {"eam": dict(snapshot)}


def _get_eam(
    args: Mapping[str, Any],
    *,
    status_service: EmergencyActionMessageService,
) -> dict[str, Any]:
    """Fetch a snapshot by callsign."""

    _reject_disallowed_fields(args)
    callsign = _required_text(args, "callsign")
    try:
        snapshot = status_service.get_message_by_callsign(callsign)
    except KeyError as exc:
        raise EmergencyActionMessageCommandError("not_found", str(exc)) from exc
    return {"eam": dict(snapshot)}


def _get_latest_eam(
    args: Mapping[str, Any],
    *,
    status_service: EmergencyActionMessageService,
) -> dict[str, Any]:
    """Fetch the latest snapshot by team member UID."""

    _reject_disallowed_fields(args)
    team_member_uid = _required_text(args, "team_member_uid")
    try:
        snapshot = status_service.get_latest_message(team_member_uid)
    except KeyError as exc:
        raise EmergencyActionMessageCommandError("not_found", str(exc)) from exc
    return {"eam": dict(snapshot)}


def _delete_eam(
    args: Mapping[str, Any],
    *,
    status_service: EmergencyActionMessageService,
) -> dict[str, Any]:
    """Delete a snapshot by callsign."""

    _reject_disallowed_fields(args)
    callsign = _required_text(args, "callsign")
    try:
        snapshot = status_service.delete_message(callsign)
    except KeyError as exc:
        raise EmergencyActionMessageCommandError("not_found", str(exc)) from exc
    return {"eam": dict(snapshot)}


def _team_summary(
    args: Mapping[str, Any],
    *,
    status_service: EmergencyActionMessageService,
) -> dict[str, Any]:
    """Compute a team summary."""

    _reject_disallowed_fields(args)
    team_uid = _required_text(args, "team_uid")
    try:
        summary = status_service.get_team_summary(team_uid)
    except KeyError as exc:
        raise EmergencyActionMessageCommandError("not_found", str(exc)) from exc
    return {"summary": dict(summary)}


def _reject_disallowed_fields(args: Mapping[str, Any]) -> None:
    """Reject fields that are not supported on the southbound contract."""

    for field_name, message in DISALLOWED_FIELD_MESSAGES.items():
        if field_name in args:
            raise EmergencyActionMessageCommandError("invalid_payload", message)


def _required_text(args: Mapping[str, Any], field_name: str) -> str:
    """Return a required non-empty string."""

    value = _optional_text(args, field_name)
    if value is None:
        raise EmergencyActionMessageCommandError(
            "invalid_payload",
            f"{field_name} is required",
        )
    return value


def _optional_text(args: Mapping[str, Any], field_name: str) -> str | None:
    """Return an optional trimmed string."""

    if field_name not in args:
        return None
    value = args.get(field_name)
    if value is None:
        return None
    text = str(value).strip()
    return text or None
