"""Mission skill and assignment methods."""
# ruff: noqa: F403,F405

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from reticulum_telemetry_hub.api.storage_models import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.enums import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.service_constants import _as_datetime
from reticulum_telemetry_hub.mission_domain.service_constants import _dt
from reticulum_telemetry_hub.mission_domain.service_constants import _utcnow
from reticulum_telemetry_hub.mission_domain.service_constants import *  # noqa: F403


class MissionSkillAssignmentMixin:
    """Mission skill and assignment methods."""

    @staticmethod
    def _serialize_skill(row: R3aktSkillRecord) -> dict[str, Any]:
        return {
            "skill_uid": row.skill_uid,
            "name": row.name,
            "category": row.category,
            "description": row.description,
            "proficiency_scale": row.proficiency_scale,
            "created_at": _dt(row.created_at),
            "updated_at": _dt(row.updated_at),
        }

    def upsert_skill(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("skill_uid") or uuid.uuid4().hex)
        with self._session() as session:
            row = session.get(R3aktSkillRecord, uid)
            if row is None:
                row = R3aktSkillRecord(skill_uid=uid, name="Skill")
                session.add(row)
            row.name = str(payload.get("name") or row.name)
            row.category = payload.get("category") or row.category
            row.description = payload.get("description") or row.description
            row.proficiency_scale = payload.get("proficiency_scale") or row.proficiency_scale
            session.flush()
            data = self._serialize_skill(row)
            self._record_event(session, domain="mission", aggregate_type="skill", aggregate_uid=uid, event_type="skill.upserted", payload=data)
            return data

    def list_skills(self) -> list[dict[str, Any]]:
        with self._session() as session:
            return [self._serialize_skill(row) for row in session.query(R3aktSkillRecord).order_by(R3aktSkillRecord.name.asc()).all()]

    @staticmethod
    def _serialize_team_member_skill(row: R3aktTeamMemberSkillRecord) -> dict[str, Any]:
        return {
            "uid": row.uid,
            "team_member_rns_identity": row.team_member_rns_identity,
            "skill_uid": row.skill_uid,
            "level": int(row.level or 0),
            "validated_by": row.validated_by,
            "validated_at": _dt(row.validated_at),
            "expires_at": _dt(row.expires_at),
        }

    def upsert_team_member_skill(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("uid") or uuid.uuid4().hex)
        member = str(payload.get("team_member_rns_identity") or "").strip()
        skill_uid = str(payload.get("skill_uid") or "").strip()
        if not member or not skill_uid:
            raise ValueError("team_member_rns_identity and skill_uid are required")
        with self._session() as session:
            self._ensure_team_member_identity_exists(session, member)
            self._ensure_skill_exists(session, skill_uid)
            row = (
                session.query(R3aktTeamMemberSkillRecord)
                .filter(
                    R3aktTeamMemberSkillRecord.team_member_rns_identity == member,
                    R3aktTeamMemberSkillRecord.skill_uid == skill_uid,
                )
                .first()
            )
            if row is None:
                row = session.get(R3aktTeamMemberSkillRecord, uid)
            if row is None:
                row = R3aktTeamMemberSkillRecord(uid=uid, team_member_rns_identity=member, skill_uid=skill_uid, level=0)
                session.add(row)
            row.team_member_rns_identity = member
            row.skill_uid = skill_uid
            level = payload.get("level")
            row.level = int(
                self._normalize_integer(
                    level,
                    field_name="level",
                    minimum=SKILL_LEVEL_MIN,
                    maximum=SKILL_LEVEL_MAX,
                    default=int(row.level or 0),
                )
                or 0
            )
            row.validated_by = payload.get("validated_by") or row.validated_by
            row.validated_at = _as_datetime(payload.get("validated_at"), default=row.validated_at)
            row.expires_at = _as_datetime(payload.get("expires_at"), default=row.expires_at)
            if row.expires_at and row.validated_at and row.expires_at <= row.validated_at:
                raise ValueError("expires_at must be greater than validated_at")
            session.flush()
            data = self._serialize_team_member_skill(row)
            self._record_event(session, domain="mission", aggregate_type="team_member_skill", aggregate_uid=row.uid, event_type="team_member_skill.upserted", payload=data)
            return data

    def list_team_member_skills(self, team_member_rns_identity: str | None = None) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(R3aktTeamMemberSkillRecord)
            if team_member_rns_identity:
                query = query.filter(R3aktTeamMemberSkillRecord.team_member_rns_identity == team_member_rns_identity)
            return [self._serialize_team_member_skill(row) for row in query.order_by(R3aktTeamMemberSkillRecord.team_member_rns_identity.asc()).all()]

    @staticmethod
    def _serialize_task_skill_requirement(row: R3aktTaskSkillRequirementRecord) -> dict[str, Any]:
        return {
            "uid": row.uid,
            "task_uid": row.task_uid,
            "skill_uid": row.skill_uid,
            "minimum_level": int(row.minimum_level or 0),
            "is_mandatory": bool(row.is_mandatory),
        }

    def upsert_task_skill_requirement(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("uid") or uuid.uuid4().hex)
        task_uid = str(payload.get("task_uid") or "").strip()
        skill_uid = str(payload.get("skill_uid") or "").strip()
        if not task_uid or not skill_uid:
            raise ValueError("task_uid and skill_uid are required")
        with self._session() as session:
            self._ensure_task_exists(session, task_uid)
            self._ensure_skill_exists(session, skill_uid)
            row = (
                session.query(R3aktTaskSkillRequirementRecord)
                .filter(
                    R3aktTaskSkillRequirementRecord.task_uid == task_uid,
                    R3aktTaskSkillRequirementRecord.skill_uid == skill_uid,
                )
                .first()
            )
            if row is None:
                row = session.get(R3aktTaskSkillRequirementRecord, uid)
            if row is None:
                row = R3aktTaskSkillRequirementRecord(uid=uid, task_uid=task_uid, skill_uid=skill_uid, minimum_level=0, is_mandatory=True)
                session.add(row)
            row.task_uid = task_uid
            row.skill_uid = skill_uid
            minimum_level = payload.get("minimum_level")
            row.minimum_level = int(
                self._normalize_integer(
                    minimum_level,
                    field_name="minimum_level",
                    minimum=SKILL_LEVEL_MIN,
                    maximum=SKILL_LEVEL_MAX,
                    default=int(row.minimum_level or 0),
                )
                or 0
            )
            row.is_mandatory = bool(payload.get("is_mandatory", row.is_mandatory))
            session.flush()
            data = self._serialize_task_skill_requirement(row)
            self._record_event(session, domain="mission", aggregate_type="task_skill_requirement", aggregate_uid=row.uid, event_type="task_skill_requirement.upserted", payload=data)
            return data

    def list_task_skill_requirements(self, task_uid: str | None = None) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(R3aktTaskSkillRequirementRecord)
            if task_uid:
                query = query.filter(R3aktTaskSkillRequirementRecord.task_uid == task_uid)
            return [self._serialize_task_skill_requirement(row) for row in query.order_by(R3aktTaskSkillRequirementRecord.task_uid.asc()).all()]

    @staticmethod
    def _assignment_assets(
        session: Session,
        assignment_uid: str,
        fallback_assets: list[str] | None = None,
    ) -> list[str]:
        rows = (
            session.query(R3aktAssignmentAssetLinkRecord.asset_uid)
            .filter(R3aktAssignmentAssetLinkRecord.assignment_uid == assignment_uid)
            .order_by(R3aktAssignmentAssetLinkRecord.created_at.asc())
            .all()
        )
        if rows:
            return [str(row[0]) for row in rows]
        return list(fallback_assets or [])

    def _serialize_assignment(
        self, session: Session, row: R3aktMissionTaskAssignmentRecord
    ) -> dict[str, Any]:
        return {
            "assignment_uid": row.assignment_uid,
            "mission_uid": row.mission_uid,
            "task_uid": row.task_uid,
            "team_member_rns_identity": row.team_member_rns_identity,
            "assigned_by": row.assigned_by,
            "assigned_at": _dt(row.assigned_at),
            "due_dtg": _dt(row.due_dtg),
            "status": row.status,
            "notes": row.notes,
            "assets": self._assignment_assets(
                session,
                row.assignment_uid,
                fallback_assets=list(row.assets_json or []),
            ),
        }

    def upsert_assignment(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("assignment_uid") or uuid.uuid4().hex)
        mission_uid = str(payload.get("mission_uid") or payload.get("mission_id") or "").strip()
        task_uid = str(payload.get("task_uid") or "").strip()
        member = str(payload.get("team_member_rns_identity") or "").strip()
        if not mission_uid or not task_uid or not member:
            raise ValueError("mission_uid, task_uid and team_member_rns_identity are required")
        with self._session() as session:
            self._ensure_mission_exists(session, mission_uid)
            self._ensure_task_exists(session, task_uid)
            self._ensure_team_member_identity_exists(session, member)
            assets = list(payload.get("assets") or [])
            for asset_uid in assets:
                self._ensure_asset_exists(session, str(asset_uid))
            row = session.get(R3aktMissionTaskAssignmentRecord, uid)
            if row is None:
                row = R3aktMissionTaskAssignmentRecord(assignment_uid=uid, mission_uid=mission_uid, task_uid=task_uid, team_member_rns_identity=member, status=CHECKLIST_TASK_PENDING)
                session.add(row)
            row.mission_uid = mission_uid
            row.task_uid = task_uid
            row.team_member_rns_identity = member
            row.assigned_by = payload.get("assigned_by") or row.assigned_by
            row.assigned_at = _as_datetime(payload.get("assigned_at"), default=row.assigned_at or _utcnow()) or _utcnow()
            row.due_dtg = _as_datetime(payload.get("due_dtg"), default=row.due_dtg)
            row.status = self._normalize_task_status(
                payload.get("status"),
                current=row.status,
            )
            row.notes = payload.get("notes") or row.notes
            if payload.get("assets") is not None:
                row.assets_json = assets
                (
                    session.query(R3aktAssignmentAssetLinkRecord)
                    .filter(R3aktAssignmentAssetLinkRecord.assignment_uid == uid)
                    .delete(synchronize_session=False)
                )
                for asset_uid in assets:
                    session.add(
                        R3aktAssignmentAssetLinkRecord(
                            link_uid=uuid.uuid4().hex,
                            assignment_uid=uid,
                            asset_uid=str(asset_uid),
                        )
                    )
            session.flush()
            data = self._serialize_assignment(session, row)
            self._record_event(session, domain="mission", aggregate_type="assignment", aggregate_uid=uid, event_type="assignment.upserted", payload=data)
            task_delta = {
                "op": "assignment_upsert",
                "mission_uid": data["mission_uid"],
                "task_uid": data["task_uid"],
                "assignment_uid": data["assignment_uid"],
                "team_member_rns_identity": data["team_member_rns_identity"],
                "status": data["status"],
                "due_dtg": data["due_dtg"],
                "notes": data["notes"],
                "assets": list(data.get("assets") or []),
            }
            self._emit_auto_mission_change(
                session,
                mission_uid=mission_uid,
                source_event_type="mission.assignment.upserted",
                change_type=MissionChangeType.ADD_CONTENT.value,
                delta=self._build_delta_envelope(
                    source_event_type="mission.assignment.upserted",
                    tasks=[task_delta],
                ),
                team_member_rns_identity=member,
            )
            return data

    def list_assignments(self, *, mission_uid: str | None = None, task_uid: str | None = None) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(R3aktMissionTaskAssignmentRecord)
            if mission_uid:
                query = query.filter(R3aktMissionTaskAssignmentRecord.mission_uid == mission_uid)
            if task_uid:
                query = query.filter(R3aktMissionTaskAssignmentRecord.task_uid == task_uid)
            return [
                self._serialize_assignment(session, row)
                for row in query.order_by(R3aktMissionTaskAssignmentRecord.assigned_at.desc()).all()
            ]

    def set_assignment_assets(self, assignment_uid: str, asset_uids: list[str]) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktMissionTaskAssignmentRecord, assignment_uid)
            if row is None:
                raise KeyError(f"Assignment '{assignment_uid}' not found")
            normalized_assets = [str(item).strip() for item in asset_uids if str(item).strip()]
            for asset_uid in normalized_assets:
                self._ensure_asset_exists(session, asset_uid)
            row.assets_json = normalized_assets
            (
                session.query(R3aktAssignmentAssetLinkRecord)
                .filter(R3aktAssignmentAssetLinkRecord.assignment_uid == assignment_uid)
                .delete(synchronize_session=False)
            )
            for asset_uid in normalized_assets:
                session.add(
                    R3aktAssignmentAssetLinkRecord(
                        link_uid=uuid.uuid4().hex,
                        assignment_uid=assignment_uid,
                        asset_uid=asset_uid,
                    )
                )
            session.flush()
            data = self._serialize_assignment(session, row)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="assignment",
                aggregate_uid=assignment_uid,
                event_type="assignment.assets.updated",
                payload=data,
            )
            task_delta = {
                "op": "assignment_assets_set",
                "mission_uid": data["mission_uid"],
                "task_uid": data["task_uid"],
                "assignment_uid": data["assignment_uid"],
                "assets": list(data.get("assets") or []),
            }
            self._emit_auto_mission_change(
                session,
                mission_uid=data["mission_uid"],
                source_event_type="mission.assignment.assets.updated",
                change_type=MissionChangeType.ADD_CONTENT.value,
                delta=self._build_delta_envelope(
                    source_event_type="mission.assignment.assets.updated",
                    tasks=[task_delta],
                ),
                team_member_rns_identity=data.get("team_member_rns_identity"),
            )
            return data

    def link_assignment_asset(self, assignment_uid: str, asset_uid: str) -> dict[str, Any]:
        asset_value = str(asset_uid or "").strip()
        if not asset_value:
            raise ValueError("asset_uid is required")
        with self._session() as session:
            row = session.get(R3aktMissionTaskAssignmentRecord, assignment_uid)
            if row is None:
                raise KeyError(f"Assignment '{assignment_uid}' not found")
            self._ensure_asset_exists(session, asset_value)
            existing_assets = self._assignment_assets(
                session,
                assignment_uid,
                fallback_assets=list(row.assets_json or []),
            )
            if asset_value not in existing_assets:
                existing_assets.append(asset_value)
            row.assets_json = existing_assets
            (
                session.query(R3aktAssignmentAssetLinkRecord)
                .filter(
                    R3aktAssignmentAssetLinkRecord.assignment_uid == assignment_uid,
                    R3aktAssignmentAssetLinkRecord.asset_uid == asset_value,
                )
                .delete(synchronize_session=False)
            )
            session.add(
                R3aktAssignmentAssetLinkRecord(
                    link_uid=uuid.uuid4().hex,
                    assignment_uid=assignment_uid,
                    asset_uid=asset_value,
                )
            )
            session.flush()
            data = self._serialize_assignment(session, row)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="assignment",
                aggregate_uid=assignment_uid,
                event_type="assignment.asset.linked",
                payload={"assignment_uid": assignment_uid, "asset_uid": asset_value},
            )
            task_delta = {
                "op": "assignment_asset_linked",
                "mission_uid": data["mission_uid"],
                "task_uid": data["task_uid"],
                "assignment_uid": data["assignment_uid"],
                "asset_uid": asset_value,
                "assets": list(data.get("assets") or []),
            }
            self._emit_auto_mission_change(
                session,
                mission_uid=data["mission_uid"],
                source_event_type="mission.assignment.asset.linked",
                change_type=MissionChangeType.ADD_CONTENT.value,
                delta=self._build_delta_envelope(
                    source_event_type="mission.assignment.asset.linked",
                    tasks=[task_delta],
                ),
                team_member_rns_identity=data.get("team_member_rns_identity"),
            )
            return data

    def unlink_assignment_asset(self, assignment_uid: str, asset_uid: str) -> dict[str, Any]:
        asset_value = str(asset_uid or "").strip()
        if not asset_value:
            raise ValueError("asset_uid is required")
        with self._session() as session:
            row = session.get(R3aktMissionTaskAssignmentRecord, assignment_uid)
            if row is None:
                raise KeyError(f"Assignment '{assignment_uid}' not found")
            existing_assets = [
                item
                for item in self._assignment_assets(
                    session,
                    assignment_uid,
                    fallback_assets=list(row.assets_json or []),
                )
                if item != asset_value
            ]
            row.assets_json = existing_assets
            (
                session.query(R3aktAssignmentAssetLinkRecord)
                .filter(
                    R3aktAssignmentAssetLinkRecord.assignment_uid == assignment_uid,
                    R3aktAssignmentAssetLinkRecord.asset_uid == asset_value,
                )
                .delete(synchronize_session=False)
            )
            session.flush()
            data = self._serialize_assignment(session, row)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="assignment",
                aggregate_uid=assignment_uid,
                event_type="assignment.asset.unlinked",
                payload={"assignment_uid": assignment_uid, "asset_uid": asset_value},
            )
            task_delta = {
                "op": "assignment_asset_unlinked",
                "mission_uid": data["mission_uid"],
                "task_uid": data["task_uid"],
                "assignment_uid": data["assignment_uid"],
                "asset_uid": asset_value,
                "assets": list(data.get("assets") or []),
            }
            self._emit_auto_mission_change(
                session,
                mission_uid=data["mission_uid"],
                source_event_type="mission.assignment.asset.unlinked",
                change_type=MissionChangeType.REMOVE_CONTENT.value,
                delta=self._build_delta_envelope(
                    source_event_type="mission.assignment.asset.unlinked",
                    tasks=[task_delta],
                ),
                team_member_rns_identity=data.get("team_member_rns_identity"),
            )
            return data
