"""Mission serialization helpers."""
# ruff: noqa: F403,F405

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from reticulum_telemetry_hub.api.storage_models import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.enums import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.service_constants import _dt
from reticulum_telemetry_hub.mission_domain.service_constants import *  # noqa: F403


class MissionSerializationMixin:
    """Mission serialization helpers."""

    def _serialize_mission(
        self,
        session: Session,
        row: R3aktMissionRecord,
        *,
        expand_topic: bool = False,
        expand: set[str] | None = None,
    ) -> dict[str, Any]:
        expand_values = self._normalize_mission_expand(expand)
        include_topic = bool(expand_topic or "topic" in expand_values)
        payload = {
            "uid": row.uid,
            "mission_name": row.mission_name,
            "description": row.description or "",
            "topic_id": row.topic_id,
            "path": row.path,
            "classification": row.classification,
            "tool": row.tool,
            "keywords": list(row.keywords_json or []),
            "parent_uid": row.parent_uid,
            "children": self._mission_children(session, row.uid),
            "feeds": list(row.feeds_json or []),
            "zones": self._mission_zone_ids(session, row.uid),
            "markers": self._mission_marker_ids(session, row.uid),
            "password_hash": row.password_hash,
            "default_role": row.default_role,
            "mission_priority": row.mission_priority,
            "mission_status": row.mission_status,
            "owner_role": row.owner_role,
            "token": row.token,
            "invite_only": bool(row.invite_only),
            "expiration": _dt(row.expiration),
            "mission_rde_role": self._mission_rde(session, row.uid),
            "created_at": _dt(row.created_at),
            "updated_at": _dt(row.updated_at),
        }
        if include_topic:
            payload["topic"] = self._topic_payload(session, row.topic_id)

        team_uids: list[str] = []
        if any(item in expand_values for item in {"teams", "team_members", "assets"}):
            team_uids = self._mission_team_uids(session, row.uid)

        member_rows: list[R3aktTeamMemberRecord] = []
        if any(item in expand_values for item in {"team_members", "assets"}) and team_uids:
            member_rows = (
                session.query(R3aktTeamMemberRecord)
                .filter(R3aktTeamMemberRecord.team_uid.in_(team_uids))
                .order_by(R3aktTeamMemberRecord.display_name.asc())
                .all()
            )

        if "teams" in expand_values:
            if team_uids:
                team_rows = (
                    session.query(R3aktTeamRecord)
                    .filter(R3aktTeamRecord.uid.in_(team_uids))
                    .order_by(R3aktTeamRecord.team_name.asc())
                    .all()
                )
                payload["teams"] = [self._serialize_team(session, item) for item in team_rows]
            else:
                payload["teams"] = []

        if "team_members" in expand_values:
            payload["team_members"] = [
                self._serialize_team_member(session, item) for item in member_rows
            ]

        if "assets" in expand_values:
            member_uids = [str(item.uid) for item in member_rows]
            if member_uids:
                asset_rows = (
                    session.query(R3aktAssetRecord)
                    .filter(R3aktAssetRecord.team_member_uid.in_(member_uids))
                    .order_by(R3aktAssetRecord.name.asc())
                    .all()
                )
                payload["assets"] = [self._serialize_asset(item) for item in asset_rows]
            else:
                payload["assets"] = []

        if "mission_changes" in expand_values:
            mission_change_rows = (
                session.query(R3aktMissionChangeRecord)
                .filter(R3aktMissionChangeRecord.mission_uid == row.uid)
                .order_by(R3aktMissionChangeRecord.timestamp.desc())
                .all()
            )
            payload["mission_changes"] = [
                self._serialize_mission_change(item) for item in mission_change_rows
            ]

        if "log_entries" in expand_values:
            log_rows = (
                session.query(R3aktLogEntryRecord)
                .filter(R3aktLogEntryRecord.mission_uid == row.uid)
                .order_by(R3aktLogEntryRecord.server_time.desc())
                .all()
            )
            payload["log_entries"] = [self._serialize_log_entry(item) for item in log_rows]

        if "assignments" in expand_values:
            assignment_rows = (
                session.query(R3aktMissionTaskAssignmentRecord)
                .filter(R3aktMissionTaskAssignmentRecord.mission_uid == row.uid)
                .order_by(R3aktMissionTaskAssignmentRecord.assigned_at.desc())
                .all()
            )
            payload["assignments"] = [
                self._serialize_assignment(session, item) for item in assignment_rows
            ]

        if "checklists" in expand_values:
            checklist_rows = (
                session.query(R3aktChecklistRecord)
                .filter(R3aktChecklistRecord.mission_uid == row.uid)
                .order_by(R3aktChecklistRecord.created_at.desc())
                .all()
            )
            payload["checklists"] = [
                self._serialize_checklist(session, item) for item in checklist_rows
            ]

        if "mission_rde" in expand_values:
            rde_row = session.get(R3aktMissionRdeRecord, row.uid)
            payload["mission_rde"] = {
                "mission_uid": row.uid,
                "role": rde_row.role if rde_row is not None else None,
                "updated_at": _dt(rde_row.updated_at) if rde_row is not None else None,
            }
        return payload

    @staticmethod
    def _resolve_parent_uid(payload: dict[str, Any], current: str | None) -> str | None:
        if "parent_uid" in payload:
            raw_parent = payload.get("parent_uid")
        elif "parent" in payload:
            raw_parent = payload.get("parent")
            if isinstance(raw_parent, dict):
                raw_parent = raw_parent.get("uid")
        else:
            return current
        value = str(raw_parent or "").strip()
        return value or None

    @staticmethod
    def _ensure_parent_chain_is_acyclic(
        session: Session, *, mission_uid: str, parent_uid: str | None
    ) -> None:
        if parent_uid is None:
            return
        if parent_uid == mission_uid:
            raise ValueError("parent_uid cannot reference itself")
        seen: set[str] = {mission_uid}
        current = parent_uid
        while current:
            if current in seen:
                raise ValueError("mission parent relationship would create a cycle")
            seen.add(current)
            parent_row = session.get(R3aktMissionRecord, current)
            if parent_row is None:
                raise ValueError(f"Parent mission '{current}' not found")
            current = parent_row.parent_uid

