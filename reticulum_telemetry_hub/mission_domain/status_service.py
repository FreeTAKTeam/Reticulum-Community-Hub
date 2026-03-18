"""Persistence-backed Emergency Action Message status service."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from typing import Any
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


ALLOWED_EAM_STATUSES = {"Green", "Yellow", "Red", "Unknown"}
ALLOWED_SUBJECT_TYPES = {"member"}
STATUS_DIMENSION_FIELDS = (
    "securityStatus",
    "capabilityStatus",
    "preparednessStatus",
    "medicalStatus",
    "mobilityStatus",
    "commsStatus",
)


def _utcnow() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc)


def _dt(value: datetime | None) -> str | None:
    """Return a JSON-friendly datetime string."""

    return value.isoformat() if value else None


def _as_datetime(value: Any, *, default: datetime | None = None) -> datetime | None:
    """Normalize an ISO-8601 datetime-like value."""

    if value is None:
        return default
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value).strip()
    if not text:
        return default
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return default
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


def _normalize_subject_type(value: object) -> str:
    """Normalize the subject type for status records."""

    if value is None:
        return "member"
    text = str(value).strip().lower()
    if not text:
        return "member"
    if text not in ALLOWED_SUBJECT_TYPES:
        raise ValueError("subjectType must be 'member'")
    return text


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
    """Manage current member-scoped Emergency Action Message snapshots."""

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
        team_id: str | None = None,
        subject_type: str | None = None,
        overall_status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return status snapshots with optional filters."""

        with self._session() as session:
            query = session.query(EmergencyActionMessageRecord)
            if team_id:
                query = query.filter(EmergencyActionMessageRecord.team_id == str(team_id).strip())
            if subject_type:
                query = query.filter(
                    EmergencyActionMessageRecord.subject_type
                    == _normalize_subject_type(subject_type)
                )
            if overall_status:
                query = query.filter(
                    EmergencyActionMessageRecord.overall_status
                    == _normalize_status(overall_status, field_name="overallStatus")
                )
            rows = (
                query.order_by(
                    EmergencyActionMessageRecord.callsign.asc(),
                    EmergencyActionMessageRecord.subject_id.asc(),
                ).all()
            )
            return [
                self._serialize_message(row)
                for row in rows
                if not self._is_expired(row)
            ]

    def upsert_message(
        self, payload: dict[str, Any], *, expected_callsign: str | None = None
    ) -> dict[str, Any]:
        """Create or update the current status snapshot for a member."""

        normalized = self._normalize_payload(payload, expected_callsign=expected_callsign)
        with self._session() as session:
            subject_id = normalized["subjectId"]
            team_id = normalized["teamId"]
            member = session.get(R3aktTeamMemberRecord, subject_id)
            if member is None:
                raise ValueError(f"subjectId '{subject_id}' does not map to a team member")
            member_team_id = str(member.team_uid or "").strip()
            if not member_team_id:
                raise ValueError(f"team member '{subject_id}' is not assigned to a team")
            if member_team_id != team_id:
                raise ValueError(
                    f"teamId '{team_id}' does not match team member '{subject_id}'"
                )
            if session.get(R3aktTeamRecord, team_id) is None:
                raise ValueError(f"teamId '{team_id}' does not map to a team")

            row = (
                session.query(EmergencyActionMessageRecord)
                .filter(
                    EmergencyActionMessageRecord.subject_type == normalized["subjectType"],
                    EmergencyActionMessageRecord.subject_id == subject_id,
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
                row = EmergencyActionMessageRecord(id=uuid.uuid4().hex)
                session.add(row)

            row.callsign = normalized["callsign"]
            row.subject_type = normalized["subjectType"]
            row.subject_id = subject_id
            row.team_id = team_id
            row.reported_by = normalized["reportedBy"]
            row.reported_at = normalized["reportedAt"]
            row.ttl_seconds = normalized["ttlSeconds"]
            row.notes = normalized["notes"]
            row.confidence = normalized["confidence"]
            row.source = normalized["source"]
            row.security_status = normalized["securityStatus"]
            row.capability_status = normalized["capabilityStatus"]
            row.preparedness_status = normalized["preparednessStatus"]
            row.medical_status = normalized["medicalStatus"]
            row.mobility_status = normalized["mobilityStatus"]
            row.comms_status = normalized["commsStatus"]
            row.overall_status = self._compute_overall_status(normalized)

            try:
                session.flush()
            except IntegrityError as exc:
                raise ValueError("EmergencyActionMessage conflicts with an existing snapshot") from exc

            return self._serialize_message(row)

    def get_message_by_callsign(self, callsign: str) -> dict[str, Any]:
        """Return the current snapshot for a callsign."""

        with self._session() as session:
            row = self._get_message_row_by_callsign(session, callsign)
            return self._serialize_message(row)

    def delete_message(self, callsign: str) -> dict[str, Any]:
        """Delete the current snapshot for a callsign."""

        with self._session() as session:
            row = self._get_message_row_by_callsign(session, callsign)
            data = self._serialize_message(row)
            session.delete(row)
            return data

    def get_latest_message(self, subject_type: str, subject_id: str) -> dict[str, Any]:
        """Return the latest stored snapshot for a subject."""

        normalized_subject_type = _normalize_subject_type(subject_type)
        normalized_subject_id = str(subject_id or "").strip()
        if not normalized_subject_id:
            raise ValueError("subjectId is required")
        with self._session() as session:
            row = (
                session.query(EmergencyActionMessageRecord)
                .filter(
                    EmergencyActionMessageRecord.subject_type == normalized_subject_type,
                    EmergencyActionMessageRecord.subject_id == normalized_subject_id,
                )
                .one_or_none()
            )
            if row is None:
                raise KeyError(
                    f"No EmergencyActionMessage found for {normalized_subject_type}/{normalized_subject_id}"
                )
            if self._is_expired(row):
                raise KeyError(
                    f"No active EmergencyActionMessage found for {normalized_subject_type}/{normalized_subject_id}"
                )
            return self._serialize_message(row)

    def get_team_summary(self, team_id: str) -> dict[str, Any]:
        """Compute a team summary from the latest valid member snapshots."""

        normalized_team_id = str(team_id or "").strip()
        if not normalized_team_id:
            raise ValueError("teamId is required")
        with self._session() as session:
            team = session.get(R3aktTeamRecord, normalized_team_id)
            if team is None:
                raise KeyError(f"Team '{normalized_team_id}' not found")
            members = (
                session.query(R3aktTeamMemberRecord)
                .filter(R3aktTeamMemberRecord.team_uid == normalized_team_id)
                .order_by(R3aktTeamMemberRecord.created_at.asc())
                .all()
            )
            snapshots = (
                session.query(EmergencyActionMessageRecord)
                .filter(
                    EmergencyActionMessageRecord.subject_type == "member",
                    EmergencyActionMessageRecord.team_id == normalized_team_id,
                )
                .all()
            )
            snapshot_by_subject = {
                str(row.subject_id): row for row in snapshots
            }
            aggregated_dimensions: dict[str, str] = {}
            now = _utcnow()
            for field_name in STATUS_DIMENSION_FIELDS:
                values: list[str] = []
                for member in members:
                    row = snapshot_by_subject.get(str(member.uid))
                    if row is None or self._is_expired(row, now=now):
                        values.append("Unknown")
                        continue
                    values.append(self._message_dimension_value(row, field_name))
                aggregated_dimensions[field_name] = _aggregate_status(values)

            overall_status = _aggregate_status(list(aggregated_dimensions.values()))
            return {
                "teamId": normalized_team_id,
                "computedAt": _dt(now),
                "overallStatus": overall_status,
                "securityStatus": aggregated_dimensions["securityStatus"],
                "capabilityStatus": aggregated_dimensions["capabilityStatus"],
                "securityCapability": aggregated_dimensions["capabilityStatus"],
                "preparednessStatus": aggregated_dimensions["preparednessStatus"],
                "medicalStatus": aggregated_dimensions["medicalStatus"],
                "mobilityStatus": aggregated_dimensions["mobilityStatus"],
                "commsStatus": aggregated_dimensions["commsStatus"],
                "memberCount": len(members),
                "aggregationMethod": "worst-of",
            }

    def _normalize_payload(
        self, payload: dict[str, Any], *, expected_callsign: str | None = None
    ) -> dict[str, Any]:
        """Normalize and validate an incoming status payload."""

        normalized = dict(payload or {})
        raw_capability = normalized.get("capabilityStatus")
        raw_legacy_capability = normalized.get("securityCapability")
        if raw_capability is not None and raw_legacy_capability is not None:
            if _normalize_status(
                raw_capability, field_name="capabilityStatus"
            ) != _normalize_status(raw_legacy_capability, field_name="securityCapability"):
                raise ValueError(
                    "capabilityStatus and securityCapability must match when both are provided"
                )
        if raw_capability is None and raw_legacy_capability is not None:
            normalized["capabilityStatus"] = raw_legacy_capability

        callsign = str(normalized.get("callsign") or expected_callsign or "").strip()
        if not callsign:
            raise ValueError("callsign is required")
        if expected_callsign is not None and callsign != str(expected_callsign).strip():
            raise ValueError("callsign in body must match the path callsign")

        subject_id = str(normalized.get("subjectId") or "").strip()
        if not subject_id:
            raise ValueError("subjectId is required")
        team_id = str(normalized.get("teamId") or "").strip()
        if not team_id:
            raise ValueError("teamId is required")

        reported_at = _as_datetime(normalized.get("reportedAt"), default=_utcnow())
        if reported_at is None:
            raise ValueError("reportedAt must be ISO-8601")

        ttl_seconds = normalized.get("ttlSeconds")
        if ttl_seconds is None or ttl_seconds == "":
            normalized_ttl = None
        else:
            try:
                normalized_ttl = int(ttl_seconds)
            except (TypeError, ValueError) as exc:
                raise ValueError("ttlSeconds must be an integer") from exc
            if normalized_ttl < 0:
                raise ValueError("ttlSeconds must be greater than or equal to 0")

        confidence = normalized.get("confidence")
        if confidence is None or confidence == "":
            normalized_confidence = None
        else:
            try:
                normalized_confidence = float(confidence)
            except (TypeError, ValueError) as exc:
                raise ValueError("confidence must be numeric") from exc
            if normalized_confidence < 0 or normalized_confidence > 1:
                raise ValueError("confidence must be between 0 and 1")

        normalized_payload = {
            "callsign": callsign,
            "subjectType": _normalize_subject_type(normalized.get("subjectType")),
            "subjectId": subject_id,
            "teamId": team_id,
            "reportedBy": self._normalize_optional_text(normalized.get("reportedBy")),
            "reportedAt": reported_at,
            "ttlSeconds": normalized_ttl,
            "notes": self._normalize_optional_text(normalized.get("notes")),
            "confidence": normalized_confidence,
            "source": self._normalize_optional_text(normalized.get("source")),
            "securityStatus": _normalize_status(
                normalized.get("securityStatus"), field_name="securityStatus"
            ),
            "capabilityStatus": _normalize_status(
                normalized.get("capabilityStatus"), field_name="capabilityStatus"
            ),
            "preparednessStatus": _normalize_status(
                normalized.get("preparednessStatus"), field_name="preparednessStatus"
            ),
            "medicalStatus": _normalize_status(
                normalized.get("medicalStatus"), field_name="medicalStatus"
            ),
            "mobilityStatus": _normalize_status(
                normalized.get("mobilityStatus"), field_name="mobilityStatus"
            ),
            "commsStatus": _normalize_status(
                normalized.get("commsStatus"), field_name="commsStatus"
            ),
        }
        return normalized_payload

    @staticmethod
    def _normalize_optional_text(value: object) -> str | None:
        """Normalize optional text fields."""

        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _compute_overall_status(self, payload: dict[str, Any]) -> str:
        """Compute overall status from the six dimensions."""

        return _aggregate_status(
            [str(payload[field_name]) for field_name in STATUS_DIMENSION_FIELDS]
        )

    @staticmethod
    def _message_dimension_value(
        row: EmergencyActionMessageRecord, field_name: str
    ) -> str:
        """Return a dimension value from a stored snapshot."""

        if field_name == "securityStatus":
            return str(row.security_status)
        if field_name == "capabilityStatus":
            return str(row.capability_status)
        if field_name == "preparednessStatus":
            return str(row.preparedness_status)
        if field_name == "medicalStatus":
            return str(row.medical_status)
        if field_name == "mobilityStatus":
            return str(row.mobility_status)
        if field_name == "commsStatus":
            return str(row.comms_status)
        raise KeyError(f"Unknown dimension '{field_name}'")

    @staticmethod
    def _is_expired(
        row: EmergencyActionMessageRecord, *, now: datetime | None = None
    ) -> bool:
        """Return True when the snapshot is outside its TTL window."""

        if row.ttl_seconds is None:
            return False
        current_time = now or _utcnow()
        reported_at = _as_datetime(row.reported_at, default=_utcnow())
        if reported_at is None:
            return False
        return current_time >= reported_at + timedelta(seconds=int(row.ttl_seconds))

    def _get_message_row_by_callsign(
        self, session: Session, callsign: str
    ) -> EmergencyActionMessageRecord:
        """Return a stored snapshot for a callsign or raise KeyError."""

        normalized_callsign = str(callsign or "").strip()
        if not normalized_callsign:
            raise ValueError("callsign is required")
        row = (
            session.query(EmergencyActionMessageRecord)
            .filter(EmergencyActionMessageRecord.callsign == normalized_callsign)
            .one_or_none()
        )
        if row is None:
            raise KeyError(f"EmergencyActionMessage '{normalized_callsign}' not found")
        return row

    def _serialize_message(self, row: EmergencyActionMessageRecord) -> dict[str, Any]:
        """Serialize a snapshot into the compatibility API shape."""

        return {
            "id": row.id,
            "callsign": row.callsign,
            "subjectType": row.subject_type,
            "subjectId": row.subject_id,
            "teamId": row.team_id,
            "reportedBy": row.reported_by,
            "reportedAt": _dt(row.reported_at),
            "overallStatus": row.overall_status,
            "securityStatus": row.security_status,
            "capabilityStatus": row.capability_status,
            "securityCapability": row.capability_status,
            "preparednessStatus": row.preparedness_status,
            "medicalStatus": row.medical_status,
            "mobilityStatus": row.mobility_status,
            "commsStatus": row.comms_status,
            "notes": row.notes,
            "confidence": row.confidence,
            "ttlSeconds": row.ttl_seconds,
            "source": row.source,
        }
