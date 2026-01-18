"""Marker storage helpers for the Reticulum Telemetry Hub API."""

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

from .marker_symbols import resolve_marker_symbol_set
from .models import Marker
from .storage_base import HubStorageBase
from .storage_models import Base
from .storage_models import MarkerRecord
from .storage_models import _utcnow


class MarkerStorage(HubStorageBase):
    """SQLAlchemy-backed persistence for operator markers."""

    _POOL_SIZE = 10
    _POOL_OVERFLOW = 25
    _CONNECT_TIMEOUT_SECONDS = 30
    _session_retries = 3
    _session_backoff = 0.1

    def __init__(self, db_path: Path):
        """Create a marker storage instance backed by SQLite.

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

    def create_marker(self, marker: Marker) -> Marker:
        """Insert or update a marker record.

        Args:
            marker (Marker): Marker data to persist.

        Returns:
            Marker: Stored marker instance.
        """

        marker_id = marker.marker_id or uuid.uuid4().hex
        marker_type = marker.marker_type or resolve_marker_symbol_set(marker.category)
        with self._session_scope() as session:
            record = MarkerRecord(
                id=marker_id,
                marker_type=marker_type,
                name=marker.name,
                category=marker.category,
                notes=marker.notes,
                lat=marker.lat,
                lon=marker.lon,
                created_at=marker.created_at,
                updated_at=marker.updated_at,
            )
            session.merge(record)
            session.commit()
            return self._marker_from_record(record)

    def list_markers(self) -> List[Marker]:
        """Return all stored markers."""

        with self._session_scope() as session:
            records = (
                session.query(MarkerRecord)
                .order_by(MarkerRecord.created_at, MarkerRecord.id)
                .all()
            )
            return [self._marker_from_record(record) for record in records]

    def get_marker(self, marker_id: str) -> Optional[Marker]:
        """Return a marker by its identifier.

        Args:
            marker_id (str): Marker identifier.

        Returns:
            Optional[Marker]: Matching marker or None.
        """

        with self._session_scope() as session:
            record = session.get(MarkerRecord, marker_id)
            return self._marker_from_record(record) if record else None

    def update_marker_position(
        self,
        marker_id: str,
        *,
        lat: float,
        lon: float,
        updated_at: Optional[datetime] = None,
    ) -> Optional[Marker]:
        """Update marker coordinates and return the updated record.

        Args:
            marker_id (str): Marker identifier to update.
            lat (float): Updated latitude.
            lon (float): Updated longitude.
            updated_at (Optional[object]): Optional timestamp override.

        Returns:
            Optional[Marker]: Updated marker or None if missing.
        """

        with self._session_scope() as session:
            record = session.get(MarkerRecord, marker_id)
            if not record:
                return None
            record.lat = float(lat)
            record.lon = float(lon)
            if updated_at is not None:
                record.updated_at = updated_at
            else:
                record.updated_at = _utcnow()
            session.commit()
            return self._marker_from_record(record)

    def _create_engine(self, db_path: Path) -> Engine:
        """Build a SQLite engine configured for concurrency.

        Args:
            db_path (Path): Database path for the engine.

        Returns:
            Engine: Configured SQLAlchemy engine.
        """

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
            logging.warning("Failed to enable WAL mode for markers: %s", exc)

    @staticmethod
    def _marker_from_record(record: MarkerRecord) -> Marker:
        """Convert a MarkerRecord into a domain model.

        Args:
            record (MarkerRecord): Marker record instance.

        Returns:
            Marker: Domain marker instance.
        """

        return Marker(
            marker_id=record.id,
            marker_type=record.marker_type,
            name=record.name,
            category=record.category,
            notes=record.notes,
            lat=record.lat,
            lon=record.lon,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
