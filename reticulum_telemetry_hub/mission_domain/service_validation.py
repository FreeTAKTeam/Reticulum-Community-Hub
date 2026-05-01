"""Mission domain validation and relationship helper methods."""
# ruff: noqa: F403,F405

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from reticulum_telemetry_hub.api.storage_models import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.enums import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.enums import normalize_enum_value
from reticulum_telemetry_hub.mission_domain.service_constants import _utcnow
from reticulum_telemetry_hub.mission_domain.service_constants import *  # noqa: F403


class MissionValidationMixin:
    """Mission domain validation and relationship helper methods."""

    @staticmethod
    def _ensure_mission_exists(session: Session, mission_uid: str) -> None:
        if session.get(R3aktMissionRecord, mission_uid) is None:
            raise ValueError(f"Mission '{mission_uid}' not found")

    @staticmethod
    def _ensure_default_log_mission(session: Session) -> str:
        """Ensure the synthetic default mission exists for missionless log entries."""

        mission = session.get(R3aktMissionRecord, DEFAULT_LOG_MISSION_UID)
        if mission is None:
            now = _utcnow()
            mission = R3aktMissionRecord(
                uid=DEFAULT_LOG_MISSION_UID,
                mission_name=DEFAULT_LOG_MISSION_NAME,
                description="Synthetic mission used for missionless log submissions.",
                mission_status=MissionStatus.MISSION_ACTIVE.value,
                created_at=now,
                updated_at=now,
            )
            session.add(mission)
            session.flush()
        return str(mission.uid)

    @staticmethod
    def _ensure_team_exists(session: Session, team_uid: str) -> None:
        if session.get(R3aktTeamRecord, team_uid) is None:
            raise ValueError(f"Team '{team_uid}' not found")

    @staticmethod
    def _ensure_team_member_uid_exists(session: Session, team_member_uid: str) -> None:
        if session.get(R3aktTeamMemberRecord, team_member_uid) is None:
            raise ValueError(f"Team member '{team_member_uid}' not found")

    @staticmethod
    def _ensure_team_member_identity_exists(session: Session, rns_identity: str) -> None:
        row = (
            session.query(R3aktTeamMemberRecord.uid)
            .filter(R3aktTeamMemberRecord.rns_identity == rns_identity)
            .first()
        )
        if row is None:
            raise ValueError(
                f"Team member identity '{rns_identity}' not found"
            )

    @staticmethod
    def _ensure_skill_exists(session: Session, skill_uid: str) -> None:
        if session.get(R3aktSkillRecord, skill_uid) is None:
            raise ValueError(f"Skill '{skill_uid}' not found")

    @staticmethod
    def _ensure_asset_exists(session: Session, asset_uid: str) -> None:
        if session.get(R3aktAssetRecord, asset_uid) is None:
            raise ValueError(f"Asset '{asset_uid}' not found")

    @staticmethod
    def _ensure_task_exists(session: Session, task_uid: str) -> None:
        if session.get(R3aktChecklistTaskRecord, task_uid) is None:
            raise ValueError(f"Task '{task_uid}' not found")

    @staticmethod
    def _ensure_marker_exists(session: Session, marker_ref: str) -> None:
        value = str(marker_ref or "").strip()
        if not value:
            raise ValueError("marker reference cannot be empty")
        row = (
            session.query(MarkerRecord.id)
            .filter(
                (MarkerRecord.id == value)
                | (MarkerRecord.object_destination_hash == value)
            )
            .first()
        )
        if row is None:
            raise ValueError(f"Marker '{value}' not found")

    @staticmethod
    def _normalize_string_list(value: Any, *, field_name: str) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError(f"{field_name} must be a list")
        items: list[str] = []
        for item in value:
            text = str(item).strip()
            if not text:
                continue
            items.append(text)
        return items

    @staticmethod
    def _normalize_asset_status(value: Any, *, default: str) -> str:
        return normalize_enum_value(
            value,
            field_name="status",
            allowed_values=ALLOWED_ASSET_STATUSES,
            default=default,
        )

    @staticmethod
    def _normalize_optional_enum(
        value: Any,
        *,
        field_name: str,
        allowed_values: set[str],
        current: str | None = None,
    ) -> str | None:
        if value is None:
            return current
        if str(value).strip() == "":
            return current
        return normalize_enum_value(
            value,
            field_name=field_name,
            allowed_values=allowed_values,
            default=current,
        )

    @staticmethod
    def _normalize_integer(
        value: Any,
        *,
        field_name: str,
        minimum: int,
        maximum: int,
        default: int | None = None,
    ) -> int | None:
        if value is None:
            return default
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be an integer") from exc
        if normalized < minimum or normalized > maximum:
            raise ValueError(f"{field_name} must be between {minimum} and {maximum}")
        return normalized

    @staticmethod
    def _normalize_identity(value: Any, *, field_name: str) -> str:
        text = str(value or "").strip().lower()
        if not text:
            raise ValueError(f"{field_name} is required")
        return text

    @staticmethod
    def _normalize_task_status(value: Any, *, current: str | None = None) -> str:
        return normalize_enum_value(
            value,
            field_name="status",
            allowed_values=enum_values(ChecklistTaskStatus),
            default=current or CHECKLIST_TASK_PENDING,
        )
    @staticmethod
    def _topic_payload(session: Session, topic_id: str | None) -> dict[str, Any] | None:
        if not topic_id:
            return None
        topic = session.get(TopicRecord, topic_id)
        if topic is None:
            return None
        return {
            "topic_id": topic.id,
            "topic_name": topic.name,
            "topic_path": topic.path,
            "topic_description": topic.description or "",
        }

    @staticmethod
    def _mission_children(session: Session, mission_uid: str) -> list[str]:
        rows = (
            session.query(R3aktMissionRecord.uid)
            .filter(R3aktMissionRecord.parent_uid == mission_uid)
            .order_by(R3aktMissionRecord.created_at.asc())
            .all()
        )
        return [str(row[0]) for row in rows]

    @staticmethod
    def _mission_zone_ids(session: Session, mission_uid: str) -> list[str]:
        rows = (
            session.query(R3aktMissionZoneLinkRecord.zone_id)
            .filter(R3aktMissionZoneLinkRecord.mission_uid == mission_uid)
            .order_by(R3aktMissionZoneLinkRecord.created_at.asc())
            .all()
        )
        return [str(row[0]) for row in rows]

    @staticmethod
    def _mission_marker_ids(session: Session, mission_uid: str) -> list[str]:
        rows = (
            session.query(R3aktMissionMarkerLinkRecord.marker_id)
            .filter(R3aktMissionMarkerLinkRecord.mission_uid == mission_uid)
            .order_by(R3aktMissionMarkerLinkRecord.created_at.asc())
            .all()
        )
        return [str(row[0]) for row in rows]

    @staticmethod
    def _dedupe_non_empty(values: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for raw in values:
            text = str(raw or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            normalized.append(text)
        return normalized

    @staticmethod
    def _team_mission_ids(session: Session, team_uid: str) -> list[str]:
        linked_rows = (
            session.query(R3aktMissionTeamLinkRecord.mission_uid)
            .filter(R3aktMissionTeamLinkRecord.team_uid == team_uid)
            .order_by(R3aktMissionTeamLinkRecord.created_at.asc())
            .all()
        )
        mission_uids = [str(row[0]) for row in linked_rows]
        team_row = session.get(R3aktTeamRecord, team_uid)
        if team_row is not None and team_row.mission_uid:
            mission_uids.append(str(team_row.mission_uid))
        return MissionValidationMixin._dedupe_non_empty(mission_uids)

    @staticmethod
    def _mission_team_uids(session: Session, mission_uid: str) -> list[str]:
        linked_rows = (
            session.query(R3aktMissionTeamLinkRecord.team_uid)
            .filter(R3aktMissionTeamLinkRecord.mission_uid == mission_uid)
            .order_by(R3aktMissionTeamLinkRecord.created_at.asc())
            .all()
        )
        team_uids = [str(row[0]) for row in linked_rows]
        legacy_rows = (
            session.query(R3aktTeamRecord.uid)
            .filter(R3aktTeamRecord.mission_uid == mission_uid)
            .order_by(R3aktTeamRecord.created_at.asc())
            .all()
        )
        team_uids.extend(str(row[0]) for row in legacy_rows)
        return MissionValidationMixin._dedupe_non_empty(team_uids)

    @staticmethod
    def _team_member_mission_uids(session: Session, team_member_uid: str) -> list[str]:
        team_member = session.get(R3aktTeamMemberRecord, team_member_uid)
        if team_member is None or not team_member.team_uid:
            return []
        return MissionValidationMixin._team_mission_ids(session, str(team_member.team_uid))

    @staticmethod
    def _checklist_mission_uid(session: Session, checklist_uid: str) -> str | None:
        checklist = session.get(R3aktChecklistRecord, checklist_uid)
        if checklist is None:
            return None
        mission_uid = str(checklist.mission_uid or "").strip()
        return mission_uid or None

    @staticmethod
    def _set_team_mission_links(
        session: Session, *, team_uid: str, mission_uids: list[str]
    ) -> None:
        (
            session.query(R3aktMissionTeamLinkRecord)
            .filter(R3aktMissionTeamLinkRecord.team_uid == team_uid)
            .delete(synchronize_session=False)
        )
        for mission_uid in mission_uids:
            session.add(
                R3aktMissionTeamLinkRecord(
                    link_uid=uuid.uuid4().hex,
                    mission_uid=mission_uid,
                    team_uid=team_uid,
                )
            )

    @staticmethod
    def _mission_rde(session: Session, mission_uid: str) -> str | None:
        row = session.get(R3aktMissionRdeRecord, mission_uid)
        if row is None:
            return None
        return row.role

    @staticmethod
    def _normalize_mission_expand(expand: Any) -> set[str]:
        tokens: set[str] = set()
        if expand is None:
            return tokens

        raw_values: list[Any]
        if isinstance(expand, str):
            raw_values = [item.strip() for item in expand.split(",")]
        elif isinstance(expand, (list, tuple, set)):
            raw_values = list(expand)
        else:
            raw_values = [expand]

        for item in raw_values:
            token = str(item or "").strip().lower()
            if not token:
                continue
            mapped = MISSION_EXPAND_ALIASES.get(token, token)
            if mapped == "all":
                tokens.update(MISSION_EXPAND_KEYS)
                continue
            if mapped in MISSION_EXPAND_KEYS:
                tokens.add(mapped)
        return tokens

