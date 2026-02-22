"""R3AKT domain enum definitions and normalization helpers."""

from __future__ import annotations

from enum import Enum
from typing import Iterable


class MissionRole(str, Enum):
    """Mission role values from the R3AKT domain diagram."""

    MISSION_OWNER = "MISSION_OWNER"
    MISSION_SUBSCRIBER = "MISSION_SUBSCRIBER"
    MISSION_READONLY_SUBSCRIBER = "MISSION_READONLY_SUBSCRIBER"


class MissionStatus(str, Enum):
    """Mission status values from the R3AKT domain diagram."""

    MISSION_ACTIVE = "MISSION_ACTIVE"
    MISSION_PENDING = "MISSION_PENDING"
    MISSION_DELETED = "MISSION_DELETED"
    MISSION_COMPLETED_SUCCESS = "MISSION_COMPLETED_SUCCESS"
    MISSION_COMPLETED_FAILED = "MISSION_COMPLETED_FAILED"


class MissionChangeType(str, Enum):
    """Mission change types from the R3AKT domain diagram."""

    CREATE_MISSION = "CREATE_MISSION"
    DELETE_MISSION = "DELETE_MISSION"
    ADD_CONTENT = "ADD_CONTENT"
    REMOVE_CONTENT = "REMOVE_CONTENT"
    CREATE_DATA_FEED = "CREATE_DATA_FEED"
    DELETE_DATA_FEED = "DELETE_DATA_FEED"
    MAP_LAYER = "MAP_LAYER"
    SITREP_IMPORTED = "SITREP_IMPORTED"


class TeamRole(str, Enum):
    """Team member role values."""

    TEAM_MEMBER = "TEAM_MEMBER"
    TEAM_LEAD = "TEAM_LEAD"
    HQ = "HQ"
    SNIPER = "SNIPER"
    MEDIC = "MEDIC"
    FORWARD_OBSERVER = "FORWARD_OBSERVER"
    RTO = "RTO"
    K9 = "K9"


class TeamColor(str, Enum):
    """Team color values from the diagram."""

    YELLOW = "YELLOW"
    RED = "RED"
    BLUE = "BLUE"
    ORANGE = "ORANGE"
    MAGENTA = "MAGENTA"
    MAROON = "MAROON"
    PURPLE = "PURPLE"
    DARK_BLUE = "DARK_BLUE"
    CYAN = "CYAN"
    TEAL = "TEAL"
    GREEN = "GREEN"
    DARK_GREEN = "DARK_GREEN"
    BROWN = "BROWN"


class ChecklistStatus(str, Enum):
    """Checklist status values."""

    PENDING = "PENDING"
    COMPLETE = "COMPLETE"
    COMPLETE_LATE = "COMPLETE_LATE"
    LATE = "LATE"


class ChecklistTaskStatus(str, Enum):
    """Checklist task status values."""

    PENDING = "PENDING"
    COMPLETE = "COMPLETE"
    COMPLETE_LATE = "COMPLETE_LATE"
    LATE = "LATE"


class ChecklistUserTaskStatus(str, Enum):
    """Checklist user-set task status values."""

    PENDING = "PENDING"
    COMPLETE = "COMPLETE"


class ChecklistColumnType(str, Enum):
    """Checklist column type values."""

    SHORT_STRING = "SHORT_STRING"
    LONG_STRING = "LONG_STRING"
    INTEGER = "INTEGER"
    ACTUAL_TIME = "ACTUAL_TIME"
    RELATIVE_TIME = "RELATIVE_TIME"


class ChecklistMode(str, Enum):
    """Checklist mode values."""

    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


class ChecklistSyncState(str, Enum):
    """Checklist sync state values."""

    LOCAL_ONLY = "LOCAL_ONLY"
    UPLOAD_PENDING = "UPLOAD_PENDING"
    SYNCED = "SYNCED"


class ChecklistOriginType(str, Enum):
    """Checklist origin type values."""

    RCH_TEMPLATE = "RCH_TEMPLATE"
    BLANK_TEMPLATE = "BLANK_TEMPLATE"
    CSV_IMPORT = "CSV_IMPORT"
    EXISTING_TEMPLATE_CLONE = "EXISTING_TEMPLATE_CLONE"


class ChecklistSystemColumnKey(str, Enum):
    """Checklist system column keys."""

    DUE_RELATIVE_DTG = "DUE_RELATIVE_DTG"


class AssetStatus(str, Enum):
    """Asset lifecycle status values."""

    AVAILABLE = "AVAILABLE"
    IN_USE = "IN_USE"
    LOST = "LOST"
    MAINTENANCE = "MAINTENANCE"
    RETIRED = "RETIRED"


SKILL_LEVEL_MIN = 0
SKILL_LEVEL_MAX = 10
MISSION_PRIORITY_MIN = 0
MISSION_PRIORITY_MAX = 100


def enum_values(enum_cls: type[Enum]) -> set[str]:
    """Return the value set for ``enum_cls``."""

    return {str(member.value) for member in enum_cls}


def normalize_enum_value(
    value: object,
    *,
    field_name: str,
    allowed_values: Iterable[str],
    default: str | None = None,
    upper: bool = True,
) -> str:
    """Normalize and validate an enum-like string value."""

    if value is None:
        if default is None:
            raise ValueError(f"{field_name} is required")
        return default
    text = str(value).strip()
    if not text:
        if default is None:
            raise ValueError(f"{field_name} is required")
        return default
    if upper:
        text = text.upper()
    allowed = {str(item) for item in allowed_values}
    if text not in allowed:
        raise ValueError(f"{field_name} must be one of: {', '.join(sorted(allowed))}")
    return text

