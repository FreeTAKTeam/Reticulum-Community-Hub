"""Outbound message routing and fan-out orchestration."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
import time
from typing import Any

import LXMF
import RNS

from reticulum_telemetry_hub.api.models import ChatMessage
from reticulum_telemetry_hub.api.service import FileAttachment
from reticulum_telemetry_hub.message_delivery import DEFAULT_PRIORITY
from reticulum_telemetry_hub.message_delivery import DEFAULT_TTL_SECONDS
from reticulum_telemetry_hub.message_delivery import DeliveryContractError
from reticulum_telemetry_hub.message_delivery import attach_delivery_envelope
from reticulum_telemetry_hub.message_delivery import build_delivery_envelope
from reticulum_telemetry_hub.message_delivery import classify_delivery_mode
from reticulum_telemetry_hub.message_delivery import extract_delivery_envelope
from reticulum_telemetry_hub.message_delivery import normalize_hash
from reticulum_telemetry_hub.message_delivery import normalize_message_id
from reticulum_telemetry_hub.message_delivery import normalize_topic_id
from reticulum_telemetry_hub.message_delivery import utc_now_ms
from reticulum_telemetry_hub.message_delivery import utc_now_rfc3339
from reticulum_telemetry_hub.message_delivery import validate_delivery_envelope
from reticulum_telemetry_hub.reticulum_server.outbound_queue import OutboundPayload
from reticulum_telemetry_hub.reticulum_server.runtime_events import report_nonfatal_exception


def _utcnow() -> datetime:
    """Return a UTC timestamp for persisted chat event records."""

    return datetime.now(timezone.utc)



class MessageRouter:
    """Handles outbound routing decisions and payload fan-out."""

    def __init__(self, hub: Any) -> None:
        self._hub = hub

    def send_message(
        self,
        message: str,
        *,
        topic: str | None = None,
        destination: str | None = None,
        exclude: set[str] | None = None,
        fields: dict | None = None,
        sender: RNS.Destination | None = None,
        chat_message_id: str | None = None,
    ) -> bool:
        """Send a message to eligible recipients through the outbound queue."""

        queue = self._hub._ensure_outbound_queue()
        if queue is None:
            RNS.log(
                "Outbound queue unavailable; dropping message broadcast request.",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return False

        try:
            route_type = classify_delivery_mode(topic_id=topic, destination=destination)
        except DeliveryContractError as exc:
            RNS.log(
                f"Rejected outbound message with mixed routing semantics: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return False

        normalized_destination = normalize_hash(destination)
        normalized_topic_id = normalize_topic_id(topic)
        message_id = self.delivery_message_id(fields, chat_message_id=chat_message_id)
        shared_fields = self.prepare_outbound_delivery_fields(
            fields=fields,
            topic_id=normalized_topic_id,
            message_id=message_id,
        )
        payloads, metrics = self.build_outbound_payloads(
            message=message,
            route_type=route_type,
            topic_id=normalized_topic_id,
            destination=normalized_destination,
            exclude=exclude,
            fields=shared_fields,
            sender=sender,
            chat_message_id=chat_message_id,
            message_id=message_id,
        )
        enqueue_started = time.perf_counter()
        enqueue_results = queue.queue_messages(payloads)
        enqueued_count = sum(1 for enqueued in enqueue_results if enqueued)
        for payload, enqueued in zip(payloads, enqueue_results):
            if not enqueued:
                RNS.log(
                    (
                        "Failed to enqueue outbound LXMF message for"
                        f" {payload.destination_hex or 'unknown destination'}"
                    ),
                    getattr(RNS, "LOG_WARNING", 2),
                )
        enqueue_duration_ms = round((time.perf_counter() - enqueue_started) * 1000, 3)
        queue_stats = queue.stats()
        enqueued_any = enqueued_count > 0
        self.record_outbound_route_metrics(
            message_id=message_id,
            route_type=route_type,
            fanout_count=enqueued_count if route_type == "fanout" else 0,
            targeted_recipient_count=enqueued_count if route_type == "targeted" else 0,
            eligible_recipient_count=metrics["eligible_recipient_count"],
            selected_recipient_count=metrics["selected_recipient_count"],
            dropped_by_fanout_cap=metrics["dropped_by_fanout_cap"],
            deferred_by_fanout_cap=metrics["deferred_by_fanout_cap"],
            drop_reason=None if enqueued_any else "no_recipients",
            enqueue_duration_ms=enqueue_duration_ms,
            queue_depth=queue_stats["queue_depth"],
            active_sends=queue_stats["active_dispatches"],
            pending_receipts=queue_stats["pending_receipts"],
        )
        return enqueued_any

    def dispatch_northbound_message(
        self,
        message: str,
        topic_id: str | None = None,
        destination: str | None = None,
        fields: dict | None = None,
    ) -> ChatMessage | None:
        """Dispatch a message originating from the northbound interface."""

        api = getattr(self._hub, "api", None)
        normalized_topic_id = normalize_topic_id(topic_id)
        normalized_destination = normalize_hash(destination)
        route_type = classify_delivery_mode(
            topic_id=normalized_topic_id,
            destination=normalized_destination,
        )
        attachments: list[FileAttachment] = []
        scope = "broadcast"
        if route_type == "targeted":
            scope = "dm"
        elif route_type == "fanout":
            scope = "topic"
        if isinstance(fields, dict):
            raw_attachments = fields.get("attachments")
            if isinstance(raw_attachments, list):
                attachments = [item for item in raw_attachments if isinstance(item, FileAttachment)]
            override_scope = fields.get("scope")
            if isinstance(override_scope, str) and override_scope.strip():
                scope = override_scope.strip()
        outbound_message = message
        if normalized_topic_id and message:
            topic_path = self._hub._resolve_topic_path(normalized_topic_id)
            if self._hub._has_sender_prefix(message):
                outbound_message = f"{topic_path}: {message}"
            else:
                outbound_message = self._hub._format_chat_broadcast_text(
                    source_label=self._hub._hub_sender_label(),
                    content_text=message,
                    topic_id=normalized_topic_id,
                )
        sender_hash = self._hub._origin_rch_hex() or "hub"
        envelope = build_delivery_envelope(
            sender=sender_hash,
            message_id=None,
            topic_id=normalized_topic_id,
            content_type="text/plain; schema=lxmf.chat.v1",
            ttl_seconds=DEFAULT_TTL_SECONDS,
            priority=DEFAULT_PRIORITY,
            born_at_ms=utc_now_ms(),
            created_at=utc_now_rfc3339(),
        )
        queued = None
        now = _utcnow()
        if api is not None:
            queued = api.record_chat_message(
                ChatMessage(
                    direction="outbound",
                    scope=scope,
                    state="queued",
                    content=outbound_message,
                    source=None,
                    destination=normalized_destination,
                    topic_id=normalized_topic_id,
                    attachments=[api.chat_attachment_from_file(item) for item in attachments],
                    delivery_metadata={
                        "message_id": envelope.message_id,
                        "route_type": route_type,
                        "content_type": envelope.content_type,
                        "schema_version": envelope.schema_version,
                        "ttl_seconds": envelope.ttl_seconds,
                        "priority": envelope.priority,
                        "sender": envelope.sender,
                        "born_at_ms": envelope.born_at_ms,
                        "created_at": envelope.created_at,
                        "attempts": 0,
                        "acked": False,
                        "fanout_count": 0,
                        "targeted_recipient_count": 0,
                        "drop_reason": None,
                    },
                    created_at=now,
                    updated_at=now,
                    message_id=envelope.message_id,
                )
            )
            self._hub._notify_message_listeners(queued.to_dict())
            if getattr(self._hub, "event_log", None) is not None:
                self._hub.event_log.add_event(
                    "message_queued",
                    "Message queued for delivery",
                    metadata=queued.to_dict(),
                )
        lxmf_fields = None
        if attachments:
            try:
                lxmf_fields = self._hub._build_lxmf_attachment_fields(attachments)
            except Exception as exc:  # pragma: no cover - defensive log
                report_nonfatal_exception(
                    getattr(self._hub, "event_log", None),
                    "lxmf_runtime_error",
                    f"Failed to build attachment fields: {exc}",
                    exc,
                    metadata={
                        "operation": "build_attachment_fields",
                        "attachment_count": len(attachments),
                    },
                    log_level=getattr(RNS, "LOG_WARNING", 2),
                )
        lxmf_fields = self._hub._merge_standard_fields(
            source_fields=fields,
            extra_fields=lxmf_fields,
        )
        if lxmf_fields is None:
            lxmf_fields = {}
        lxmf_fields = attach_delivery_envelope(lxmf_fields, envelope)
        if LXMF.FIELD_EVENT not in lxmf_fields:
            lxmf_fields[LXMF.FIELD_EVENT] = self._hub._build_event_field(
                event_type="rch.message.outbound",
                direction="outbound",
                topic_id=normalized_topic_id,
                destination=normalized_destination,
            )
        enqueued = self.send_message(
            outbound_message,
            topic=normalized_topic_id,
            destination=normalized_destination,
            fields=lxmf_fields,
            chat_message_id=queued.message_id if queued is not None else envelope.message_id,
        )
        if api is not None and queued is not None and not enqueued:
            updated = api.update_chat_message_state(
                queued.message_id or "",
                "failed",
                delivery_metadata={
                    "drop_reason": "no_recipients",
                    "acked": False,
                    "fanout_count": 0,
                    "targeted_recipient_count": 0,
                },
            )
            if updated is not None:
                self._hub._notify_message_listeners(updated.to_dict())
                if getattr(self._hub, "event_log", None) is not None:
                    self._hub.event_log.add_event(
                        "message_failed",
                        "Message failed",
                        metadata=updated.to_dict(),
                    )
                return updated
            return queued
        return queued

    def delivery_message_id(
        self,
        fields: dict | None,
        *,
        chat_message_id: str | None,
    ) -> str:
        """Return the outbound Message-ID for a queued payload."""

        envelope = extract_delivery_envelope(fields)
        if envelope is not None:
            try:
                validated = validate_delivery_envelope(envelope)
            except DeliveryContractError:
                pass
            else:
                return validated.message_id
        return normalize_message_id(chat_message_id)

    def record_outbound_route_metrics(
        self,
        *,
        message_id: str,
        route_type: str,
        fanout_count: int,
        targeted_recipient_count: int,
        eligible_recipient_count: int,
        selected_recipient_count: int,
        dropped_by_fanout_cap: int,
        deferred_by_fanout_cap: int,
        drop_reason: str | None,
        enqueue_duration_ms: float,
        queue_depth: int,
        active_sends: int,
        pending_receipts: int,
    ) -> None:
        """Emit event-log metrics for routing selection outcomes."""

        event_log = getattr(self._hub, "event_log", None)
        if event_log is None:
            return
        event_log.add_event(
            "message_routed",
            "Outbound message routing selected",
            metadata={
                "MessageID": message_id,
                "route_type": route_type,
                "fanout_count": fanout_count,
                "targeted_recipient_count": targeted_recipient_count,
                "eligible_recipient_count": eligible_recipient_count,
                "selected_recipient_count": selected_recipient_count,
                "dropped_by_fanout_cap": dropped_by_fanout_cap,
                "deferred_by_fanout_cap": deferred_by_fanout_cap,
                "enqueue_duration_ms": enqueue_duration_ms,
                "queue_depth": queue_depth,
                "active_sends": active_sends,
                "pending_receipts": pending_receipts,
                "drop_reason": drop_reason,
            },
        )

    def prepare_outbound_delivery_fields(
        self,
        *,
        fields: dict | None,
        topic_id: str | None,
        message_id: str,
    ) -> dict | None:
        normalized_fields = dict(fields) if isinstance(fields, dict) else {}
        envelope = extract_delivery_envelope(normalized_fields)
        if envelope is None:
            outbound_envelope = build_delivery_envelope(
                sender=self._hub._origin_rch_hex() or "hub",
                message_id=message_id,
                topic_id=topic_id,
                content_type="text/plain; schema=lxmf.chat.v1",
                ttl_seconds=DEFAULT_TTL_SECONDS,
                priority=DEFAULT_PRIORITY,
                born_at_ms=utc_now_ms(),
                created_at=utc_now_rfc3339(),
            )
            return attach_delivery_envelope(normalized_fields, outbound_envelope)
        try:
            validate_delivery_envelope(envelope)
        except DeliveryContractError:
            return normalized_fields
        return normalized_fields

    def build_outbound_payloads(
        self,
        *,
        message: str,
        route_type: str,
        topic_id: str | None,
        destination: str | None,
        exclude: set[str] | None,
        fields: dict | None,
        sender: RNS.Destination | None,
        chat_message_id: str | None,
        message_id: str,
    ) -> tuple[list[OutboundPayload], dict[str, int]]:
        available = (
            list(self._hub.connections.values())
            if hasattr(self._hub.connections, "values")
            else list(self._hub.connections)
        )
        excluded = {value.lower() for value in exclude if value} if exclude else set()
        subscribers = self._hub._subscribers_for_topic(topic_id) if topic_id is not None else None
        recipients: list[tuple[RNS.Destination, str | None, bytes | None]] = []
        for connection in available:
            connection_hex = self._hub._connection_hex(connection)
            if destination and connection_hex != destination:
                continue
            if excluded and connection_hex and connection_hex in excluded:
                continue
            if subscribers is not None and connection_hex not in subscribers:
                continue
            identity = getattr(connection, "identity", None)
            destination_hash = getattr(identity, "hash", None)
            recipients.append(
                (
                    connection,
                    connection_hex,
                    destination_hash if isinstance(destination_hash, (bytes, bytearray)) else None,
                )
            )

        eligible_recipient_count = len(recipients)
        deferred_by_fanout_cap = 0
        fanout_soft_max = int(getattr(self._hub, "outbound_fanout_soft_max_recipients", 0))
        if route_type == "fanout" and fanout_soft_max > 0 and eligible_recipient_count > fanout_soft_max:
            deferred_by_fanout_cap = eligible_recipient_count - fanout_soft_max
            self.record_fanout_backpressure_warning(
                message_id=message_id,
                topic_id=topic_id,
                selected_count=fanout_soft_max,
                deferred_count=deferred_by_fanout_cap,
            )

        stagger_step_seconds = max(float(getattr(self._hub, "outbound_backoff", 0.5)), 0.05)
        payloads: list[OutboundPayload] = []
        for index, (connection, connection_hex, destination_hash) in enumerate(recipients):
            payload = OutboundPayload(
                connection=connection,
                message_text=message,
                destination_hash=destination_hash,
                destination_hex=connection_hex,
                fields=fields,
                sender=sender or self._hub.my_lxmf_dest,
                chat_message_id=chat_message_id,
                message_id=message_id,
                topic_id=topic_id,
                route_type=route_type,
            )
            if (
                route_type == "fanout"
                and fanout_soft_max > 0
                and eligible_recipient_count > fanout_soft_max
                and index >= fanout_soft_max
            ):
                batch_index = index // fanout_soft_max
                payload.next_attempt_at = time.monotonic() + (batch_index * stagger_step_seconds)
            payloads.append(payload)
        return payloads, {
            "eligible_recipient_count": eligible_recipient_count,
            "selected_recipient_count": len(payloads),
            "dropped_by_fanout_cap": 0,
            "deferred_by_fanout_cap": deferred_by_fanout_cap,
        }

    def record_fanout_backpressure_warning(
        self,
        *,
        message_id: str,
        topic_id: str | None,
        selected_count: int,
        deferred_count: int,
    ) -> None:
        RNS.log(
            (
                "Outbound fan-out soft cap exceeded; sending to"
                f" {selected_count} recipients this tick and deferring {deferred_count}."
            ),
            getattr(RNS, "LOG_WARNING", 2),
        )
        event_log = getattr(self._hub, "event_log", None)
        if event_log is None:
            return
        event_log.add_event(
            "message_fanout_capped",
            "Outbound fan-out exceeded soft cap",
            metadata={
                "MessageID": message_id,
                "topic_id": topic_id,
                "selected_recipient_count": selected_count,
                "deferred_recipient_count": deferred_count,
                "fanout_soft_max_recipients": int(
                    getattr(self._hub, "outbound_fanout_soft_max_recipients", 0)
                ),
            },
        )
