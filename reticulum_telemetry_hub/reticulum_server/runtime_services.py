"""Message service and inbound parsing helpers."""
# ruff: noqa: F403,F405

from __future__ import annotations

import json
from typing import Callable

import LXMF
import RNS

from reticulum_telemetry_hub.api.models import FileAttachment
import reticulum_telemetry_hub.lxmf_runtime  # noqa: F401
from reticulum_telemetry_hub.config.constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.announce_capabilities import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.delivery_defaults import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.delivery_service import DeliveryService
from reticulum_telemetry_hub.reticulum_server.message_events import MessageEventEmitter
from reticulum_telemetry_hub.reticulum_server.message_router import MessageRouter
from reticulum_telemetry_hub.reticulum_server.propagation_selection import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_support import *  # noqa: F403


class RuntimeServiceMixin:
    """Message service and inbound parsing helpers."""

    def _message_events_service(self) -> MessageEventEmitter:
        """Return the message event emitter, creating it for test-only hub stubs."""

        service = getattr(self, "message_events", None)
        if service is None:
            service = MessageEventEmitter(self)
            self.message_events = service
        return service

    def _delivery_service(self) -> DeliveryService:
        """Return the delivery service, creating it for test-only hub stubs."""

        service = getattr(self, "delivery_service", None)
        if service is None:
            service = DeliveryService(self)
            self.delivery_service = service
        return service

    def _message_router_service(self) -> MessageRouter:
        """Return the message router, creating it for test-only hub stubs."""

        service = getattr(self, "message_router", None)
        if service is None:
            service = MessageRouter(self)
            self.message_router = service
        return service

    def register_message_listener(
        self, listener: Callable[[dict[str, object]], None]
    ) -> Callable[[], None]:
        """Register a callback invoked for inbound LXMF messages."""

        return self._message_events_service().register_message_listener(listener)


    def _notify_message_listeners(self, entry: dict[str, object]) -> None:
        """Dispatch an inbound message entry to registered listeners."""

        self._message_events_service().notify_message_listeners(entry)


    def _record_message_event(
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

        self._message_events_service().record_message_event(
            content=content,
            source_label=source_label,
            source_hash=source_hash,
            topic_id=topic_id,
            timestamp=timestamp,
            direction=direction,
            state=state,
            destination=destination,
            attachments=attachments,
            message_id=message_id,
        )


    def _parse_escape_prefixed_commands(
        self, message: LXMF.LXMessage
    ) -> tuple[list[dict] | None, bool, str | None]:
        """Parse a command list from an escape-prefixed message body.

        The `Commands` LXMF field may be unavailable in some clients, so the
        hub accepts a leading ``\\\\\\`` prefix in the message content and
        treats the remainder as a command payload.

        Args:
            message (LXMF.LXMessage): LXMF message object.

        Returns:
            tuple[list[dict] | None, bool, str | None]: Normalized command list,
                an empty list when the payload is malformed, or ``None`` when no
                escape prefix is present, paired with a boolean indicating whether
                the escape prefix was detected and an optional error message.
        """

        if LXMF.FIELD_COMMANDS in message.fields:
            return None, False, None

        if message.content is None or message.content == b"":
            return None, False, None

        try:
            content_text = message.content_as_string()
        except Exception as exc:
            RNS.log(
                f"Unable to decode message content for escape-prefixed commands: {exc}",
                RNS.LOG_WARNING,
            )
            return [], False, "Unable to decode message content."

        if not content_text.startswith(ESCAPED_COMMAND_PREFIX):
            return None, False, None

        # Reason: the prefix signals that the body should be treated as a command
        # payload even when the `Commands` field is unavailable.
        body = content_text[len(ESCAPED_COMMAND_PREFIX) :].strip()
        if not body:
            RNS.log(
                "Ignored escape-prefixed command payload with no body.",
                RNS.LOG_WARNING,
            )
            return [], True, "Command payload is empty."

        if body.startswith("\\[") or body.startswith("\\{"):
            body = body[1:]

        parsed_payload = None
        if body.startswith("{") or body.startswith("["):
            try:
                parsed_payload = json.loads(body)
            except json.JSONDecodeError as exc:
                RNS.log(
                    f"Failed to parse escape-prefixed JSON payload: {exc}",
                    RNS.LOG_WARNING,
                )
                return [], True, "Command payload is not valid JSON."

        if parsed_payload is None:
            return [{"Command": body}], True, None

        if isinstance(parsed_payload, dict):
            return [parsed_payload], True, None

        if isinstance(parsed_payload, list):
            if not parsed_payload:
                RNS.log(
                    "Ignored escape-prefixed command list with no entries.",
                    RNS.LOG_WARNING,
                )
                return [], True, "Command payload list is empty."

            if not all(isinstance(item, dict) for item in parsed_payload):
                RNS.log(
                    "Escape-prefixed JSON must be an object or list of objects.",
                    RNS.LOG_WARNING,
                )
                return [], True, "Command payload must be a JSON object or list of objects."

            return parsed_payload, True, None

        RNS.log(
            "Escape-prefixed payload must decode to a JSON object or list of objects.",
            RNS.LOG_WARNING,
        )
        return [], True, "Command payload must be a JSON object or list of objects."

