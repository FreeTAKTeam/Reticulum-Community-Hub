"""Service helpers for the northbound API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional

from reticulum_telemetry_hub.api.models import Client
from reticulum_telemetry_hub.api.models import FileAttachment
from reticulum_telemetry_hub.api.models import IdentityStatus
from reticulum_telemetry_hub.api.models import ReticulumInfo
from reticulum_telemetry_hub.api.models import Subscriber
from reticulum_telemetry_hub.api.models import Topic
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.reticulum_server import command_text
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog


@dataclass
class NorthboundServices:
    """Aggregate services needed by the northbound API."""

    api: ReticulumTelemetryHubAPI
    telemetry: TelemetryController
    event_log: EventLog
    started_at: datetime
    command_manager: Optional[Any] = None
    routing_provider: Optional[Callable[[], List[str]]] = None
    message_sender: Optional[
        Callable[[str, Optional[str], Optional[set[str]]], None]
    ] = None

    def help_text(self) -> str:
        """Return the Help command text.

        Returns:
            str: Markdown formatted help content.
        """

        if not self.command_manager:
            return "# Command list\n\nCommand manager is not configured."
        return command_text.build_help_text(self.command_manager)

    def examples_text(self) -> str:
        """Return the Examples command text.

        Returns:
            str: Markdown formatted examples content.
        """

        if not self.command_manager:
            return "# Command examples\n\nCommand manager is not configured."
        return command_text.build_examples_text(self.command_manager)

    def status_snapshot(self) -> Dict[str, object]:
        """Return the current status snapshot.

        Returns:
            Dict[str, object]: Status payload for the dashboard.
        """

        uptime = datetime.now(timezone.utc) - self.started_at
        return {
            "uptime_seconds": int(uptime.total_seconds()),
            "clients": len(self.api.list_clients()),
            "topics": len(self.api.list_topics()),
            "subscribers": len(self.api.list_subscribers()),
            "files": len(self.api.list_files()),
            "images": len(self.api.list_images()),
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

    def list_identity_statuses(self) -> List[IdentityStatus]:
        """Return identity moderation statuses.

        Returns:
            List[IdentityStatus]: Identity status records.
        """

        return self.api.list_identity_statuses()

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

    def reload_config(self) -> ReticulumInfo:
        """Reload configuration from disk.

        Returns:
            ReticulumInfo: Updated configuration snapshot.
        """

        return self.api.reload_config()

    def send_message(
        self,
        message: str,
        *,
        topic_id: Optional[str] = None,
        exclude: Optional[list[str]] = None,
    ) -> Dict[str, object]:
        """Send a message to connected LXMF clients.

        Args:
            message (str): Message content to send.
            topic_id (Optional[str]): Optional topic to filter recipients.
            exclude (Optional[list[str]]): Optional destination hashes to skip.

        Returns:
            Dict[str, object]: Summary payload for the send request.

        Raises:
            RuntimeError: If no message sender is configured.
        """

        if not self.message_sender:
            raise RuntimeError("Message sender is not configured")
        exclude_set = {entry.lower() for entry in exclude} if exclude else None
        self.message_sender(message, topic_id=topic_id, exclude=exclude_set)
        self.record_event(
            "northbound_message_sent",
            "Northbound message sent",
            metadata={
                "topic_id": topic_id,
                "exclude": exclude or [],
                "message": message,
            },
        )
        return {"status": "sent"}
