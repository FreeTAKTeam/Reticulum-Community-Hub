"""Zone business logic for the Reticulum Telemetry Hub API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from math import isclose
from typing import Optional
import uuid

from .models import Zone
from .models import ZonePoint
from .zone_storage import ZoneStorage


MIN_ZONE_POINTS = 3
MAX_ZONE_POINTS = 200
MAX_ZONE_NAME_LENGTH = 96
_COORD_EPSILON = 1e-9


def _utcnow() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc)


def _points_equal(left: ZonePoint, right: ZonePoint) -> bool:
    """Return True when two points are effectively identical."""

    return isclose(left.lat, right.lat, abs_tol=_COORD_EPSILON) and isclose(
        left.lon, right.lon, abs_tol=_COORD_EPSILON
    )


def _normalize_name(name: str) -> str:
    """Validate and normalize a zone name."""

    resolved = (name or "").strip()
    if not resolved:
        raise ValueError("Zone name is required")
    if len(resolved) > MAX_ZONE_NAME_LENGTH:
        raise ValueError(f"Zone name cannot exceed {MAX_ZONE_NAME_LENGTH} characters")
    return resolved


def _normalize_points(points: list[ZonePoint]) -> list[ZonePoint]:
    """Validate and normalize polygon points."""

    if not points:
        raise ValueError("Zone points are required")
    normalized = [ZonePoint(lat=float(point.lat), lon=float(point.lon)) for point in points]
    if len(normalized) >= 2 and _points_equal(normalized[0], normalized[-1]):
        normalized = normalized[:-1]
    if len(normalized) < MIN_ZONE_POINTS:
        raise ValueError(f"Zone must contain at least {MIN_ZONE_POINTS} points")
    if len(normalized) > MAX_ZONE_POINTS:
        raise ValueError(f"Zone cannot contain more than {MAX_ZONE_POINTS} points")
    for point in normalized:
        if point.lat < -90 or point.lat > 90:
            raise ValueError("Zone point latitude must be between -90 and 90")
        if point.lon < -180 or point.lon > 180:
            raise ValueError("Zone point longitude must be between -180 and 180")
    if _is_self_intersecting(normalized):
        raise ValueError("Zone polygon cannot self-intersect")
    return normalized


def _orientation(a: ZonePoint, b: ZonePoint, c: ZonePoint) -> float:
    """Return orientation cross-product of the triplet."""

    return (b.lon - a.lon) * (c.lat - a.lat) - (b.lat - a.lat) * (c.lon - a.lon)


def _on_segment(a: ZonePoint, b: ZonePoint, c: ZonePoint) -> bool:
    """Return True when point b lies on segment a-c."""

    return (
        min(a.lon, c.lon) - _COORD_EPSILON <= b.lon <= max(a.lon, c.lon) + _COORD_EPSILON
        and min(a.lat, c.lat) - _COORD_EPSILON <= b.lat <= max(a.lat, c.lat) + _COORD_EPSILON
    )


def _segments_intersect(a1: ZonePoint, a2: ZonePoint, b1: ZonePoint, b2: ZonePoint) -> bool:
    """Return True when two segments intersect."""

    o1 = _orientation(a1, a2, b1)
    o2 = _orientation(a1, a2, b2)
    o3 = _orientation(b1, b2, a1)
    o4 = _orientation(b1, b2, a2)

    if ((o1 > _COORD_EPSILON and o2 < -_COORD_EPSILON) or (o1 < -_COORD_EPSILON and o2 > _COORD_EPSILON)) and (
        (o3 > _COORD_EPSILON and o4 < -_COORD_EPSILON) or (o3 < -_COORD_EPSILON and o4 > _COORD_EPSILON)
    ):
        return True

    if abs(o1) <= _COORD_EPSILON and _on_segment(a1, b1, a2):
        return True
    if abs(o2) <= _COORD_EPSILON and _on_segment(a1, b2, a2):
        return True
    if abs(o3) <= _COORD_EPSILON and _on_segment(b1, a1, b2):
        return True
    if abs(o4) <= _COORD_EPSILON and _on_segment(b1, a2, b2):
        return True
    return False


def _is_self_intersecting(points: list[ZonePoint]) -> bool:
    """Return True when polygon edges intersect non-adjacent edges."""

    edge_count = len(points)
    for i in range(edge_count):
        a1 = points[i]
        a2 = points[(i + 1) % edge_count]
        for j in range(i + 1, edge_count):
            if i == j:
                continue
            if (i + 1) % edge_count == j or i == (j + 1) % edge_count:
                continue
            b1 = points[j]
            b2 = points[(j + 1) % edge_count]
            if _segments_intersect(a1, a2, b1, b2):
                return True
    return False


@dataclass(frozen=True)
class ZoneUpdateResult:
    """Result of a zone update operation."""

    zone: Zone


class ZoneService:
    """Service layer for managing operator zones."""

    def __init__(self, storage: ZoneStorage) -> None:
        """Create a zone service.

        Args:
            storage (ZoneStorage): Storage provider for zone data.
        """

        self._storage = storage

    def list_zones(self) -> list[Zone]:
        """Return all persisted zones."""

        return self._storage.list_zones()

    def create_zone(self, *, name: str, points: list[ZonePoint]) -> Zone:
        """Create and persist a new zone."""

        resolved_name = _normalize_name(name)
        resolved_points = _normalize_points(points)
        timestamp = _utcnow()
        zone = Zone(
            zone_id=uuid.uuid4().hex,
            name=resolved_name,
            points=resolved_points,
            created_at=timestamp,
            updated_at=timestamp,
        )
        return self._storage.create_zone(zone)

    def update_zone(
        self,
        zone_id: str,
        *,
        name: Optional[str] = None,
        points: Optional[list[ZonePoint]] = None,
    ) -> ZoneUpdateResult:
        """Update zone metadata and geometry."""

        if name is None and points is None:
            raise ValueError("At least one zone field must be provided")
        existing = self._storage.get_zone(zone_id)
        if existing is None:
            raise KeyError(f"Zone '{zone_id}' not found")
        resolved_name = _normalize_name(name) if name is not None else None
        resolved_points = _normalize_points(points) if points is not None else None
        updated = self._storage.update_zone(
            zone_id,
            name=resolved_name,
            points=resolved_points,
            updated_at=_utcnow(),
        )
        if updated is None:
            raise KeyError(f"Zone '{zone_id}' not found")
        return ZoneUpdateResult(zone=updated)

    def delete_zone(self, zone_id: str) -> Zone:
        """Delete a zone."""

        removed = self._storage.delete_zone(zone_id)
        if removed is None:
            raise KeyError(f"Zone '{zone_id}' not found")
        return removed
