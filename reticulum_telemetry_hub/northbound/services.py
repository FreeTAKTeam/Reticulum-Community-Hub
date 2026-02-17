"""Service helpers for the northbound API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional

from reticulum_telemetry_hub.api.models import ChatMessage
from reticulum_telemetry_hub.api.models import Client
from reticulum_telemetry_hub.api.models import FileAttachment
from reticulum_telemetry_hub.api.models import IdentityStatus
from reticulum_telemetry_hub.api.models import Marker
from reticulum_telemetry_hub.api.models import ReticulumInfo
from reticulum_telemetry_hub.api.models import Subscriber
from reticulum_telemetry_hub.api.models import Topic
from reticulum_telemetry_hub.api.models import Zone
from reticulum_telemetry_hub.api.models import ZonePoint
from reticulum_telemetry_hub.api.marker_service import MarkerService
from reticulum_telemetry_hub.api.marker_service import MarkerUpdateResult
from reticulum_telemetry_hub.api.reticulum_discovery import (
    get_discovery_snapshot,
)
from reticulum_telemetry_hub.api.reticulum_discovery import (
    get_interface_capabilities,
)
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.api.zone_service import ZoneService
from reticulum_telemetry_hub.api.zone_service import ZoneUpdateResult
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.reticulum_server import command_text
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog
from reticulum_telemetry_hub.reticulum_server.marker_objects import (
    build_marker_telemetry_payload,
)


def _load_supported_commands_doc() -> Optional[str]:
    doc_path = Path(__file__).resolve().parents[2] / "docs" / "supportedCommands.md"
    try:
        return doc_path.read_text(encoding="utf-8")
    except OSError:
        return None


def _build_help_fallback(doc_text: str) -> str:
    public_commands: list[str] = []
    protected_commands: list[str] = []
    section: Optional[str] = None
    for line in doc_text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("public commands"):
            section = "public"
            continue
        if stripped.lower().startswith("protected commands"):
            section = "protected"
            continue
        if stripped.startswith("| `"):
            parts = [part.strip() for part in stripped.split("|")]
            if len(parts) < 2:
                continue
            command_cell = parts[1].replace("`", "").strip()
            if not command_cell:
                continue
            if section == "protected":
                protected_commands.append(command_cell)
            else:
                public_commands.append(command_cell)
    if not public_commands and not protected_commands:
        return "# Command list\n\nCommand documentation not available."
    lines = ["# Command list", ""]
    if public_commands:
        lines.append("Public:")
        lines.extend([f"- {command}" for command in public_commands])
        lines.append("")
    if protected_commands:
        lines.append("Protected:")
        lines.extend([f"- {command}" for command in protected_commands])
    return "\n".join(lines).strip() + "\n"


def _build_examples_fallback(doc_text: str) -> str:
    marker = "Public commands:"
    start = doc_text.find(marker)
    if start == -1:
        return doc_text
    snippet = doc_text[start:].strip()
    return f"# Command examples\n\n{snippet}\n"


@dataclass
class NorthboundServices:
    """Aggregate services needed by the northbound API."""

    api: ReticulumTelemetryHubAPI
    telemetry: TelemetryController
    event_log: EventLog
    started_at: datetime
    command_manager: Optional[Any] = None
    routing_provider: Optional[Callable[[], List[str]]] = None
    message_dispatcher: Optional[
        Callable[[str, Optional[str], Optional[str], Optional[dict]], ChatMessage | None]
    ] = None
    marker_service: MarkerService | None = None
    marker_dispatcher: Optional[Callable[[Marker, str], bool]] = None
    zone_service: ZoneService | None = None
    origin_rch: str = ""

    def help_text(self) -> str:
        """Return the Help command text.

        Returns:
            str: Markdown formatted help content.
        """

        if not self.command_manager:
            doc_text = _load_supported_commands_doc()
            if doc_text:
                return _build_help_fallback(doc_text)
            return "# Command list\n\nCommand manager is not configured."
        return command_text.build_help_text(self.command_manager)

    def examples_text(self) -> str:
        """Return the Examples command text.

        Returns:
            str: Markdown formatted examples content.
        """

        if not self.command_manager:
            doc_text = _load_supported_commands_doc()
            if doc_text:
                return _build_examples_fallback(doc_text)
            return "# Command examples\n\nCommand manager is not configured."
        return command_text.build_examples_text(self.command_manager)

    def status_snapshot(self) -> Dict[str, object]:
        """Return the current status snapshot.

        Returns:
            Dict[str, object]: Status payload for the dashboard.
        """

        uptime = datetime.now(timezone.utc) - self.started_at
        chat_stats = self.api.chat_message_stats()
        return {
            "uptime_seconds": int(uptime.total_seconds()),
            "clients": len(self.api.list_clients()),
            "topics": len(self.api.list_topics()),
            "subscribers": len(self.api.list_subscribers()),
            "files": len(self.api.list_files()),
            "images": len(self.api.list_images()),
            "chat": {
                "sent": chat_stats.get("sent", 0),
                "failed": chat_stats.get("failed", 0),
                "received": chat_stats.get("delivered", 0),
            },
            "telemetry": self.telemetry.telemetry_stats(),
        }

    def list_events(self, limit: Optional[int] = None) -> List[Dict[str, object]]:
        """Return recent events.

        Args:
            limit (Optional[int]): Optional limit for returned events.

        Returns:
            List[Dict[str, object]]: Event entries.
        """

        return self.event_log.list_events(limit=limit)

    def record_event(
        self, event_type: str, message: str, metadata: Optional[Dict[str, object]] = None
    ) -> Dict[str, object]:
        """Record an event entry.

        Args:
            event_type (str): Event category.
            message (str): Human readable description.
            metadata (Optional[Dict[str, object]]): Optional structured data.

        Returns:
            Dict[str, object]: Event entry payload.
        """

        return self.event_log.add_event(event_type, message, metadata=metadata)

    def list_clients(self) -> List[Client]:
        """Return connected clients.

        Returns:
            List[Client]: Client entries.
        """

        return self.api.list_clients()

    def list_topics(self) -> List[Topic]:
        """Return topics.

        Returns:
            List[Topic]: Topic entries.
        """

        return self.api.list_topics()

    def list_subscribers(self) -> List[Subscriber]:
        """Return subscribers.

        Returns:
            List[Subscriber]: Subscriber entries.
        """

        return self.api.list_subscribers()

    def list_files(self) -> List[FileAttachment]:
        """Return file attachments.

        Returns:
            List[FileAttachment]: File records.
        """

        return self.api.list_files()

    def list_images(self) -> List[FileAttachment]:
        """Return image attachments.

        Returns:
            List[FileAttachment]: Image records.
        """

        return self.api.list_images()

    def delete_file(self, file_id: int) -> FileAttachment:
        """Delete a stored file."""

        return self.api.delete_file(file_id)

    def delete_image(self, file_id: int) -> FileAttachment:
        """Delete a stored image."""

        return self.api.delete_image(file_id)

    def list_identity_statuses(self) -> List[IdentityStatus]:
        """Return identity moderation statuses.

        Returns:
            List[IdentityStatus]: Identity status records.
        """

        return self.api.list_identity_statuses()

    def list_markers(self) -> List[Marker]:
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

    def list_chat_messages(
        self,
        *,
        limit: int = 200,
        direction: Optional[str] = None,
        topic_id: Optional[str] = None,
        destination: Optional[str] = None,
        source: Optional[str] = None,
    ) -> List[ChatMessage]:
        """Return persisted chat messages."""

        return self.api.list_chat_messages(
            limit=limit,
            direction=direction,
            topic_id=topic_id,
            destination=destination,
            source=source,
        )

    def store_uploaded_attachment(
        self,
        *,
        content: bytes,
        filename: str,
        media_type: Optional[str],
        category: str,
        topic_id: Optional[str] = None,
    ) -> FileAttachment:
        """Persist an uploaded attachment to storage."""

        return self.api.store_uploaded_attachment(
            content=content,
            filename=filename,
            media_type=media_type,
            category=category,
            topic_id=topic_id,
        )

    def resolve_attachments(
        self,
        *,
        file_ids: list[int],
        image_ids: list[int],
    ) -> list[FileAttachment]:
        """Resolve stored attachment records by ID."""

        attachments: list[FileAttachment] = []
        for file_id in file_ids:
            attachments.append(self.api.retrieve_file(file_id))
        for image_id in image_ids:
            attachments.append(self.api.retrieve_image(image_id))
        return attachments

    def dump_routing(self) -> Dict[str, List[str]]:
        """Return connected destinations.

        Returns:
            Dict[str, List[str]]: Routing summary payload.
        """

        if self.routing_provider:
            return {"destinations": list(self.routing_provider())}
        return {"destinations": [client.identity for client in self.api.list_clients()]}

    def telemetry_entries(
        self, *, since: int, topic_id: Optional[str] = None
    ) -> List[Dict[str, object]]:
        """Return telemetry entries for REST responses.

        Args:
            since (int): Unix timestamp in seconds.
            topic_id (Optional[str]): Optional topic filter.

        Returns:
            List[Dict[str, object]]: Telemetry entries.
        """

        return self.telemetry.list_telemetry_entries(since=since, topic_id=topic_id)

    def app_info(self) -> ReticulumInfo:
        """Return application metadata.

        Returns:
            ReticulumInfo: Application info snapshot.
        """

        return self.api.get_app_info()

    def reticulum_interface_capabilities(self) -> Dict[str, object]:
        """Return Reticulum interface capabilities for the current runtime."""

        return get_interface_capabilities()

    def reticulum_discovery_snapshot(self) -> Dict[str, object]:
        """Return Reticulum interface discovery snapshot."""

        return get_discovery_snapshot()

    def send_message(
        self,
        content: str,
        *,
        topic_id: Optional[str] = None,
        destination: Optional[str] = None,
    ) -> None:
        """Dispatch a message from northbound into the core hub."""

        if not self.message_dispatcher:
            raise RuntimeError("Message dispatch is not configured")
        self.message_dispatcher(content, topic_id, destination, None)

    def send_chat_message(
        self,
        *,
        content: str,
        scope: str,
        topic_id: Optional[str],
        destination: Optional[str],
        attachments: list[FileAttachment],
    ) -> ChatMessage:
        """Send a chat message via the core hub."""

        if not self.message_dispatcher:
            raise RuntimeError("Message dispatch is not configured")
        chat_attachments = [
            self.api.chat_attachment_from_file(item) for item in attachments
        ]
        fields = {"attachments": attachments}
        if scope:
            fields["scope"] = scope
        message = self.message_dispatcher(content, topic_id, destination, fields)
        if message is None:
            message = ChatMessage(
                direction="outbound",
                scope=scope,
                state="failed",
                content=content,
                source=None,
                destination=destination,
                topic_id=topic_id,
                attachments=chat_attachments,
            )
            return self.api.record_chat_message(message)
        return message

    def reload_config(self) -> ReticulumInfo:
        """Reload configuration from disk.

        Returns:
            ReticulumInfo: Updated configuration snapshot.
        """

        return self.api.reload_config()

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
