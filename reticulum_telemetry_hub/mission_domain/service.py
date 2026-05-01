"""Persistence-backed R3AKT mission/checklist domain services."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any
from typing import Callable

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from reticulum_telemetry_hub.api.storage_models import Base
from reticulum_telemetry_hub.mission_domain.enums import AssetStatus
from reticulum_telemetry_hub.mission_domain.enums import ChecklistMode
from reticulum_telemetry_hub.mission_domain.enums import ChecklistSyncState
from reticulum_telemetry_hub.mission_domain.enums import ChecklistSystemColumnKey
from reticulum_telemetry_hub.mission_domain.enums import ChecklistTaskStatus
from reticulum_telemetry_hub.mission_domain.enums import ChecklistUserTaskStatus
from reticulum_telemetry_hub.mission_domain.enums import enum_values
from reticulum_telemetry_hub.mission_domain.service_assets import MissionAssetMixin
from reticulum_telemetry_hub.mission_domain.service_changes_logs import (
    MissionChangeLogMixin,
)
from reticulum_telemetry_hub.mission_domain.service_checklist_csv import ChecklistCsvMixin
from reticulum_telemetry_hub.mission_domain.service_checklist_tasks import ChecklistTaskMixin
from reticulum_telemetry_hub.mission_domain.service_checklist_templates import (
    ChecklistTemplateMixin,
)
from reticulum_telemetry_hub.mission_domain.service_checklists import ChecklistCoreMixin
from reticulum_telemetry_hub.mission_domain.service_lifecycle import MissionLifecycleMixin
from reticulum_telemetry_hub.mission_domain.service_missions import MissionCrudMixin
from reticulum_telemetry_hub.mission_domain.service_missions_serialization import (
    MissionSerializationMixin,
)
from reticulum_telemetry_hub.mission_domain.service_skills_assignments import (
    MissionSkillAssignmentMixin,
)
from reticulum_telemetry_hub.mission_domain.service_team_members import (
    MissionTeamMemberMixin,
)
from reticulum_telemetry_hub.mission_domain.service_teams import MissionTeamMixin
from reticulum_telemetry_hub.mission_domain.service_validation import (
    MissionValidationMixin,
)


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


class MissionDomainService(  # pylint: disable=too-many-public-methods
    MissionLifecycleMixin,
    MissionValidationMixin,
    MissionSerializationMixin,
    MissionCrudMixin,
    MissionChangeLogMixin,
    MissionTeamMixin,
    MissionTeamMemberMixin,
    MissionAssetMixin,
    MissionSkillAssignmentMixin,
    ChecklistTemplateMixin,
    ChecklistCoreMixin,
    ChecklistCsvMixin,
    ChecklistTaskMixin,
):
    """Domain service for R3AKT mission/checklist objects."""

    def __init__(self, db_path: Path, *, event_retention_days: int = 90) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._mission_change_listeners: list[Callable[[dict[str, Any]], None]] = []
        self._engine = create_engine(
            f"sqlite:///{self._db_path}",
            connect_args={"check_same_thread": False, "timeout": 30},
            poolclass=QueuePool,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
        )
        self._enable_wal_mode()
        Base.metadata.create_all(self._engine)
        self._run_additive_migrations()
        self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False)
        self._event_retention_days = max(1, int(event_retention_days))

