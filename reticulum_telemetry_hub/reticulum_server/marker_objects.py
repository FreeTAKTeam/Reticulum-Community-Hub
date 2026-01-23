"""Marker identity and telemetry helpers for ReticulumTelemetryHub."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from typing import Callable
from typing import Iterable
from typing import Optional

import RNS

from reticulum_telemetry_hub.api.marker_identity import build_marker_announce_data
from reticulum_telemetry_hub.api.marker_identity import build_marker_destination
from reticulum_telemetry_hub.api.marker_identity import decrypt_marker_identity
from reticulum_telemetry_hub.api.models import Marker
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.generic import (
    Custom,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.information import (
    Information,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.location import (
    Location,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_enum import (
    SID_CUSTOM,
    SID_INFORMATION,
    SID_LOCATION,
    SID_TIME,
)
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog


def _utcnow() -> datetime:
    """Return the current UTC timestamp.

    Returns:
        datetime: Current UTC timestamp.
    """

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


def _is_marker_expired(marker: Marker, now: Optional[datetime] = None) -> bool:
    """Return True when a marker has expired.

    Args:
        marker (Marker): Marker to inspect.
        now (Optional[datetime]): Timestamp override.

    Returns:
        bool: True when the marker is expired.
    """

    if marker.stale_at is None:
        return False
    now_value = now or _utcnow()
    return _normalize_timestamp(now_value) > _normalize_timestamp(marker.stale_at)


def build_marker_custom_payload(
    marker: Marker,
    event_type: str,
    *,
    origin_rch: str,
    time_value: datetime,
    stale_at_value: datetime,
) -> list[list[object]] | None:
    """Build a Sideband-compatible custom payload for marker telemetry."""

    custom = Custom()
    metadata: dict[str, object] = {
        "object_type": "marker",
        "object_id": marker.object_destination_hash,
        "event_type": event_type,
        "marker_type": marker.marker_type,
        "symbol": marker.symbol,
        "category": marker.category,
        "name": marker.name,
        "origin_rch": origin_rch,
        "position": {"lat": marker.lat, "lon": marker.lon},
        "time": time_value.isoformat(),
        "stale_at": stale_at_value.isoformat(),
    }
    if marker.notes:
        metadata["notes"] = marker.notes
    custom.update_entry(metadata, type_label="marker")
    return custom.pack()


def build_marker_telemetry_payload(
    marker: Marker,
    event_type: str,
    *,
    origin_rch: str,
) -> dict[int, object]:
    """Build a Sideband-compatible telemetry payload for markers."""

    time_value = _normalize_timestamp(marker.time or marker.updated_at or _utcnow())
    stale_at_value = _normalize_timestamp(marker.stale_at or time_value)
    payload: dict[int, object] = {
        SID_TIME: time_value.timestamp(),
    }

    location = Location()
    location.latitude = marker.lat
    location.longitude = marker.lon
    location.altitude = 0.0
    location.speed = 0.0
    location.bearing = 0.0
    location.accuracy = 0.0
    location.last_update = time_value
    location_payload = location.pack()
    if location_payload is not None:
        payload[SID_LOCATION] = location_payload

    info_payload = Information(marker.name).pack()
    if info_payload:
        payload[SID_INFORMATION] = info_payload

    custom_payload = build_marker_custom_payload(
        marker,
        event_type,
        origin_rch=origin_rch,
        time_value=time_value,
        stale_at_value=stale_at_value,
    )
    if custom_payload is not None:
        payload[SID_CUSTOM] = custom_payload
    return payload


@dataclass
class MarkerObjectManager:
    """Manage marker object identities and announcements."""

    origin_rch_provider: Callable[[], str]
    event_log: Optional[EventLog]
    telemetry_recorder: Optional[
        Callable[[dict[int, object] | bytes, str], None]
    ] = None
    identity_key_provider: Optional[Callable[[], bytes]] = None
    announce_interval_seconds: int = 900

    def __post_init__(self) -> None:
        """Initialize marker destination cache."""

        self._destinations: dict[str, RNS.Destination] = {}
        self._last_announce_at: datetime | None = None

    def announce_marker(self, marker: Marker) -> None:
        """Announce a marker object identity with metadata.

        Args:
            marker (Marker): Marker to announce.
        """

        if _is_marker_expired(marker):
            return
        try:
            destination = self._get_destination(marker)
            destination.display_name = marker.name
            app_data = build_marker_announce_data(marker)
            destination.announce(app_data=app_data)
            self._record_event("marker_announced", marker, {"event": "announce"})
        except Exception as exc:  # pragma: no cover - defensive logging
            self._log_marker_error("marker_announce_skipped", marker, exc)

    def announce_active_markers(self, markers: Iterable[Marker]) -> None:
        """Announce all non-expired markers when the interval elapses.

        Args:
            markers (Iterable[Marker]): Markers to announce.
        """

        if not self._should_announce():
            return
        for marker in markers:
            if _is_marker_expired(marker):
                continue
            self.announce_marker(marker)
        self._last_announce_at = _utcnow()

    def dispatch_marker_telemetry(self, marker: Marker, event_type: str) -> bool:
        """Persist marker telemetry for delivery on telemetry requests.

        Args:
            marker (Marker): Marker to emit.
            event_type (str): Event type string.

        Returns:
            bool: True when the telemetry payload was recorded.
        """

        if _is_marker_expired(marker):
            self._record_event(
                "marker_telemetry_skipped",
                marker,
                {"event_type": event_type, "reason": "expired"},
            )
            return False
        if not marker.object_destination_hash or not marker.object_identity_storage_key:
            self._record_event(
                "marker_telemetry_failed",
                marker,
                {"event_type": event_type, "reason": "missing_identity"},
            )
            return False
        if self.telemetry_recorder is None:
            self._record_event(
                "marker_telemetry_skipped",
                marker,
                {
                    "event_type": event_type,
                    "reason": "telemetry_recorder_unavailable",
                },
            )
            return False
        try:
            payload = self._build_telemetry_payload(marker, event_type)
            self.telemetry_recorder(payload, marker.object_destination_hash)
            self._record_event(
                "marker_telemetry_recorded",
                marker,
                {"event_type": event_type},
            )
            return True
        except Exception as exc:  # pragma: no cover - defensive logging
            self._log_marker_error("marker_telemetry_failed", marker, exc)
            return False

    def _get_destination(self, marker: Marker) -> RNS.Destination:
        """Return or create the Reticulum destination for a marker.

        Args:
            marker (Marker): Marker metadata.

        Returns:
            RNS.Destination: Cached or newly created destination.
        """

        if not marker.object_destination_hash:
            raise ValueError("Marker is missing destination hash")
        existing = self._destinations.get(marker.object_destination_hash)
        if existing is not None:
            return existing
        if not marker.object_identity_storage_key:
            raise ValueError("Marker identity storage key is missing")
        identity_key = (
            self.identity_key_provider() if self.identity_key_provider else None
        )
        identity = decrypt_marker_identity(
            marker.object_identity_storage_key,
            identity_key=identity_key,
        )
        destination = build_marker_destination(identity)
        dest_hash = destination.hash.hex().lower()
        if dest_hash != marker.object_destination_hash:
            self._record_event(
                "marker_identity_mismatch",
                marker,
                {"expected": marker.object_destination_hash, "actual": dest_hash},
            )
        self._destinations[marker.object_destination_hash] = destination
        return destination

    def _build_telemetry_payload(
        self, marker: Marker, event_type: str
    ) -> dict[int, object]:
        """Build a Sideband-compatible telemetry payload for markers.

        Args:
            marker (Marker): Marker to serialize.
            event_type (str): Event type for the telemetry payload.

        Returns:
            dict[int, object]: Packed telemetry payload keyed by sensor id.
        """

        origin_rch = marker.origin_rch or self.origin_rch_provider()
        return build_marker_telemetry_payload(
            marker,
            event_type,
            origin_rch=origin_rch,
        )

    @staticmethod
    def _build_custom_payload(
        marker: Marker,
        event_type: str,
        *,
        origin_rch: str,
        time_value: datetime,
        stale_at_value: datetime,
    ) -> list[list[object]] | None:
        return build_marker_custom_payload(
            marker,
            event_type,
            origin_rch=origin_rch,
            time_value=time_value,
            stale_at_value=stale_at_value,
        )

    def _should_announce(self) -> bool:
        """Return True when the marker announce interval has elapsed.

        Returns:
            bool: True when the announce interval elapsed.
        """

        if self._last_announce_at is None:
            return True
        elapsed = _utcnow() - self._last_announce_at
        return elapsed.total_seconds() >= self.announce_interval_seconds

    def _record_event(
        self, event_type: str, marker: Marker, metadata: dict[str, object]
    ) -> None:
        """Record marker event metadata when logging is enabled.

        Args:
            event_type (str): Event identifier.
            marker (Marker): Marker to log.
            metadata (dict[str, object]): Event metadata payload.
        """

        if self.event_log is None:
            return
        payload = dict(metadata)
        payload["object_destination_hash"] = marker.object_destination_hash
        payload["marker_type"] = marker.marker_type
        payload["symbol"] = marker.symbol
        self.event_log.add_event(event_type, f"Marker: {marker.name}", metadata=payload)

    def _log_marker_error(self, event_type: str, marker: Marker, exc: Exception) -> None:
        """Record and log marker errors without interrupting the scheduler.

        Args:
            event_type (str): Event identifier.
            marker (Marker): Marker associated with the error.
            exc (Exception): Error instance.
        """

        self._record_event(event_type, marker, {"reason": str(exc)})
        RNS.log(
            f"{event_type} for marker {marker.object_destination_hash}: {exc}",
            getattr(RNS, "LOG_WARNING", 2),
        )
