"""R3AKT mission-domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Mission:
    """Mission aggregate root."""

    uid: str
    mission_name: str
    description: str = ""
    topic_id: str | None = None
    mission_status: str = "MISSION_ACTIVE"
    default_role: str | None = None
    owner_role: str | None = None
    invite_only: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class MissionChange:
    """Mission change-log entry."""

    uid: str
    mission_uid: str
    timestamp: datetime
    change_type: str | None = None
    notes: str | None = None
    team_member_rns_identity: str | None = None


@dataclass
class LogEntry:
    """Mission log entry."""

    entry_uid: str
    mission_uid: str
    content: str
    server_time: datetime
    client_time: datetime | None = None
    content_hashes: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


@dataclass
class Team:
    """Team metadata."""

    uid: str
    team_name: str
    mission_uid: str | None = None
    team_description: str = ""
    color: str | None = None


@dataclass
class TeamMember:
    """Team-member profile metadata."""

    uid: str
    team_uid: str | None
    rns_identity: str
    display_name: str
    role: str | None = None


@dataclass
class Asset:
    """Asset registry entry."""

    asset_uid: str
    name: str
    asset_type: str
    team_member_uid: str | None = None
    serial_number: str | None = None
    status: str = "AVAILABLE"
    location: str | None = None
    notes: str | None = None


@dataclass
class Skill:
    """Skill catalog entry."""

    skill_uid: str
    name: str
    category: str | None = None


@dataclass
class TeamMemberSkill:
    """Team-member skill mapping."""

    uid: str
    team_member_rns_identity: str
    skill_uid: str
    level: int = 0


@dataclass
class TaskSkillRequirement:
    """Task-level skill requirement."""

    uid: str
    task_uid: str
    skill_uid: str
    minimum_level: int = 0
    is_mandatory: bool = True


@dataclass
class ChecklistColumn:
    """Checklist column schema."""

    column_uid: str
    column_name: str
    display_order: int
    column_type: str
    column_editable: bool
    is_removable: bool
    system_key: str | None = None


@dataclass
class ChecklistCell:
    """Checklist task cell value."""

    cell_uid: str
    task_uid: str
    column_uid: str
    updated_at: datetime
    value: str | None = None
    updated_by_team_member_rns_identity: str | None = None


@dataclass
class ChecklistTask:
    """Checklist task row."""

    task_uid: str
    number: int
    user_status: str
    task_status: str
    line_break_enabled: bool
    is_late: bool
    due_dtg: datetime | None = None
    due_relative_minutes: int | None = None
    completed_at: datetime | None = None
    completed_by_team_member_rns_identity: str | None = None
    notes: str | None = None
    row_background_color: str | None = None
    cells: list[ChecklistCell] = field(default_factory=list)


@dataclass
class ChecklistTemplate:
    """Checklist template aggregate."""

    uid: str
    template_name: str
    description: str
    created_at: datetime
    created_by_team_member_rns_identity: str
    updated_at: datetime
    source_template_uid: str | None = None
    server_only: bool = True
    columns: list[ChecklistColumn] = field(default_factory=list)


@dataclass
class ChecklistFeedPublication:
    """Checklist publication into a mission feed."""

    publication_uid: str
    checklist_uid: str
    mission_feed_uid: str
    published_at: datetime
    published_by_team_member_rns_identity: str


@dataclass
class Checklist:
    """Checklist aggregate."""

    uid: str
    name: str
    description: str
    start_time: datetime
    mode: str
    sync_state: str
    origin_type: str
    created_at: datetime
    created_by_team_member_rns_identity: str
    updated_at: datetime
    checklist_status: str
    progress_percent: float
    counts: dict[str, int]
    columns: list[ChecklistColumn] = field(default_factory=list)
    tasks: list[ChecklistTask] = field(default_factory=list)
    mission_uid: str | None = None
    template_uid: str | None = None
    template_version: int | None = None
    template_name: str | None = None
    uploaded_at: datetime | None = None


@dataclass
class MissionTaskAssignment:
    """Mission task-assignment entry."""

    assignment_uid: str
    mission_uid: str
    task_uid: str
    team_member_rns_identity: str
    status: str
    assigned_at: datetime
    assets: list[str] = field(default_factory=list)
    assigned_by: str | None = None
    due_dtg: datetime | None = None
    notes: str | None = None


def json_safe(value: Any) -> Any:
    """Return a JSON-serializable representation of ``value``."""

    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    return value
