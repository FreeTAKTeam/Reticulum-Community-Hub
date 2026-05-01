"""Shared helpers for Emergency Action Message status handling."""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone
import json
from typing import Any
from typing import Mapping

from reticulum_telemetry_hub.api.storage_models import EmergencyActionMessageRecord
from reticulum_telemetry_hub.api.storage_models import R3aktTeamRecord
from reticulum_telemetry_hub.mission_domain.canonical_teams import canonical_team_for_color
from reticulum_telemetry_hub.mission_domain.canonical_teams import canonical_team_for_uid


ALLOWED_EAM_STATUSES = {"Green", "Yellow", "Red", "Unknown"}
STATUS_DIMENSION_FIELDS = (
    "security_status",
    "capability_status",
    "preparedness_status",
    "medical_status",
    "mobility_status",
    "comms_status",
)


def utcnow() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc)


def dt(value: datetime | None) -> str | None:
    """Return a JSON-friendly datetime string."""

    return value.isoformat() if value else None


def dt_ms(value: datetime | None) -> int:
    """Return a Unix timestamp in milliseconds."""

    resolved = value or utcnow()
    if resolved.tzinfo is None:
        resolved = resolved.replace(tzinfo=timezone.utc)
    else:
        resolved = resolved.astimezone(timezone.utc)
    return int(resolved.timestamp() * 1000)


def as_datetime(value: Any) -> datetime | None:
    """Normalize an ISO-8601 datetime-like value."""

    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_status(value: object, *, field_name: str) -> str:
    """Normalize a single status field into the canonical enum casing."""

    if value is None:
        return "Unknown"
    text = str(value).strip()
    if not text:
        return "Unknown"
    normalized = text.lower()
    mapping = {
        "green": "Green",
        "yellow": "Yellow",
        "red": "Red",
        "unknown": "Unknown",
    }
    if normalized not in mapping:
        raise ValueError(
            f"{field_name} must be one of: {', '.join(sorted(ALLOWED_EAM_STATUSES))}"
        )
    return mapping[normalized]


def aggregate_status(values: list[str]) -> str:
    """Aggregate a list of statuses using worst-of semantics."""

    normalized = [normalize_status(value, field_name="status") for value in values]
    if "Red" in normalized:
        return "Red"
    if "Yellow" in normalized:
        return "Yellow"
    known = [value for value in normalized if value != "Unknown"]
    if known and all(value == "Green" for value in known):
        return "Green"
    return "Unknown"


def normalize_optional_text(value: object) -> str | None:
    """Normalize optional text fields."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_reported_at(value: object) -> datetime:
    """Normalize the ``reported_at`` field."""

    if value is None or str(value).strip() == "":
        return utcnow()
    reported_at = as_datetime(value)
    if reported_at is None:
        raise ValueError("reported_at must be ISO-8601")
    return reported_at


def normalize_ttl(value: object) -> int | None:
    """Normalize ``ttl_seconds``."""

    if value is None or value == "":
        return None
    try:
        ttl_seconds = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("ttl_seconds must be an integer") from exc
    if ttl_seconds < 0:
        raise ValueError("ttl_seconds must be greater than or equal to 0")
    return ttl_seconds


def normalize_confidence(value: object) -> float | None:
    """Normalize ``confidence``."""

    if value is None or value == "":
        return None
    try:
        confidence = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence must be numeric") from exc
    if confidence < 0 or confidence > 1:
        raise ValueError("confidence must be between 0 and 1")
    return confidence


def normalize_source(value: object) -> dict[str, str | None] | None:
    """Normalize a REM EAM source payload."""

    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("source must be an object")
    rns_identity = str(value.get("rns_identity") or "").strip() or None
    display_name = str(value.get("display_name") or "").strip() or None
    if rns_identity is None and display_name is None:
        return None
    return {
        "rns_identity": rns_identity,
        "display_name": display_name,
    }


def is_expired(row: EmergencyActionMessageRecord, *, now: datetime | None = None) -> bool:
    """Return True when the snapshot is outside its TTL window."""

    if row.ttl_seconds is None:
        return False
    current_time = now or utcnow()
    reported_at = as_datetime(row.reported_at)
    if reported_at is None:
        return False
    return current_time >= reported_at + timedelta(seconds=int(row.ttl_seconds))


def serialize_source(source: Mapping[str, str | None] | None) -> str | None:
    """Serialize a source payload for storage."""

    if source is None:
        return None
    return json.dumps(
        {
            "rns_identity": source.get("rns_identity"),
            "display_name": source.get("display_name"),
        },
        sort_keys=True,
    )


def deserialize_source(source: str | None) -> dict[str, str | None] | None:
    """Deserialize a source payload from storage."""

    if source is None:
        return None
    text = str(source).strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"rns_identity": text, "display_name": None}
    if not isinstance(payload, dict):
        return None
    rns_identity = str(payload.get("rns_identity") or "").strip() or None
    display_name = str(payload.get("display_name") or "").strip() or None
    if rns_identity is None and display_name is None:
        return None
    return {
        "rns_identity": rns_identity,
        "display_name": display_name,
    }


def group_name_for_team(team_row: R3aktTeamRecord | None, team_uid: str) -> str | None:
    """Return the REM group name for a team row."""

    canonical_team = canonical_team_for_uid(team_uid)
    if canonical_team is not None:
        return canonical_team["group_name"]
    if team_row is None:
        return None
    if team_row is not None:
        if team_row.color:
            return str(team_row.color).strip()
        if team_row.team_name:
            return str(team_row.team_name).strip() or None
    return None


def resolve_team_row(session, team_uid: str, group_name: str | None) -> R3aktTeamRecord:
    """Return the referenced team, auto-provisioning canonical color teams."""

    canonical_team = canonical_team_for_uid(team_uid)
    if canonical_team is not None and group_name is not None:
        canonical_group = canonical_team_for_color(group_name)
        if canonical_group is None or canonical_group["uid"] != canonical_team["uid"]:
            raise ValueError(
                f"group_name '{group_name}' does not match canonical team_uid '{team_uid}'"
            )

    team_row = session.get(R3aktTeamRecord, team_uid)
    if team_row is not None:
        if canonical_team is not None:
            team_row.color = canonical_team["color"]
            team_row.team_name = canonical_team["team_name"]
        return team_row
    if canonical_team is None:
        raise ValueError(f"team_uid '{team_uid}' does not map to a team")

    team_row = R3aktTeamRecord(
        uid=canonical_team["uid"],
        mission_uid=None,
        color=canonical_team["color"],
        team_name=canonical_team["team_name"],
        team_description="",
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(team_row)
    session.flush()
    return team_row
