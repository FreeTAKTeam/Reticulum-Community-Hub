"""Outbound send and fanout helpers."""
# ruff: noqa: F403,F405

from __future__ import annotations

import time

import RNS

from reticulum_telemetry_hub.message_delivery import normalize_hash
import reticulum_telemetry_hub.lxmf_runtime  # noqa: F401
from reticulum_telemetry_hub.config.constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.announce_capabilities import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.delivery_defaults import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.outbound_queue import OutboundPayload
from reticulum_telemetry_hub.reticulum_server.propagation_selection import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_support import *  # noqa: F403


class RuntimeSendMixin:
    """Outbound send and fanout helpers."""

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
        """Sends a message to connected clients."""

        return self._message_router_service().send_message(
            message,
            topic=topic,
            destination=destination,
            exclude=exclude,
            fields=fields,
            sender=sender,
            chat_message_id=chat_message_id,
        )


    def send_many(
        self,
        message: str,
        destinations: list[str],
        *,
        fields: dict | None = None,
        sender: RNS.Destination | None = None,
        chat_message_id: str | None = None,
    ) -> bool:
        """Send one payload body to many explicit destination identities."""

        queue = self._ensure_outbound_queue()
        if queue is None:
            return False
        unique_destinations = [
            value
            for value in dict.fromkeys(
                normalize_hash(identity) for identity in destinations if identity
            )
            if value
        ]
        if not unique_destinations:
            return False
        scanned = 0
        resolved: list[tuple[RNS.Destination, str, bytes | None]] = []
        for identity in unique_destinations:
            scanned += 1
            connection = self._cached_destination(identity)
            if connection is None:
                self._ensure_reachable_identity_destination(identity)
                connection = self._cached_destination(identity)
            if connection is None:
                continue
            destination_hash = getattr(connection, "hash", None)
            if not isinstance(destination_hash, (bytes, bytearray)):
                identity_obj = getattr(connection, "identity", None)
                destination_hash = getattr(identity_obj, "hash", None)
            resolved.append(
                (
                    connection,
                    identity,
                    destination_hash if isinstance(destination_hash, (bytes, bytearray)) else None,
                )
            )
        if not resolved:
            return False

        message_id = self._delivery_message_id(fields, chat_message_id=chat_message_id)
        shared_fields = self._prepare_outbound_delivery_fields(
            fields=fields,
            topic_id=None,
            message_id=message_id,
        )
        payloads = [
            OutboundPayload(
                connection=connection,
                message_text=message,
                destination_hash=destination_hash,
                destination_hex=identity_hex,
                fields=shared_fields,
                sender=sender or self.my_lxmf_dest,
                chat_message_id=chat_message_id,
                message_id=message_id,
                topic_id=None,
                route_type="fanout",
                delivery_mode=(
                    getattr(self, "outbound_delivery_policy", None).delivery_decision(
                        "fanout",
                        identity_hex,
                    )[0]
                    if getattr(self, "outbound_delivery_policy", None) is not None
                    else "direct"
                ),
                delivery_policy_reason=(
                    getattr(self, "outbound_delivery_policy", None).delivery_decision(
                        "fanout",
                        identity_hex,
                    )[1]
                    if getattr(self, "outbound_delivery_policy", None) is not None
                    else "default_direct"
                ),
            )
            for connection, identity_hex, destination_hash in resolved
        ]
        selected_direct_recipient_count = sum(
            1 for payload in payloads if payload.delivery_mode != "propagated"
        )
        selected_propagated_recipient_count = len(payloads) - selected_direct_recipient_count
        delivery_policy_reason_counts: dict[str, int] = {}
        for payload in payloads:
            reason = payload.delivery_policy_reason or "default_direct"
            delivery_policy_reason_counts[reason] = (
                delivery_policy_reason_counts.get(reason, 0) + 1
            )
        enqueue_started = time.perf_counter()
        enqueue_results = queue.queue_messages(payloads)
        enqueue_duration_ms = round((time.perf_counter() - enqueue_started) * 1000, 3)
        enqueued_count = sum(1 for value in enqueue_results if value)
        queue_stats = queue.stats()
        metrics = self._runtime_metrics_store()
        metrics.increment("fanout_recipients_scanned_total", scanned)
        metrics.increment("fanout_recipients_resolved_total", len(resolved))
        self._record_outbound_route_metrics(
            message_id=message_id,
            route_type="fanout",
            fanout_count=enqueued_count,
            targeted_recipient_count=0,
            eligible_recipient_count=len(resolved),
            selected_recipient_count=len(resolved),
            selected_direct_recipient_count=selected_direct_recipient_count,
            selected_propagated_recipient_count=selected_propagated_recipient_count,
            delivery_policy_reason_counts=delivery_policy_reason_counts,
            dropped_by_fanout_cap=max(len(resolved) - enqueued_count, 0),
            deferred_by_fanout_cap=0,
            drop_reason=None if enqueued_count > 0 else "no_recipients",
            enqueue_duration_ms=enqueue_duration_ms,
            queue_depth=queue_stats["queue_depth"],
            active_sends=queue_stats["active_dispatches"],
            pending_receipts=queue_stats["pending_receipts"],
        )
        return enqueued_count > 0

    def _prepare_outbound_delivery_fields(
        self,
        *,
        fields: dict | None,
        topic_id: str | None,
        message_id: str,
    ) -> dict | None:
        """Return shared outbound fields with a validated delivery envelope."""

        return self._message_router_service().prepare_outbound_delivery_fields(
            fields=fields,
            topic_id=topic_id,
            message_id=message_id,
        )


    def _build_outbound_payloads(
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
        """Build outbound payloads while precomputing fan-out metadata once."""

        return self._message_router_service().build_outbound_payloads(
            message=message,
            route_type=route_type,
            topic_id=topic_id,
            destination=destination,
            exclude=exclude,
            fields=fields,
            sender=sender,
            chat_message_id=chat_message_id,
            message_id=message_id,
        )


    def _record_fanout_backpressure_warning(
        self,
        *,
        message_id: str,
        topic_id: str | None,
        selected_count: int,
        deferred_count: int,
    ) -> None:
        """Emit an explicit warning when fan-out soft caps defer recipients."""

        self._message_router_service().record_fanout_backpressure_warning(
            message_id=message_id,
            topic_id=topic_id,
            selected_count=selected_count,
            deferred_count=deferred_count,
        )


