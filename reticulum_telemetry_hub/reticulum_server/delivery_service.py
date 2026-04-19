"""Outbound delivery transitions and queue orchestration."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
import time
from typing import Any
from typing import Protocol
from typing import TypedDict

import LXMF
import RNS

from reticulum_telemetry_hub.message_delivery import DeliveryContractError
from reticulum_telemetry_hub.message_delivery import extract_delivery_envelope
from reticulum_telemetry_hub.message_delivery import normalize_topic_id
from reticulum_telemetry_hub.message_delivery import utc_now_rfc3339
from reticulum_telemetry_hub.message_delivery import validate_delivery_envelope
from reticulum_telemetry_hub.reticulum_server.delivery_defaults import DEFAULT_OUTBOUND_BACKOFF
from reticulum_telemetry_hub.reticulum_server.delivery_defaults import DEFAULT_OUTBOUND_DELIVERY_RECEIPT_TIMEOUT
from reticulum_telemetry_hub.reticulum_server.delivery_defaults import DEFAULT_OUTBOUND_MAX_ATTEMPTS
from reticulum_telemetry_hub.reticulum_server.delivery_defaults import DEFAULT_OUTBOUND_QUEUE_SIZE
from reticulum_telemetry_hub.reticulum_server.delivery_defaults import DEFAULT_OUTBOUND_SEND_TIMEOUT
from reticulum_telemetry_hub.reticulum_server.delivery_defaults import DEFAULT_OUTBOUND_WORKERS
from reticulum_telemetry_hub.reticulum_server.outbound_queue import OutboundMessageQueue
from reticulum_telemetry_hub.reticulum_server.outbound_queue import OutboundPayload
from reticulum_telemetry_hub.reticulum_server.propagation_selection import PropagationNodeCandidate


def _utcnow() -> datetime:
    """Return a UTC timestamp for persisted chat event records."""

    return datetime.now(timezone.utc)


class QueueStats(TypedDict):
    """Typed snapshot of outbound queue counters for diagnostics."""

    queue_depth: int
    inflight: int
    active_dispatches: int
    in_progress_futures: int
    pending_dispatches: int
    pending_receipts: int
    timed_out_sends: int
    worker_count: int


class DeliveryTransition(TypedDict, total=False):
    """Typed event payload emitted during delivery state transitions."""

    MessageID: str | None
    Direction: str
    Scope: str
    State: str
    Content: str
    Source: str | None
    Destination: str | None
    TopicID: str | None
    SourceHash: str
    SourceLabel: str
    Timestamp: str
    DeliveryMetadata: dict[str, object]


class DeliveryMonitoringHooks(Protocol):
    """Hook interface used by outbound queue callbacks."""

    def handle_outbound_retry_scheduled(self, payload: OutboundPayload) -> None:
        """Observe direct retry scheduling."""

    def handle_outbound_propagation_fallback(self, payload: OutboundPayload) -> None:
        """Observe propagation fallback transitions."""

    def handle_outbound_attempt_started(self, payload: OutboundPayload) -> None:
        """Observe attempt start transitions."""

    def handle_outbound_payload_dropped(self, payload: OutboundPayload, reason: str) -> None:
        """Observe terminal queue drop transitions."""


class DeliveryService:
    """Handles outbound delivery transitions and queue lifecycle."""

    def __init__(self, hub: Any) -> None:
        self._hub = hub

    def ensure_outbound_queue(self) -> OutboundMessageQueue | None:
        """Initialize and start the outbound worker queue."""

        if getattr(self._hub, "my_lxmf_dest", None) is None:
            return None

        if not hasattr(self._hub, "_outbound_queue"):
            self._hub._outbound_queue = None

        if self._hub._outbound_queue is None:
            self._hub._outbound_queue = OutboundMessageQueue(
                self._hub.lxm_router,
                self._hub.my_lxmf_dest,
                queue_size=getattr(
                    self._hub, "outbound_queue_size", DEFAULT_OUTBOUND_QUEUE_SIZE
                )
                or DEFAULT_OUTBOUND_QUEUE_SIZE,
                worker_count=getattr(self._hub, "outbound_workers", DEFAULT_OUTBOUND_WORKERS)
                or DEFAULT_OUTBOUND_WORKERS,
                send_timeout=getattr(
                    self._hub, "outbound_send_timeout", DEFAULT_OUTBOUND_SEND_TIMEOUT
                )
                or DEFAULT_OUTBOUND_SEND_TIMEOUT,
                delivery_receipt_timeout=getattr(
                    self._hub,
                    "outbound_delivery_receipt_timeout",
                    DEFAULT_OUTBOUND_DELIVERY_RECEIPT_TIMEOUT,
                )
                or DEFAULT_OUTBOUND_DELIVERY_RECEIPT_TIMEOUT,
                backoff_seconds=getattr(
                    self._hub, "outbound_backoff", DEFAULT_OUTBOUND_BACKOFF
                )
                or DEFAULT_OUTBOUND_BACKOFF,
                max_attempts=getattr(
                    self._hub, "outbound_max_attempts", DEFAULT_OUTBOUND_MAX_ATTEMPTS
                )
                or DEFAULT_OUTBOUND_MAX_ATTEMPTS,
                delivery_receipt_callback=self.handle_outbound_delivery_receipt,
                delivery_failure_callback=self.handle_outbound_delivery_failure,
                propagation_selector=self.select_best_propagation_node,
                retry_scheduled_callback=self.handle_outbound_retry_scheduled,
                propagation_fallback_callback=self.handle_outbound_propagation_fallback,
                attempt_started_callback=self.handle_outbound_attempt_started,
                payload_dropped_callback=self.handle_outbound_payload_dropped,
            )
        self._hub._outbound_queue.start()
        return self._hub._outbound_queue

    def queue_stats(self) -> QueueStats | None:
        """Return typed queue statistics when queue is available."""

        queue = getattr(self._hub, "_outbound_queue", None)
        if queue is None:
            return None
        return queue.stats()

    def handle_outbound_delivery_receipt(
        self,
        message: LXMF.LXMessage,
        payload: OutboundPayload,
    ) -> None:
        """Persist and broadcast outbound delivery acknowledgements."""

        destination = payload.destination_hex or self._hub._message_destination_hex(message)
        is_propagated = payload.delivery_mode == "propagated"
        entry = self.update_outbound_chat_state(
            message=message,
            payload=payload,
            state="propagated" if is_propagated else "delivered",
            destination=destination,
        )
        entry = self.augment_outbound_delivery_metadata(entry, payload)
        entry["acknowledgement_type"] = (
            "propagation_acceptance" if is_propagated else "delivery_receipt"
        )
        event_log = getattr(self._hub, "event_log", None)
        if event_log is None:
            return
        destination_label = self._hub._lookup_identity_label(destination) if destination else "unknown"
        if is_propagated:
            if payload.local_propagation_fallback:
                event_log.add_event(
                    "message_propagated",
                    f"Message stored for local propagation to {destination_label}",
                    metadata=entry,
                )
                return
            node_label = self.resolve_propagation_node_label(payload)
            event_log.add_event(
                "message_propagated",
                f"Message accepted for propagation to {destination_label} via {node_label}",
                metadata=entry,
            )
            return
        event_log.add_event(
            "message_delivered",
            f"Message delivered to {destination_label}",
            metadata=entry,
        )

    def handle_outbound_delivery_failure(
        self,
        message: LXMF.LXMessage,
        payload: OutboundPayload,
    ) -> None:
        """Persist and broadcast outbound delivery failures."""

        destination = payload.destination_hex or self._hub._message_destination_hex(message)
        entry = self.update_outbound_chat_state(
            message=message,
            payload=payload,
            state="failed",
            destination=destination,
        )
        entry = self.augment_outbound_delivery_metadata(entry, payload)
        event_log = getattr(self._hub, "event_log", None)
        if event_log is None:
            return
        destination_label = self._hub._lookup_identity_label(destination) if destination else "unknown"
        event_log.add_event(
            "message_delivery_failed",
            f"Message delivery failed for {destination_label}",
            metadata=entry,
        )

    def handle_outbound_retry_scheduled(self, payload: OutboundPayload) -> None:
        """Record a direct-delivery retry event."""

        self.persist_outbound_delivery_metadata(
            payload,
            state="queued",
            delivery_metadata={"retry_scheduled": True},
        )
        event_log = getattr(self._hub, "event_log", None)
        if event_log is None:
            return
        destination_label = (
            self._hub._lookup_identity_label(payload.destination_hex)
            if payload.destination_hex
            else "unknown"
        )
        event_log.add_event(
            "message_delivery_retrying",
            f"Retrying message delivery to {destination_label}",
            metadata=self.build_outbound_attempt_metadata(payload),
        )

    def handle_outbound_propagation_fallback(self, payload: OutboundPayload) -> None:
        """Record that direct delivery exhausted and propagation fallback is in use."""

        self.persist_outbound_delivery_metadata(
            payload,
            state="queued",
            delivery_metadata={
                "delivery_mode": payload.delivery_mode,
                "local_propagation_fallback": payload.local_propagation_fallback,
                "propagation_node_hex": payload.propagation_node_hex,
            },
        )
        event_log = getattr(self._hub, "event_log", None)
        if event_log is None:
            return
        destination_label = (
            self._hub._lookup_identity_label(payload.destination_hex)
            if payload.destination_hex
            else "unknown"
        )
        if payload.local_propagation_fallback:
            message = f"Direct delivery exhausted; stored message for local propagation to {destination_label}"
        else:
            node_label = self.resolve_propagation_node_label(payload)
            message = (
                "Direct delivery exhausted; queued message for propagation to"
                f" {destination_label} via {node_label}"
            )
        event_log.add_event(
            "message_propagation_queued",
            message,
            metadata=self.build_outbound_attempt_metadata(payload),
        )

    def handle_outbound_attempt_started(self, payload: OutboundPayload) -> None:
        """Persist attempt counters when a queue worker starts delivery."""

        self.persist_outbound_delivery_metadata(
            payload,
            state="queued",
            delivery_metadata={
                "last_attempt_at": utc_now_rfc3339(),
                "retry_scheduled": False,
            },
        )

    def handle_outbound_payload_dropped(
        self,
        payload: OutboundPayload,
        reason: str,
    ) -> None:
        """Record queue backpressure drops as terminal failures."""

        self.persist_outbound_delivery_metadata(
            payload,
            state="failed",
            delivery_metadata={"drop_reason": reason, "acked": False},
        )
        event_log = getattr(self._hub, "event_log", None)
        if event_log is None:
            return
        event_log.add_event(
            "message_delivery_failed",
            "Outbound payload dropped before delivery",
            metadata=self.build_outbound_attempt_metadata(payload),
        )

    def select_best_propagation_node(self) -> PropagationNodeCandidate | None:
        """Return the current best remote propagation node and activate it."""

        registry = getattr(self._hub, "_propagation_node_registry", None)
        if registry is None:
            return None
        return registry.best_candidate()

    def resolve_propagation_node_label(self, payload: OutboundPayload) -> str:
        if payload.local_propagation_fallback:
            return self._hub._hub_sender_label()
        if payload.propagation_node_hex:
            return self._hub._lookup_identity_label(payload.propagation_node_hex)
        return "unknown"

    def augment_outbound_delivery_metadata(
        self,
        entry: dict[str, object],
        payload: OutboundPayload,
    ) -> dict[str, object]:
        augmented = dict(entry)
        delivery_metadata = self.delivery_metadata_snapshot(payload)
        augmented["DeliveryMetadata"] = delivery_metadata
        if payload.attempts > 0:
            augmented["direct_attempts"] = payload.attempts
        augmented["delivery_method"] = "direct"
        augmented["route_type"] = payload.route_type
        augmented["fanout_count"] = 1 if payload.route_type == "fanout" else 0
        augmented["targeted_recipient_count"] = 1 if payload.route_type == "targeted" else 0
        if payload.delivery_mode != "propagated":
            return augmented
        augmented["fallback_reason"] = "direct_delivery_failed"
        augmented["delivery_method"] = (
            "local_propagation_store"
            if payload.local_propagation_fallback
            else "propagated"
        )
        if payload.propagation_node_hex:
            augmented["propagation_node"] = payload.propagation_node_hex
        return augmented

    def build_outbound_attempt_metadata(
        self,
        payload: OutboundPayload,
    ) -> DeliveryTransition:
        timestamp = _utcnow().isoformat()
        topic_id = normalize_topic_id(payload.topic_id or self._hub._extract_target_topic(payload.fields))
        scope = "topic" if topic_id else "dm"
        if payload.route_type == "broadcast":
            scope = "broadcast"
        entry: DeliveryTransition = {
            "MessageID": payload.message_id or payload.chat_message_id,
            "Direction": "outbound",
            "Scope": scope,
            "State": "queued",
            "Content": payload.message_text,
            "Source": self._hub._origin_rch_hex() or self._hub._hub_sender_label(),
            "Destination": payload.destination_hex,
            "TopicID": topic_id,
            "SourceHash": self._hub._origin_rch_hex(),
            "SourceLabel": self._hub._hub_sender_label(),
            "Timestamp": timestamp,
        }
        return self.augment_outbound_delivery_metadata(entry, payload)

    def update_outbound_chat_state(
        self,
        *,
        message: LXMF.LXMessage,
        payload: OutboundPayload,
        state: str,
        destination: str | None,
    ) -> DeliveryTransition:
        timestamp = _utcnow()
        source_hash = self._hub._origin_rch_hex()
        source_label = self._hub._hub_sender_label()
        topic_id = normalize_topic_id(
            payload.topic_id or self._hub._extract_target_topic(getattr(message, "fields", None))
        )
        chat_message_id = payload.chat_message_id or payload.message_id
        api = getattr(self._hub, "api", None)
        delivery_metadata = self.delivery_metadata_snapshot(payload)
        delivery_metadata["acked"] = state in {"delivered", "propagated"}

        if api is not None and chat_message_id and hasattr(api, "update_chat_message_state"):
            try:
                updated = api.update_chat_message_state(
                    chat_message_id,
                    state,
                    delivery_metadata=delivery_metadata,
                )
            except Exception as exc:  # pragma: no cover - defensive log
                RNS.log(
                    f"Failed to update chat message state for '{chat_message_id}': {exc}",
                    getattr(RNS, "LOG_WARNING", 2),
                )
            else:
                if updated is not None:
                    entry = updated.to_dict()
                    entry["SourceHash"] = source_hash
                    entry["SourceLabel"] = source_label
                    entry["Timestamp"] = timestamp.isoformat()
                    self._hub._notify_message_listeners(entry)
                    return entry

        scope = "topic" if topic_id else "dm"
        if payload.route_type == "broadcast":
            scope = "broadcast"
        return {
            "MessageID": chat_message_id or self._hub._message_id_hex(message),
            "Direction": "outbound",
            "Scope": scope,
            "State": state,
            "Content": payload.message_text,
            "Source": source_hash or source_label,
            "Destination": destination,
            "TopicID": topic_id,
            "SourceHash": source_hash,
            "SourceLabel": source_label,
            "Timestamp": timestamp.isoformat(),
            "DeliveryMetadata": delivery_metadata,
        }

    def persist_outbound_delivery_metadata(
        self,
        payload: OutboundPayload,
        *,
        state: str,
        delivery_metadata: dict[str, object] | None = None,
    ) -> None:
        api = getattr(self._hub, "api", None)
        message_id = payload.chat_message_id or payload.message_id
        if api is None or not message_id or not hasattr(api, "update_chat_message_state"):
            return
        merged_metadata = self.delivery_metadata_snapshot(payload)
        if delivery_metadata:
            merged_metadata.update(delivery_metadata)
        try:
            updated = api.update_chat_message_state(
                message_id,
                state,
                delivery_metadata=merged_metadata,
            )
        except Exception as exc:  # pragma: no cover - defensive log
            RNS.log(
                f"Failed to persist outbound delivery metadata for '{message_id}': {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return
        if updated is not None:
            entry = updated.to_dict()
            entry["SourceHash"] = self._hub._origin_rch_hex()
            entry["SourceLabel"] = self._hub._hub_sender_label()
            entry["Timestamp"] = _utcnow().isoformat()
            self._hub._notify_message_listeners(entry)

    def delivery_metadata_snapshot(self, payload: OutboundPayload) -> dict[str, object]:
        envelope = extract_delivery_envelope(payload.fields)
        validated = None
        if envelope is not None:
            try:
                validated = validate_delivery_envelope(envelope)
            except DeliveryContractError:
                validated = None
        metadata: dict[str, object] = {
            "message_id": payload.message_id or payload.chat_message_id,
            "route_type": payload.route_type,
            "topic_id": payload.topic_id,
            "attempts": payload.attempts,
            "delivery_mode": payload.delivery_mode,
            "enqueue_age_ms": round((time.monotonic() - payload.enqueued_at) * 1000, 3),
            "propagation_node_hex": payload.propagation_node_hex,
            "local_propagation_fallback": payload.local_propagation_fallback,
            "destination": payload.destination_hex,
            "fanout_count": 1 if payload.route_type == "fanout" else 0,
            "targeted_recipient_count": 1 if payload.route_type == "targeted" else 0,
            "acked": False,
        }
        if validated is not None:
            metadata.update(
                {
                    "content_type": validated.content_type,
                    "schema_version": validated.schema_version,
                    "ttl_seconds": validated.ttl_seconds,
                    "priority": validated.priority,
                    "sender": validated.sender,
                    "born_at_ms": validated.born_at_ms,
                    "created_at": validated.created_at,
                }
            )
        return metadata
