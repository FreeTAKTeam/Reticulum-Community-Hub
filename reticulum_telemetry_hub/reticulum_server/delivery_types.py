"""Typed delivery service contracts."""

from __future__ import annotations

from typing import Protocol
from typing import TypedDict

from reticulum_telemetry_hub.reticulum_server.outbound_queue import OutboundPayload


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

    def handle_outbound_direct_failure(
        self, payload: OutboundPayload, reason: str
    ) -> None:
        """Observe direct-attempt failures before retry or fallback."""

    def handle_outbound_propagation_fallback(self, payload: OutboundPayload) -> None:
        """Observe propagation fallback transitions."""

    def handle_outbound_attempt_started(self, payload: OutboundPayload) -> None:
        """Observe attempt start transitions."""

    def handle_outbound_payload_dropped(
        self, payload: OutboundPayload, reason: str
    ) -> None:
        """Observe terminal queue drop transitions."""
