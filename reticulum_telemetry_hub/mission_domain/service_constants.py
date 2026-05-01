"""Mission domain constants and datetime helpers."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from typing import Any

from reticulum_telemetry_hub.mission_domain.enums import AssetStatus
from reticulum_telemetry_hub.mission_domain.enums import ChecklistMode
from reticulum_telemetry_hub.mission_domain.enums import ChecklistSyncState
from reticulum_telemetry_hub.mission_domain.enums import ChecklistSystemColumnKey
from reticulum_telemetry_hub.mission_domain.enums import ChecklistTaskStatus
from reticulum_telemetry_hub.mission_domain.enums import ChecklistUserTaskStatus
from reticulum_telemetry_hub.mission_domain.enums import enum_values

CHECKLIST_USER_PENDING = ChecklistUserTaskStatus.PENDING.value
CHECKLIST_USER_COMPLETE = ChecklistUserTaskStatus.COMPLETE.value
CHECKLIST_TASK_PENDING = ChecklistTaskStatus.PENDING.value
CHECKLIST_TASK_COMPLETE = ChecklistTaskStatus.COMPLETE.value
CHECKLIST_TASK_COMPLETE_LATE = ChecklistTaskStatus.COMPLETE_LATE.value
CHECKLIST_TASK_LATE = ChecklistTaskStatus.LATE.value
CHECKLIST_MODE_ONLINE = ChecklistMode.ONLINE.value
CHECKLIST_MODE_OFFLINE = ChecklistMode.OFFLINE.value
CHECKLIST_SYNC_LOCAL_ONLY = ChecklistSyncState.LOCAL_ONLY.value
CHECKLIST_SYNC_UPLOAD_PENDING = ChecklistSyncState.UPLOAD_PENDING.value
CHECKLIST_SYNC_SYNCED = ChecklistSyncState.SYNCED.value
CHECKLIST_DEFAULT_DUE_STEP_MINUTES = 30
SYSTEM_COLUMN_KEY_DUE_RELATIVE_DTG = ChecklistSystemColumnKey.DUE_RELATIVE_DTG.value
ASSET_STATUS_AVAILABLE = AssetStatus.AVAILABLE.value
ASSET_STATUS_IN_USE = AssetStatus.IN_USE.value
ASSET_STATUS_LOST = AssetStatus.LOST.value
ASSET_STATUS_MAINTENANCE = AssetStatus.MAINTENANCE.value
ASSET_STATUS_RETIRED = AssetStatus.RETIRED.value
ALLOWED_ASSET_STATUSES = enum_values(AssetStatus)
MISSION_DELTA_CONTRACT_VERSION = "r3akt.mission.change.v1"
MISSION_CHANGE_LISTENER_KEY = "mission_change_notifications"
MISSION_EXPAND_KEYS = {
    "topic",
    "teams",
    "team_members",
    "assets",
    "mission_changes",
    "log_entries",
    "assignments",
    "checklists",
    "mission_rde",
}
MISSION_EXPAND_ALIASES = {
    "team": "teams",
    "members": "team_members",
    "member": "team_members",
    "team_members": "team_members",
    "teammembers": "team_members",
    "changes": "mission_changes",
    "change": "mission_changes",
    "logs": "log_entries",
    "log": "log_entries",
    "entries": "log_entries",
    "assignment": "assignments",
    "checklist": "checklists",
    "rde": "mission_rde",
    "all": "all",
}
DEFAULT_LOG_MISSION_UID = "mission-default"
DEFAULT_LOG_MISSION_NAME = "Mission Default"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_datetime(value: Any, *, default: datetime | None = None) -> datetime | None:
    if value is None:
        return default
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return default
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return default


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


__all__ = [
    "ALLOWED_ASSET_STATUSES",
    "ASSET_STATUS_AVAILABLE",
    "ASSET_STATUS_IN_USE",
    "ASSET_STATUS_LOST",
    "ASSET_STATUS_MAINTENANCE",
    "ASSET_STATUS_RETIRED",
    "CHECKLIST_DEFAULT_DUE_STEP_MINUTES",
    "CHECKLIST_MODE_OFFLINE",
    "CHECKLIST_MODE_ONLINE",
    "CHECKLIST_SYNC_LOCAL_ONLY",
    "CHECKLIST_SYNC_SYNCED",
    "CHECKLIST_SYNC_UPLOAD_PENDING",
    "CHECKLIST_TASK_COMPLETE",
    "CHECKLIST_TASK_COMPLETE_LATE",
    "CHECKLIST_TASK_LATE",
    "CHECKLIST_TASK_PENDING",
    "CHECKLIST_USER_COMPLETE",
    "CHECKLIST_USER_PENDING",
    "DEFAULT_LOG_MISSION_NAME",
    "DEFAULT_LOG_MISSION_UID",
    "MISSION_CHANGE_LISTENER_KEY",
    "MISSION_DELTA_CONTRACT_VERSION",
    "MISSION_EXPAND_ALIASES",
    "MISSION_EXPAND_KEYS",
    "SYSTEM_COLUMN_KEY_DUE_RELATIVE_DTG",
    "_as_datetime",
    "_dt",
    "_utcnow",
]


