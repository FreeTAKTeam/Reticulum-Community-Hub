"""Northbound dispatch and outbound metadata helpers."""
# ruff: noqa: F403,F405

from __future__ import annotations

import threading
import time

import LXMF

from reticulum_telemetry_hub.api.models import ChatMessage
import reticulum_telemetry_hub.lxmf_runtime  # noqa: F401
from reticulum_telemetry_hub.config.constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.announce_capabilities import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.delivery_defaults import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.outbound_queue import OutboundPayload
from reticulum_telemetry_hub.reticulum_server.propagation_selection import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_support import *  # noqa: F403


class RuntimeOutboundMixin:
    """Northbound dispatch and outbound metadata helpers."""

    def dispatch_northbound_message(
        self,
        message: str,
        topic_id: str | None = None,
        destination: str | None = None,
        fields: dict | None = None,
    ) -> ChatMessage | None:
        """Dispatch a message originating from the northbound interface."""

        return self._message_router_service().dispatch_northbound_message(
            message,
            topic_id=topic_id,
            destination=destination,
            fields=fields,
        )


    def _handle_outbound_delivery_receipt(
        self,
        message: LXMF.LXMessage,
        payload: OutboundPayload,
    ) -> None:
        """Persist and broadcast outbound delivery acknowledgements."""

        self._delivery_service().handle_outbound_delivery_receipt(message, payload)


    def _handle_outbound_delivery_failure(
        self,
        message: LXMF.LXMessage,
        payload: OutboundPayload,
    ) -> None:
        """Persist and broadcast outbound delivery failures."""

        self._delivery_service().handle_outbound_delivery_failure(message, payload)


    def _augment_outbound_delivery_metadata(
        self,
        entry: dict[str, object],
        payload: OutboundPayload,
    ) -> dict[str, object]:
        """Add retry and propagation metadata to outbound event entries."""

        return self._delivery_service().augment_outbound_delivery_metadata(entry, payload)


    def _build_outbound_attempt_metadata(
        self,
        payload: OutboundPayload,
    ) -> dict[str, object]:
        """Build event metadata for retry and fallback transitions."""

        return self._delivery_service().build_outbound_attempt_metadata(payload)


    def _resolve_propagation_node_label(self, payload: OutboundPayload) -> str:
        """Return the most useful label for the selected propagation node."""

        return self._delivery_service().resolve_propagation_node_label(payload)


    def _select_best_propagation_node(self) -> PropagationNodeCandidate | None:
        """Return the current best remote propagation node and activate it."""

        return self._delivery_service().select_best_propagation_node()


    def _should_emit_outbound_transition_event(
        self,
        event_type: str,
        payload: OutboundPayload,
    ) -> bool:
        """Return whether an outbound transition event should be emitted now."""

        if not hasattr(self, "_outbound_transition_log_lock"):
            self._outbound_transition_log_lock = threading.Lock()
        if not hasattr(self, "_outbound_transition_log_last_emitted"):
            self._outbound_transition_log_last_emitted = {}
        if not hasattr(self, "_outbound_transition_log_window_seconds"):
            self._outbound_transition_log_window_seconds = 1.0

        message_id = payload.chat_message_id or payload.message_id or "unknown"
        destination = payload.destination_hex or "unknown"
        key = f"{event_type}:{message_id}:{destination}"
        now = time.monotonic()
        with self._outbound_transition_log_lock:
            last_emitted_at = self._outbound_transition_log_last_emitted.get(key, 0.0)
            if now - last_emitted_at < self._outbound_transition_log_window_seconds:
                return False
            self._outbound_transition_log_last_emitted[key] = now
        return True

    def _handle_outbound_retry_scheduled(self, payload: OutboundPayload) -> None:
        """Record a direct-delivery retry event."""

        self._delivery_service().handle_outbound_retry_scheduled(payload)

    def _handle_outbound_direct_failure(self, payload: OutboundPayload, reason: str) -> None:
        """Track direct-delivery cooldown state after a failed attempt."""

        self._delivery_service().handle_outbound_direct_failure(payload, reason)


    def _handle_outbound_propagation_fallback(self, payload: OutboundPayload) -> None:
        """Record that direct delivery exhausted and propagation fallback is in use."""

        self._delivery_service().handle_outbound_propagation_fallback(payload)


    def _update_outbound_chat_state(
        self,
        *,
        message: LXMF.LXMessage,
        payload: OutboundPayload,
        state: str,
        destination: str | None,
    ) -> dict[str, object]:
        """Return metadata for outbound delivery state transitions."""

        return self._delivery_service().update_outbound_chat_state(
            message=message,
            payload=payload,
            state=state,
            destination=destination,
        )


    def _handle_outbound_attempt_started(self, payload: OutboundPayload) -> None:
        """Mark attempt activity in runtime metrics without DB churn."""

        self._delivery_service().handle_outbound_attempt_started(payload)


    def _handle_outbound_payload_dropped(
        self,
        payload: OutboundPayload,
        reason: str,
    ) -> None:
        """Record queue backpressure drops as terminal failures."""

        self._delivery_service().handle_outbound_payload_dropped(payload, reason)


    def _persist_outbound_delivery_metadata(
        self,
        payload: OutboundPayload,
        *,
        state: str,
        delivery_metadata: dict[str, object] | None = None,
    ) -> None:
        """Persist the latest outbound delivery metadata when chat storage exists."""

        self._delivery_service().persist_outbound_delivery_metadata(
            payload,
            state=state,
            delivery_metadata=delivery_metadata,
        )

    def _mark_presence_evidence(self, identity: str | None) -> None:
        """Record fresh presence evidence for outbound delivery policy decisions."""

        policy = getattr(self, "outbound_delivery_policy", None)
        if policy is None:
            return
        policy.mark_presence(identity)


    def _delivery_metadata_snapshot(self, payload: OutboundPayload) -> dict[str, object]:
        """Return a serializable snapshot of outbound delivery state."""

        return self._delivery_service().delivery_metadata_snapshot(payload)


    def _delivery_message_id(
        self,
        fields: dict | None,
        *,
        chat_message_id: str | None,
    ) -> str:
        """Return the outbound Message-ID for a queued payload."""

        return self._message_router_service().delivery_message_id(
            fields,
            chat_message_id=chat_message_id,
        )


    def _record_outbound_route_metrics(
        self,
        *,
        message_id: str,
        route_type: str,
        fanout_count: int,
        targeted_recipient_count: int,
        eligible_recipient_count: int,
        selected_recipient_count: int,
        selected_direct_recipient_count: int,
        selected_propagated_recipient_count: int,
        delivery_policy_reason_counts: dict[str, int],
        dropped_by_fanout_cap: int,
        deferred_by_fanout_cap: int,
        drop_reason: str | None,
        enqueue_duration_ms: float,
        queue_depth: int,
        active_sends: int,
        pending_receipts: int,
    ) -> None:
        """Emit event-log metrics for routing selection outcomes."""

        self._message_router_service().record_outbound_route_metrics(
            message_id=message_id,
            route_type=route_type,
            fanout_count=fanout_count,
            targeted_recipient_count=targeted_recipient_count,
            eligible_recipient_count=eligible_recipient_count,
            selected_recipient_count=selected_recipient_count,
            selected_direct_recipient_count=selected_direct_recipient_count,
            selected_propagated_recipient_count=selected_propagated_recipient_count,
            delivery_policy_reason_counts=delivery_policy_reason_counts,
            dropped_by_fanout_cap=dropped_by_fanout_cap,
            deferred_by_fanout_cap=deferred_by_fanout_cap,
            drop_reason=drop_reason,
            enqueue_duration_ms=enqueue_duration_ms,
            queue_depth=queue_depth,
            active_sends=active_sends,
            pending_receipts=pending_receipts,
        )


