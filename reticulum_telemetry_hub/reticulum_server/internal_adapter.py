"""Reticulum-facing adapter for the internal API."""

from __future__ import annotations

import asyncio
import copy
import logging
import time
from dataclasses import dataclass
from typing import Awaitable
from typing import Callable
from typing import Optional
from typing import Union
from uuid import uuid4

import LXMF
from msgpack import unpackb
from datetime import datetime
from datetime import timezone

from reticulum_telemetry_hub.internal_api.core import InternalApiCore
from reticulum_telemetry_hub.internal_api.v1.enums import CommandStatus
from reticulum_telemetry_hub.internal_api.v1.enums import CommandType
from reticulum_telemetry_hub.internal_api.v1.enums import EventType
from reticulum_telemetry_hub.internal_api.v1.enums import IssuerType
from reticulum_telemetry_hub.internal_api.v1.enums import MessageType
from reticulum_telemetry_hub.internal_api.v1.enums import NodeType
from reticulum_telemetry_hub.internal_api.v1.enums import Qos
from reticulum_telemetry_hub.internal_api.v1.schemas import CommandEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import EventEnvelope
from reticulum_telemetry_hub.internal_api.versioning import select_api_version
from reticulum_telemetry_hub.reticulum_server.constants import PLUGIN_COMMAND


_DEDUP_TTL_SECONDS = 600.0
_LOGGER = logging.getLogger(__name__)


def _maybe_await(result: Union[None, Awaitable[None]]) -> Awaitable[None]:
    if asyncio.iscoroutine(result):
        return result
    return asyncio.sleep(0)


class InlineEventBus:
    """Inline event bus for synchronous Reticulum adapters."""

    def __init__(self) -> None:
        self._subscribers: list[Callable[[EventEnvelope], Union[None, Awaitable[None]]]] = []

    def subscribe(self, handler):
        """Subscribe to events and return an unsubscribe callback."""

        self._subscribers.append(handler)

        def _unsubscribe() -> None:
            if handler in self._subscribers:
                self._subscribers.remove(handler)

        return _unsubscribe

    async def start(self) -> None:
        """No-op start."""

        return None

    async def stop(self) -> None:
        """No-op stop."""

        return None

    async def publish(self, event: EventEnvelope) -> None:
        """Publish events to subscribers immediately."""

        for handler in list(self._subscribers):
            await _maybe_await(handler(_copy_event(event)))


@dataclass
class LxmfInbound:
    """Normalized LXMF inbound payload for adapter processing."""

    message_id: Optional[str]
    source_id: Optional[str]
    topic_id: Optional[str]
    text: Optional[str]
    fields: dict
    commands: list[dict]


class MessageDeduper:
    """TTL-based duplicate filter for LXMF message IDs."""

    def __init__(self, *, ttl_seconds: float, clock: Callable[[], float]) -> None:
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: dict[str, float] = {}
        self._order: list[tuple[float, str]] = []

    def is_duplicate(self, message_id: str) -> bool:
        """Return True when message_id has been seen within the TTL window."""

        now = self._clock()
        self._prune(now)
        if message_id in self._entries:
            return True
        self._entries[message_id] = now
        self._order.append((now, message_id))
        return False

    def _prune(self, now: float) -> None:
        cutoff = now - self._ttl_seconds
        while self._order and self._order[0][0] < cutoff:
            _, message_id = self._order.pop(0)
            self._entries.pop(message_id, None)


class ReticulumInternalAdapter:
    """Adapter translating LXMF inputs to internal API commands."""

    def __init__(
        self,
        *,
        send_message: Callable[[str, Optional[str]], None],
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.event_bus = InlineEventBus()
        self.core = InternalApiCore(self.event_bus)
        self._send_message = send_message
        self._clock = clock
        self._seen_nodes: set[str] = set()
        self._deduper = MessageDeduper(ttl_seconds=_DEDUP_TTL_SECONDS, clock=clock)
        self._pending_text: dict[str, tuple[str, str]] = {}
        self.event_bus.subscribe(self._handle_event)

    def handle_inbound(self, inbound: LxmfInbound) -> None:
        """Handle normalized LXMF inputs."""

        message_id = (inbound.message_id or "").lower()
        if message_id and self._deduper.is_duplicate(message_id):
            return

        node_id = inbound.source_id
        if node_id:
            if node_id not in self._seen_nodes:
                self._seen_nodes.add(node_id)
                self._register_node(node_id)
            self.core.touch_node(node_id)

        commands = inbound.commands or []
        for command in commands:
            name = _command_name(command)
            if not name:
                continue
            normalized = name.lower()
            if normalized == "join":
                if node_id and node_id not in self._seen_nodes:
                    self._seen_nodes.add(node_id)
                    self._register_node(node_id)
                continue
            if normalized == "subscribetopic":
                topic_id = _extract_topic_id(command)
                if node_id and topic_id:
                    self._subscribe_topic(node_id, topic_id)
                continue
            if normalized == "createtopic":
                continue

        if inbound.topic_id and inbound.text:
            self._publish_text(node_id, inbound.topic_id, inbound.text)

        telemetry_payloads = _extract_telemetry_payloads(inbound.fields)
        if inbound.topic_id and telemetry_payloads:
            for payload in telemetry_payloads:
                self._publish_telemetry(node_id, inbound.topic_id, payload)

    def _register_node(self, node_id: str) -> None:
        command = _build_command(
            CommandType.REGISTER_NODE,
            {
                "node_id": node_id,
                "node_type": NodeType.RETICULUM,
                "metadata": None,
            },
            issuer_id=node_id,
        )
        _run_command(self.core, command)

    def _subscribe_topic(self, node_id: str, topic_id: str) -> None:
        command = _build_command(
            CommandType.SUBSCRIBE_TOPIC,
            {"subscriber_id": node_id, "topic_path": topic_id},
            issuer_id=node_id,
        )
        _run_command(self.core, command)

    def _publish_text(self, node_id: Optional[str], topic_id: str, text: str) -> None:
        if not node_id:
            return
        command = _build_command(
            CommandType.PUBLISH_MESSAGE,
            {
                "topic_path": topic_id,
                "message_type": MessageType.TEXT,
                "content": {
                    "message_type": MessageType.TEXT,
                    "text": text,
                    "encoding": "utf-8",
                },
                "qos": Qos.BEST_EFFORT,
            },
            issuer_id=node_id,
        )
        message_id = command.command_id.hex
        self._pending_text[message_id] = (topic_id, text)
        result = _run_command(self.core, command)
        if result.status != CommandStatus.ACCEPTED:
            self._pending_text.pop(message_id, None)

    def _publish_telemetry(
        self, node_id: Optional[str], topic_id: str, payload: dict
    ) -> None:
        if not node_id:
            return
        telemetry_type = payload.get("telemetry_type")
        command = _build_command(
            CommandType.PUBLISH_MESSAGE,
            {
                "topic_path": topic_id,
                "message_type": MessageType.TELEMETRY,
                "content": {
                    "message_type": MessageType.TELEMETRY,
                    "telemetry_type": telemetry_type if isinstance(telemetry_type, str) else None,
                    "data": payload,
                },
                "qos": Qos.BEST_EFFORT,
            },
            issuer_id=node_id,
        )
        _run_command(self.core, command)

    async def _handle_event(self, event: EventEnvelope) -> None:
        """Fan out message events to LXMF recipients."""

        if event.event_type != EventType.MESSAGE_PUBLISHED:
            return
        payload = event.payload
        message_id = getattr(payload, "message_id", "")
        pending = self._pending_text.pop(message_id, None)
        if not pending:
            return
        topic_id, text = pending
        message_text = f"[topic:{topic_id}]\n{text}"
        for subscriber_id in self.core.get_subscriber_ids(topic_id):
            self._send_message(message_text, subscriber_id)


def _run_command(core: InternalApiCore, command: CommandEnvelope):
    return asyncio.run(core.handle_command(command))


def _build_command(
    command_type: CommandType, payload: dict, *, issuer_id: str
) -> CommandEnvelope:
    command = CommandEnvelope.model_validate(
        {
            "api_version": select_api_version(),
            "command_id": uuid4(),
            "command_type": command_type,
            "issued_at": datetime.now(timezone.utc),
            "issuer": {"type": IssuerType.RETICULUM, "id": issuer_id},
            "payload": payload,
        }
    )
    _LOGGER.debug(
        "Reticulum adapter command built",
        extra={
            "command_id": str(command.command_id),
            "command_type": command.command_type.value,
            "correlation_id": str(command.command_id),
        },
    )
    return command


def _copy_event(event: EventEnvelope) -> EventEnvelope:
    copy_method = getattr(event, "model_copy", None)
    if callable(copy_method):
        return copy_method(deep=True)
    return copy.deepcopy(event)


def _command_name(command: dict) -> Optional[str]:
    value = command.get("Command") or command.get("command")
    if isinstance(value, str):
        return value.strip()
    plugin_value = command.get(PLUGIN_COMMAND) or command.get(str(PLUGIN_COMMAND))
    if isinstance(plugin_value, str):
        return plugin_value.strip()
    return None


def _extract_topic_id(command: dict) -> Optional[str]:
    for key in ("TopicID", "topic_id", "topic", "Topic"):
        value = command.get(key)
        if value:
            return str(value)
    return None


def _extract_telemetry_payloads(fields: dict) -> list[dict]:
    payloads: list[dict] = []
    if not isinstance(fields, dict):
        return payloads
    if LXMF.FIELD_TELEMETRY in fields:
        raw = fields.get(LXMF.FIELD_TELEMETRY)
        payload = _decode_telemetry_payload(raw)
        if isinstance(payload, dict):
            payloads.append(payload)
    if LXMF.FIELD_TELEMETRY_STREAM in fields:
        raw_stream = fields.get(LXMF.FIELD_TELEMETRY_STREAM)
        entries = _decode_telemetry_stream(raw_stream)
        for payload in entries:
            if isinstance(payload, dict):
                payloads.append(payload)
    return payloads


def _decode_telemetry_payload(raw) -> Optional[dict]:
    if isinstance(raw, (bytes, bytearray)):
        try:
            decoded = unpackb(raw, strict_map_key=False)
        except Exception:
            return None
        return decoded if isinstance(decoded, dict) else None
    if isinstance(raw, dict):
        return raw
    return None


def _decode_telemetry_stream(raw) -> list[dict]:
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = unpackb(raw, strict_map_key=False)
        except Exception:
            return []
    if not isinstance(raw, (list, tuple)):
        return []
    payloads: list[dict] = []
    for entry in raw:
        if not isinstance(entry, (list, tuple)) or len(entry) < 3:
            continue
        payload = entry[2]
        if isinstance(payload, (bytes, bytearray)):
            payload = _decode_telemetry_payload(payload)
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads
