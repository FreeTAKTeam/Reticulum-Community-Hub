"""Payload normalization and serialization for EAM status records."""

from __future__ import annotations

from typing import Any
from typing import Mapping

from sqlalchemy.orm import Session

from reticulum_telemetry_hub.api.storage_models import EmergencyActionMessageRecord
from reticulum_telemetry_hub.api.storage_models import R3aktTeamRecord
from reticulum_telemetry_hub.mission_domain.status_helpers import deserialize_source
from reticulum_telemetry_hub.mission_domain.status_helpers import dt as _dt
from reticulum_telemetry_hub.mission_domain.status_helpers import group_name_for_team
from reticulum_telemetry_hub.mission_domain.status_helpers import normalize_confidence
from reticulum_telemetry_hub.mission_domain.status_helpers import normalize_optional_text
from reticulum_telemetry_hub.mission_domain.status_helpers import normalize_reported_at
from reticulum_telemetry_hub.mission_domain.status_helpers import normalize_source
from reticulum_telemetry_hub.mission_domain.status_helpers import normalize_status as _normalize_status
from reticulum_telemetry_hub.mission_domain.status_helpers import normalize_ttl


class StatusPayloadMixin:
    """Normalize inbound EAM payloads and serialize stored records."""

    def _normalize_payload(
        self, payload: Mapping[str, Any], *, expected_callsign: str | None = None
    ) -> dict[str, Any]:
        """Normalize and validate an incoming REM-compatible EAM payload."""

        normalized = dict(payload or {})

        callsign = str(normalized.get("callsign") or expected_callsign or "").strip()
        if not callsign:
            raise ValueError("callsign is required")
        if expected_callsign is not None and callsign != str(expected_callsign).strip():
            raise ValueError("callsign in body must match the path callsign")

        team_member_uid = str(normalized.get("team_member_uid") or "").strip()
        if not team_member_uid:
            raise ValueError("team_member_uid is required")
        team_uid = str(normalized.get("team_uid") or "").strip()
        if not team_uid:
            raise ValueError("team_uid is required")

        reported_at = normalize_reported_at(normalized.get("reported_at"))
        ttl_seconds = normalize_ttl(normalized.get("ttl_seconds"))
        confidence = normalize_confidence(normalized.get("confidence"))
        source = normalize_source(normalized.get("source"))

        return {
            "eam_uid": normalize_optional_text(normalized.get("eam_uid")),
            "callsign": callsign,
            "group_name": normalize_optional_text(normalized.get("group_name")),
            "team_member_uid": team_member_uid,
            "team_uid": team_uid,
            "reported_by": normalize_optional_text(normalized.get("reported_by")),
            "reported_at": reported_at,
            "notes": normalize_optional_text(normalized.get("notes")),
            "confidence": confidence,
            "ttl_seconds": ttl_seconds,
            "source": source,
            "security_status": _normalize_status(
                normalized.get("security_status"),
                field_name="security_status",
            ),
            "capability_status": _normalize_status(
                normalized.get("capability_status"),
                field_name="capability_status",
            ),
            "preparedness_status": _normalize_status(
                normalized.get("preparedness_status"),
                field_name="preparedness_status",
            ),
            "medical_status": _normalize_status(
                normalized.get("medical_status"),
                field_name="medical_status",
            ),
            "mobility_status": _normalize_status(
                normalized.get("mobility_status"),
                field_name="mobility_status",
            ),
            "comms_status": _normalize_status(
                normalized.get("comms_status"),
                field_name="comms_status",
            ),
        }

    def _serialize_message(
        self, session: Session, row: EmergencyActionMessageRecord
    ) -> dict[str, Any]:
        """Serialize a snapshot into the REM-compatible API shape."""

        team_row = session.get(R3aktTeamRecord, str(row.team_id or ""))
        return {
            "eam_uid": row.id,
            "callsign": row.callsign,
            "group_name": group_name_for_team(team_row, str(row.team_id or "")),
            "team_member_uid": row.subject_id,
            "team_uid": row.team_id,
            "reported_by": row.reported_by,
            "reported_at": _dt(row.reported_at),
            "overall_status": row.overall_status,
            "security_status": row.security_status,
            "capability_status": row.capability_status,
            "preparedness_status": row.preparedness_status,
            "medical_status": row.medical_status,
            "mobility_status": row.mobility_status,
            "comms_status": row.comms_status,
            "notes": row.notes,
            "confidence": row.confidence,
            "ttl_seconds": row.ttl_seconds,
            "source": deserialize_source(row.source),
        }
