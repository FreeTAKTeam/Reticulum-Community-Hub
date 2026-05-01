"""Shared TAK connector models and timestamp helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timezone


@dataclass
class LocationSnapshot:  # pylint: disable=too-many-instance-attributes
    """Represents the latest known position of the hub."""

    latitude: float
    longitude: float
    altitude: float
    speed: float
    bearing: float
    accuracy: float
    updated_at: datetime
    peer_hash: str | None = None


def utc_iso(dt: datetime) -> str:
    """Format a ``datetime`` in UTC without microseconds."""

    normalized = normalize_utc(dt).replace(microsecond=0)
    return normalized.isoformat() + "Z"


def utc_iso_millis(dt: datetime) -> str:
    """Format a ``datetime`` in UTC with millisecond precision."""

    normalized = normalize_utc(dt)
    normalized = normalized.replace(microsecond=int(normalized.microsecond / 1000) * 1000)
    return normalized.isoformat(timespec="milliseconds") + "Z"


def normalize_utc(dt: datetime) -> datetime:
    """Return a naive UTC datetime suitable for CoT serialization."""

    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def utcnow() -> datetime:
    """Return the current UTC time as a naive datetime."""

    return datetime.now(timezone.utc).replace(tzinfo=None)
