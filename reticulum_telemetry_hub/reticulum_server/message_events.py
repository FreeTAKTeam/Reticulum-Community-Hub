"""Listener registration and message event emission helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from typing import Callable
from typing import Protocol

import RNS

from reticulum_telemetry_hub.api.models import ChatMessage
from reticulum_telemetry_hub.api.service import FileAttachment
from reticulum_telemetry_hub.message_delivery import normalize_topic_id


class MessageEventsHubProtocol(Protocol):
    """Protocol describing hub dependencies for message event emission."""

    _message_listeners: list[Callable[[dict[str, object]], None]]

    def _notify_message_listeners(self, entry: dict[str, object]) -> None:
        """Notify registered listeners."""


class MessageEventEmitter:
    """Coordinates message listeners and northbound message events."""

    def __init__(self, hub: Any) -> None:
        self._hub = hub

    def register_message_listener(
        self, listener: Callable[[dict[str, object]], None]
    ) -> Callable[[], None]:
        """Register a callback invoked for inbound LXMF messages."""

        self._hub._message_listeners.append(listener)

        def _remove_listener() -> None:
            """Remove a previously registered message listener."""

            if listener in self._hub._message_listeners:
                self._hub._message_listeners.remove(listener)

        return _remove_listener

    def notify_message_listeners(self, entry: dict[str, object]) -> None:
        """Dispatch an inbound message entry to registered listeners."""

        listeners = list(getattr(self._hub, "_message_listeners", []))
        for listener in listeners:
            try:
                listener(entry)
            except Exception as exc:  # pragma: no cover - defensive logging
                RNS.log(
                    f"Message listener raised an exception: {exc}",
                    getattr(RNS, "LOG_WARNING", 2),
                )

    def record_message_event(
        self,
        *,
        content: str,
        source_label: str,
        source_hash: str | None,
        topic_id: str | None,
        timestamp: datetime,
        direction: str,
        state: str,
        destination: str | None,
        attachments: list[FileAttachment],
        message_id: str | None = None,
    ) -> None:
        """Emit a message event for northbound consumers."""

        topic_id = normalize_topic_id(topic_id)
        scope = "topic" if topic_id else "dm"
        if direction == "outbound" and not destination and not topic_id:
            scope = "broadcast"
        api = getattr(self._hub, "api", None)
        has_chat_support = api is not None and all(
            hasattr(api, name) for name in ("record_chat_message", "chat_attachment_from_file")
        )
        attachment_payloads = []
        if has_chat_support:
            attachment_payloads = [
                api.chat_attachment_from_file(item).to_dict()
                for item in attachments
            ]
            chat_message = ChatMessage(
                message_id=message_id,
                direction=direction,
                scope=scope,
                state=state,
                content=content,
                source=source_hash or source_label,
                destination=destination,
                topic_id=topic_id,
                attachments=[
                    api.chat_attachment_from_file(item) for item in attachments
                ],
                created_at=timestamp,
                updated_at=timestamp,
            )
            stored = api.record_chat_message(chat_message)
            entry = stored.to_dict()
            entry["SourceHash"] = source_hash or ""
            entry["SourceLabel"] = source_label
            entry["Timestamp"] = timestamp.isoformat()
            entry["Attachments"] = attachment_payloads
            self.notify_message_listeners(entry)
        else:
            entry = {
                "MessageID": message_id,
                "Direction": direction,
                "Scope": scope,
                "State": state,
                "Content": content,
                "Source": source_hash or source_label,
                "Destination": destination,
                "TopicID": topic_id,
                "Attachments": attachment_payloads,
                "CreatedAt": timestamp.isoformat(),
                "UpdatedAt": timestamp.isoformat(),
                "SourceHash": source_hash or "",
                "SourceLabel": source_label,
                "Timestamp": timestamp.isoformat(),
            }
            self.notify_message_listeners(entry)
        event_log = getattr(self._hub, "event_log", None)
        if event_log is not None:
            event_log.add_event(
                "message_received" if direction == "inbound" else "message_sent",
                (
                    f"Message received from {source_label}"
                    if direction == "inbound"
                    else "Message sent from hub"
                ),
                metadata=entry,
            )
