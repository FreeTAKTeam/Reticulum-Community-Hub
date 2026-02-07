"""Marker storage helpers for the Reticulum Telemetry Hub API."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import List
from typing import Optional
import uuid

from sqlalchemy import create_engine
from sqlalchemy import or_
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

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
        self._ensure_marker_schema()
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

        marker_id = marker.local_id or uuid.uuid4().hex
        with self._session_scope() as session:
            record = MarkerRecord(
                id=marker_id,
                object_destination_hash=marker.object_destination_hash,
                origin_rch=marker.origin_rch,
                object_identity_storage_key=marker.object_identity_storage_key,
                marker_type=marker.marker_type,
                symbol=marker.symbol,
                name=marker.name,
                category=marker.category,
                notes=marker.notes,
                lat=marker.lat,
                lon=marker.lon,
                time=marker.time,
                stale_at=marker.stale_at,
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

    def list_uninitialized_markers(self) -> List[Marker]:
        """Return markers missing identity metadata."""

        with self._session_scope() as session:
            records = (
                session.query(MarkerRecord)
                .filter(
                    or_(
                        MarkerRecord.object_destination_hash.is_(None),
                        MarkerRecord.object_destination_hash == "",
                    )
                )
                .all()
            )
            return [self._marker_from_record(record) for record in records]

    def get_marker(self, object_destination_hash: str) -> Optional[Marker]:
        """Return a marker by its destination hash.

        Args:
            object_destination_hash (str): Marker destination hash.

        Returns:
            Optional[Marker]: Matching marker or None.
        """

        with self._session_scope() as session:
            record = (
                session.query(MarkerRecord)
                .filter(MarkerRecord.object_destination_hash == object_destination_hash)
                .one_or_none()
            )
            return self._marker_from_record(record) if record else None

    def get_marker_by_local_id(self, local_id: str) -> Optional[Marker]:
        """Return a marker by its local identifier.

        Args:
            local_id (str): Marker local identifier.

        Returns:
            Optional[Marker]: Matching marker or None.
        """

        with self._session_scope() as session:
            record = session.get(MarkerRecord, local_id)
            return self._marker_from_record(record) if record else None

    def update_marker_position(
        self,
        object_destination_hash: str,
        *,
        lat: float,
        lon: float,
        updated_at: Optional[datetime] = None,
        time: Optional[datetime] = None,
        stale_at: Optional[datetime] = None,
    ) -> Optional[Marker]:
        """Update marker coordinates and return the updated record.

        Args:
            object_destination_hash (str): Marker destination hash to update.
            lat (float): Updated latitude.
            lon (float): Updated longitude.
            updated_at (Optional[object]): Optional timestamp override.
            time (Optional[datetime]): Optional marker observation time.
            stale_at (Optional[datetime]): Optional marker expiration timestamp.

        Returns:
            Optional[Marker]: Updated marker or None if missing.
        """

        with self._session_scope() as session:
            record = (
                session.query(MarkerRecord)
                .filter(MarkerRecord.object_destination_hash == object_destination_hash)
                .one_or_none()
            )
            if not record:
                return None
            record.lat = float(lat)
            record.lon = float(lon)
            if time is not None:
                record.time = time
            if stale_at is not None:
                record.stale_at = stale_at
            if updated_at is not None:
                record.updated_at = updated_at
            else:
                record.updated_at = _utcnow()
            session.commit()
            return self._marker_from_record(record)

    def update_marker_name(
        self,
        object_destination_hash: str,
        *,
        name: str,
        updated_at: Optional[datetime] = None,
        time: Optional[datetime] = None,
        stale_at: Optional[datetime] = None,
    ) -> Optional[Marker]:
        """Update marker name and return the updated record."""

        with self._session_scope() as session:
            record = (
                session.query(MarkerRecord)
                .filter(MarkerRecord.object_destination_hash == object_destination_hash)
                .one_or_none()
            )
            if not record:
                return None
            record.name = name
            if time is not None:
                record.time = time
            if stale_at is not None:
                record.stale_at = stale_at
            if updated_at is not None:
                record.updated_at = updated_at
            else:
                record.updated_at = _utcnow()
            session.commit()
            return self._marker_from_record(record)

    def update_marker_identity(
        self,
        local_id: str,
        *,
        object_destination_hash: str,
        origin_rch: str,
        object_identity_storage_key: str,
        marker_type: str,
        symbol: str,
        time: datetime,
        stale_at: datetime,
    ) -> Optional[Marker]:
        """Update marker identity metadata for a local marker.

        Args:
            local_id (str): Marker local identifier.
            object_destination_hash (str): Destination hash for the marker.
            origin_rch (str): Originating hub identity hash.
            object_identity_storage_key (str): Encrypted identity storage key.
            marker_type (str): Marker type identifier.
            symbol (str): Marker symbol identifier.
            time (datetime): Marker observation time.
            stale_at (datetime): Marker expiration timestamp.

        Returns:
            Optional[Marker]: Updated marker or None if missing.
        """

        with self._session_scope() as session:
            record = session.get(MarkerRecord, local_id)
            if not record:
                return None
            record.object_destination_hash = object_destination_hash
            record.origin_rch = origin_rch
            record.object_identity_storage_key = object_identity_storage_key
            record.marker_type = marker_type
            record.symbol = symbol
            record.time = time
            record.stale_at = stale_at
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

    def _ensure_marker_schema(self) -> None:
        """Ensure marker schema columns exist for legacy databases."""

        try:
            with self._engine.connect() as conn:
                result = conn.exec_driver_sql("PRAGMA table_info(markers);")
                existing = {row[1] for row in result.fetchall()}
                if not existing:
                    return
                statements = []
                if "object_destination_hash" not in existing:
                    statements.append(
                        "ALTER TABLE markers ADD COLUMN object_destination_hash TEXT"
                    )
                if "origin_rch" not in existing:
                    statements.append(
                        "ALTER TABLE markers ADD COLUMN origin_rch TEXT"
                    )
                if "object_identity_storage_key" not in existing:
                    statements.append(
                        "ALTER TABLE markers ADD COLUMN object_identity_storage_key TEXT"
                    )
                if "symbol" not in existing:
                    statements.append("ALTER TABLE markers ADD COLUMN symbol TEXT")
                if "time" not in existing:
                    statements.append("ALTER TABLE markers ADD COLUMN time DATETIME")
                if "stale_at" not in existing:
                    statements.append(
                        "ALTER TABLE markers ADD COLUMN stale_at DATETIME"
                    )
                for statement in statements:
                    conn.exec_driver_sql(statement)
        except OperationalError as exc:
            logging.warning("Failed to update marker schema: %s", exc)

    @staticmethod
    def _marker_from_record(record: MarkerRecord) -> Marker:
        """Convert a MarkerRecord into a domain model.

        Args:
            record (MarkerRecord): Marker record instance.

        Returns:
            Marker: Domain marker instance.
        """

        return Marker(
            local_id=record.id,
            object_destination_hash=record.object_destination_hash,
            origin_rch=record.origin_rch,
            object_identity_storage_key=record.object_identity_storage_key,
            marker_type=record.marker_type,
            symbol=record.symbol or "",
            name=record.name,
            category=record.category,
            notes=record.notes,
            lat=record.lat,
            lon=record.lon,
            time=record.time,
            stale_at=record.stale_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
