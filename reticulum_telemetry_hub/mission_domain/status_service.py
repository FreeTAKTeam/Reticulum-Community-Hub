"""Persistence-backed Emergency Action Message status service."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from datetime import timedelta
from datetime import timezone
import json
from pathlib import Path
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
from reticulum_telemetry_hub.mission_domain.canonical_teams import canonical_team_for_color
from reticulum_telemetry_hub.mission_domain.canonical_teams import canonical_team_for_uid


ALLOWED_EAM_STATUSES = {"Green", "Yellow", "Red", "Unknown"}
STATUS_DIMENSION_FIELDS = (
    "security_status",
    "capability_status",
    "preparedness_status",
    "medical_status",
    "mobility_status",
    "comms_status",
)


def _utcnow() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc)


def _dt(value: datetime | None) -> str | None:
    """Return a JSON-friendly datetime string."""

    return value.isoformat() if value else None


def _dt_ms(value: datetime | None) -> int:
    """Return a Unix timestamp in milliseconds."""

    resolved = value or _utcnow()
    if resolved.tzinfo is None:
        resolved = resolved.replace(tzinfo=timezone.utc)
    else:
        resolved = resolved.astimezone(timezone.utc)
    return int(resolved.timestamp() * 1000)


def _as_datetime(value: Any) -> datetime | None:
    """Normalize an ISO-8601 datetime-like value."""

    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_status(value: object, *, field_name: str) -> str:
    """Normalize a single status field into the canonical enum casing."""

    if value is None:
        return "Unknown"
    text = str(value).strip()
    if not text:
        return "Unknown"
    normalized = text.lower()
    mapping = {
        "green": "Green",
        "yellow": "Yellow",
        "red": "Red",
        "unknown": "Unknown",
    }
    if normalized not in mapping:
        raise ValueError(
            f"{field_name} must be one of: {', '.join(sorted(ALLOWED_EAM_STATUSES))}"
        )
    return mapping[normalized]


def _aggregate_status(values: list[str]) -> str:
    """Aggregate a list of statuses using worst-of semantics."""

    normalized = [_normalize_status(value, field_name="status") for value in values]
    if "Red" in normalized:
        return "Red"
    if "Yellow" in normalized:
        return "Yellow"
    known = [value for value in normalized if value != "Unknown"]
    if known and all(value == "Green" for value in known):
        return "Green"
    return "Unknown"


class EmergencyActionMessageService:
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
                if row.deleted_at is None and not self._is_expired(row)
            ]

    def upsert_message(
        self, payload: dict[str, Any], *, expected_callsign: str | None = None
    ) -> dict[str, Any]:
        """Create or update the current REM-compatible EAM snapshot."""

        normalized = self._normalize_payload(payload, expected_callsign=expected_callsign)
        with self._session() as session:
            team_row = self._resolve_team_row(
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
                        f"team_member_uid '{normalized['team_member_uid']}' does not belong to team_uid '{normalized['team_uid']}'"
                    )

            row = (
                session.query(EmergencyActionMessageRecord)
                .filter(
                    EmergencyActionMessageRecord.subject_type == "member",
                    EmergencyActionMessageRecord.subject_id == normalized["team_member_uid"],
                )
                .one_or_none()
            )
            conflicting_callsign = (
                session.query(EmergencyActionMessageRecord)
                .filter(EmergencyActionMessageRecord.callsign == normalized["callsign"])
                .one_or_none()
            )
            if conflicting_callsign is not None and (
                row is None or conflicting_callsign.id != row.id
            ):
                raise ValueError(
                    f"callsign '{normalized['callsign']}' is already assigned to another status snapshot"
                )

            if row is None:
                row = EmergencyActionMessageRecord(
                    id=normalized["eam_uid"] or uuid.uuid4().hex
                )
                session.add(row)
            elif normalized["eam_uid"] and row.id != normalized["eam_uid"]:
                raise ValueError(
                    f"eam_uid '{normalized['eam_uid']}' does not match the existing snapshot for team_member_uid '{normalized['team_member_uid']}'"
                )

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
            row.source = self._serialize_source(normalized["source"])
            row.security_status = normalized["security_status"]
            row.capability_status = normalized["capability_status"]
            row.preparedness_status = normalized["preparedness_status"]
            row.medical_status = normalized["medical_status"]
            row.mobility_status = normalized["mobility_status"]
            row.comms_status = normalized["comms_status"]
            row.overall_status = self._compute_overall_status(normalized)

            try:
                session.flush()
            except IntegrityError as exc:
                raise ValueError(
                    "EmergencyActionMessage conflicts with an existing snapshot"
                ) from exc

            return self._serialize_message(session, row)

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
            if row is None or row.deleted_at is not None or self._is_expired(row):
                raise KeyError(
                    f"No active EmergencyActionMessage found for member/{normalized_team_member_uid}"
                )
            return self._serialize_message(session, row)

    def get_team_summary(self, team_uid: str) -> dict[str, Any]:
        """Compute a REM-compatible team summary from active snapshots."""

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
                if row.deleted_at is None and not self._is_expired(row)
            ]
            updated_at = max(
                (row.updated_at for row in rows),
                default=_utcnow(),
            )
            deleted_total = sum(1 for row in rows if row.deleted_at is not None)
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
                "deleted_total": deleted_total,
                "overall_status": overall_status,
                "green_total": green_total,
                "yellow_total": yellow_total,
                "red_total": red_total,
                "updated_at_ms": _dt_ms(updated_at),
            }

    def _normalize_payload(
        self, payload: Mapping[str, Any], *, expected_callsign: str | None = None
    ) -> dict[str, Any]:
        """Normalize and validate an incoming REM-compatible EAM payload."""

        normalized = dict(payload or {})

        callsign = str(normalized.get("callsign") or expected_callsign or "").strip()
        if not callsign:
            raise ValueError("callsign is required")
        if expected_callsign is not None and callsign != str(expected_callsign).strip():
            raise ValueError("callsign in body must match the path callsign")

        team_member_uid = str(normalized.get("team_member_uid") or "").strip()
        if not team_member_uid:
            raise ValueError("team_member_uid is required")
        team_uid = str(normalized.get("team_uid") or "").strip()
        if not team_uid:
            raise ValueError("team_uid is required")

        reported_at = self._normalize_reported_at(normalized.get("reported_at"))
        ttl_seconds = self._normalize_ttl(normalized.get("ttl_seconds"))
        confidence = self._normalize_confidence(normalized.get("confidence"))
        source = self._normalize_source(normalized.get("source"))

        return {
            "eam_uid": self._normalize_optional_text(normalized.get("eam_uid")),
            "callsign": callsign,
            "group_name": self._normalize_optional_text(normalized.get("group_name")),
            "team_member_uid": team_member_uid,
            "team_uid": team_uid,
            "reported_by": self._normalize_optional_text(normalized.get("reported_by")),
            "reported_at": reported_at,
            "notes": self._normalize_optional_text(normalized.get("notes")),
            "confidence": confidence,
            "ttl_seconds": ttl_seconds,
            "source": source,
            "security_status": _normalize_status(
                normalized.get("security_status"),
                field_name="security_status",
            ),
            "capability_status": _normalize_status(
                normalized.get("capability_status"),
                field_name="capability_status",
            ),
            "preparedness_status": _normalize_status(
                normalized.get("preparedness_status"),
                field_name="preparedness_status",
            ),
            "medical_status": _normalize_status(
                normalized.get("medical_status"),
                field_name="medical_status",
            ),
            "mobility_status": _normalize_status(
                normalized.get("mobility_status"),
                field_name="mobility_status",
            ),
            "comms_status": _normalize_status(
                normalized.get("comms_status"),
                field_name="comms_status",
            ),
        }

    @staticmethod
    def _normalize_optional_text(value: object) -> str | None:
        """Normalize optional text fields."""

        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _normalize_reported_at(value: object) -> datetime:
        """Normalize the ``reported_at`` field."""

        if value is None or str(value).strip() == "":
            return _utcnow()
        reported_at = _as_datetime(value)
        if reported_at is None:
            raise ValueError("reported_at must be ISO-8601")
        return reported_at

    @staticmethod
    def _normalize_ttl(value: object) -> int | None:
        """Normalize ``ttl_seconds``."""

        if value is None or value == "":
            return None
        try:
            ttl_seconds = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("ttl_seconds must be an integer") from exc
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must be greater than or equal to 0")
        return ttl_seconds

    @staticmethod
    def _normalize_confidence(value: object) -> float | None:
        """Normalize ``confidence``."""

        if value is None or value == "":
            return None
        try:
            confidence = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("confidence must be numeric") from exc
        if confidence < 0 or confidence > 1:
            raise ValueError("confidence must be between 0 and 1")
        return confidence

    @staticmethod
    def _normalize_source(value: object) -> dict[str, str | None] | None:
        """Normalize a REM EAM source payload."""

        if value is None:
            return None
        if not isinstance(value, Mapping):
            raise ValueError("source must be an object")
        rns_identity = str(value.get("rns_identity") or "").strip() or None
        display_name = str(value.get("display_name") or "").strip() or None
        if rns_identity is None and display_name is None:
            return None
        return {
            "rns_identity": rns_identity,
            "display_name": display_name,
        }

    def _compute_overall_status(self, payload: Mapping[str, Any]) -> str:
        """Compute overall status from the six dimensions."""

        return _aggregate_status(
            [str(payload[field_name]) for field_name in STATUS_DIMENSION_FIELDS]
        )

    @staticmethod
    def _is_expired(
        row: EmergencyActionMessageRecord, *, now: datetime | None = None
    ) -> bool:
        """Return True when the snapshot is outside its TTL window."""

        if row.ttl_seconds is None:
            return False
        current_time = now or _utcnow()
        reported_at = _as_datetime(row.reported_at)
        if reported_at is None:
            return False
        return current_time >= reported_at + timedelta(seconds=int(row.ttl_seconds))

    def _resolve_team_row(
        self,
        session: Session,
        team_uid: str,
        group_name: str | None,
    ) -> R3aktTeamRecord:
        """Return the referenced team, auto-provisioning canonical color teams."""

        canonical_team = canonical_team_for_uid(team_uid)
        if canonical_team is not None and group_name is not None:
            canonical_group = canonical_team_for_color(group_name)
            if canonical_group is None or canonical_group["uid"] != canonical_team["uid"]:
                raise ValueError(
                    f"group_name '{group_name}' does not match canonical team_uid '{team_uid}'"
                )

        team_row = session.get(R3aktTeamRecord, team_uid)
        if team_row is not None:
            if canonical_team is not None:
                team_row.color = canonical_team["color"]
                team_row.team_name = canonical_team["team_name"]
            return team_row
        if canonical_team is None:
            raise ValueError(f"team_uid '{team_uid}' does not map to a team")

        team_row = R3aktTeamRecord(
            uid=canonical_team["uid"],
            mission_uid=None,
            color=canonical_team["color"],
            team_name=canonical_team["team_name"],
            team_description="",
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        session.add(team_row)
        session.flush()
        return team_row

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

    @staticmethod
    def _serialize_source(source: Mapping[str, str | None] | None) -> str | None:
        """Serialize a REM source payload for storage."""

        if source is None:
            return None
        return json.dumps(
            {
                "rns_identity": source.get("rns_identity"),
                "display_name": source.get("display_name"),
            },
            sort_keys=True,
        )

    @staticmethod
    def _deserialize_source(source: str | None) -> dict[str, str | None] | None:
        """Deserialize a stored REM source payload."""

        if source is None:
            return None
        text = str(source).strip()
        if not text:
            return None
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return {"rns_identity": text, "display_name": None}
        if not isinstance(payload, dict):
            return None
        rns_identity = str(payload.get("rns_identity") or "").strip() or None
        display_name = str(payload.get("display_name") or "").strip() or None
        if rns_identity is None and display_name is None:
            return None
        return {
            "rns_identity": rns_identity,
            "display_name": display_name,
        }

    @staticmethod
    def _group_name_for_team(team_row: R3aktTeamRecord | None, team_uid: str) -> str | None:
        """Derive the REM group name for a team."""

        canonical_team = canonical_team_for_uid(team_uid)
        if canonical_team is not None:
            return canonical_team["group_name"]
        if team_row is None:
            return None
        color = str(team_row.color or "").strip()
        if color:
            return color
        name = str(team_row.team_name or "").strip()
        return name or None

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

    def _serialize_message(
        self, session: Session, row: EmergencyActionMessageRecord
    ) -> dict[str, Any]:
        """Serialize a snapshot into the REM-compatible API shape."""

        team_row = session.get(R3aktTeamRecord, str(row.team_id or ""))
        return {
            "eam_uid": row.id,
            "callsign": row.callsign,
            "group_name": self._group_name_for_team(team_row, str(row.team_id or "")),
            "team_member_uid": row.subject_id,
            "team_uid": row.team_id,
            "reported_by": row.reported_by,
            "reported_at": _dt(row.reported_at),
            "overall_status": row.overall_status,
            "security_status": row.security_status,
            "capability_status": row.capability_status,
            "preparedness_status": row.preparedness_status,
            "medical_status": row.medical_status,
            "mobility_status": row.mobility_status,
            "comms_status": row.comms_status,
            "notes": row.notes,
            "confidence": row.confidence,
            "ttl_seconds": row.ttl_seconds,
            "source": self._deserialize_source(row.source),
        }
