"""TAK, field, topic, and destination helper methods."""
# pylint: disable=not-callable
# ruff: noqa: F403,F405

from __future__ import annotations

from typing import Any
from typing import Callable
from typing import cast

import LXMF
import RNS

from reticulum_telemetry_hub.message_delivery import DeliveryContractError
from reticulum_telemetry_hub.message_delivery import extract_delivery_envelope
from reticulum_telemetry_hub.message_delivery import normalize_hash
from reticulum_telemetry_hub.message_delivery import normalize_topic_id
from reticulum_telemetry_hub.message_delivery import utc_now_ms
from reticulum_telemetry_hub.message_delivery import utc_now_rfc3339
from reticulum_telemetry_hub.message_delivery import validate_delivery_envelope
import reticulum_telemetry_hub.lxmf_runtime  # noqa: F401
from reticulum_telemetry_hub.config.constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.announce_capabilities import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.constants import PLUGIN_COMMAND
from reticulum_telemetry_hub.reticulum_server.delivery_defaults import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.propagation_selection import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_events import report_nonfatal_exception
from reticulum_telemetry_hub.reticulum_server.command_manager import CommandManager
from reticulum_telemetry_hub.reticulum_server.runtime_constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_support import _dispatch_coroutine
from reticulum_telemetry_hub.reticulum_server.runtime_support import *  # noqa: F403


class RuntimeTakFieldMixin:
    """TAK, field, topic, and destination helper methods."""

    def _handle_telemetry_for_tak(
        self,
        telemetry: dict,
        peer_hash: str | bytes | None,
        timestamp: datetime | None,
    ) -> None:
        """Convert telemetry payloads into CoT events for TAK consumers."""

        tak_connector = getattr(self, "tak_connector", None)
        if tak_connector is None:
            return
        try:
            coroutine = tak_connector.send_telemetry_event(
                telemetry,
                peer_hash=peer_hash,
                timestamp=timestamp,
            )
            runner = getattr(self, "_tak_async_runner", None)
            if runner is not None:
                runner.submit(coroutine)
            else:
                _dispatch_coroutine(coroutine)
        except Exception as exc:  # pragma: no cover - defensive logging
            RNS.log(
                f"Failed to send telemetry CoT event: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )

    def _extract_target_topic(self, fields) -> str | None:
        if not isinstance(fields, dict):
            return None
        envelope = extract_delivery_envelope(fields)
        if envelope is not None:
            try:
                validated = validate_delivery_envelope(envelope)
            except DeliveryContractError:
                validated = None
            if validated is not None and validated.topic_id:
                return validated.topic_id
        for key in ("TopicID", "topic_id", "topic", "Topic"):
            topic_id = fields.get(key)
            if topic_id:
                return normalize_topic_id(topic_id)
        commands = fields.get(LXMF.FIELD_COMMANDS)
        if isinstance(commands, list):
            for command in commands:
                if not isinstance(command, dict):
                    continue
                for key in ("TopicID", "topic_id", "topic", "Topic"):
                    topic_id = command.get(key)
                    if topic_id:
                        return normalize_topic_id(topic_id)
        return None

    @staticmethod
    def _relay_standard_fields(fields: dict | None) -> dict | None:
        """Return relay-safe standard LXMF metadata fields.

        The hub forwards threading and group metadata so downstream clients keep
        conversation context when messages are relayed.
        """

        if not isinstance(fields, dict):
            return None
        relayed: dict = {}
        for key in (LXMF.FIELD_THREAD, LXMF.FIELD_GROUP):
            value = fields.get(key)
            if value is not None:
                relayed[key] = value
        return relayed or None

    @classmethod
    def _merge_standard_fields(
        cls,
        *,
        source_fields: dict | None,
        extra_fields: dict | None,
    ) -> dict | None:
        """Merge relay-safe standard fields with explicit outbound fields."""

        merged: dict = {}
        relayed = cls._relay_standard_fields(source_fields)
        if relayed:
            merged.update(relayed)
        if isinstance(extra_fields, dict):
            merged.update(extra_fields)
        return merged or None

    def _validate_inbound_delivery_contract(self, message: LXMF.LXMessage) -> str | None:
        """Validate the optional delivery envelope on an inbound message."""

        fields = getattr(message, "fields", None)
        envelope = extract_delivery_envelope(fields)
        if envelope is None:
            return None
        try:
            validate_delivery_envelope(envelope)
        except DeliveryContractError as exc:
            report_nonfatal_exception(
                getattr(self, "event_log", None),
                "message_quarantined",
                f"Rejected inbound delivery envelope: {exc}",
                exc,
                metadata={
                    "reason": str(exc),
                    "content_type": envelope.get("Content-Type"),
                    "message_id": envelope.get("Message-ID"),
                },
                log_level=getattr(RNS, "LOG_WARNING", 2),
            )
            return f"Delivery envelope rejected: {exc}"
        return None

    @staticmethod
    def _build_event_field(
        *,
        event_type: str,
        direction: str | None = None,
        topic_id: str | None = None,
        source_hash: str | None = None,
        destination: str | None = None,
    ) -> dict[str, object]:
        """Return a structured event payload for FIELD_EVENT."""

        payload: dict[str, object] = {
            "event_type": event_type,
            "ts": utc_now_ms(),
            "source": "rch",
        }
        if direction:
            payload["direction"] = direction
        if topic_id:
            payload["topic_id"] = normalize_topic_id(topic_id)
        if source_hash:
            payload["source_hash"] = source_hash
        if destination:
            payload["destination"] = destination
        payload["created_at"] = utc_now_rfc3339()
        return payload

    def _format_chat_broadcast_text(
        self,
        *,
        source_label: str,
        content_text: str,
        topic_id: str | None,
    ) -> str:
        """Build the relayed chat text for topic and non-topic messages."""

        if not topic_id:
            return f"{source_label} > {content_text}"

        topic_path = self._resolve_topic_path(topic_id)
        return f"{topic_path}: {source_label} > {content_text}"

    def _hub_sender_label(self) -> str:
        """Return the sender label used for hub-originated chat messages."""

        display_name = getattr(self, "display_name", None)
        if isinstance(display_name, str):
            normalized = display_name.strip()
            if normalized:
                return normalized
        return "Hub"

    @staticmethod
    def _has_sender_prefix(content_text: str) -> bool:
        """Return True when ``content_text`` already contains ``User > Text``."""

        if not isinstance(content_text, str):
            return False
        separator = " > "
        left, marker, right = content_text.partition(separator)
        if marker != separator:
            return False
        return bool(left.strip() and right.strip())

    def _resolve_topic_path(self, topic_id: str) -> str:
        """Return the topic path for ``topic_id`` when available."""

        fallback = str(topic_id)
        api = getattr(self, "api", None)
        if api is None:
            return fallback

        raw_resolver = getattr(api, "retrieve_topic", None)
        if not callable(raw_resolver):
            return fallback
        resolver = cast(Callable[[str], Any], raw_resolver)

        try:
            topic = resolver(topic_id)
        except Exception:
            return fallback

        topic_path = getattr(topic, "topic_path", None)
        if isinstance(topic_path, str):
            normalized = topic_path.strip()
            if normalized:
                return normalized
        return fallback

    def _refresh_topic_registry(self) -> None:
        if not self.api:
            return
        try:
            subscribers = self.api.list_subscribers()
        except Exception as exc:  # pragma: no cover - defensive logging
            RNS.log(
                f"Failed to refresh topic registry: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )
            self.topic_subscribers = {}
            self._topic_registry_dirty = True
            return
        registry: dict[str, set[str]] = {}
        for subscriber in subscribers:
            topic_id = normalize_topic_id(getattr(subscriber, "topic_id", None))
            destination = getattr(subscriber, "destination", "")
            if not topic_id or not destination:
                continue
            registry.setdefault(topic_id, set()).add(destination.lower())
        self.topic_subscribers = registry

        self._topic_registry_dirty = False

    def _invalidate_topic_registry(self) -> None:
        """Mark the topic subscriber cache dirty."""

        self._topic_registry_dirty = True

    def _subscribers_for_topic(self, topic_id: str) -> set[str]:
        normalized_topic_id = normalize_topic_id(topic_id)
        if not normalized_topic_id:
            return set()
        if getattr(self, "_topic_registry_dirty", False) or normalized_topic_id not in self.topic_subscribers:
            if self.api:
                self._refresh_topic_registry()
        return self.topic_subscribers.get(normalized_topic_id, set())

    def _commands_affect_subscribers(self, commands: list[dict] | None) -> bool:
        """Return True when commands modify subscriber mappings."""

        if not commands:
            return False

        subscriber_commands = {
            CommandManager.CMD_SUBSCRIBE_TOPIC,
            CommandManager.CMD_CREATE_SUBSCRIBER,
            CommandManager.CMD_ADD_SUBSCRIBER,
            CommandManager.CMD_DELETE_SUBSCRIBER,
            CommandManager.CMD_REMOVE_SUBSCRIBER,
            CommandManager.CMD_PATCH_SUBSCRIBER,
        }

        for command in commands:
            if not isinstance(command, dict):
                continue
            name = command.get(PLUGIN_COMMAND) or command.get("Command")
            if name in subscriber_commands:
                return True

        return False

    @staticmethod
    def _mission_commands_affect_subscribers(commands: list[dict] | None) -> bool:
        """Return True when mission-sync commands modify subscriber mappings."""

        if not commands:
            return False
        for command in commands:
            if not isinstance(command, dict):
                continue
            command_type = command.get("command_type")
            if command_type == "topic.subscribe":
                return True
        return False

    @staticmethod
    def _connection_hex(connection: RNS.Destination) -> str | None:
        identity = getattr(connection, "identity", None)
        hash_bytes = getattr(identity, "hash", None)
        if isinstance(hash_bytes, (bytes, bytearray)) and hash_bytes:
            return hash_bytes.hex().lower()
        return None

    def _cache_destination(self, connection: RNS.Destination) -> None:
        """Cache a connection by normalized identity hash for fast targeted routing."""

        identity_hex = self._connection_hex(connection)
        if not identity_hex:
            return
        with self._destination_cache_lock:
            self._destination_cache[identity_hex] = connection

    def _evict_cached_destination(self, identity: str | None) -> None:
        """Remove a cached destination for ``identity`` if present."""

        normalized_identity = normalize_hash(identity)
        if not normalized_identity:
            return
        with self._destination_cache_lock:
            self._destination_cache.pop(normalized_identity, None)

    def _cached_destination(self, identity: str) -> RNS.Destination | None:
        """Return a cached destination for ``identity`` when available."""

        normalized_identity = normalize_hash(identity)
        if not normalized_identity:
            return None
        with self._destination_cache_lock:
            cached = self._destination_cache.get(normalized_identity)
        if cached is not None:
            return cached
        for connection in (
            list(self.connections.values())
            if hasattr(self.connections, "values")
            else list(self.connections)
        ):
            if self._connection_hex(connection) == normalized_identity:
                self._cache_destination(connection)
                return connection
        return None

    def _message_source_hex(self, message: LXMF.LXMessage) -> str | None:
        source = message.get_source()
        if source is not None:
            identity = getattr(source, "identity", None)
            hash_bytes = getattr(identity, "hash", None)
            if isinstance(hash_bytes, (bytes, bytearray)) and hash_bytes:
                return hash_bytes.hex().lower()
        source_hash = getattr(message, "source_hash", None)
        if isinstance(source_hash, (bytes, bytearray)) and source_hash:
            return source_hash.hex().lower()
        return None

    @staticmethod
    def _message_destination_hex(message: LXMF.LXMessage) -> str | None:
        destination_hash = getattr(message, "destination_hash", None)
        if isinstance(destination_hash, (bytes, bytearray, memoryview)) and destination_hash:
            return bytes(destination_hash).hex().lower()
        if isinstance(destination_hash, str) and destination_hash:
            return destination_hash.lower()
        return None

    @staticmethod
    def _message_id_hex(message: LXMF.LXMessage) -> str | None:
        message_id = getattr(message, "message_id", None) or getattr(message, "hash", None)
        if isinstance(message_id, (bytes, bytearray)) and message_id:
            return message_id.hex().lower()
        if isinstance(message_id, str) and message_id:
            return message_id.lower()
        return None

    def _sender_is_joined(self, message: LXMF.LXMessage) -> bool:
        """Return True when the message sender has previously joined.

        Args:
            message (LXMF.LXMessage): Incoming LXMF message.

        Returns:
            bool: ``True`` if the sender exists in the connection cache or the
            persisted client registry.
        """

        connections = getattr(self, "connections", {}) or {}
        source = None
        try:
            source = message.get_source()
        except Exception:
            source = None
        identity = getattr(source, "identity", None)
        hash_bytes = getattr(identity, "hash", None)
        if isinstance(hash_bytes, (bytes, bytearray)) and hash_bytes:
            if hash_bytes in connections:
                return True

        sender_hex = self._message_source_hex(message)
        if not sender_hex:
            return False

        api = getattr(self, "api", None)
        if api is None:
            return False
        try:
            if hasattr(api, "has_client"):
                return bool(api.has_client(sender_hex))
            if hasattr(api, "list_clients"):
                lower_hex = sender_hex.lower()
                return any(
                    getattr(client, "identity", "").lower() == lower_hex
                    for client in api.list_clients()
                )
        except Exception as exc:  # pragma: no cover - defensive log
            RNS.log(
                f"Failed to determine join status for {sender_hex}: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )
        return False

