"""Northbound dispatch path for outbound message routing."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone

from typing import Any

import LXMF
import RNS

from reticulum_telemetry_hub.api.models import ChatMessage
from reticulum_telemetry_hub.api.service import FileAttachment
from reticulum_telemetry_hub.message_delivery import DEFAULT_PRIORITY
from reticulum_telemetry_hub.message_delivery import DEFAULT_TTL_SECONDS
from reticulum_telemetry_hub.message_delivery import attach_delivery_envelope
from reticulum_telemetry_hub.message_delivery import build_delivery_envelope
from reticulum_telemetry_hub.message_delivery import classify_delivery_mode
from reticulum_telemetry_hub.message_delivery import normalize_hash
from reticulum_telemetry_hub.message_delivery import normalize_topic_id
from reticulum_telemetry_hub.message_delivery import utc_now_ms
from reticulum_telemetry_hub.message_delivery import utc_now_rfc3339
from reticulum_telemetry_hub.reticulum_server.runtime_events import report_nonfatal_exception


def _utcnow() -> datetime:
    """Return a UTC timestamp for persisted chat event records."""

    return datetime.now(timezone.utc)


class NorthboundDispatchMixin:
    """Provide northbound-originated dispatch behavior for message routers."""

    _hub: Any

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
                attachments = [
                    item for item in raw_attachments if isinstance(item, FileAttachment)
                ]
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
        send_message_fn = getattr(self._hub, "send_message", self.send_message)
        enqueued = send_message_fn(
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
