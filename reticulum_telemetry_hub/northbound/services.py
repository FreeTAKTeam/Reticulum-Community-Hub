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
from reticulum_telemetry_hub.api.models import ReticulumInfo
from reticulum_telemetry_hub.api.models import Subscriber
from reticulum_telemetry_hub.api.models import Topic
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.reticulum_server import command_text
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog


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

    def list_identity_statuses(self) -> List[IdentityStatus]:
        """Return identity moderation statuses.

        Returns:
            List[IdentityStatus]: Identity status records.
        """

        return self.api.list_identity_statuses()

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
