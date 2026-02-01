"""Marker business logic for the Reticulum Telemetry Hub API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from datetime import timezone
import hashlib
from typing import Callable
from typing import Optional
import uuid

import RNS

from .marker_identity import encrypt_marker_identity
from .marker_identity import marker_destination_hash
from .marker_storage import MarkerStorage
from .marker_symbols import is_supported_marker_symbol
from .marker_symbols import normalize_marker_symbol
from .models import Marker


DEFAULT_MARKER_TTL_SECONDS = 24 * 60 * 60
DEFAULT_POSITION_EPSILON = 1e-6


def _utcnow() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc)


def _normalize_timestamp(value: datetime) -> datetime:
    """Return an aware UTC timestamp for comparisons.

    Args:
        value (datetime): Timestamp to normalize.

    Returns:
        datetime: Aware UTC timestamp.
    """

    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _default_marker_name(marker_type: str, local_id: str) -> str:
    """Return a default marker name for a type and identifier.

    Args:
        marker_type (str): Marker type identifier.
        local_id (str): Marker local identifier.

    Returns:
        str: Default marker name.
    """

    trimmed = (marker_type or "marker").strip() or "marker"
    suffix = hashlib.sha1(local_id.encode("utf-8")).hexdigest()[:6]
    return f"{trimmed}+{suffix}"


def _compute_stale_at(timestamp: datetime, ttl_seconds: Optional[int]) -> datetime:
    """Compute the stale timestamp for a marker event.

    Args:
        timestamp (datetime): Event timestamp.
        ttl_seconds (Optional[int]): Optional TTL override in seconds.

    Returns:
        datetime: Stale timestamp.
    """

    ttl_value = ttl_seconds if ttl_seconds is not None else DEFAULT_MARKER_TTL_SECONDS
    return timestamp + timedelta(seconds=ttl_value)


def _position_changed(marker: Marker, lat: float, lon: float) -> bool:
    """Return True when a marker position changes beyond the epsilon.

    Args:
        marker (Marker): Existing marker state.
        lat (float): Updated latitude.
        lon (float): Updated longitude.

    Returns:
        bool: True when the position changed.
    """

    return (
        abs(marker.lat - float(lat)) > DEFAULT_POSITION_EPSILON
        or abs(marker.lon - float(lon)) > DEFAULT_POSITION_EPSILON
    )


def _resolve_marker_ttl_seconds(marker: Marker) -> int:
    """Return the TTL seconds derived from marker timestamps.

    Args:
        marker (Marker): Marker to inspect.

    Returns:
        int: TTL in seconds.
    """

    if marker.time and marker.stale_at:
        time_value = _normalize_timestamp(marker.time)
        stale_at_value = _normalize_timestamp(marker.stale_at)
        delta = stale_at_value - time_value
        if delta.total_seconds() > 0:
            return int(delta.total_seconds())
    return DEFAULT_MARKER_TTL_SECONDS


@dataclass(frozen=True)
class MarkerUpdateResult:
    """Result of a marker update operation."""

    marker: Marker
    changed: bool


class MarkerService:
    """Service layer for managing operator markers."""

    def __init__(
        self,
        storage: MarkerStorage,
        *,
        identity_key_provider: Optional[Callable[[], bytes]] = None,
    ) -> None:
        """Create a marker service.

        Args:
            storage (MarkerStorage): Storage provider for marker data.
            identity_key_provider (Optional[Callable[[], bytes]]): Provider for encryption keys.
        """

        self._storage = storage
        self._identity_key_provider = identity_key_provider

    def _resolve_identity_key(self) -> Optional[bytes]:
        """Return the marker identity encryption key, when configured.

        Returns:
            Optional[bytes]: Encryption key bytes.
        """

        provider = self._identity_key_provider
        if provider is None:
            return None
        return provider()

    def list_markers(self) -> list[Marker]:
        """Return all persisted markers."""

        return self._storage.list_markers()

    def create_marker(
        self,
        *,
        name: Optional[str],
        marker_type: str,
        symbol: str,
        category: str,
        lat: float,
        lon: float,
        origin_rch: str,
        notes: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
    ) -> Marker:
        """Create and persist a new marker.

        Args:
            name (Optional[str]): Optional marker name.
            marker_type (str): Marker type identifier.
            symbol (str): Marker symbol identifier.
            category (str): Marker category identifier.
            lat (float): Latitude.
            lon (float): Longitude.
            origin_rch (str): Originating hub identity hash.
            notes (Optional[str]): Optional notes.
            ttl_seconds (Optional[int]): Optional TTL override in seconds.

        Returns:
            Marker: Persisted marker record.
        """

        local_id = uuid.uuid4().hex
        normalized_type = normalize_marker_symbol(marker_type or "marker")
        normalized_symbol = normalize_marker_symbol(symbol or "marker")
        normalized_category = normalize_marker_symbol(category or "")
        if not normalized_category:
            normalized_category = normalized_symbol or normalized_type or "marker"
        if not normalized_type:
            normalized_type = normalized_symbol or normalized_category or "marker"
        if not normalized_symbol:
            normalized_symbol = normalized_type or normalized_category or "marker"
        if not is_supported_marker_symbol(normalized_type):
            raise ValueError("Unsupported marker type")
        if not is_supported_marker_symbol(normalized_symbol):
            raise ValueError("Unsupported marker symbol")
        resolved_name = name.strip() if isinstance(name, str) else ""
        if not resolved_name:
            resolved_name = _default_marker_name(normalized_type, local_id)
        timestamp = _utcnow()
        stale_at = _compute_stale_at(timestamp, ttl_seconds)
        identity = RNS.Identity()
        identity_key = self._resolve_identity_key()
        storage_key = encrypt_marker_identity(identity, identity_key=identity_key)
        destination_hash = marker_destination_hash(identity)
        marker = Marker(
            local_id=local_id,
            object_destination_hash=destination_hash,
            origin_rch=origin_rch,
            object_identity_storage_key=storage_key,
            marker_type=normalized_type,
            symbol=normalized_symbol,
            name=resolved_name,
            category=normalized_category,
            notes=notes,
            lat=float(lat),
            lon=float(lon),
            time=timestamp,
            stale_at=stale_at,
            created_at=timestamp,
            updated_at=timestamp,
        )
        return self._storage.create_marker(marker)

    def update_marker_position(
        self,
        object_destination_hash: str,
        *,
        lat: float,
        lon: float,
    ) -> MarkerUpdateResult:
        """Update marker coordinates when they have changed.

        Args:
            object_destination_hash (str): Marker destination hash to update.
            lat (float): Updated latitude.
            lon (float): Updated longitude.

        Returns:
            MarkerUpdateResult: Updated marker plus change indicator.

        Raises:
            KeyError: When the marker does not exist.
        """

        marker = self._storage.get_marker(object_destination_hash)
        if marker is None:
            raise KeyError(f"Marker '{object_destination_hash}' not found")
        now = _utcnow()
        expired = (
            marker.stale_at is not None
            and _normalize_timestamp(now) > _normalize_timestamp(marker.stale_at)
        )
        position_changed = _position_changed(marker, lat, lon)
        if not position_changed and not expired:
            return MarkerUpdateResult(marker=marker, changed=False)
        ttl_seconds = _resolve_marker_ttl_seconds(marker)
        stale_at = _compute_stale_at(now, ttl_seconds)
        updated = self._storage.update_marker_position(
            object_destination_hash,
            lat=float(lat),
            lon=float(lon),
            updated_at=now,
            time=now,
            stale_at=stale_at,
        )
        if updated is None:
            raise KeyError(f"Marker '{object_destination_hash}' not found")
        return MarkerUpdateResult(marker=updated, changed=True)

    def migrate_markers(self, *, origin_rch: str) -> list[Marker]:
        """Migrate legacy markers to identity-backed objects.

        Args:
            origin_rch (str): Originating hub identity hash.

        Returns:
            list[Marker]: Updated marker records.
        """

        migrated: list[Marker] = []
        legacy_markers = self._storage.list_uninitialized_markers()
        for marker in legacy_markers:
            identity = RNS.Identity()
            identity_key = self._resolve_identity_key()
            storage_key = encrypt_marker_identity(identity, identity_key=identity_key)
            destination_hash = marker_destination_hash(identity)
            marker_type = normalize_marker_symbol(
                marker.marker_type or marker.category or "marker"
            )
            symbol = normalize_marker_symbol(
                marker.symbol or marker.category or marker_type
            )
            if not is_supported_marker_symbol(symbol):
                symbol = marker_type if is_supported_marker_symbol(marker_type) else "marker"
            if not is_supported_marker_symbol(marker_type):
                marker_type = symbol if is_supported_marker_symbol(symbol) else "marker"
            timestamp = marker.updated_at or _utcnow()
            stale_at = _compute_stale_at(timestamp, None)
            updated = self._storage.update_marker_identity(
                marker.local_id,
                object_destination_hash=destination_hash,
                origin_rch=origin_rch,
                object_identity_storage_key=storage_key,
                marker_type=marker_type,
                symbol=symbol,
                time=timestamp,
                stale_at=stale_at,
            )
            if updated is not None:
                migrated.append(updated)
        return migrated
