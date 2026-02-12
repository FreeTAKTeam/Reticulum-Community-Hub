"""Zone storage helpers for the Reticulum Telemetry Hub API."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import List
from typing import Optional
import uuid

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from .models import Zone
from .models import ZonePoint
from .storage_base import HubStorageBase
from .storage_models import Base
from .storage_models import ZoneRecord
from .storage_models import _utcnow


class ZoneStorage(HubStorageBase):
    """SQLAlchemy-backed persistence for operator zones."""

    _POOL_SIZE = 10
    _POOL_OVERFLOW = 25
    _CONNECT_TIMEOUT_SECONDS = 30
    _session_retries = 3
    _session_backoff = 0.1

    def __init__(self, db_path: Path):
        """Create a zone storage instance backed by SQLite.

        Args:
            db_path (Path): Path to the SQLite database file.
        """

        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._engine = self._create_engine(db_path)
        self._enable_wal_mode()
        Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(  # pylint: disable=invalid-name
            bind=self._engine, expire_on_commit=False
        )

    def create_zone(self, zone: Zone) -> Zone:
        """Insert or update a zone record."""

        zone_id = zone.zone_id or uuid.uuid4().hex
        with self._session_scope() as session:
            record = ZoneRecord(
                id=zone_id,
                name=zone.name,
                points_json=self._points_to_json(zone.points),
                created_at=zone.created_at,
                updated_at=zone.updated_at,
            )
            session.merge(record)
            session.commit()
            return self._zone_from_record(record)

    def list_zones(self) -> List[Zone]:
        """Return all stored zones."""

        with self._session_scope() as session:
            records = (
                session.query(ZoneRecord)
                .order_by(ZoneRecord.created_at, ZoneRecord.id)
                .all()
            )
            return [self._zone_from_record(record) for record in records]

    def get_zone(self, zone_id: str) -> Optional[Zone]:
        """Return a zone by identifier."""

        with self._session_scope() as session:
            record = session.get(ZoneRecord, zone_id)
            return self._zone_from_record(record) if record else None

    def update_zone(
        self,
        zone_id: str,
        *,
        name: str | None = None,
        points: list[ZonePoint] | None = None,
        updated_at: datetime | None = None,
    ) -> Optional[Zone]:
        """Update zone fields and return the updated record."""

        with self._session_scope() as session:
            record = session.get(ZoneRecord, zone_id)
            if not record:
                return None
            if name is not None:
                record.name = name
            if points is not None:
                record.points_json = self._points_to_json(points)
            record.updated_at = updated_at or _utcnow()
            session.commit()
            return self._zone_from_record(record)

    def delete_zone(self, zone_id: str) -> Optional[Zone]:
        """Delete a zone record."""

        with self._session_scope() as session:
            record = session.get(ZoneRecord, zone_id)
            if not record:
                return None
            zone = self._zone_from_record(record)
            session.delete(record)
            session.commit()
            return zone

    def _create_engine(self, db_path: Path) -> Engine:
        """Build a SQLite engine configured for concurrency."""

        return create_engine(
            f"sqlite:///{db_path}",
            connect_args={
                "check_same_thread": False,
                "timeout": self._CONNECT_TIMEOUT_SECONDS,
            },
            poolclass=QueuePool,
            pool_size=self._POOL_SIZE,
            max_overflow=self._POOL_OVERFLOW,
            pool_pre_ping=True,
        )

    def _enable_wal_mode(self) -> None:
        """Enable write-ahead logging on the SQLite connection."""

        try:
            with self._engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as conn:
                conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
        except OperationalError as exc:
            logging.warning("Failed to enable WAL mode for zones: %s", exc)

    @staticmethod
    def _points_to_json(points: list[ZonePoint]) -> list[dict[str, float]]:
        """Serialize zone points into JSON-compatible mappings."""

        return [{"lat": float(point.lat), "lon": float(point.lon)} for point in points]

    @staticmethod
    def _points_from_json(payload: object) -> list[ZonePoint]:
        """Deserialize zone points from JSON payload."""

        if not isinstance(payload, list):
            return []
        points: list[ZonePoint] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            lat = item.get("lat")
            lon = item.get("lon")
            if lat is None or lon is None:
                continue
            points.append(ZonePoint(lat=float(lat), lon=float(lon)))
        return points

    @classmethod
    def _zone_from_record(cls, record: ZoneRecord) -> Zone:
        """Convert a ZoneRecord into a domain model."""

        return Zone(
            zone_id=record.id,
            name=record.name,
            points=cls._points_from_json(record.points_json),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
