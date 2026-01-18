"""Marker business logic for the Reticulum Telemetry Hub API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
import hashlib
from typing import Optional
import uuid

from .marker_storage import MarkerStorage
from .marker_symbols import resolve_marker_symbol_set
from .models import Marker


def _utcnow() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc)


def _default_marker_name(category: str, marker_id: str) -> str:
    """Return a default marker name for a category and identifier.

    Args:
        category (str): Marker symbol identifier.
        marker_id (str): Marker identifier.

    Returns:
        str: Default marker name.
    """

    trimmed = (category or "marker").strip() or "marker"
    suffix = hashlib.sha1(marker_id.encode("utf-8")).hexdigest()[:6]
    return f"{trimmed}+{suffix}"


@dataclass(frozen=True)
class MarkerUpdateResult:
    """Result of a marker update operation."""

    marker: Marker
    changed: bool


class MarkerService:
    """Service layer for managing operator markers."""

    def __init__(self, storage: MarkerStorage) -> None:
        """Create a marker service.

        Args:
            storage (MarkerStorage): Storage provider for marker data.
        """

        self._storage = storage

    def list_markers(self) -> list[Marker]:
        """Return all persisted markers."""

        return self._storage.list_markers()

    def create_marker(
        self,
        *,
        name: Optional[str],
        category: str,
        lat: float,
        lon: float,
        notes: Optional[str] = None,
    ) -> Marker:
        """Create and persist a new marker.

        Args:
            name (Optional[str]): Optional marker name.
            category (str): Marker symbol identifier.
            lat (float): Latitude.
            lon (float): Longitude.
            notes (Optional[str]): Optional notes.

        Returns:
            Marker: Persisted marker record.
        """

        marker_id = uuid.uuid4().hex
        normalized_category = (category or "").strip().lower()
        marker_type = resolve_marker_symbol_set(normalized_category)
        resolved_name = name.strip() if isinstance(name, str) else ""
        if not resolved_name:
            resolved_name = _default_marker_name(normalized_category, marker_id)
        timestamp = _utcnow()
        marker = Marker(
            marker_id=marker_id,
            marker_type=marker_type,
            name=resolved_name,
            category=normalized_category,
            notes=notes,
            lat=float(lat),
            lon=float(lon),
            created_at=timestamp,
            updated_at=timestamp,
        )
        return self._storage.create_marker(marker)

    def update_marker_position(
        self,
        marker_id: str,
        *,
        lat: float,
        lon: float,
    ) -> MarkerUpdateResult:
        """Update marker coordinates when they have changed.

        Args:
            marker_id (str): Marker identifier to update.
            lat (float): Updated latitude.
            lon (float): Updated longitude.

        Returns:
            MarkerUpdateResult: Updated marker plus change indicator.

        Raises:
            KeyError: When the marker does not exist.
        """

        marker = self._storage.get_marker(marker_id)
        if marker is None:
            raise KeyError(f"Marker '{marker_id}' not found")
        if marker.lat == float(lat) and marker.lon == float(lon):
            return MarkerUpdateResult(marker=marker, changed=False)
        updated = self._storage.update_marker_position(
            marker_id, lat=float(lat), lon=float(lon), updated_at=_utcnow()
        )
        if updated is None:
            raise KeyError(f"Marker '{marker_id}' not found")
        return MarkerUpdateResult(marker=updated, changed=True)
