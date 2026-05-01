"""Persistence-backed Emergency Action Message status service."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Callable
from typing import Any
from typing import Mapping
import uuid

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from reticulum_telemetry_hub.api.storage_models import Base
from reticulum_telemetry_hub.api.storage_models import EmergencyActionMessageRecord
from reticulum_telemetry_hub.api.storage_models import R3aktTeamMemberRecord
from reticulum_telemetry_hub.api.storage_models import R3aktTeamRecord
from reticulum_telemetry_hub.mission_domain.status_helpers import aggregate_status as _aggregate_status
from reticulum_telemetry_hub.mission_domain.status_helpers import dt_ms as _dt_ms
from reticulum_telemetry_hub.mission_domain.status_helpers import is_expired
from reticulum_telemetry_hub.mission_domain.status_helpers import normalize_status as _normalize_status
from reticulum_telemetry_hub.mission_domain.status_helpers import resolve_team_row
from reticulum_telemetry_hub.mission_domain.status_helpers import serialize_source
from reticulum_telemetry_hub.mission_domain.status_helpers import STATUS_DIMENSION_FIELDS
from reticulum_telemetry_hub.mission_domain.status_helpers import utcnow as _utcnow
from reticulum_telemetry_hub.mission_domain.status_payloads import StatusPayloadMixin


class EmergencyActionMessageService(StatusPayloadMixin):
    """Manage REM-compatible member-scoped Emergency Action Message snapshots."""

    def __init__(self, db_path: Path) -> None:
        """Initialize the service against the shared hub database."""

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
        self._ensure_deleted_at_column()
        self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False)
        self._status_listeners: list[Callable[[str, dict[str, Any]], None]] = []

    def _enable_wal_mode(self) -> None:
        """Enable WAL mode when SQLite supports it."""

        try:
            with self._engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as conn:
                conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
        except OperationalError:
            return

    def _ensure_deleted_at_column(self) -> None:
        """Backfill the soft-delete column for existing SQLite databases."""

        try:
            with self._engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as conn:
                columns = {
                    str(row[1])
                    for row in conn.exec_driver_sql(
                        "PRAGMA table_info(emergency_action_messages);"
                    ).fetchall()
                }
                if "deleted_at" not in columns:
                    conn.exec_driver_sql(
                        "ALTER TABLE emergency_action_messages ADD COLUMN deleted_at DATETIME;"
                    )
        except OperationalError:
            return

    @contextmanager
    def _session(self):
        """Yield a database session with commit/rollback handling."""

        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def register_status_listener(
        self,
        listener: Callable[[str, dict[str, Any]], None],
    ) -> Callable[[], None]:
        """Register a callback invoked after EAM upsert/delete operations."""

        self._status_listeners.append(listener)

        def _remove_listener() -> None:
            if listener in self._status_listeners:
                self._status_listeners.remove(listener)

        return _remove_listener

    def _notify_status_listeners(self, event_type: str, payload: dict[str, Any]) -> None:
        """Notify registered EAM listeners with the latest snapshot payload."""

        for listener in list(self._status_listeners):
            try:
                listener(event_type, dict(payload))
            except Exception:
                continue

    def list_messages(
        self,
        *,
        team_uid: str | None = None,
        overall_status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return REM-compatible EAM snapshots with optional filters."""

        with self._session() as session:
            query = session.query(EmergencyActionMessageRecord)
            if team_uid:
                query = query.filter(
                    EmergencyActionMessageRecord.team_id == str(team_uid).strip()
                )
            if overall_status:
                query = query.filter(
                    EmergencyActionMessageRecord.overall_status
                    == _normalize_status(overall_status, field_name="overall_status")
                )
            rows = (
                query.order_by(
                    EmergencyActionMessageRecord.callsign.asc(),
                    EmergencyActionMessageRecord.subject_id.asc(),
                ).all()
            )
            return [
                self._serialize_message(session, row)
                for row in rows
                if row.deleted_at is None and not is_expired(row)
            ]

    def upsert_message(
        self, payload: dict[str, Any], *, expected_callsign: str | None = None
    ) -> dict[str, Any]:
        """Create or update the current REM-compatible EAM snapshot."""

        normalized = self._normalize_payload(payload, expected_callsign=expected_callsign)
        with self._session() as session:
            team_row = resolve_team_row(
                session,
                normalized["team_uid"],
                normalized["group_name"],
            )
            member_row = session.get(R3aktTeamMemberRecord, normalized["team_member_uid"])
            if member_row is None:
                member_row = self._provision_team_member(
                    session,
                    team_uid=str(team_row.uid),
                    team_member_uid=normalized["team_member_uid"],
                    callsign=normalized["callsign"],
                    reported_by=normalized["reported_by"],
                    source=normalized["source"],
                )
            else:
                member_team_uid = str(member_row.team_uid or "").strip()
                if member_team_uid != normalized["team_uid"]:
                    raise ValueError(
                        (
                            f"team_member_uid '{normalized['team_member_uid']}'"
                            f" does not belong to team_uid '{normalized['team_uid']}'"
                        )
                    )

            active_row = (
                session.query(EmergencyActionMessageRecord)
                .filter(
                    EmergencyActionMessageRecord.subject_type == "member",
                    EmergencyActionMessageRecord.subject_id == normalized["team_member_uid"],
                    EmergencyActionMessageRecord.deleted_at.is_(None),
                )
                .one_or_none()
            )
            deleted_row = (
                session.query(EmergencyActionMessageRecord)
                .filter(
                    EmergencyActionMessageRecord.subject_type == "member",
                    EmergencyActionMessageRecord.subject_id == normalized["team_member_uid"],
                    EmergencyActionMessageRecord.deleted_at.is_not(None),
                )
                .one_or_none()
            )
            active_callsign = (
                session.query(EmergencyActionMessageRecord)
                .filter(
                    EmergencyActionMessageRecord.callsign == normalized["callsign"],
                    EmergencyActionMessageRecord.deleted_at.is_(None),
                )
                .one_or_none()
            )
            deleted_callsign = (
                session.query(EmergencyActionMessageRecord)
                .filter(
                    EmergencyActionMessageRecord.callsign == normalized["callsign"],
                    EmergencyActionMessageRecord.deleted_at.is_not(None),
                )
                .one_or_none()
            )

            if active_callsign is not None and (
                active_row is None or active_callsign.id != active_row.id
            ):
                raise ValueError(
                    f"callsign '{normalized['callsign']}' is already assigned to another status snapshot"
                )

            row = active_row
            if row is None:
                revive_candidates = {
                    candidate.id: candidate
                    for candidate in (deleted_row, deleted_callsign)
                    if candidate is not None
                }
                if len(revive_candidates) > 1:
                    raise ValueError(
                        (
                            "eam_uid cannot be recreated because deleted subject and"
                            " callsign snapshots refer to different records"
                        )
                    )
                row = next(iter(revive_candidates.values()), None)

            if row is None:
                row = EmergencyActionMessageRecord(
                    id=normalized["eam_uid"] or uuid.uuid4().hex
                )
                session.add(row)
            elif (
                active_row is not None
                and normalized["eam_uid"]
                and row.id != normalized["eam_uid"]
            ):
                raise ValueError(
                    (
                        f"eam_uid '{normalized['eam_uid']}' does not match the"
                        " existing snapshot for team_member_uid"
                        f" '{normalized['team_member_uid']}'"
                    )
                )
            elif normalized["eam_uid"]:
                row.id = normalized["eam_uid"]

            row.callsign = normalized["callsign"]
            row.subject_type = "member"
            row.subject_id = normalized["team_member_uid"]
            row.team_id = normalized["team_uid"]
            row.reported_by = normalized["reported_by"]
            row.reported_at = normalized["reported_at"]
            row.ttl_seconds = normalized["ttl_seconds"]
            row.deleted_at = None
            row.notes = normalized["notes"]
            row.confidence = normalized["confidence"]
            row.source = serialize_source(normalized["source"])
            row.security_status = normalized["security_status"]
            row.capability_status = normalized["capability_status"]
            row.preparedness_status = normalized["preparedness_status"]
            row.medical_status = normalized["medical_status"]
            row.mobility_status = normalized["mobility_status"]
            row.comms_status = normalized["comms_status"]
            row.overall_status = _aggregate_status(
                [str(normalized[field_name]) for field_name in STATUS_DIMENSION_FIELDS]
            )

            try:
                session.flush()
            except IntegrityError as exc:
                raise ValueError(
                    "EmergencyActionMessage conflicts with an existing snapshot"
                ) from exc

            snapshot = self._serialize_message(session, row)
            self._notify_status_listeners("mission.registry.eam.upserted", snapshot)
            return snapshot

    def get_message_by_callsign(self, callsign: str) -> dict[str, Any]:
        """Return the current snapshot for a callsign."""

        with self._session() as session:
            row = self._get_message_row_by_callsign(session, callsign)
            return self._serialize_message(session, row)

    def delete_message(self, callsign: str) -> dict[str, Any]:
        """Delete the current snapshot for a callsign."""

        with self._session() as session:
            row = self._get_message_row_by_callsign(session, callsign)
            data = self._serialize_message(session, row)
            row.deleted_at = _utcnow()
            self._notify_status_listeners("mission.registry.eam.deleted", data)
            return data

    def get_latest_message(self, team_member_uid: str) -> dict[str, Any]:
        """Return the latest stored snapshot for a team member UID."""

        normalized_team_member_uid = str(team_member_uid or "").strip()
        if not normalized_team_member_uid:
            raise ValueError("team_member_uid is required")
        with self._session() as session:
            row = (
                session.query(EmergencyActionMessageRecord)
                .filter(
                    EmergencyActionMessageRecord.subject_type == "member",
                    EmergencyActionMessageRecord.subject_id == normalized_team_member_uid,
                )
                .one_or_none()
            )
            if row is None or row.deleted_at is not None or is_expired(row):
                raise KeyError(
                    f"No active EmergencyActionMessage found for member/{normalized_team_member_uid}"
                )
            return self._serialize_message(session, row)

    def get_team_summary(self, team_uid: str) -> dict[str, Any]:
        """Compute a REM-compatible team summary using active/deleted buckets."""

        normalized_team_uid = str(team_uid or "").strip()
        if not normalized_team_uid:
            raise ValueError("team_uid is required")
        with self._session() as session:
            team = session.get(R3aktTeamRecord, normalized_team_uid)
            if team is None:
                raise KeyError(f"Team '{normalized_team_uid}' not found")
            rows = (
                session.query(EmergencyActionMessageRecord)
                .filter(EmergencyActionMessageRecord.team_id == normalized_team_uid)
                .all()
            )
            active_rows = [
                row
                for row in rows
                if row.deleted_at is None and not is_expired(row)
            ]
            deleted_or_expired_total = sum(
                1 for row in rows if row.deleted_at is not None or is_expired(row)
            )
            updated_at = max(
                (row.updated_at for row in rows),
                default=_utcnow(),
            )
            green_total = sum(1 for row in active_rows if row.overall_status == "Green")
            yellow_total = sum(1 for row in active_rows if row.overall_status == "Yellow")
            red_total = sum(1 for row in active_rows if row.overall_status == "Red")
            overall_status: str | None = None
            if red_total > 0:
                overall_status = "Red"
            elif yellow_total > 0:
                overall_status = "Yellow"
            elif green_total > 0:
                overall_status = "Green"
            return {
                "team_uid": normalized_team_uid,
                "total": len(rows),
                "active_total": len(active_rows),
                "deleted_total": deleted_or_expired_total,
                "overall_status": overall_status,
                "green_total": green_total,
                "yellow_total": yellow_total,
                "red_total": red_total,
                "updated_at_ms": _dt_ms(updated_at),
            }

    @staticmethod
    def _provision_team_member(
        session: Session,
        *,
        team_uid: str,
        team_member_uid: str,
        callsign: str,
        reported_by: str | None,
        source: Mapping[str, str | None] | None,
    ) -> R3aktTeamMemberRecord:
        """Create a missing team-member record from an inbound REM EAM."""

        source_identity = str((source or {}).get("rns_identity") or "").strip()
        if not source_identity:
            raise ValueError(
                f"team_member_uid '{team_member_uid}' is missing and source.rns_identity is required to provision it"
            )
        display_name = str(reported_by or callsign).strip()
        if not display_name:
            display_name = team_member_uid
        member_row = R3aktTeamMemberRecord(
            uid=team_member_uid,
            team_uid=team_uid,
            rns_identity=source_identity,
            icon=None,
            display_name=display_name,
            role=None,
            callsign=callsign,
            freq=None,
            email=None,
            phone=None,
            modulation=None,
            availability=None,
            certifications_json=[],
            last_active=None,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        session.add(member_row)
        session.flush()
        return member_row

    def _get_message_row_by_callsign(
        self, session: Session, callsign: str
    ) -> EmergencyActionMessageRecord:
        """Return a stored snapshot for a callsign or raise KeyError."""

        normalized_callsign = str(callsign or "").strip()
        if not normalized_callsign:
            raise ValueError("callsign is required")
        row = (
            session.query(EmergencyActionMessageRecord)
            .filter(
                EmergencyActionMessageRecord.callsign == normalized_callsign,
                EmergencyActionMessageRecord.deleted_at.is_(None),
            )
            .one_or_none()
        )
        if row is None:
            raise KeyError(f"EmergencyActionMessage '{normalized_callsign}' not found")
        return row
