"""Persistence-backed R3AKT mission/checklist domain services."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from datetime import timedelta
from datetime import timezone
import base64
import csv
from io import StringIO
from pathlib import Path
from typing import Any
import uuid

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from reticulum_telemetry_hub.api.storage_models import Base
from reticulum_telemetry_hub.api.storage_models import R3aktAssetRecord
from reticulum_telemetry_hub.api.storage_models import R3aktChecklistCellRecord
from reticulum_telemetry_hub.api.storage_models import R3aktChecklistColumnRecord
from reticulum_telemetry_hub.api.storage_models import R3aktChecklistFeedPublicationRecord
from reticulum_telemetry_hub.api.storage_models import R3aktChecklistRecord
from reticulum_telemetry_hub.api.storage_models import R3aktChecklistTaskRecord
from reticulum_telemetry_hub.api.storage_models import R3aktChecklistTemplateRecord
from reticulum_telemetry_hub.api.storage_models import R3aktDomainEventRecord
from reticulum_telemetry_hub.api.storage_models import R3aktDomainSnapshotRecord
from reticulum_telemetry_hub.api.storage_models import R3aktMissionChangeRecord
from reticulum_telemetry_hub.api.storage_models import R3aktMissionRecord
from reticulum_telemetry_hub.api.storage_models import R3aktMissionTaskAssignmentRecord
from reticulum_telemetry_hub.api.storage_models import R3aktSkillRecord
from reticulum_telemetry_hub.api.storage_models import R3aktTaskSkillRequirementRecord
from reticulum_telemetry_hub.api.storage_models import R3aktTeamMemberRecord
from reticulum_telemetry_hub.api.storage_models import R3aktTeamMemberSkillRecord
from reticulum_telemetry_hub.api.storage_models import R3aktTeamRecord


CHECKLIST_USER_PENDING = "PENDING"
CHECKLIST_USER_COMPLETE = "COMPLETE"
CHECKLIST_TASK_PENDING = "PENDING"
CHECKLIST_TASK_COMPLETE = "COMPLETE"
CHECKLIST_TASK_COMPLETE_LATE = "COMPLETE_LATE"
CHECKLIST_TASK_LATE = "LATE"
CHECKLIST_MODE_ONLINE = "ONLINE"
CHECKLIST_MODE_OFFLINE = "OFFLINE"
CHECKLIST_SYNC_LOCAL_ONLY = "LOCAL_ONLY"
CHECKLIST_SYNC_SYNCED = "SYNCED"
SYSTEM_COLUMN_KEY_DUE_RELATIVE_DTG = "DUE_RELATIVE_DTG"


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


class MissionDomainService:  # pylint: disable=too-many-public-methods
    """Domain service for R3AKT mission/checklist objects."""

    def __init__(self, db_path: Path, *, event_retention_days: int = 90) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
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
        self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False)
        self._event_retention_days = max(1, int(event_retention_days))

    def _enable_wal_mode(self) -> None:
        try:
            with self._engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as conn:
                conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
        except OperationalError:
            return

    @contextmanager
    def _session(self):
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _prune_domain_history(self, session: Session) -> None:
        cutoff = _utcnow() - timedelta(days=self._event_retention_days)
        session.query(R3aktDomainEventRecord).filter(
            R3aktDomainEventRecord.created_at < cutoff
        ).delete(synchronize_session=False)
        session.query(R3aktDomainSnapshotRecord).filter(
            R3aktDomainSnapshotRecord.created_at < cutoff
        ).delete(synchronize_session=False)

    def _record_event(
        self,
        session: Session,
        *,
        domain: str,
        aggregate_type: str,
        aggregate_uid: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        session.add(
            R3aktDomainEventRecord(
                event_uid=uuid.uuid4().hex,
                domain=domain,
                aggregate_type=aggregate_type,
                aggregate_uid=aggregate_uid,
                event_type=event_type,
                payload_json=payload,
                created_at=_utcnow(),
            )
        )
        self._prune_domain_history(session)

    def _record_snapshot(
        self,
        session: Session,
        *,
        domain: str,
        aggregate_type: str,
        aggregate_uid: str,
        state: dict[str, Any],
    ) -> None:
        latest = (
            session.query(R3aktDomainSnapshotRecord)
            .filter(
                R3aktDomainSnapshotRecord.domain == domain,
                R3aktDomainSnapshotRecord.aggregate_type == aggregate_type,
                R3aktDomainSnapshotRecord.aggregate_uid == aggregate_uid,
            )
            .order_by(R3aktDomainSnapshotRecord.version.desc())
            .first()
        )
        session.add(
            R3aktDomainSnapshotRecord(
                snapshot_uid=uuid.uuid4().hex,
                domain=domain,
                aggregate_type=aggregate_type,
                aggregate_uid=aggregate_uid,
                version=(int(latest.version) + 1) if latest else 1,
                state_json=state,
                created_at=_utcnow(),
            )
        )
        self._prune_domain_history(session)

    def list_domain_events(self, *, limit: int = 200) -> list[dict[str, Any]]:
        with self._session() as session:
            rows = (
                session.query(R3aktDomainEventRecord)
                .order_by(R3aktDomainEventRecord.created_at.desc())
                .limit(max(1, int(limit)))
                .all()
            )
            return [
                {
                    "event_uid": row.event_uid,
                    "domain": row.domain,
                    "aggregate_type": row.aggregate_type,
                    "aggregate_uid": row.aggregate_uid,
                    "event_type": row.event_type,
                    "payload": dict(row.payload_json or {}),
                    "created_at": _dt(row.created_at),
                }
                for row in rows
            ]

    def list_domain_snapshots(self, *, limit: int = 200) -> list[dict[str, Any]]:
        with self._session() as session:
            rows = (
                session.query(R3aktDomainSnapshotRecord)
                .order_by(R3aktDomainSnapshotRecord.created_at.desc())
                .limit(max(1, int(limit)))
                .all()
            )
            return [
                {
                    "snapshot_uid": row.snapshot_uid,
                    "domain": row.domain,
                    "aggregate_type": row.aggregate_type,
                    "aggregate_uid": row.aggregate_uid,
                    "version": int(row.version or 1),
                    "state": dict(row.state_json or {}),
                    "created_at": _dt(row.created_at),
                }
                for row in rows
            ]

    @staticmethod
    def _ensure_mission_exists(session: Session, mission_uid: str) -> None:
        if session.get(R3aktMissionRecord, mission_uid) is None:
            raise ValueError(f"Mission '{mission_uid}' not found")

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
    def _serialize_mission(row: R3aktMissionRecord) -> dict[str, Any]:
        return {
            "uid": row.uid,
            "mission_name": row.mission_name,
            "description": row.description or "",
            "topic_id": row.topic_id,
            "mission_status": row.mission_status,
            "default_role": row.default_role,
            "owner_role": row.owner_role,
            "invite_only": bool(row.invite_only),
            "created_at": _dt(row.created_at),
            "updated_at": _dt(row.updated_at),
        }

    def upsert_mission(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("uid") or payload.get("mission_id") or uuid.uuid4().hex)
        with self._session() as session:
            row = session.get(R3aktMissionRecord, uid)
            if row is None:
                row = R3aktMissionRecord(uid=uid, mission_name="Mission")
                session.add(row)
            row.mission_name = str(payload.get("mission_name") or payload.get("name") or row.mission_name)
            row.description = str(payload.get("description") or row.description or "")
            row.topic_id = payload.get("topic_id") or row.topic_id
            row.mission_status = payload.get("mission_status") or row.mission_status or "MISSION_ACTIVE"
            row.default_role = payload.get("default_role") or row.default_role
            row.owner_role = payload.get("owner_role") or row.owner_role
            if payload.get("invite_only") is not None:
                row.invite_only = bool(payload.get("invite_only"))
            session.flush()
            data = self._serialize_mission(row)
            self._record_event(session, domain="mission", aggregate_type="mission", aggregate_uid=uid, event_type="mission.upserted", payload=data)
            self._record_snapshot(session, domain="mission", aggregate_type="mission", aggregate_uid=uid, state=data)
            return data

    def list_missions(self) -> list[dict[str, Any]]:
        with self._session() as session:
            return [
                self._serialize_mission(row)
                for row in session.query(R3aktMissionRecord).order_by(R3aktMissionRecord.created_at.desc()).all()
            ]

    def get_mission(self, mission_uid: str) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktMissionRecord, mission_uid)
            if row is None:
                raise KeyError(f"Mission '{mission_uid}' not found")
            return self._serialize_mission(row)

    @staticmethod
    def _serialize_mission_change(row: R3aktMissionChangeRecord) -> dict[str, Any]:
        return {
            "uid": row.uid,
            "mission_uid": row.mission_uid,
            "name": row.name,
            "team_member_rns_identity": row.team_member_rns_identity,
            "timestamp": _dt(row.timestamp),
            "notes": row.notes,
            "change_type": row.change_type,
            "is_federated_change": bool(row.is_federated_change),
            "hashes": list(row.hashes_json or []),
        }

    def upsert_mission_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("uid") or uuid.uuid4().hex)
        mission_uid = str(payload.get("mission_uid") or payload.get("mission_id") or "").strip()
        if not mission_uid:
            raise ValueError("mission_uid is required")
        with self._session() as session:
            self._ensure_mission_exists(session, mission_uid)
            row = session.get(R3aktMissionChangeRecord, uid)
            if row is None:
                row = R3aktMissionChangeRecord(uid=uid, mission_uid=mission_uid)
                session.add(row)
            row.mission_uid = mission_uid
            row.name = payload.get("name")
            row.team_member_rns_identity = payload.get("team_member_rns_identity")
            row.timestamp = _as_datetime(payload.get("timestamp"), default=_utcnow()) or _utcnow()
            row.notes = payload.get("notes")
            row.change_type = payload.get("change_type")
            if payload.get("is_federated_change") is not None:
                row.is_federated_change = bool(payload.get("is_federated_change"))
            row.hashes_json = payload.get("hashes")
            session.flush()
            data = self._serialize_mission_change(row)
            self._record_event(session, domain="mission", aggregate_type="mission_change", aggregate_uid=uid, event_type="mission.change.upserted", payload=data)
            return data

    def list_mission_changes(self, mission_uid: str | None = None) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(R3aktMissionChangeRecord)
            if mission_uid:
                query = query.filter(R3aktMissionChangeRecord.mission_uid == mission_uid)
            return [self._serialize_mission_change(row) for row in query.order_by(R3aktMissionChangeRecord.timestamp.desc()).all()]

    @staticmethod
    def _serialize_team(row: R3aktTeamRecord) -> dict[str, Any]:
        return {
            "uid": row.uid,
            "mission_uid": row.mission_uid,
            "color": row.color,
            "team_name": row.team_name,
            "team_description": row.team_description or "",
            "created_at": _dt(row.created_at),
            "updated_at": _dt(row.updated_at),
        }

    def upsert_team(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("uid") or uuid.uuid4().hex)
        with self._session() as session:
            row = session.get(R3aktTeamRecord, uid)
            if row is None:
                row = R3aktTeamRecord(uid=uid, team_name="Team")
                session.add(row)
            mission_uid = payload.get("mission_uid") or row.mission_uid
            if mission_uid:
                self._ensure_mission_exists(session, str(mission_uid))
            row.mission_uid = mission_uid
            row.color = payload.get("color") or row.color
            row.team_name = str(payload.get("team_name") or payload.get("name") or row.team_name)
            row.team_description = str(payload.get("team_description") or payload.get("description") or row.team_description or "")
            session.flush()
            data = self._serialize_team(row)
            self._record_event(session, domain="mission", aggregate_type="team", aggregate_uid=uid, event_type="team.upserted", payload=data)
            return data

    def list_teams(self, mission_uid: str | None = None) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(R3aktTeamRecord)
            if mission_uid:
                query = query.filter(R3aktTeamRecord.mission_uid == mission_uid)
            return [self._serialize_team(row) for row in query.order_by(R3aktTeamRecord.team_name.asc()).all()]

    @staticmethod
    def _serialize_team_member(row: R3aktTeamMemberRecord) -> dict[str, Any]:
        return {
            "uid": row.uid,
            "team_uid": row.team_uid,
            "rns_identity": row.rns_identity,
            "display_name": row.display_name,
            "role": row.role,
            "callsign": row.callsign,
            "created_at": _dt(row.created_at),
            "updated_at": _dt(row.updated_at),
        }

    def upsert_team_member(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("uid") or uuid.uuid4().hex)
        identity = str(payload.get("rns_identity") or payload.get("team_member_rns_identity") or "").strip()
        if not identity:
            raise ValueError("rns_identity is required")
        with self._session() as session:
            row = session.get(R3aktTeamMemberRecord, uid)
            if row is None:
                row = R3aktTeamMemberRecord(uid=uid, team_uid=None, rns_identity=identity, display_name=identity)
                session.add(row)
            team_uid = payload.get("team_uid") or row.team_uid
            if team_uid:
                self._ensure_team_exists(session, str(team_uid))
            row.team_uid = team_uid
            row.rns_identity = identity
            row.display_name = str(payload.get("display_name") or payload.get("callsign") or row.display_name)
            row.role = payload.get("role") or row.role
            row.callsign = payload.get("callsign") or row.callsign
            session.flush()
            data = self._serialize_team_member(row)
            self._record_event(session, domain="mission", aggregate_type="team_member", aggregate_uid=uid, event_type="team_member.upserted", payload=data)
            return data

    def list_team_members(self, team_uid: str | None = None) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(R3aktTeamMemberRecord)
            if team_uid:
                query = query.filter(R3aktTeamMemberRecord.team_uid == team_uid)
            return [self._serialize_team_member(row) for row in query.order_by(R3aktTeamMemberRecord.display_name.asc()).all()]
    @staticmethod
    def _serialize_asset(row: R3aktAssetRecord) -> dict[str, Any]:
        return {
            "asset_uid": row.asset_uid,
            "team_member_uid": row.team_member_uid,
            "name": row.name,
            "asset_type": row.asset_type,
            "serial_number": row.serial_number,
            "status": row.status,
            "location": row.location,
            "notes": row.notes,
            "created_at": _dt(row.created_at),
            "updated_at": _dt(row.updated_at),
        }

    def upsert_asset(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("asset_uid") or uuid.uuid4().hex)
        with self._session() as session:
            row = session.get(R3aktAssetRecord, uid)
            if row is None:
                row = R3aktAssetRecord(asset_uid=uid, team_member_uid=None, name="Asset", asset_type="generic", status="AVAILABLE")
                session.add(row)
            team_member_uid = payload.get("team_member_uid") or row.team_member_uid
            if team_member_uid:
                self._ensure_team_member_uid_exists(session, str(team_member_uid))
            row.team_member_uid = team_member_uid
            row.name = str(payload.get("name") or row.name)
            row.asset_type = str(payload.get("asset_type") or row.asset_type)
            row.serial_number = payload.get("serial_number") or row.serial_number
            row.status = str(payload.get("status") or row.status)
            row.location = payload.get("location") or row.location
            row.notes = payload.get("notes") or row.notes
            session.flush()
            data = self._serialize_asset(row)
            self._record_event(session, domain="mission", aggregate_type="asset", aggregate_uid=uid, event_type="asset.upserted", payload=data)
            return data

    def list_assets(self, team_member_uid: str | None = None) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(R3aktAssetRecord)
            if team_member_uid:
                query = query.filter(R3aktAssetRecord.team_member_uid == team_member_uid)
            return [self._serialize_asset(row) for row in query.order_by(R3aktAssetRecord.name.asc()).all()]

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
            row.level = int(payload.get("level") or row.level or 0)
            row.validated_by = payload.get("validated_by") or row.validated_by
            row.validated_at = _as_datetime(payload.get("validated_at"), default=row.validated_at)
            row.expires_at = _as_datetime(payload.get("expires_at"), default=row.expires_at)
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
            row.minimum_level = int(payload.get("minimum_level") or row.minimum_level or 0)
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
    def _serialize_assignment(row: R3aktMissionTaskAssignmentRecord) -> dict[str, Any]:
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
            "assets": list(row.assets_json or []),
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
            row.status = str(payload.get("status") or row.status)
            row.notes = payload.get("notes") or row.notes
            if payload.get("assets") is not None:
                row.assets_json = assets
            session.flush()
            data = self._serialize_assignment(row)
            self._record_event(session, domain="mission", aggregate_type="assignment", aggregate_uid=uid, event_type="assignment.upserted", payload=data)
            return data

    def list_assignments(self, *, mission_uid: str | None = None, task_uid: str | None = None) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(R3aktMissionTaskAssignmentRecord)
            if mission_uid:
                query = query.filter(R3aktMissionTaskAssignmentRecord.mission_uid == mission_uid)
            if task_uid:
                query = query.filter(R3aktMissionTaskAssignmentRecord.task_uid == task_uid)
            return [self._serialize_assignment(row) for row in query.order_by(R3aktMissionTaskAssignmentRecord.assigned_at.desc()).all()]
    def _default_columns(self) -> list[dict[str, Any]]:
        return [
            {
                "column_uid": uuid.uuid4().hex,
                "column_name": "Due",
                "display_order": 1,
                "column_type": "RELATIVE_TIME",
                "column_editable": False,
                "is_removable": False,
                "system_key": SYSTEM_COLUMN_KEY_DUE_RELATIVE_DTG,
                "background_color": None,
                "text_color": None,
            },
            {
                "column_uid": uuid.uuid4().hex,
                "column_name": "Task",
                "display_order": 2,
                "column_type": "SHORT_STRING",
                "column_editable": True,
                "is_removable": True,
                "system_key": None,
                "background_color": None,
                "text_color": None,
            },
        ]

    def _normalize_column(self, payload: dict[str, Any], *, order: int) -> dict[str, Any]:
        return {
            "column_uid": str(payload.get("column_uid") or payload.get("uid") or uuid.uuid4().hex),
            "column_name": str(payload.get("column_name") or payload.get("name") or "Column"),
            "display_order": int(payload.get("display_order") or order),
            "column_type": str(payload.get("column_type") or "SHORT_STRING"),
            "column_editable": bool(payload.get("column_editable", True)),
            "is_removable": bool(payload.get("is_removable", True)),
            "system_key": payload.get("system_key"),
            "background_color": payload.get("background_color"),
            "text_color": payload.get("text_color"),
        }

    def _validate_columns(self, columns: list[dict[str, Any]]) -> None:
        if not columns:
            raise ValueError("columns are required")
        due = [c for c in columns if c.get("system_key") == SYSTEM_COLUMN_KEY_DUE_RELATIVE_DTG]
        if len(due) != 1:
            raise ValueError("Exactly one DUE_RELATIVE_DTG system column is required")
        due_col = due[0]
        if due_col.get("column_type") != "RELATIVE_TIME":
            raise ValueError("DUE_RELATIVE_DTG column must be RELATIVE_TIME")
        if bool(due_col.get("is_removable", True)):
            raise ValueError("DUE_RELATIVE_DTG column cannot be removable")

    @staticmethod
    def _serialize_column(row: R3aktChecklistColumnRecord) -> dict[str, Any]:
        return {
            "column_uid": row.column_uid,
            "column_name": row.column_name,
            "display_order": int(row.display_order or 0),
            "column_type": row.column_type,
            "column_editable": bool(row.column_editable),
            "background_color": row.background_color,
            "text_color": row.text_color,
            "is_removable": bool(row.is_removable),
            "system_key": row.system_key,
        }

    def _template_columns(self, session: Session, template_uid: str) -> list[R3aktChecklistColumnRecord]:
        return (
            session.query(R3aktChecklistColumnRecord)
            .filter(
                R3aktChecklistColumnRecord.template_uid == template_uid,
                R3aktChecklistColumnRecord.checklist_uid.is_(None),
            )
            .order_by(R3aktChecklistColumnRecord.display_order.asc())
            .all()
        )

    def _checklist_columns(self, session: Session, checklist_uid: str) -> list[R3aktChecklistColumnRecord]:
        return (
            session.query(R3aktChecklistColumnRecord)
            .filter(R3aktChecklistColumnRecord.checklist_uid == checklist_uid)
            .order_by(R3aktChecklistColumnRecord.display_order.asc())
            .all()
        )

    def _serialize_template(self, session: Session, row: R3aktChecklistTemplateRecord) -> dict[str, Any]:
        return {
            "uid": row.uid,
            "template_name": row.template_name,
            "description": row.description or "",
            "created_at": _dt(row.created_at),
            "created_by_team_member_rns_identity": row.created_by_team_member_rns_identity,
            "updated_at": _dt(row.updated_at),
            "source_template_uid": row.source_template_uid,
            "server_only": bool(row.server_only),
            "columns": [self._serialize_column(col) for col in self._template_columns(session, row.uid)],
        }

    def list_checklist_templates(self, *, search: str | None = None, sort_by: str | None = None) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(R3aktChecklistTemplateRecord)
            if search:
                query = query.filter(R3aktChecklistTemplateRecord.template_name.ilike(f"%{search}%"))
            if sort_by == "name_desc":
                query = query.order_by(R3aktChecklistTemplateRecord.template_name.desc())
            elif sort_by == "created_at_asc":
                query = query.order_by(R3aktChecklistTemplateRecord.created_at.asc())
            elif sort_by == "created_at_desc":
                query = query.order_by(R3aktChecklistTemplateRecord.created_at.desc())
            else:
                query = query.order_by(R3aktChecklistTemplateRecord.template_name.asc())
            return [self._serialize_template(session, row) for row in query.all()]

    def create_checklist_template(self, template: dict[str, Any]) -> dict[str, Any]:
        uid = str(template.get("uid") or uuid.uuid4().hex)
        now = _utcnow()
        cols = [self._normalize_column(item, order=index) for index, item in enumerate(template.get("columns") or self._default_columns(), start=1)]
        self._validate_columns(cols)
        with self._session() as session:
            row = R3aktChecklistTemplateRecord(
                uid=uid,
                template_name=str(template.get("template_name") or template.get("name") or "Template"),
                description=str(template.get("description") or ""),
                created_at=_as_datetime(template.get("created_at"), default=now) or now,
                created_by_team_member_rns_identity=str(template.get("created_by_team_member_rns_identity") or template.get("created_by") or "unknown"),
                updated_at=_as_datetime(template.get("updated_at"), default=now) or now,
                source_template_uid=template.get("source_template_uid"),
                server_only=bool(template.get("server_only", True)),
            )
            session.add(row)
            for col in cols:
                session.add(
                    R3aktChecklistColumnRecord(
                        column_uid=col["column_uid"],
                        checklist_uid=None,
                        template_uid=uid,
                        column_name=col["column_name"],
                        display_order=col["display_order"],
                        column_type=col["column_type"],
                        column_editable=col["column_editable"],
                        background_color=col["background_color"],
                        text_color=col["text_color"],
                        is_removable=col["is_removable"],
                        system_key=col["system_key"],
                        created_at=now,
                        updated_at=now,
                    )
                )
            session.flush()
            data = self._serialize_template(session, row)
            self._record_event(session, domain="checklist", aggregate_type="template", aggregate_uid=uid, event_type="checklist.template.created", payload=data)
            self._record_snapshot(session, domain="checklist", aggregate_type="template", aggregate_uid=uid, state=data)
            return data

    def update_checklist_template(self, template_uid: str, patch: dict[str, Any]) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktChecklistTemplateRecord, template_uid)
            if row is None:
                raise KeyError(f"Checklist template '{template_uid}' not found")
            if patch.get("template_name") is not None:
                row.template_name = str(patch.get("template_name"))
            if patch.get("description") is not None:
                row.description = str(patch.get("description"))
            if patch.get("source_template_uid") is not None:
                row.source_template_uid = patch.get("source_template_uid")
            if patch.get("columns") is not None:
                cols = [self._normalize_column(item, order=index) for index, item in enumerate(patch.get("columns") or [], start=1)]
                self._validate_columns(cols)
                session.query(R3aktChecklistColumnRecord).filter(
                    R3aktChecklistColumnRecord.template_uid == template_uid,
                    R3aktChecklistColumnRecord.checklist_uid.is_(None),
                ).delete(synchronize_session=False)
                now = _utcnow()
                for col in cols:
                    session.add(
                        R3aktChecklistColumnRecord(
                            column_uid=col["column_uid"], checklist_uid=None, template_uid=template_uid,
                            column_name=col["column_name"], display_order=col["display_order"], column_type=col["column_type"],
                            column_editable=col["column_editable"], background_color=col["background_color"], text_color=col["text_color"],
                            is_removable=col["is_removable"], system_key=col["system_key"], created_at=now, updated_at=now,
                        )
                    )
            row.updated_at = _utcnow()
            session.flush()
            data = self._serialize_template(session, row)
            self._record_event(session, domain="checklist", aggregate_type="template", aggregate_uid=template_uid, event_type="checklist.template.updated", payload=data)
            self._record_snapshot(session, domain="checklist", aggregate_type="template", aggregate_uid=template_uid, state=data)
            return data

    def clone_checklist_template(self, source_template_uid: str, *, template_name: str, description: str | None = None, created_by_team_member_rns_identity: str = "unknown") -> dict[str, Any]:
        with self._session() as session:
            source = session.get(R3aktChecklistTemplateRecord, source_template_uid)
            if source is None:
                raise KeyError(f"Checklist template '{source_template_uid}' not found")
            source_cols = []
            for col in self._template_columns(session, source_template_uid):
                serialized = self._serialize_column(col)
                # Template clones must allocate fresh column UIDs to satisfy
                # global primary-key uniqueness across templates/checklists.
                serialized["column_uid"] = uuid.uuid4().hex
                source_cols.append(serialized)
        return self.create_checklist_template(
            {
                "template_name": template_name,
                "description": description if description is not None else source.description,
                "source_template_uid": source_template_uid,
                "created_by_team_member_rns_identity": created_by_team_member_rns_identity,
                "columns": source_cols,
            }
        )

    def delete_checklist_template(self, template_uid: str) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktChecklistTemplateRecord, template_uid)
            if row is None:
                raise KeyError(f"Checklist template '{template_uid}' not found")
            data = self._serialize_template(session, row)
            session.query(R3aktChecklistColumnRecord).filter(
                R3aktChecklistColumnRecord.template_uid == template_uid,
                R3aktChecklistColumnRecord.checklist_uid.is_(None),
            ).delete(synchronize_session=False)
            session.delete(row)
            self._record_event(session, domain="checklist", aggregate_type="template", aggregate_uid=template_uid, event_type="checklist.template.deleted", payload=data)
            return data
    @staticmethod
    def _serialize_publication(row: R3aktChecklistFeedPublicationRecord) -> dict[str, Any]:
        return {
            "publication_uid": row.publication_uid,
            "checklist_uid": row.checklist_uid,
            "mission_feed_uid": row.mission_feed_uid,
            "published_at": _dt(row.published_at),
            "published_by_team_member_rns_identity": row.published_by_team_member_rns_identity,
        }

    def _serialize_checklist(self, session: Session, row: R3aktChecklistRecord) -> dict[str, Any]:
        columns = [self._serialize_column(col) for col in self._checklist_columns(session, row.uid)]
        tasks = (
            session.query(R3aktChecklistTaskRecord)
            .filter(R3aktChecklistTaskRecord.checklist_uid == row.uid)
            .order_by(R3aktChecklistTaskRecord.number.asc())
            .all()
        )
        task_ids = [task.task_uid for task in tasks]
        cells_by_task: dict[str, list[dict[str, Any]]] = {task_id: [] for task_id in task_ids}
        if task_ids:
            for cell in session.query(R3aktChecklistCellRecord).filter(R3aktChecklistCellRecord.task_uid.in_(task_ids)).all():
                cells_by_task.setdefault(cell.task_uid, []).append(
                    {
                        "cell_uid": cell.cell_uid,
                        "task_uid": cell.task_uid,
                        "column_uid": cell.column_uid,
                        "value": cell.value,
                        "updated_at": _dt(cell.updated_at),
                        "updated_by_team_member_rns_identity": cell.updated_by_team_member_rns_identity,
                    }
                )
        publications = (
            session.query(R3aktChecklistFeedPublicationRecord)
            .filter(R3aktChecklistFeedPublicationRecord.checklist_uid == row.uid)
            .order_by(R3aktChecklistFeedPublicationRecord.published_at.desc())
            .all()
        )
        return {
            "uid": row.uid,
            "mission_id": row.mission_uid,
            "template_uid": row.template_uid,
            "template_version": row.template_version,
            "template_name": row.template_name,
            "name": row.name,
            "description": row.description,
            "start_time": _dt(row.start_time),
            "mode": row.mode,
            "sync_state": row.sync_state,
            "origin_type": row.origin_type,
            "checklist_status": row.checklist_status,
            "created_at": _dt(row.created_at),
            "created_by_team_member_rns_identity": row.created_by_team_member_rns_identity,
            "updated_at": _dt(row.updated_at),
            "uploaded_at": _dt(row.uploaded_at),
            "progress_percent": float(row.progress_percent or 0.0),
            "counts": {
                "pending_count": int(row.pending_count or 0),
                "late_count": int(row.late_count or 0),
                "complete_count": int(row.complete_count or 0),
            },
            "columns": columns,
            "tasks": [
                {
                    "task_uid": task.task_uid,
                    "number": int(task.number or 0),
                    "user_status": task.user_status,
                    "task_status": task.task_status,
                    "is_late": bool(task.is_late),
                    "custom_status": task.custom_status,
                    "due_relative_minutes": task.due_relative_minutes,
                    "due_dtg": _dt(task.due_dtg),
                    "notes": task.notes,
                    "row_background_color": task.row_background_color,
                    "line_break_enabled": bool(task.line_break_enabled),
                    "completed_at": _dt(task.completed_at),
                    "completed_by_team_member_rns_identity": task.completed_by_team_member_rns_identity,
                    "legacy_value": task.legacy_value,
                    "cells": cells_by_task.get(task.task_uid, []),
                }
                for task in tasks
            ],
            "feed_publications": [self._serialize_publication(item) for item in publications],
        }

    def _derive_task_status(self, *, user_status: str, due_dtg: datetime | None, completed_at: datetime | None) -> tuple[str, bool]:
        due = _as_datetime(due_dtg)
        completed = _as_datetime(completed_at)
        if user_status == CHECKLIST_USER_COMPLETE:
            if due and completed and completed > due:
                return CHECKLIST_TASK_COMPLETE_LATE, True
            return CHECKLIST_TASK_COMPLETE, False
        if due and _utcnow() > due:
            return CHECKLIST_TASK_LATE, True
        return CHECKLIST_TASK_PENDING, False

    def _recompute_checklist_status(self, session: Session, checklist: R3aktChecklistRecord) -> None:
        tasks = (
            session.query(R3aktChecklistTaskRecord)
            .filter(R3aktChecklistTaskRecord.checklist_uid == checklist.uid)
            .order_by(R3aktChecklistTaskRecord.number.asc())
            .all()
        )
        pending = 0
        late = 0
        complete = 0
        has_complete_late = False
        for task in tasks:
            status, is_late = self._derive_task_status(user_status=str(task.user_status or CHECKLIST_USER_PENDING), due_dtg=task.due_dtg, completed_at=task.completed_at)
            task.task_status = status
            task.is_late = is_late
            if task.user_status == CHECKLIST_USER_COMPLETE:
                complete += 1
                if status == CHECKLIST_TASK_COMPLETE_LATE:
                    has_complete_late = True
            else:
                pending += 1
                if status == CHECKLIST_TASK_LATE:
                    late += 1
        total = len(tasks)
        checklist.pending_count = pending
        checklist.late_count = late
        checklist.complete_count = complete
        checklist.progress_percent = round((complete / total) * 100.0, 2) if total else 0.0
        if total == 0:
            checklist.checklist_status = CHECKLIST_TASK_PENDING
        elif pending == 0:
            checklist.checklist_status = CHECKLIST_TASK_COMPLETE_LATE if has_complete_late else CHECKLIST_TASK_COMPLETE
        elif late > 0:
            checklist.checklist_status = CHECKLIST_TASK_LATE
        else:
            checklist.checklist_status = CHECKLIST_TASK_PENDING
        checklist.updated_at = _utcnow()

    def _create_checklist(self, *, mode: str, sync_state: str, origin_type: str, name: str, description: str, start_time: datetime, created_by: str, mission_uid: str | None = None, template_uid: str | None = None) -> dict[str, Any]:
        with self._session() as session:
            if mission_uid:
                self._ensure_mission_exists(session, str(mission_uid))
            if template_uid:
                template = session.get(R3aktChecklistTemplateRecord, template_uid)
                if template is None:
                    raise KeyError(f"Checklist template '{template_uid}' not found")
                cols = [self._serialize_column(col) for col in self._template_columns(session, template_uid)]
                template_name = template.template_name
            else:
                cols = self._default_columns()
                template_name = None
            self._validate_columns(cols)
            now = _utcnow()
            checklist_uid = uuid.uuid4().hex
            row = R3aktChecklistRecord(
                uid=checklist_uid,
                mission_uid=mission_uid,
                template_uid=template_uid,
                template_version=1 if template_uid else None,
                template_name=template_name,
                name=name,
                description=description,
                start_time=start_time,
                mode=mode,
                sync_state=sync_state,
                origin_type=origin_type,
                checklist_status=CHECKLIST_TASK_PENDING,
                progress_percent=0.0,
                pending_count=0,
                late_count=0,
                complete_count=0,
                created_at=now,
                created_by_team_member_rns_identity=created_by,
                updated_at=now,
                uploaded_at=None,
            )
            session.add(row)
            for col in cols:
                session.add(
                    R3aktChecklistColumnRecord(
                        column_uid=uuid.uuid4().hex,
                        checklist_uid=checklist_uid,
                        template_uid=None,
                        column_name=col["column_name"],
                        display_order=int(col["display_order"]),
                        column_type=col["column_type"],
                        column_editable=bool(col["column_editable"]),
                        background_color=col.get("background_color"),
                        text_color=col.get("text_color"),
                        is_removable=bool(col["is_removable"]),
                        system_key=col.get("system_key"),
                        created_at=now,
                        updated_at=now,
                    )
                )
            session.flush()
            self._recompute_checklist_status(session, row)
            data = self._serialize_checklist(session, row)
            self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.created", payload=data)
            self._record_snapshot(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, state=data)
            return data

    def list_active_checklists(self, *, search: str | None = None, sort_by: str | None = None) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(R3aktChecklistRecord)
            if search:
                query = query.filter(R3aktChecklistRecord.name.ilike(f"%{search}%"))
            if sort_by == "name_desc":
                query = query.order_by(R3aktChecklistRecord.name.desc())
            elif sort_by == "created_at_asc":
                query = query.order_by(R3aktChecklistRecord.created_at.asc())
            elif sort_by == "created_at_desc":
                query = query.order_by(R3aktChecklistRecord.created_at.desc())
            else:
                query = query.order_by(R3aktChecklistRecord.name.asc())
            return [self._serialize_checklist(session, row) for row in query.all()]

    def create_checklist_online(self, args: dict[str, Any]) -> dict[str, Any]:
        template_uid = str(args.get("template_uid") or "").strip()
        if not template_uid:
            raise ValueError("template_uid is required")
        name = str(args.get("name") or "").strip()
        if not name:
            raise ValueError("name is required")
        return self._create_checklist(
            mode=CHECKLIST_MODE_ONLINE,
            sync_state=CHECKLIST_SYNC_SYNCED,
            origin_type="RCH_TEMPLATE",
            name=name,
            description=str(args.get("description") or ""),
            start_time=_as_datetime(args.get("start_time"), default=_utcnow()) or _utcnow(),
            created_by=str(args.get("source_identity") or args.get("created_by_team_member_rns_identity") or "unknown"),
            mission_uid=args.get("mission_uid"),
            template_uid=template_uid,
        )

    def create_checklist_offline(self, args: dict[str, Any]) -> dict[str, Any]:
        name = str(args.get("name") or "").strip()
        if not name:
            raise ValueError("name is required")
        return self._create_checklist(
            mode=CHECKLIST_MODE_OFFLINE,
            sync_state=CHECKLIST_SYNC_LOCAL_ONLY,
            origin_type=str(args.get("origin_type") or "BLANK_TEMPLATE"),
            name=name,
            description=str(args.get("description") or ""),
            start_time=_as_datetime(args.get("start_time"), default=_utcnow()) or _utcnow(),
            created_by=str(args.get("source_identity") or args.get("created_by_team_member_rns_identity") or "unknown"),
            mission_uid=args.get("mission_uid"),
            template_uid=args.get("template_uid"),
        )

    def get_checklist(self, checklist_uid: str) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktChecklistRecord, checklist_uid)
            if row is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            return self._serialize_checklist(session, row)

    def join_checklist(self, checklist_uid: str, *, source_identity: str | None = None) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktChecklistRecord, checklist_uid)
            if row is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            data = self._serialize_checklist(session, row)
            self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.joined", payload={"checklist": data, "joined_by_team_member_rns_identity": source_identity})
            return data

    def upload_checklist(self, checklist_uid: str, *, source_identity: str | None = None) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktChecklistRecord, checklist_uid)
            if row is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            row.sync_state = CHECKLIST_SYNC_SYNCED
            row.uploaded_at = _utcnow()
            row.updated_at = _utcnow()
            session.flush()
            data = self._serialize_checklist(session, row)
            self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.uploaded", payload={"checklist": data, "uploaded_by_team_member_rns_identity": source_identity})
            self._record_snapshot(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, state=data)
            return data

    def publish_checklist_feed(self, checklist_uid: str, mission_feed_uid: str, *, source_identity: str | None = None) -> dict[str, Any]:
        mission_feed_uid = str(mission_feed_uid or "").strip()
        if not mission_feed_uid:
            raise ValueError("mission_feed_uid is required")
        with self._session() as session:
            checklist = session.get(R3aktChecklistRecord, checklist_uid)
            if checklist is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            if checklist.mode == CHECKLIST_MODE_OFFLINE and checklist.sync_state != CHECKLIST_SYNC_SYNCED:
                raise ValueError("Offline checklists must be SYNCED before publication")
            pub = R3aktChecklistFeedPublicationRecord(
                publication_uid=uuid.uuid4().hex,
                checklist_uid=checklist_uid,
                mission_feed_uid=mission_feed_uid,
                published_at=_utcnow(),
                published_by_team_member_rns_identity=str(source_identity or "unknown"),
            )
            session.add(pub)
            session.flush()
            data = self._serialize_publication(pub)
            self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.feed.published", payload=data)
            return data
    def import_checklist_csv(self, args: dict[str, Any]) -> dict[str, Any]:
        filename = str(args.get("csv_filename") or "checklist.csv")
        encoded = str(args.get("csv_base64") or "")
        if not encoded:
            raise ValueError("csv_base64 is required")
        try:
            decoded = base64.b64decode(encoded)
        except Exception as exc:
            raise ValueError("csv_base64 is invalid") from exc
        rows = [row for row in csv.reader(StringIO(decoded.decode("utf-8", errors="ignore"))) if row]
        checklist = self.create_checklist_offline(
            {
                "origin_type": "CSV_IMPORT",
                "name": Path(filename).stem or "Checklist CSV",
                "description": f"Imported from {filename}",
                "source_identity": args.get("source_identity"),
            }
        )
        for index, row in enumerate(rows, start=1):
            due = int(row[0]) if row and row[0].isdigit() else None
            self.add_checklist_task_row(checklist["uid"], {"number": index, "due_relative_minutes": due})
        with self._session() as session:
            entity = session.get(R3aktChecklistRecord, checklist["uid"])
            if entity is None:
                raise RuntimeError("Checklist import failed")
            data = self._serialize_checklist(session, entity)
            self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=entity.uid, event_type="checklist.imported.csv", payload=data)
            return data

    def add_checklist_task_row(self, checklist_uid: str, args: dict[str, Any]) -> dict[str, Any]:
        with self._session() as session:
            checklist = session.get(R3aktChecklistRecord, checklist_uid)
            if checklist is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            due_relative = args.get("due_relative_minutes")
            due_dtg = _as_datetime(args.get("due_dtg"))
            if due_dtg is None and due_relative is not None:
                due_dtg = checklist.start_time + timedelta(minutes=int(due_relative))
            status, is_late = self._derive_task_status(user_status=CHECKLIST_USER_PENDING, due_dtg=due_dtg, completed_at=None)
            task_uid = uuid.uuid4().hex
            task = R3aktChecklistTaskRecord(
                task_uid=task_uid,
                checklist_uid=checklist_uid,
                number=int(args.get("number") or 1),
                user_status=CHECKLIST_USER_PENDING,
                task_status=status,
                is_late=is_late,
                custom_status=None,
                due_relative_minutes=int(due_relative) if due_relative is not None else None,
                due_dtg=due_dtg,
                notes=None,
                row_background_color=None,
                line_break_enabled=False,
                completed_at=None,
                completed_by_team_member_rns_identity=None,
                legacy_value=None,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            session.add(task)
            for col in self._checklist_columns(session, checklist_uid):
                session.add(
                    R3aktChecklistCellRecord(
                        cell_uid=uuid.uuid4().hex,
                        task_uid=task_uid,
                        column_uid=col.column_uid,
                        value=None,
                        updated_at=_utcnow(),
                        updated_by_team_member_rns_identity=None,
                    )
                )
            session.flush()
            self._recompute_checklist_status(session, checklist)
            data = self._serialize_checklist(session, checklist)
            self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.progress.changed", payload=data)
            return data

    def delete_checklist_task_row(self, checklist_uid: str, task_uid: str) -> dict[str, Any]:
        with self._session() as session:
            checklist = session.get(R3aktChecklistRecord, checklist_uid)
            if checklist is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            task = session.get(R3aktChecklistTaskRecord, task_uid)
            if task is None or task.checklist_uid != checklist_uid:
                raise KeyError(f"Checklist task '{task_uid}' not found")
            session.query(R3aktChecklistCellRecord).filter(R3aktChecklistCellRecord.task_uid == task_uid).delete(synchronize_session=False)
            session.delete(task)
            session.flush()
            self._recompute_checklist_status(session, checklist)
            data = self._serialize_checklist(session, checklist)
            self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.progress.changed", payload=data)
            return data

    def set_checklist_task_row_style(self, checklist_uid: str, task_uid: str, args: dict[str, Any]) -> dict[str, Any]:
        with self._session() as session:
            checklist = session.get(R3aktChecklistRecord, checklist_uid)
            if checklist is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            task = session.get(R3aktChecklistTaskRecord, task_uid)
            if task is None or task.checklist_uid != checklist_uid:
                raise KeyError(f"Checklist task '{task_uid}' not found")
            if args.get("row_background_color") is not None:
                task.row_background_color = str(args.get("row_background_color"))
            if args.get("line_break_enabled") is not None:
                task.line_break_enabled = bool(args.get("line_break_enabled"))
            task.updated_at = _utcnow()
            session.flush()
            data = self._serialize_checklist(session, checklist)
            self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.progress.changed", payload=data)
            return data

    def set_checklist_task_cell(self, checklist_uid: str, task_uid: str, column_uid: str, args: dict[str, Any]) -> dict[str, Any]:
        with self._session() as session:
            checklist = session.get(R3aktChecklistRecord, checklist_uid)
            if checklist is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            task = session.get(R3aktChecklistTaskRecord, task_uid)
            if task is None or task.checklist_uid != checklist_uid:
                raise KeyError(f"Checklist task '{task_uid}' not found")
            column = session.get(R3aktChecklistColumnRecord, column_uid)
            if column is None or column.checklist_uid != checklist_uid:
                raise KeyError(f"Checklist column '{column_uid}' not found")
            cell = (
                session.query(R3aktChecklistCellRecord)
                .filter(R3aktChecklistCellRecord.task_uid == task_uid, R3aktChecklistCellRecord.column_uid == column_uid)
                .first()
            )
            if cell is None:
                cell = R3aktChecklistCellRecord(cell_uid=uuid.uuid4().hex, task_uid=task_uid, column_uid=column_uid, value=None, updated_at=_utcnow(), updated_by_team_member_rns_identity=None)
                session.add(cell)
            cell.value = None if args.get("value") is None else str(args.get("value"))
            cell.updated_at = _utcnow()
            if args.get("updated_by_team_member_rns_identity") is not None:
                cell.updated_by_team_member_rns_identity = str(args.get("updated_by_team_member_rns_identity"))
            session.flush()
            data = self._serialize_checklist(session, checklist)
            self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.progress.changed", payload=data)
            return data

    def set_checklist_task_status(self, checklist_uid: str, task_uid: str, args: dict[str, Any]) -> dict[str, Any]:
        user_status = str(args.get("user_status") or "").strip().upper()
        if user_status not in {CHECKLIST_USER_PENDING, CHECKLIST_USER_COMPLETE}:
            raise ValueError("user_status must be PENDING or COMPLETE")
        changed_by = args.get("changed_by_team_member_rns_identity")
        with self._session() as session:
            checklist = session.get(R3aktChecklistRecord, checklist_uid)
            if checklist is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            task = session.get(R3aktChecklistTaskRecord, task_uid)
            if task is None or task.checklist_uid != checklist_uid:
                raise KeyError(f"Checklist task '{task_uid}' not found")
            prev = task.task_status
            task.user_status = user_status
            now = _utcnow()
            if user_status == CHECKLIST_USER_COMPLETE:
                task.completed_at = task.completed_at or now
                if changed_by:
                    task.completed_by_team_member_rns_identity = str(changed_by)
            else:
                task.completed_at = None
                task.completed_by_team_member_rns_identity = None
            task.task_status, task.is_late = self._derive_task_status(user_status=task.user_status, due_dtg=task.due_dtg, completed_at=task.completed_at)
            task.updated_at = now
            session.flush()
            self._recompute_checklist_status(session, checklist)
            data = self._serialize_checklist(session, checklist)
            delta = {
                "checklist_uid": checklist_uid,
                "task_uid": task_uid,
                "previous_status": prev,
                "current_status": task.task_status,
                "changed_by_team_member_rns_identity": changed_by,
                "changed_at": now.isoformat(),
            }
            self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.task.status.changed", payload=delta)
            if task.task_status in {CHECKLIST_TASK_LATE, CHECKLIST_TASK_COMPLETE_LATE}:
                self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.task.marked.late", payload=delta)
            self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.progress.changed", payload=data)
            self._record_snapshot(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, state=data)
            return data
