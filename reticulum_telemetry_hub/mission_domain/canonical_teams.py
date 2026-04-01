"""Canonical REM color-team identifiers shared with the hub."""

from __future__ import annotations

from typing import Any
from typing import Mapping

from reticulum_telemetry_hub.mission_domain.enums import TeamColor
from reticulum_telemetry_hub.mission_domain.enums import enum_values
from reticulum_telemetry_hub.mission_domain.enums import normalize_enum_value


CANONICAL_COLOR_TEAM_UIDS: dict[str, str] = {
    "YELLOW": "d6b6e188b910d6bdd24d04b7a7ec5444",
    "RED": "65ce79a3a3e4b51ec0ec52d1d3d2b0b9",
    "BLUE": "43341e5c822d99857fa6e8641f2ca9c0",
    "ORANGE": "a83eb640e4c4884be14831e3d7ef5ae0",
    "MAGENTA": "7ac50a910f42b06cd9cb68dad3def681",
    "MAROON": "372824ef4f15881291455562f7570233",
    "PURPLE": "4bf2a1d2217c8668942658137f2a6824",
    "DARK_BLUE": "cbb35fc9a8f5a91d7bd2b5e5b644edcd",
    "CYAN": "d4cd5030b68df059ec6beabe416dd6a6",
    "TEAL": "4d7a7a974beec395bf83491604768499",
    "GREEN": "612a32262163b73a80eca944c2158546",
    "DARK_GREEN": "341653613d4c76d56bee99c1f38177b1",
    "BROWN": "4efe72ac30f5b85142fdcab6d96c7631",
}

CANONICAL_TEAM_UID_TO_COLOR: dict[str, str] = {
    uid: color for color, uid in CANONICAL_COLOR_TEAM_UIDS.items()
}


def normalize_team_color_name(value: object) -> str | None:
    """Normalize a team color token when it matches the REM canonical set."""

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return normalize_enum_value(
            text,
            field_name="team_color",
            allowed_values=enum_values(TeamColor),
            default=None,
        )
    except ValueError:
        return None


def canonical_team_for_uid(team_uid: object) -> dict[str, str] | None:
    """Return canonical metadata when ``team_uid`` is a REM color team."""

    normalized_uid = str(team_uid or "").strip()
    color = CANONICAL_TEAM_UID_TO_COLOR.get(normalized_uid)
    if color is None:
        return None
    return {
        "uid": normalized_uid,
        "color": color,
        "team_name": color,
        "group_name": color,
    }


def canonical_team_for_color(color: object) -> dict[str, str] | None:
    """Return canonical metadata when ``color`` is a REM canonical color."""

    normalized_color = normalize_team_color_name(color)
    if normalized_color is None:
        return None
    return {
        "uid": CANONICAL_COLOR_TEAM_UIDS[normalized_color],
        "color": normalized_color,
        "team_name": normalized_color,
        "group_name": normalized_color,
    }


def canonical_team_from_payload(payload: Mapping[str, Any]) -> dict[str, str] | None:
    """Resolve canonical REM team metadata from a mission/team payload."""

    by_uid = canonical_team_for_uid(payload.get("uid"))
    if by_uid is not None:
        return by_uid
    for field_name in ("color", "team_name", "name", "group_name"):
        resolved = canonical_team_for_color(payload.get(field_name))
        if resolved is not None:
            return resolved
    return None
