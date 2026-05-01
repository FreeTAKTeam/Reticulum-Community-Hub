"""Marker and zone operations for northbound services."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from typing import Optional

from reticulum_telemetry_hub.api.marker_service import MarkerService
from reticulum_telemetry_hub.api.marker_service import MarkerUpdateResult
from reticulum_telemetry_hub.api.models import Marker
from reticulum_telemetry_hub.api.models import Zone
from reticulum_telemetry_hub.api.models import ZonePoint
from reticulum_telemetry_hub.api.zone_service import ZoneService
from reticulum_telemetry_hub.api.zone_service import ZoneUpdateResult
from reticulum_telemetry_hub.reticulum_server.marker_objects import (
    build_marker_telemetry_payload,
)


class NorthboundSpatialMixin:
    """Provide marker and zone service operations."""

    marker_service: MarkerService | None
    marker_dispatcher: object
    zone_service: ZoneService | None
    origin_rch: str

    def list_markers(self) -> list[Marker]:
        """Return stored operator markers."""

        service = self._require_marker_service()
        return service.list_markers()

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
        """Create a marker and dispatch a marker.created event."""

        service = self._require_marker_service()
        marker = service.create_marker(
            name=name,
            marker_type=marker_type,
            symbol=symbol,
            category=category,
            lat=lat,
            lon=lon,
            origin_rch=origin_rch,
            notes=notes,
            ttl_seconds=ttl_seconds,
        )
        self._record_marker_event("marker.created", marker)
        return marker

    def update_marker_position(
        self,
        object_destination_hash: str,
        *,
        lat: float,
        lon: float,
    ) -> MarkerUpdateResult:
        """Update marker coordinates and dispatch marker.updated when changed."""

        service = self._require_marker_service()
        result = service.update_marker_position(
            object_destination_hash, lat=lat, lon=lon
        )
        if result.changed:
            self._record_marker_event("marker.updated", result.marker)
        return result

    def update_marker_name(
        self,
        object_destination_hash: str,
        *,
        name: str,
    ) -> MarkerUpdateResult:
        """Update marker display name and dispatch marker.updated when changed."""

        service = self._require_marker_service()
        result = service.update_marker_name(object_destination_hash, name=name)
        if result.changed:
            self._record_marker_event("marker.updated", result.marker)
        return result

    def delete_marker(self, object_destination_hash: str) -> Marker:
        """Delete a marker and dispatch marker.deleted."""

        service = self._require_marker_service()
        marker = service.delete_marker(object_destination_hash)
        self._record_marker_event("marker.deleted", marker)
        return marker

    def list_zones(self) -> list[Zone]:
        """Return stored operational zones."""

        service = self._require_zone_service()
        return service.list_zones()

    def create_zone(self, *, name: str, points: list[ZonePoint]) -> Zone:
        """Create and persist a zone."""

        service = self._require_zone_service()
        return service.create_zone(name=name, points=points)

    def update_zone(
        self,
        zone_id: str,
        *,
        name: str | None = None,
        points: list[ZonePoint] | None = None,
    ) -> ZoneUpdateResult:
        """Update zone metadata and/or geometry."""

        service = self._require_zone_service()
        return service.update_zone(zone_id, name=name, points=points)

    def delete_zone(self, zone_id: str) -> Zone:
        """Delete a zone."""

        service = self._require_zone_service()
        return service.delete_zone(zone_id)

    def _record_marker_event(self, event_type: str, marker: Marker) -> None:
        """Record marker activity and dispatch telemetry events."""

        payload = self._marker_event_payload(event_type, marker)
        self.event_log.add_event(
            event_type.replace(".", "_"),
            f"Marker {event_type.split('.')[-1]}: {marker.name}",
            metadata=payload,
        )
        if self._marker_is_expired(marker):
            self.event_log.add_event(
                "marker_dispatch_skipped",
                "Marker event dispatch skipped for expired marker",
                metadata={
                    "event_type": event_type,
                    "object_destination_hash": marker.object_destination_hash,
                },
            )
            return
        if self.marker_dispatcher is None:
            self._record_marker_telemetry(event_type, marker)
            self.event_log.add_event(
                "marker_dispatch_skipped",
                "Marker event dispatch is not configured; telemetry recorded locally",
                metadata={
                    "event_type": event_type,
                    "object_destination_hash": marker.object_destination_hash,
                },
            )
            return
        try:
            self.marker_dispatcher(marker, event_type)
        except Exception as exc:  # pragma: no cover - defensive logging
            self.event_log.add_event(
                "marker_dispatch_failed",
                f"Marker event dispatch failed: {exc}",
                metadata={
                    "event_type": event_type,
                    "object_destination_hash": marker.object_destination_hash,
                },
            )

    def _record_marker_telemetry(self, event_type: str, marker: Marker) -> None:
        """Record marker telemetry directly in the telemetry store."""

        if not marker.object_destination_hash:
            self.event_log.add_event(
                "marker_telemetry_skipped",
                "Marker telemetry skipped due to missing destination hash",
                metadata={"event_type": event_type},
            )
            return
        origin_rch = marker.origin_rch or self.origin_rch
        payload = build_marker_telemetry_payload(
            marker,
            event_type,
            origin_rch=origin_rch,
        )
        try:
            self.telemetry.record_telemetry(
                payload,
                marker.object_destination_hash,
                notify=True,
            )
            self.event_log.add_event(
                "marker_telemetry_recorded",
                "Marker telemetry recorded",
                metadata={
                    "event_type": event_type,
                    "object_destination_hash": marker.object_destination_hash,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            self.event_log.add_event(
                "marker_telemetry_failed",
                f"Marker telemetry recording failed: {exc}",
                metadata={
                    "event_type": event_type,
                    "object_destination_hash": marker.object_destination_hash,
                },
            )

    @staticmethod
    def _marker_event_payload(event_type: str, marker: Marker) -> dict[str, object]:
        """Return a marker event payload suitable for LXMF fields."""

        time_value = marker.time or marker.updated_at
        stale_at_value = marker.stale_at or time_value
        payload: dict[str, object] = {
            "object_type": "marker",
            "object_id": marker.object_destination_hash,
            "event_type": event_type,
            "marker_type": marker.marker_type,
            "symbol": marker.symbol,
            "lat": marker.lat,
            "lon": marker.lon,
            "position": {"lat": marker.lat, "lon": marker.lon},
            "origin_rch": marker.origin_rch,
            "time": time_value.isoformat() if time_value else None,
            "stale_at": stale_at_value.isoformat() if stale_at_value else None,
            "timestamp": marker.updated_at.isoformat(),
        }
        if event_type == "marker.created":
            payload["metadata"] = {
                "name": marker.name,
                "category": marker.category,
                "symbol": marker.symbol,
                "marker_type": marker.marker_type,
            }
            payload["name"] = marker.name
            payload["category"] = marker.category
            payload["symbol"] = marker.symbol
            payload["marker_type"] = marker.marker_type
        return payload

    @staticmethod
    def _marker_is_expired(marker: Marker) -> bool:
        """Return True when a marker is expired."""

        if marker.stale_at is None:
            return False
        stale_at = marker.stale_at
        if stale_at.tzinfo is None or stale_at.tzinfo.utcoffset(stale_at) is None:
            stale_at = stale_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > stale_at

    def _require_marker_service(self) -> MarkerService:
        """Return the marker service or raise when missing."""

        if self.marker_service is None:
            raise RuntimeError("Marker service is not configured")
        return self.marker_service

    def _require_zone_service(self) -> ZoneService:
        """Return the zone service or raise when missing."""

        if self.zone_service is None:
            raise RuntimeError("Zone service is not configured")
        return self.zone_service
