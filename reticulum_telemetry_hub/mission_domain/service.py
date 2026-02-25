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
from typing import Callable
import uuid

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from reticulum_telemetry_hub.api.storage_models import Base
from reticulum_telemetry_hub.api.storage_models import MarkerRecord
from reticulum_telemetry_hub.api.storage_models import R3aktAssignmentAssetLinkRecord
from reticulum_telemetry_hub.api.storage_models import R3aktAssetRecord
from reticulum_telemetry_hub.api.storage_models import R3aktChecklistCellRecord
from reticulum_telemetry_hub.api.storage_models import R3aktChecklistColumnRecord
from reticulum_telemetry_hub.api.storage_models import R3aktChecklistFeedPublicationRecord
from reticulum_telemetry_hub.api.storage_models import R3aktChecklistRecord
from reticulum_telemetry_hub.api.storage_models import R3aktChecklistTaskRecord
from reticulum_telemetry_hub.api.storage_models import R3aktChecklistTemplateRecord
from reticulum_telemetry_hub.api.storage_models import R3aktDomainEventRecord
from reticulum_telemetry_hub.api.storage_models import R3aktDomainSnapshotRecord
from reticulum_telemetry_hub.api.storage_models import R3aktLogEntryRecord
from reticulum_telemetry_hub.api.storage_models import R3aktMissionChangeRecord
from reticulum_telemetry_hub.api.storage_models import R3aktMissionRecord
from reticulum_telemetry_hub.api.storage_models import R3aktMissionRdeRecord
from reticulum_telemetry_hub.api.storage_models import R3aktMissionTaskAssignmentRecord
from reticulum_telemetry_hub.api.storage_models import R3aktMissionTeamLinkRecord
from reticulum_telemetry_hub.api.storage_models import R3aktMissionZoneLinkRecord
from reticulum_telemetry_hub.api.storage_models import R3aktSkillRecord
from reticulum_telemetry_hub.api.storage_models import R3aktTaskSkillRequirementRecord
from reticulum_telemetry_hub.api.storage_models import R3aktTeamMemberClientLinkRecord
from reticulum_telemetry_hub.api.storage_models import R3aktTeamMemberRecord
from reticulum_telemetry_hub.api.storage_models import R3aktTeamMemberSkillRecord
from reticulum_telemetry_hub.api.storage_models import R3aktTeamRecord
from reticulum_telemetry_hub.api.storage_models import TopicRecord
from reticulum_telemetry_hub.api.storage_models import ZoneRecord
from reticulum_telemetry_hub.mission_domain.enums import AssetStatus
from reticulum_telemetry_hub.mission_domain.enums import ChecklistColumnType
from reticulum_telemetry_hub.mission_domain.enums import ChecklistMode
from reticulum_telemetry_hub.mission_domain.enums import ChecklistOriginType
from reticulum_telemetry_hub.mission_domain.enums import ChecklistStatus
from reticulum_telemetry_hub.mission_domain.enums import ChecklistSyncState
from reticulum_telemetry_hub.mission_domain.enums import ChecklistSystemColumnKey
from reticulum_telemetry_hub.mission_domain.enums import ChecklistTaskStatus
from reticulum_telemetry_hub.mission_domain.enums import ChecklistUserTaskStatus
from reticulum_telemetry_hub.mission_domain.enums import MISSION_PRIORITY_MAX
from reticulum_telemetry_hub.mission_domain.enums import MISSION_PRIORITY_MIN
from reticulum_telemetry_hub.mission_domain.enums import MissionChangeType
from reticulum_telemetry_hub.mission_domain.enums import MissionRole
from reticulum_telemetry_hub.mission_domain.enums import MissionStatus
from reticulum_telemetry_hub.mission_domain.enums import SKILL_LEVEL_MAX
from reticulum_telemetry_hub.mission_domain.enums import SKILL_LEVEL_MIN
from reticulum_telemetry_hub.mission_domain.enums import TeamColor
from reticulum_telemetry_hub.mission_domain.enums import TeamRole
from reticulum_telemetry_hub.mission_domain.enums import enum_values
from reticulum_telemetry_hub.mission_domain.enums import normalize_enum_value


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
            pending_notifications = list(
                session.info.pop(MISSION_CHANGE_LISTENER_KEY, [])
            )
            if pending_notifications:
                self._notify_mission_change_listeners(pending_notifications)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _run_additive_migrations(self) -> None:
        """Apply additive schema updates that SQLAlchemy ``create_all`` cannot handle."""

        self._ensure_mission_change_delta_column()

    def _ensure_mission_change_delta_column(self) -> None:
        """Ensure the mission-change ``delta`` JSON column exists for legacy databases."""

        with self._engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as conn:
            rows = conn.exec_driver_sql(
                "PRAGMA table_info(r3akt_mission_changes);"
            ).fetchall()
            column_names = {str(row[1]) for row in rows if len(row) > 1}
            if "delta" in column_names:
                return
            conn.exec_driver_sql(
                "ALTER TABLE r3akt_mission_changes ADD COLUMN delta JSON;"
            )

    def register_mission_change_listener(
        self, listener: Callable[[dict[str, Any]], None]
    ) -> Callable[[], None]:
        """Register a callback fired after mission changes commit."""

        self._mission_change_listeners.append(listener)

        def _remove_listener() -> None:
            if listener in self._mission_change_listeners:
                self._mission_change_listeners.remove(listener)

        return _remove_listener

    def _queue_mission_change_listener_notification(
        self, session: Session, mission_change: dict[str, Any]
    ) -> None:
        queue = session.info.setdefault(MISSION_CHANGE_LISTENER_KEY, [])
        if isinstance(queue, list):
            queue.append(dict(mission_change))

    def _notify_mission_change_listeners(
        self, mission_changes: list[dict[str, Any]]
    ) -> None:
        listeners = list(self._mission_change_listeners)
        if not listeners:
            return
        for mission_change in mission_changes:
            for listener in listeners:
                try:
                    listener(dict(mission_change))
                except Exception:
                    continue

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
        return MissionDomainService._dedupe_non_empty(mission_uids)

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
        return MissionDomainService._dedupe_non_empty(team_uids)

    @staticmethod
    def _team_member_mission_uids(session: Session, team_member_uid: str) -> list[str]:
        team_member = session.get(R3aktTeamMemberRecord, team_member_uid)
        if team_member is None or not team_member.team_uid:
            return []
        return MissionDomainService._team_mission_ids(session, str(team_member.team_uid))

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

    def upsert_mission(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("uid") or payload.get("mission_id") or uuid.uuid4().hex).strip()
        if not uid:
            raise ValueError("uid is required")
        with self._session() as session:
            row = session.get(R3aktMissionRecord, uid)
            if row is None:
                row = R3aktMissionRecord(uid=uid, mission_name="Mission")
                session.add(row)

            row.mission_name = str(payload.get("mission_name") or payload.get("name") or row.mission_name).strip()
            if not row.mission_name:
                raise ValueError("mission_name is required")
            row.description = str(payload.get("description") or row.description or "")

            topic_id = payload.get("topic_id")
            if topic_id is not None:
                topic_text = str(topic_id).strip()
                if topic_text:
                    if session.get(TopicRecord, topic_text) is None:
                        raise ValueError(f"Topic '{topic_text}' not found")
                    row.topic_id = topic_text
                else:
                    row.topic_id = None

            row.path = (
                str(payload.get("path")).strip()
                if payload.get("path") is not None
                else row.path
            )
            row.classification = (
                str(payload.get("classification")).strip()
                if payload.get("classification") is not None
                else row.classification
            )
            row.tool = (
                str(payload.get("tool")).strip()
                if payload.get("tool") is not None
                else row.tool
            )
            if "keywords" in payload:
                row.keywords_json = self._normalize_string_list(
                    payload.get("keywords"),
                    field_name="keywords",
                )
            elif row.keywords_json is None:
                row.keywords_json = []

            parent_uid = self._resolve_parent_uid(payload, row.parent_uid)
            self._ensure_parent_chain_is_acyclic(session, mission_uid=uid, parent_uid=parent_uid)
            row.parent_uid = parent_uid

            if "feeds" in payload:
                row.feeds_json = self._normalize_string_list(
                    payload.get("feeds"),
                    field_name="feeds",
                )
            elif row.feeds_json is None:
                row.feeds_json = []

            if payload.get("password_hash") is not None:
                row.password_hash = str(payload.get("password_hash")).strip() or None

            row.default_role = self._normalize_optional_enum(
                payload.get("default_role"),
                field_name="default_role",
                allowed_values=enum_values(MissionRole),
                current=row.default_role,
            )
            row.owner_role = self._normalize_optional_enum(
                payload.get("owner_role"),
                field_name="owner_role",
                allowed_values=enum_values(MissionRole),
                current=row.owner_role,
            )
            row.mission_status = normalize_enum_value(
                payload.get("mission_status"),
                field_name="mission_status",
                allowed_values=enum_values(MissionStatus),
                default=row.mission_status or MissionStatus.MISSION_ACTIVE.value,
            )
            row.mission_priority = self._normalize_integer(
                payload.get("mission_priority"),
                field_name="mission_priority",
                minimum=MISSION_PRIORITY_MIN,
                maximum=MISSION_PRIORITY_MAX,
                default=row.mission_priority,
            )
            if payload.get("token") is not None:
                row.token = str(payload.get("token")).strip() or None
            if payload.get("invite_only") is not None:
                row.invite_only = bool(payload.get("invite_only"))
            if payload.get("expiration") is not None:
                row.expiration = _as_datetime(payload.get("expiration"), default=None)

            mission_rde_role = payload.get("mission_rde_role")
            if mission_rde_role is not None:
                normalized_role = normalize_enum_value(
                    mission_rde_role,
                    field_name="mission_rde_role",
                    allowed_values=enum_values(MissionRole),
                    default=MissionRole.MISSION_SUBSCRIBER.value,
                )
                rde_row = session.get(R3aktMissionRdeRecord, uid)
                if rde_row is None:
                    session.add(
                        R3aktMissionRdeRecord(
                            mission_uid=uid,
                            role=normalized_role,
                        )
                    )
                else:
                    rde_row.role = normalized_role

            session.flush()
            data = self._serialize_mission(session, row)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="mission",
                aggregate_uid=uid,
                event_type="mission.upserted",
                payload=data,
            )
            self._record_snapshot(
                session,
                domain="mission",
                aggregate_type="mission",
                aggregate_uid=uid,
                state=data,
            )
            return data

    def patch_mission(self, mission_uid: str, patch: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(patch, dict):
            raise ValueError("patch must be an object")
        with self._session() as session:
            if session.get(R3aktMissionRecord, mission_uid) is None:
                raise KeyError(f"Mission '{mission_uid}' not found")
        return self.upsert_mission({"uid": mission_uid, **patch})

    def delete_mission(self, mission_uid: str) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktMissionRecord, mission_uid)
            if row is None:
                raise KeyError(f"Mission '{mission_uid}' not found")
            row.mission_status = MissionStatus.MISSION_DELETED.value
            row.updated_at = _utcnow()
            session.flush()
            data = self._serialize_mission(session, row)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="mission",
                aggregate_uid=mission_uid,
                event_type="mission.deleted",
                payload=data,
            )
            self._record_snapshot(
                session,
                domain="mission",
                aggregate_type="mission",
                aggregate_uid=mission_uid,
                state=data,
            )
            return data

    def list_missions(
        self, *, expand_topic: bool = False, expand: set[str] | list[str] | str | None = None
    ) -> list[dict[str, Any]]:
        expand_values = self._normalize_mission_expand(expand)
        with self._session() as session:
            return [
                self._serialize_mission(
                    session,
                    row,
                    expand_topic=expand_topic,
                    expand=expand_values,
                )
                for row in session.query(R3aktMissionRecord)
                .order_by(R3aktMissionRecord.created_at.desc())
                .all()
            ]

    def get_mission(
        self,
        mission_uid: str,
        *,
        expand_topic: bool = False,
        expand: set[str] | list[str] | str | None = None,
    ) -> dict[str, Any]:
        expand_values = self._normalize_mission_expand(expand)
        with self._session() as session:
            row = session.get(R3aktMissionRecord, mission_uid)
            if row is None:
                raise KeyError(f"Mission '{mission_uid}' not found")
            return self._serialize_mission(
                session,
                row,
                expand_topic=expand_topic,
                expand=expand_values,
            )

    def set_mission_parent(
        self, mission_uid: str, *, parent_uid: str | None
    ) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktMissionRecord, mission_uid)
            if row is None:
                raise KeyError(f"Mission '{mission_uid}' not found")
            normalized_parent = str(parent_uid or "").strip() or None
            self._ensure_parent_chain_is_acyclic(
                session,
                mission_uid=mission_uid,
                parent_uid=normalized_parent,
            )
            row.parent_uid = normalized_parent
            row.updated_at = _utcnow()
            session.flush()
            data = self._serialize_mission(session, row)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="mission",
                aggregate_uid=mission_uid,
                event_type="mission.parent.updated",
                payload={"mission_uid": mission_uid, "parent_uid": normalized_parent},
            )
            self._record_snapshot(
                session,
                domain="mission",
                aggregate_type="mission",
                aggregate_uid=mission_uid,
                state=data,
            )
            return data

    def link_mission_zone(self, mission_uid: str, zone_id: str) -> dict[str, Any]:
        zone_id = str(zone_id or "").strip()
        if not zone_id:
            raise ValueError("zone_id is required")
        with self._session() as session:
            mission = session.get(R3aktMissionRecord, mission_uid)
            if mission is None:
                raise KeyError(f"Mission '{mission_uid}' not found")
            if session.get(ZoneRecord, zone_id) is None:
                raise ValueError(f"Zone '{zone_id}' not found")
            row = (
                session.query(R3aktMissionZoneLinkRecord)
                .filter(
                    R3aktMissionZoneLinkRecord.mission_uid == mission_uid,
                    R3aktMissionZoneLinkRecord.zone_id == zone_id,
                )
                .first()
            )
            if row is None:
                session.add(
                    R3aktMissionZoneLinkRecord(
                        link_uid=uuid.uuid4().hex,
                        mission_uid=mission_uid,
                        zone_id=zone_id,
                    )
                )
            session.flush()
            data = self._serialize_mission(session, mission)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="mission",
                aggregate_uid=mission_uid,
                event_type="mission.zone.linked",
                payload={"mission_uid": mission_uid, "zone_id": zone_id},
            )
            return data

    def unlink_mission_zone(self, mission_uid: str, zone_id: str) -> dict[str, Any]:
        zone_id = str(zone_id or "").strip()
        if not zone_id:
            raise ValueError("zone_id is required")
        with self._session() as session:
            mission = session.get(R3aktMissionRecord, mission_uid)
            if mission is None:
                raise KeyError(f"Mission '{mission_uid}' not found")
            (
                session.query(R3aktMissionZoneLinkRecord)
                .filter(
                    R3aktMissionZoneLinkRecord.mission_uid == mission_uid,
                    R3aktMissionZoneLinkRecord.zone_id == zone_id,
                )
                .delete(synchronize_session=False)
            )
            session.flush()
            data = self._serialize_mission(session, mission)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="mission",
                aggregate_uid=mission_uid,
                event_type="mission.zone.unlinked",
                payload={"mission_uid": mission_uid, "zone_id": zone_id},
            )
            return data

    def list_mission_zones(self, mission_uid: str) -> list[str]:
        with self._session() as session:
            if session.get(R3aktMissionRecord, mission_uid) is None:
                raise KeyError(f"Mission '{mission_uid}' not found")
            return self._mission_zone_ids(session, mission_uid)

    def upsert_mission_rde(self, mission_uid: str, role: str) -> dict[str, Any]:
        normalized_role = normalize_enum_value(
            role,
            field_name="role",
            allowed_values=enum_values(MissionRole),
            default=MissionRole.MISSION_SUBSCRIBER.value,
        )
        with self._session() as session:
            self._ensure_mission_exists(session, mission_uid)
            row = session.get(R3aktMissionRdeRecord, mission_uid)
            if row is None:
                row = R3aktMissionRdeRecord(mission_uid=mission_uid, role=normalized_role)
                session.add(row)
            else:
                row.role = normalized_role
            session.flush()
            payload = {
                "mission_uid": mission_uid,
                "role": row.role,
                "updated_at": _dt(row.updated_at),
            }
            self._record_event(
                session,
                domain="mission",
                aggregate_type="mission_rde",
                aggregate_uid=mission_uid,
                event_type="mission.rde.upserted",
                payload=payload,
            )
            return payload

    def get_mission_rde(self, mission_uid: str) -> dict[str, Any]:
        with self._session() as session:
            if session.get(R3aktMissionRecord, mission_uid) is None:
                raise KeyError(f"Mission '{mission_uid}' not found")
            row = session.get(R3aktMissionRdeRecord, mission_uid)
            if row is None:
                return {"mission_uid": mission_uid, "role": None, "updated_at": None}
            return {
                "mission_uid": mission_uid,
                "role": row.role,
                "updated_at": _dt(row.updated_at),
            }

    @staticmethod
    def _serialize_mission_change(row: R3aktMissionChangeRecord) -> dict[str, Any]:
        return {
            "uid": row.uid,
            "mission_uid": row.mission_uid,
            "mission_id": row.mission_uid,
            "name": row.name,
            "team_member_rns_identity": row.team_member_rns_identity,
            "timestamp": _dt(row.timestamp),
            "notes": row.notes,
            "change_type": row.change_type,
            "is_federated_change": bool(row.is_federated_change),
            "hashes": list(row.hashes_json or []),
            "delta": dict(row.delta_json or {}),
        }

    @staticmethod
    def _normalize_mission_change_delta(payload: Any) -> dict[str, Any]:
        if payload is None:
            return {}
        if not isinstance(payload, dict):
            raise ValueError("delta must be an object")
        return dict(payload)

    def _upsert_mission_change_in_session(
        self,
        session: Session,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        uid = str(payload.get("uid") or uuid.uuid4().hex)
        mission_uid = str(
            payload.get("mission_uid") or payload.get("mission_id") or ""
        ).strip()
        if not mission_uid:
            raise ValueError("mission_uid is required")
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
        row.change_type = normalize_enum_value(
            payload.get("change_type"),
            field_name="change_type",
            allowed_values=enum_values(MissionChangeType),
            default=row.change_type or MissionChangeType.ADD_CONTENT.value,
        )
        if payload.get("is_federated_change") is not None:
            row.is_federated_change = bool(payload.get("is_federated_change"))
        hashes = self._normalize_string_list(payload.get("hashes"), field_name="hashes")
        for marker_ref in hashes:
            self._ensure_marker_exists(session, marker_ref)
        row.hashes_json = hashes
        row.delta_json = self._normalize_mission_change_delta(payload.get("delta"))
        session.flush()
        data = self._serialize_mission_change(row)
        self._record_event(
            session,
            domain="mission",
            aggregate_type="mission_change",
            aggregate_uid=uid,
            event_type="mission.change.upserted",
            payload=data,
        )
        self._queue_mission_change_listener_notification(session, data)
        return data

    def upsert_mission_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._session() as session:
            return self._upsert_mission_change_in_session(session, payload)

    def list_mission_changes(self, mission_uid: str | None = None) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(R3aktMissionChangeRecord)
            if mission_uid:
                query = query.filter(R3aktMissionChangeRecord.mission_uid == mission_uid)
            return [self._serialize_mission_change(row) for row in query.order_by(R3aktMissionChangeRecord.timestamp.desc()).all()]

    @staticmethod
    def _build_delta_envelope(
        *,
        source_event_type: str,
        logs: list[dict[str, Any]] | None = None,
        assets: list[dict[str, Any]] | None = None,
        tasks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "version": 1,
            "contract_version": MISSION_DELTA_CONTRACT_VERSION,
            "source_event_type": source_event_type,
            "emitted_at": _dt(_utcnow()),
            "logs": list(logs or []),
            "assets": list(assets or []),
            "tasks": list(tasks or []),
        }

    def _emit_auto_mission_change(
        self,
        session: Session,
        *,
        mission_uid: str | None,
        source_event_type: str,
        change_type: str,
        delta: dict[str, Any],
        notes: str | None = None,
        team_member_rns_identity: str | None = None,
        hashes: list[str] | None = None,
    ) -> dict[str, Any] | None:
        normalized_mission_uid = str(mission_uid or "").strip()
        if not normalized_mission_uid:
            return None
        payload: dict[str, Any] = {
            "uid": uuid.uuid4().hex,
            "mission_uid": normalized_mission_uid,
            "timestamp": _dt(_utcnow()),
            "change_type": change_type,
            "notes": notes,
            "team_member_rns_identity": team_member_rns_identity,
            "hashes": list(hashes or []),
            "delta": delta,
            "name": source_event_type,
        }
        return self._upsert_mission_change_in_session(session, payload)

    @staticmethod
    def _serialize_log_entry(row: R3aktLogEntryRecord) -> dict[str, Any]:
        return {
            "entry_uid": row.entry_uid,
            "mission_uid": row.mission_uid,
            "content": row.content,
            "server_time": _dt(row.server_time),
            "client_time": _dt(row.client_time),
            "content_hashes": list(row.content_hashes_json or []),
            "keywords": list(row.keywords_json or []),
            "created_at": _dt(row.created_at),
            "updated_at": _dt(row.updated_at),
        }

    def upsert_log_entry(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("entry_uid") or payload.get("uid") or uuid.uuid4().hex)
        mission_uid = str(payload.get("mission_uid") or payload.get("mission_id") or "").strip()
        if not mission_uid:
            raise ValueError("mission_uid is required")
        raw_content = payload.get("content")
        with self._session() as session:
            self._ensure_mission_exists(session, mission_uid)
            row = session.get(R3aktLogEntryRecord, uid)
            if row is None:
                content_text = str(raw_content or "").strip()
                if not content_text:
                    raise ValueError("content is required")
                row = R3aktLogEntryRecord(
                    entry_uid=uid,
                    mission_uid=mission_uid,
                    content=content_text,
                )
                session.add(row)
            row.mission_uid = mission_uid
            if raw_content is not None:
                content_text = str(raw_content).strip()
                if not content_text:
                    raise ValueError("content must not be empty")
                row.content = content_text

            raw_server_time = payload.get("server_time")
            if raw_server_time is None:
                raw_server_time = payload.get("servertime")
            row.server_time = (
                _as_datetime(raw_server_time, default=row.server_time or _utcnow())
                or _utcnow()
            )

            has_client_time = any(
                key in payload for key in ("client_time", "clientTime", "clienttime")
            )
            if has_client_time:
                raw_client_time = payload.get("client_time")
                if raw_client_time is None:
                    raw_client_time = payload.get("clientTime")
                if raw_client_time is None:
                    raw_client_time = payload.get("clienttime")
                row.client_time = _as_datetime(raw_client_time, default=None)

            has_content_hashes = "content_hashes" in payload or "contenthashes" in payload
            if has_content_hashes:
                raw_hashes = payload.get("content_hashes")
                if raw_hashes is None:
                    raw_hashes = payload.get("contenthashes")
                content_hashes = self._normalize_string_list(
                    raw_hashes, field_name="content_hashes"
                )
                for marker_ref in content_hashes:
                    self._ensure_marker_exists(session, marker_ref)
                row.content_hashes_json = content_hashes
            elif row.content_hashes_json is None:
                row.content_hashes_json = []

            if "keywords" in payload:
                row.keywords_json = self._normalize_string_list(
                    payload.get("keywords"),
                    field_name="keywords",
                )
            elif row.keywords_json is None:
                row.keywords_json = []

            row.updated_at = _utcnow()
            session.flush()
            data = self._serialize_log_entry(row)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="log_entry",
                aggregate_uid=uid,
                event_type="mission.log_entry.upserted",
                payload=data,
            )
            log_delta = {
                "op": "upsert",
                "entry_uid": data["entry_uid"],
                "mission_uid": data["mission_uid"],
                "content": data["content"],
                "server_time": data["server_time"],
                "client_time": data["client_time"],
                "keywords": list(data.get("keywords") or []),
                "content_hashes": list(data.get("content_hashes") or []),
            }
            self._emit_auto_mission_change(
                session,
                mission_uid=mission_uid,
                source_event_type="mission.log_entry.upserted",
                change_type=MissionChangeType.ADD_CONTENT.value,
                delta=self._build_delta_envelope(
                    source_event_type="mission.log_entry.upserted",
                    logs=[log_delta],
                ),
                hashes=list(data.get("content_hashes") or []),
            )
            return data

    def list_log_entries(
        self,
        *,
        mission_uid: str | None = None,
        marker_ref: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(R3aktLogEntryRecord)
            if mission_uid:
                query = query.filter(R3aktLogEntryRecord.mission_uid == mission_uid)
            rows = query.order_by(R3aktLogEntryRecord.server_time.desc()).all()
            entries = [self._serialize_log_entry(row) for row in rows]
            if marker_ref:
                value = str(marker_ref).strip()
                if value:
                    entries = [
                        entry for entry in entries if value in entry["content_hashes"]
                    ]
            return entries

    def _serialize_team(self, session: Session, row: R3aktTeamRecord) -> dict[str, Any]:
        mission_uids = self._team_mission_ids(session, row.uid)
        mission_uid = mission_uids[0] if mission_uids else None
        return {
            "uid": row.uid,
            "mission_uid": mission_uid,
            "mission_uids": mission_uids,
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

            mission_refs_provided = any(
                key in payload for key in ("mission_uid", "mission_id", "mission_uids")
            )
            if mission_refs_provided:
                mission_uids: list[str] = []
                if "mission_uids" in payload:
                    mission_uids = self._normalize_string_list(
                        payload.get("mission_uids"),
                        field_name="mission_uids",
                    )
                single_mission = str(
                    payload.get("mission_uid") or payload.get("mission_id") or ""
                ).strip()
                if single_mission:
                    mission_uids.append(single_mission)
                mission_uids = self._dedupe_non_empty(mission_uids)
                for mission_uid in mission_uids:
                    self._ensure_mission_exists(session, mission_uid)
                self._set_team_mission_links(
                    session,
                    team_uid=uid,
                    mission_uids=mission_uids,
                )
            else:
                mission_uids = self._team_mission_ids(session, uid)

            row.mission_uid = mission_uids[0] if mission_uids else None
            row.color = self._normalize_optional_enum(
                payload.get("color"),
                field_name="color",
                allowed_values=enum_values(TeamColor),
                current=row.color,
            )
            row.team_name = str(payload.get("team_name") or payload.get("name") or row.team_name)
            row.team_description = str(payload.get("team_description") or payload.get("description") or row.team_description or "")
            session.flush()
            data = self._serialize_team(session, row)
            self._record_event(session, domain="mission", aggregate_type="team", aggregate_uid=uid, event_type="team.upserted", payload=data)
            return data

    def list_teams(self, mission_uid: str | None = None) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(R3aktTeamRecord)
            if mission_uid:
                team_uids = self._mission_team_uids(session, str(mission_uid))
                if not team_uids:
                    return []
                query = query.filter(R3aktTeamRecord.uid.in_(team_uids))
            return [
                self._serialize_team(session, row)
                for row in query.order_by(R3aktTeamRecord.team_name.asc()).all()
            ]

    def get_team(self, team_uid: str) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktTeamRecord, team_uid)
            if row is None:
                raise KeyError(f"Team '{team_uid}' not found")
            return self._serialize_team(session, row)

    def delete_team(self, team_uid: str) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktTeamRecord, team_uid)
            if row is None:
                raise KeyError(f"Team '{team_uid}' not found")
            data = self._serialize_team(session, row)
            (
                session.query(R3aktTeamMemberRecord)
                .filter(R3aktTeamMemberRecord.team_uid == team_uid)
                .update(
                    {R3aktTeamMemberRecord.team_uid: None},
                    synchronize_session=False,
                )
            )
            (
                session.query(R3aktMissionTeamLinkRecord)
                .filter(R3aktMissionTeamLinkRecord.team_uid == team_uid)
                .delete(synchronize_session=False)
            )
            session.delete(row)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="team",
                aggregate_uid=team_uid,
                event_type="team.deleted",
                payload=data,
            )
            return data

    def list_team_missions(self, team_uid: str) -> list[str]:
        with self._session() as session:
            row = session.get(R3aktTeamRecord, team_uid)
            if row is None:
                raise KeyError(f"Team '{team_uid}' not found")
            return self._team_mission_ids(session, team_uid)

    def link_team_mission(self, team_uid: str, mission_uid: str) -> dict[str, Any]:
        mission_uid = str(mission_uid or "").strip()
        if not mission_uid:
            raise ValueError("mission_uid is required")
        with self._session() as session:
            row = session.get(R3aktTeamRecord, team_uid)
            if row is None:
                raise KeyError(f"Team '{team_uid}' not found")
            self._ensure_mission_exists(session, mission_uid)
            existing = self._team_mission_ids(session, team_uid)
            if mission_uid not in existing:
                existing.append(mission_uid)
            existing = self._dedupe_non_empty(existing)
            self._set_team_mission_links(
                session,
                team_uid=team_uid,
                mission_uids=existing,
            )
            row.mission_uid = existing[0] if existing else None
            session.flush()
            data = self._serialize_team(session, row)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="team",
                aggregate_uid=team_uid,
                event_type="team.mission.linked",
                payload={"team_uid": team_uid, "mission_uid": mission_uid},
            )
            return data

    def unlink_team_mission(self, team_uid: str, mission_uid: str) -> dict[str, Any]:
        mission_uid = str(mission_uid or "").strip()
        if not mission_uid:
            raise ValueError("mission_uid is required")
        with self._session() as session:
            row = session.get(R3aktTeamRecord, team_uid)
            if row is None:
                raise KeyError(f"Team '{team_uid}' not found")
            remaining = [
                item
                for item in self._team_mission_ids(session, team_uid)
                if item != mission_uid
            ]
            self._set_team_mission_links(
                session,
                team_uid=team_uid,
                mission_uids=remaining,
            )
            row.mission_uid = remaining[0] if remaining else None
            session.flush()
            data = self._serialize_team(session, row)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="team",
                aggregate_uid=team_uid,
                event_type="team.mission.unlinked",
                payload={"team_uid": team_uid, "mission_uid": mission_uid},
            )
            return data

    def list_mission_team_member_identities(self, mission_uid: str) -> list[str]:
        with self._session() as session:
            self._ensure_mission_exists(session, mission_uid)
            team_uids = self._mission_team_uids(session, mission_uid)
            if not team_uids:
                return []
            members = (
                session.query(R3aktTeamMemberRecord)
                .filter(R3aktTeamMemberRecord.team_uid.in_(team_uids))
                .order_by(R3aktTeamMemberRecord.created_at.asc())
                .all()
            )
            identities: list[str] = []
            for member in members:
                if member.rns_identity:
                    identities.append(str(member.rns_identity).strip().lower())
                identities.extend(self._team_member_clients(session, member.uid))
            return self._dedupe_non_empty(identities)

    def _team_member_clients(
        self, session: Session, team_member_uid: str
    ) -> list[str]:
        rows = (
            session.query(R3aktTeamMemberClientLinkRecord.client_identity)
            .filter(R3aktTeamMemberClientLinkRecord.team_member_uid == team_member_uid)
            .order_by(R3aktTeamMemberClientLinkRecord.created_at.asc())
            .all()
        )
        return [str(row[0]) for row in rows]

    def _serialize_team_member(
        self, session: Session, row: R3aktTeamMemberRecord
    ) -> dict[str, Any]:
        return {
            "uid": row.uid,
            "team_uid": row.team_uid,
            "rns_identity": row.rns_identity,
            "display_name": row.display_name,
            "icon": row.icon,
            "role": row.role,
            "callsign": row.callsign,
            "freq": row.freq,
            "email": row.email,
            "phone": row.phone,
            "modulation": row.modulation,
            "availability": row.availability,
            "certifications": list(row.certifications_json or []),
            "last_active": _dt(row.last_active),
            "client_identities": self._team_member_clients(session, row.uid),
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
            if "team_uid" in payload:
                team_uid = str(payload.get("team_uid") or "").strip()
            else:
                team_uid = str(row.team_uid or "").strip()
            if team_uid:
                self._ensure_team_exists(session, team_uid)
            row.team_uid = team_uid or None
            row.rns_identity = identity
            row.display_name = str(payload.get("display_name") or payload.get("callsign") or row.display_name)
            row.icon = payload.get("icon") or row.icon
            row.role = self._normalize_optional_enum(
                payload.get("role"),
                field_name="role",
                allowed_values=enum_values(TeamRole),
                current=row.role,
            )
            row.callsign = payload.get("callsign") or row.callsign
            if payload.get("freq") is not None:
                try:
                    row.freq = float(payload.get("freq"))
                except (TypeError, ValueError) as exc:
                    raise ValueError("freq must be numeric") from exc
            row.email = payload.get("email") or row.email
            row.phone = payload.get("phone") or row.phone
            row.modulation = payload.get("modulation") or row.modulation
            row.availability = payload.get("availability") or row.availability
            if "certifications" in payload:
                row.certifications_json = self._normalize_string_list(
                    payload.get("certifications"),
                    field_name="certifications",
                )
            elif row.certifications_json is None:
                row.certifications_json = []
            if payload.get("last_active") is not None:
                row.last_active = _as_datetime(payload.get("last_active"), default=None)
            session.flush()
            data = self._serialize_team_member(session, row)
            self._record_event(session, domain="mission", aggregate_type="team_member", aggregate_uid=uid, event_type="team_member.upserted", payload=data)
            return data

    def list_team_members(self, team_uid: str | None = None) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(R3aktTeamMemberRecord)
            if team_uid:
                query = query.filter(R3aktTeamMemberRecord.team_uid == team_uid)
            return [
                self._serialize_team_member(session, row)
                for row in query.order_by(R3aktTeamMemberRecord.display_name.asc()).all()
            ]

    def get_team_member(self, team_member_uid: str) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktTeamMemberRecord, team_member_uid)
            if row is None:
                raise KeyError(f"Team member '{team_member_uid}' not found")
            return self._serialize_team_member(session, row)

    def delete_team_member(self, team_member_uid: str) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktTeamMemberRecord, team_member_uid)
            if row is None:
                raise KeyError(f"Team member '{team_member_uid}' not found")
            data = self._serialize_team_member(session, row)
            member_identity = str(row.rns_identity or "").strip()
            (
                session.query(R3aktAssetRecord)
                .filter(R3aktAssetRecord.team_member_uid == team_member_uid)
                .update(
                    {R3aktAssetRecord.team_member_uid: None},
                    synchronize_session=False,
                )
            )
            (
                session.query(R3aktTeamMemberClientLinkRecord)
                .filter(R3aktTeamMemberClientLinkRecord.team_member_uid == team_member_uid)
                .delete(synchronize_session=False)
            )
            if member_identity:
                (
                    session.query(R3aktTeamMemberSkillRecord)
                    .filter(
                        R3aktTeamMemberSkillRecord.team_member_rns_identity
                        == member_identity
                    )
                    .delete(synchronize_session=False)
                )
            session.delete(row)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="team_member",
                aggregate_uid=team_member_uid,
                event_type="team_member.deleted",
                payload=data,
            )
            return data

    def link_team_member_client(self, team_member_uid: str, client_identity: str) -> dict[str, Any]:
        normalized_identity = self._normalize_identity(
            client_identity, field_name="client_identity"
        )
        with self._session() as session:
            member = session.get(R3aktTeamMemberRecord, team_member_uid)
            if member is None:
                raise KeyError(f"Team member '{team_member_uid}' not found")
            row = (
                session.query(R3aktTeamMemberClientLinkRecord)
                .filter(
                    R3aktTeamMemberClientLinkRecord.team_member_uid == team_member_uid,
                    R3aktTeamMemberClientLinkRecord.client_identity
                    == normalized_identity,
                )
                .first()
            )
            if row is None:
                session.add(
                    R3aktTeamMemberClientLinkRecord(
                        link_uid=uuid.uuid4().hex,
                        team_member_uid=team_member_uid,
                        client_identity=normalized_identity,
                    )
                )
            session.flush()
            data = self._serialize_team_member(session, member)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="team_member",
                aggregate_uid=team_member_uid,
                event_type="team_member.client.linked",
                payload={
                    "team_member_uid": team_member_uid,
                    "client_identity": normalized_identity,
                },
            )
            return data

    def unlink_team_member_client(self, team_member_uid: str, client_identity: str) -> dict[str, Any]:
        normalized_identity = self._normalize_identity(
            client_identity, field_name="client_identity"
        )
        with self._session() as session:
            member = session.get(R3aktTeamMemberRecord, team_member_uid)
            if member is None:
                raise KeyError(f"Team member '{team_member_uid}' not found")
            (
                session.query(R3aktTeamMemberClientLinkRecord)
                .filter(
                    R3aktTeamMemberClientLinkRecord.team_member_uid == team_member_uid,
                    R3aktTeamMemberClientLinkRecord.client_identity
                    == normalized_identity,
                )
                .delete(synchronize_session=False)
            )
            session.flush()
            data = self._serialize_team_member(session, member)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="team_member",
                aggregate_uid=team_member_uid,
                event_type="team_member.client.unlinked",
                payload={
                    "team_member_uid": team_member_uid,
                    "client_identity": normalized_identity,
                },
            )
            return data

    def list_team_member_clients(self, team_member_uid: str) -> list[str]:
        with self._session() as session:
            if session.get(R3aktTeamMemberRecord, team_member_uid) is None:
                raise KeyError(f"Team member '{team_member_uid}' not found")
            return self._team_member_clients(session, team_member_uid)
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
                row = R3aktAssetRecord(
                    asset_uid=uid,
                    team_member_uid=None,
                    name="Asset",
                    asset_type="generic",
                    status=ASSET_STATUS_AVAILABLE,
                )
                session.add(row)
            previous_team_member_uid = str(row.team_member_uid or "").strip() or None
            team_member_uid = payload.get("team_member_uid") or row.team_member_uid
            if team_member_uid:
                self._ensure_team_member_uid_exists(session, str(team_member_uid))
            row.team_member_uid = team_member_uid
            row.name = str(payload.get("name") or row.name)
            row.asset_type = str(payload.get("asset_type") or row.asset_type)
            row.serial_number = payload.get("serial_number") or row.serial_number
            row.status = self._normalize_asset_status(
                payload.get("status"),
                default=str(row.status or ASSET_STATUS_AVAILABLE),
            )
            row.location = payload.get("location") or row.location
            row.notes = payload.get("notes") or row.notes
            session.flush()
            data = self._serialize_asset(row)
            self._record_event(session, domain="mission", aggregate_type="asset", aggregate_uid=uid, event_type="asset.upserted", payload=data)
            mission_uids = self._dedupe_non_empty(
                self._team_member_mission_uids(
                    session,
                    str(row.team_member_uid or "").strip(),
                )
                + self._team_member_mission_uids(
                    session,
                    str(previous_team_member_uid or "").strip(),
                )
            )
            asset_delta = {
                "op": "upsert",
                "asset_uid": data["asset_uid"],
                "team_member_uid": data["team_member_uid"],
                "name": data["name"],
                "asset_type": data["asset_type"],
                "status": data["status"],
                "location": data["location"],
                "notes": data["notes"],
            }
            for mission_uid in mission_uids:
                self._emit_auto_mission_change(
                    session,
                    mission_uid=mission_uid,
                    source_event_type="mission.asset.upserted",
                    change_type=MissionChangeType.ADD_CONTENT.value,
                    delta=self._build_delta_envelope(
                        source_event_type="mission.asset.upserted",
                        assets=[asset_delta],
                    ),
                )
            return data

    def list_assets(self, team_member_uid: str | None = None) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(R3aktAssetRecord)
            if team_member_uid:
                query = query.filter(R3aktAssetRecord.team_member_uid == team_member_uid)
            return [self._serialize_asset(row) for row in query.order_by(R3aktAssetRecord.name.asc()).all()]

    def get_asset(self, asset_uid: str) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktAssetRecord, asset_uid)
            if row is None:
                raise KeyError(f"Asset '{asset_uid}' not found")
            return self._serialize_asset(row)

    def delete_asset(self, asset_uid: str) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktAssetRecord, asset_uid)
            if row is None:
                raise KeyError(f"Asset '{asset_uid}' not found")
            data = self._serialize_asset(row)
            mission_uids = self._team_member_mission_uids(
                session,
                str(row.team_member_uid or "").strip(),
            )
            linked_assignments = (
                session.query(R3aktMissionTaskAssignmentRecord.mission_uid)
                .join(
                    R3aktAssignmentAssetLinkRecord,
                    R3aktAssignmentAssetLinkRecord.assignment_uid
                    == R3aktMissionTaskAssignmentRecord.assignment_uid,
                )
                .filter(R3aktAssignmentAssetLinkRecord.asset_uid == asset_uid)
                .all()
            )
            mission_uids.extend(str(item[0]) for item in linked_assignments)
            mission_uids = self._dedupe_non_empty(mission_uids)
            (
                session.query(R3aktAssignmentAssetLinkRecord)
                .filter(R3aktAssignmentAssetLinkRecord.asset_uid == asset_uid)
                .delete(synchronize_session=False)
            )
            assignments = session.query(R3aktMissionTaskAssignmentRecord).all()
            for assignment in assignments:
                existing_assets = [str(item) for item in list(assignment.assets_json or [])]
                filtered_assets = [
                    item for item in existing_assets if item != asset_uid
                ]
                if filtered_assets != existing_assets:
                    assignment.assets_json = filtered_assets
            session.delete(row)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="asset",
                aggregate_uid=asset_uid,
                event_type="asset.deleted",
                payload=data,
            )
            asset_delta = {
                "op": "delete",
                "asset_uid": data["asset_uid"],
                "team_member_uid": data["team_member_uid"],
                "name": data["name"],
                "asset_type": data["asset_type"],
                "status": data["status"],
                "location": data["location"],
                "notes": data["notes"],
            }
            for mission_uid in mission_uids:
                self._emit_auto_mission_change(
                    session,
                    mission_uid=mission_uid,
                    source_event_type="mission.asset.deleted",
                    change_type=MissionChangeType.REMOVE_CONTENT.value,
                    delta=self._build_delta_envelope(
                        source_event_type="mission.asset.deleted",
                        assets=[asset_delta],
                    ),
                )
            return data

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
        column_type = normalize_enum_value(
            payload.get("column_type"),
            field_name="column_type",
            allowed_values=enum_values(ChecklistColumnType),
            default=ChecklistColumnType.SHORT_STRING.value,
        )
        system_key = payload.get("system_key")
        if system_key is not None and str(system_key).strip():
            system_key = normalize_enum_value(
                system_key,
                field_name="system_key",
                allowed_values=enum_values(ChecklistSystemColumnKey),
                default=None,
            )
        else:
            system_key = None
        return {
            "column_uid": str(payload.get("column_uid") or payload.get("uid") or uuid.uuid4().hex),
            "column_name": str(payload.get("column_name") or payload.get("name") or "Column"),
            "display_order": int(payload.get("display_order") or order),
            "column_type": column_type,
            "column_editable": bool(payload.get("column_editable", True)),
            "is_removable": bool(payload.get("is_removable", True)),
            "system_key": system_key,
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

    def get_checklist_template(self, template_uid: str) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktChecklistTemplateRecord, template_uid)
            if row is None:
                raise KeyError(f"Checklist template '{template_uid}' not found")
            return self._serialize_template(session, row)

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

    def _create_checklist(
        self,
        *,
        mode: str,
        sync_state: str,
        origin_type: str,
        name: str,
        description: str,
        start_time: datetime,
        created_by: str,
        mission_uid: str | None = None,
        template_uid: str | None = None,
        columns: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        mode = normalize_enum_value(
            mode,
            field_name="mode",
            allowed_values=enum_values(ChecklistMode),
            default=CHECKLIST_MODE_ONLINE,
        )
        sync_state = normalize_enum_value(
            sync_state,
            field_name="sync_state",
            allowed_values=enum_values(ChecklistSyncState),
            default=CHECKLIST_SYNC_LOCAL_ONLY,
        )
        origin_type = normalize_enum_value(
            origin_type,
            field_name="origin_type",
            allowed_values=enum_values(ChecklistOriginType),
            default=ChecklistOriginType.BLANK_TEMPLATE.value,
        )
        with self._session() as session:
            if mission_uid:
                self._ensure_mission_exists(session, str(mission_uid))
            if template_uid:
                template = session.get(R3aktChecklistTemplateRecord, template_uid)
                if template is None:
                    raise KeyError(f"Checklist template '{template_uid}' not found")
                cols = [self._serialize_column(col) for col in self._template_columns(session, template_uid)]
                template_name = template.template_name
            elif columns:
                cols = [self._normalize_column(item, order=index) for index, item in enumerate(columns, start=1)]
                template_name = None
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
            origin_type=ChecklistOriginType.RCH_TEMPLATE.value,
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
        raw_columns = args.get("columns")
        columns = list(raw_columns) if isinstance(raw_columns, list) else None
        requested_sync_state = args.get("sync_state")
        return self._create_checklist(
            mode=CHECKLIST_MODE_OFFLINE,
            sync_state=str(requested_sync_state or CHECKLIST_SYNC_LOCAL_ONLY),
            origin_type=str(
                args.get("origin_type") or ChecklistOriginType.BLANK_TEMPLATE.value
            ),
            name=name,
            description=str(args.get("description") or ""),
            start_time=_as_datetime(args.get("start_time"), default=_utcnow()) or _utcnow(),
            created_by=str(args.get("source_identity") or args.get("created_by_team_member_rns_identity") or "unknown"),
            mission_uid=args.get("mission_uid"),
            template_uid=args.get("template_uid"),
            columns=columns,
        )

    def get_checklist(self, checklist_uid: str) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktChecklistRecord, checklist_uid)
            if row is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            return self._serialize_checklist(session, row)

    def update_checklist(self, checklist_uid: str, patch: dict[str, Any]) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktChecklistRecord, checklist_uid)
            if row is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")

            if patch.get("name") is not None:
                row.name = str(patch.get("name"))

            if patch.get("description") is not None:
                row.description = str(patch.get("description"))

            if "mission_uid" in patch or "mission_id" in patch:
                raw_mission_uid = patch.get("mission_uid")
                if raw_mission_uid is None and "mission_uid" not in patch:
                    raw_mission_uid = patch.get("mission_id")
                mission_uid = str(raw_mission_uid or "").strip() or None
                if mission_uid:
                    self._ensure_mission_exists(session, mission_uid)
                row.mission_uid = mission_uid

            if patch.get("mode") is not None:
                row.mode = normalize_enum_value(
                    patch.get("mode"),
                    field_name="mode",
                    allowed_values=enum_values(ChecklistMode),
                    default=row.mode or CHECKLIST_MODE_ONLINE,
                )

            if patch.get("sync_state") is not None:
                row.sync_state = normalize_enum_value(
                    patch.get("sync_state"),
                    field_name="sync_state",
                    allowed_values=enum_values(ChecklistSyncState),
                    default=row.sync_state or CHECKLIST_SYNC_LOCAL_ONLY,
                )

            if patch.get("origin_type") is not None:
                row.origin_type = normalize_enum_value(
                    patch.get("origin_type"),
                    field_name="origin_type",
                    allowed_values=enum_values(ChecklistOriginType),
                    default=row.origin_type or ChecklistOriginType.BLANK_TEMPLATE.value,
                )

            if patch.get("checklist_status") is not None:
                row.checklist_status = normalize_enum_value(
                    patch.get("checklist_status"),
                    field_name="checklist_status",
                    allowed_values=enum_values(ChecklistStatus),
                    default=row.checklist_status or ChecklistStatus.PENDING.value,
                )

            row.updated_at = _utcnow()
            session.flush()
            data = self._serialize_checklist(session, row)
            self._record_event(
                session,
                domain="checklist",
                aggregate_type="checklist",
                aggregate_uid=checklist_uid,
                event_type="checklist.updated",
                payload=data,
            )
            self._record_snapshot(
                session,
                domain="checklist",
                aggregate_type="checklist",
                aggregate_uid=checklist_uid,
                state=data,
            )
            return data

    def delete_checklist(self, checklist_uid: str) -> dict[str, Any]:
        with self._session() as session:
            checklist = session.get(R3aktChecklistRecord, checklist_uid)
            if checklist is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            data = self._serialize_checklist(session, checklist)
            task_uids = [
                str(task.task_uid)
                for task in session.query(R3aktChecklistTaskRecord.task_uid)
                .filter(R3aktChecklistTaskRecord.checklist_uid == checklist_uid)
                .all()
            ]
            if task_uids:
                session.query(R3aktChecklistCellRecord).filter(
                    R3aktChecklistCellRecord.task_uid.in_(task_uids)
                ).delete(synchronize_session=False)
                session.query(R3aktTaskSkillRequirementRecord).filter(
                    R3aktTaskSkillRequirementRecord.task_uid.in_(task_uids)
                ).delete(synchronize_session=False)
                session.query(R3aktMissionTaskAssignmentRecord).filter(
                    R3aktMissionTaskAssignmentRecord.task_uid.in_(task_uids)
                ).delete(synchronize_session=False)
            session.query(R3aktChecklistTaskRecord).filter(
                R3aktChecklistTaskRecord.checklist_uid == checklist_uid
            ).delete(synchronize_session=False)
            session.query(R3aktChecklistColumnRecord).filter(
                R3aktChecklistColumnRecord.checklist_uid == checklist_uid
            ).delete(synchronize_session=False)
            session.query(R3aktChecklistFeedPublicationRecord).filter(
                R3aktChecklistFeedPublicationRecord.checklist_uid == checklist_uid
            ).delete(synchronize_session=False)
            session.delete(checklist)
            self._record_event(
                session,
                domain="checklist",
                aggregate_type="checklist",
                aggregate_uid=checklist_uid,
                event_type="checklist.deleted",
                payload=data,
            )
            return data

    def join_checklist(self, checklist_uid: str, *, source_identity: str | None = None) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktChecklistRecord, checklist_uid)
            if row is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            data = self._serialize_checklist(session, row)
            self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.joined", payload={"checklist": data, "joined_by_team_member_rns_identity": source_identity})
            return data

    def mark_checklist_upload_pending(
        self, checklist_uid: str, *, source_identity: str | None = None
    ) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktChecklistRecord, checklist_uid)
            if row is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            row.sync_state = CHECKLIST_SYNC_UPLOAD_PENDING
            row.updated_at = _utcnow()
            session.flush()
            data = self._serialize_checklist(session, row)
            self._record_event(
                session,
                domain="checklist",
                aggregate_type="checklist",
                aggregate_uid=checklist_uid,
                event_type="checklist.upload.pending",
                payload={
                    "checklist": data,
                    "marked_by_team_member_rns_identity": source_identity,
                },
            )
            self._record_snapshot(
                session,
                domain="checklist",
                aggregate_type="checklist",
                aggregate_uid=checklist_uid,
                state=data,
            )
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
        rows = [
            [str(cell).replace("\ufeff", "").strip() for cell in row]
            for row in csv.reader(StringIO(decoded.decode("utf-8", errors="ignore")))
        ]
        rows = [row for row in rows if any(cell for cell in row)]
        if len(rows) < 2:
            raise ValueError("CSV must include a header row and at least one task row")

        header_row = rows[0]
        task_rows = rows[1:]
        max_columns = max(len(header_row), *(len(row) for row in task_rows))
        if max_columns <= 0:
            raise ValueError("CSV header row is empty")

        headers = [
            (header_row[index] if index < len(header_row) else "").strip() or f"Column {index + 1}"
            for index in range(max_columns)
        ]

        def _normalize_header(value: str) -> str:
            return " ".join(value.lower().replace("_", " ").replace("-", " ").split())

        due_aliases = {"due", "due relative minutes", "due minutes"}
        due_header_index = next(
            (index for index, value in enumerate(headers) if _normalize_header(value) in due_aliases),
            None,
        )

        columns: list[dict[str, Any]] = []
        if due_header_index is None:
            columns.append(
                {
                    "column_name": "Due",
                    "column_type": "RELATIVE_TIME",
                    "column_editable": False,
                    "is_removable": False,
                    "system_key": SYSTEM_COLUMN_KEY_DUE_RELATIVE_DTG,
                }
            )
            for header in headers:
                columns.append(
                    {
                        "column_name": header,
                        "column_type": "SHORT_STRING",
                        "column_editable": True,
                        "is_removable": True,
                    }
                )
            header_display_orders: dict[int, int] = {index: index + 2 for index in range(len(headers))}
        else:
            for index, header in enumerate(headers):
                if index == due_header_index:
                    columns.append(
                        {
                            "column_name": header or "Due",
                            "column_type": "RELATIVE_TIME",
                            "column_editable": False,
                            "is_removable": False,
                            "system_key": SYSTEM_COLUMN_KEY_DUE_RELATIVE_DTG,
                        }
                    )
                else:
                    columns.append(
                        {
                            "column_name": header,
                            "column_type": "SHORT_STRING",
                            "column_editable": True,
                            "is_removable": True,
                        }
                    )
            header_display_orders = {index: index + 1 for index in range(len(headers))}

        checklist = self.create_checklist_offline(
            {
                "origin_type": "CSV_IMPORT",
                "name": Path(filename).stem or "Checklist CSV",
                "description": f"Imported from {filename}",
                "source_identity": args.get("source_identity"),
                "mission_uid": args.get("mission_uid"),
                "columns": columns,
            }
        )
        checklist_uid = str(checklist["uid"])
        created_columns = {int(col.get("display_order") or 0): str(col.get("column_uid") or "") for col in checklist.get("columns") or []}
        header_column_uids: dict[int, str] = {}
        for header_index, order in header_display_orders.items():
            if due_header_index is not None and header_index == due_header_index:
                continue
            column_uid = created_columns.get(order, "")
            if column_uid:
                header_column_uids[header_index] = column_uid

        source_identity = str(args.get("source_identity") or "unknown")

        def _parse_due_minutes(value: str) -> int | None:
            text = str(value or "").strip()
            if not text:
                return None
            if text.startswith("+"):
                text = text[1:]
            negative = text.startswith("-")
            digits = text[1:] if negative else text
            if not digits.isdigit():
                return None
            return -int(digits) if negative else int(digits)

        for index, row in enumerate(task_rows, start=1):
            normalized_row = [(row[col_index] if col_index < len(row) else "").strip() for col_index in range(len(headers))]
            due_minutes = None
            if due_header_index is not None:
                due_value = normalized_row[due_header_index] if due_header_index < len(normalized_row) else ""
                due_minutes = _parse_due_minutes(due_value)

            row_value = next(
                (
                    value
                    for cell_index, value in enumerate(normalized_row)
                    if value and (due_header_index is None or cell_index != due_header_index)
                ),
                None,
            )

            updated = self.add_checklist_task_row(
                checklist_uid,
                {
                    "number": index,
                    "due_relative_minutes": due_minutes,
                    "legacy_value": row_value,
                },
            )
            task_uid = str(
                next(
                    (
                        task.get("task_uid")
                        for task in updated.get("tasks") or []
                        if int(task.get("number") or 0) == index
                    ),
                    "",
                )
            )
            if not task_uid:
                raise RuntimeError("Checklist import failed to create task row")

            for column_index, column_uid in header_column_uids.items():
                value = normalized_row[column_index] if column_index < len(normalized_row) else ""
                if not value:
                    continue
                self.set_checklist_task_cell(
                    checklist_uid,
                    task_uid,
                    column_uid,
                    {
                        "value": value,
                        "updated_by_team_member_rns_identity": source_identity,
                    },
                )

        with self._session() as session:
            entity = session.get(R3aktChecklistRecord, checklist_uid)
            if entity is None:
                raise RuntimeError("Checklist import failed")
            data = self._serialize_checklist(session, entity)
            self._record_event(
                session,
                domain="checklist",
                aggregate_type="checklist",
                aggregate_uid=entity.uid,
                event_type="checklist.imported.csv",
                payload=data,
            )
            self._record_snapshot(
                session,
                domain="checklist",
                aggregate_type="checklist",
                aggregate_uid=entity.uid,
                state=data,
            )
            return data

    def add_checklist_task_row(self, checklist_uid: str, args: dict[str, Any]) -> dict[str, Any]:
        with self._session() as session:
            checklist = session.get(R3aktChecklistRecord, checklist_uid)
            if checklist is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            mission_uid = str(checklist.mission_uid or "").strip() or None
            task_number = int(args.get("number") or 1)
            due_dtg = _as_datetime(args.get("due_dtg"))
            due_relative_minutes: int | None
            raw_due_relative = args.get("due_relative_minutes")
            if raw_due_relative is None:
                due_relative_minutes = (
                    task_number * CHECKLIST_DEFAULT_DUE_STEP_MINUTES
                    if due_dtg is None
                    else None
                )
            else:
                due_relative_minutes = int(raw_due_relative)
            if due_dtg is None and due_relative_minutes is not None:
                due_dtg = checklist.start_time + timedelta(minutes=due_relative_minutes)
            legacy_value_raw = args.get("legacy_value")
            legacy_value = None
            if legacy_value_raw is not None:
                legacy_value_text = str(legacy_value_raw).strip()
                legacy_value = legacy_value_text or None
            status, is_late = self._derive_task_status(user_status=CHECKLIST_USER_PENDING, due_dtg=due_dtg, completed_at=None)
            task_uid = uuid.uuid4().hex
            task = R3aktChecklistTaskRecord(
                task_uid=task_uid,
                checklist_uid=checklist_uid,
                number=task_number,
                user_status=CHECKLIST_USER_PENDING,
                task_status=status,
                is_late=is_late,
                custom_status=None,
                due_relative_minutes=due_relative_minutes,
                due_dtg=due_dtg,
                notes=None,
                row_background_color=None,
                line_break_enabled=False,
                completed_at=None,
                completed_by_team_member_rns_identity=None,
                legacy_value=legacy_value,
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
            task_delta = {
                "op": "row_added",
                "mission_uid": mission_uid,
                "checklist_uid": checklist_uid,
                "task_uid": task_uid,
                "number": int(task.number or 0),
                "status": task.task_status,
                "user_status": task.user_status,
                "due_dtg": _dt(task.due_dtg),
                "due_relative_minutes": task.due_relative_minutes,
            }
            self._emit_auto_mission_change(
                session,
                mission_uid=mission_uid,
                source_event_type="mission.checklist.task.row.added",
                change_type=MissionChangeType.ADD_CONTENT.value,
                delta=self._build_delta_envelope(
                    source_event_type="mission.checklist.task.row.added",
                    tasks=[task_delta],
                ),
            )
            return data

    def delete_checklist_task_row(self, checklist_uid: str, task_uid: str) -> dict[str, Any]:
        with self._session() as session:
            checklist = session.get(R3aktChecklistRecord, checklist_uid)
            if checklist is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            mission_uid = str(checklist.mission_uid or "").strip() or None
            task = session.get(R3aktChecklistTaskRecord, task_uid)
            if task is None or task.checklist_uid != checklist_uid:
                raise KeyError(f"Checklist task '{task_uid}' not found")
            deleted_task_payload = {
                "op": "row_deleted",
                "mission_uid": mission_uid,
                "checklist_uid": checklist_uid,
                "task_uid": task_uid,
                "number": int(task.number or 0),
                "status": task.task_status,
                "user_status": task.user_status,
            }
            session.query(R3aktChecklistCellRecord).filter(R3aktChecklistCellRecord.task_uid == task_uid).delete(synchronize_session=False)
            session.delete(task)
            session.flush()
            self._recompute_checklist_status(session, checklist)
            data = self._serialize_checklist(session, checklist)
            self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.progress.changed", payload=data)
            self._emit_auto_mission_change(
                session,
                mission_uid=mission_uid,
                source_event_type="mission.checklist.task.row.deleted",
                change_type=MissionChangeType.REMOVE_CONTENT.value,
                delta=self._build_delta_envelope(
                    source_event_type="mission.checklist.task.row.deleted",
                    tasks=[deleted_task_payload],
                ),
            )
            return data

    def set_checklist_task_row_style(self, checklist_uid: str, task_uid: str, args: dict[str, Any]) -> dict[str, Any]:
        with self._session() as session:
            checklist = session.get(R3aktChecklistRecord, checklist_uid)
            if checklist is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            mission_uid = str(checklist.mission_uid or "").strip() or None
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
            task_delta = {
                "op": "row_style_set",
                "mission_uid": mission_uid,
                "checklist_uid": checklist_uid,
                "task_uid": task_uid,
                "row_background_color": task.row_background_color,
                "line_break_enabled": bool(task.line_break_enabled),
            }
            self._emit_auto_mission_change(
                session,
                mission_uid=mission_uid,
                source_event_type="mission.checklist.task.row.style_set",
                change_type=MissionChangeType.ADD_CONTENT.value,
                delta=self._build_delta_envelope(
                    source_event_type="mission.checklist.task.row.style_set",
                    tasks=[task_delta],
                ),
            )
            return data

    def set_checklist_task_cell(self, checklist_uid: str, task_uid: str, column_uid: str, args: dict[str, Any]) -> dict[str, Any]:
        with self._session() as session:
            checklist = session.get(R3aktChecklistRecord, checklist_uid)
            if checklist is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            mission_uid = str(checklist.mission_uid or "").strip() or None
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
            task_delta = {
                "op": "cell_set",
                "mission_uid": mission_uid,
                "checklist_uid": checklist_uid,
                "task_uid": task_uid,
                "column_uid": column_uid,
                "value": cell.value,
                "updated_by_team_member_rns_identity": cell.updated_by_team_member_rns_identity,
                "updated_at": _dt(cell.updated_at),
            }
            self._emit_auto_mission_change(
                session,
                mission_uid=mission_uid,
                source_event_type="mission.checklist.task.cell_set",
                change_type=MissionChangeType.ADD_CONTENT.value,
                delta=self._build_delta_envelope(
                    source_event_type="mission.checklist.task.cell_set",
                    tasks=[task_delta],
                ),
                team_member_rns_identity=cell.updated_by_team_member_rns_identity,
            )
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
            mission_uid = str(checklist.mission_uid or "").strip() or None
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
            task_delta = {
                "op": "status_set",
                "mission_uid": mission_uid,
                "checklist_uid": checklist_uid,
                "task_uid": task_uid,
                "previous_status": prev,
                "current_status": task.task_status,
                "user_status": task.user_status,
                "changed_by_team_member_rns_identity": changed_by,
                "changed_at": _dt(now),
                "completed_at": _dt(task.completed_at),
                "due_dtg": _dt(task.due_dtg),
            }
            self._emit_auto_mission_change(
                session,
                mission_uid=mission_uid,
                source_event_type="mission.checklist.task.status_set",
                change_type=MissionChangeType.ADD_CONTENT.value,
                delta=self._build_delta_envelope(
                    source_event_type="mission.checklist.task.status_set",
                    tasks=[task_delta],
                ),
                team_member_rns_identity=(
                    str(changed_by).strip() if changed_by is not None else None
                ),
            )
            return data
