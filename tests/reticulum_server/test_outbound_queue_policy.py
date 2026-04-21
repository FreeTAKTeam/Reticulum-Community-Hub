from __future__ import annotations

import time

from reticulum_telemetry_hub.reticulum_server.outbound_queue import OutboundMessageQueue
from reticulum_telemetry_hub.reticulum_server.outbound_queue import OutboundPayload
from reticulum_telemetry_hub.reticulum_server.propagation_selection import (
    PropagationNodeCandidate,
)


class _RouterStub:
    def __init__(self) -> None:
        self.propagation_node = False
        self.active_propagation_nodes: list[bytes] = []

    def set_active_propagation_node(self, destination_hash: bytes) -> None:
        self.active_propagation_nodes.append(destination_hash)


def _make_payload() -> OutboundPayload:
    return OutboundPayload(
        connection=object(),
        message_text="payload",
        destination_hash=b"\x11" * 16,
        destination_hex=(b"\x11" * 16).hex(),
        sender=object(),
        chat_message_id="chat-queue",
        message_id="msg-queue",
        route_type="targeted",
        delivery_mode="direct",
    )


def test_direct_failure_with_one_attempt_immediately_falls_back_to_propagation() -> None:
    retry_events: list[str] = []
    direct_failures: list[str] = []
    propagation_events: list[str] = []
    router = _RouterStub()
    queue = OutboundMessageQueue(
        router,
        object(),
        max_attempts=1,
        retry_scheduled_callback=lambda payload: retry_events.append(payload.destination_hex or ""),
        direct_failure_callback=lambda payload, reason: direct_failures.append(reason),
        propagation_fallback_callback=lambda payload: propagation_events.append(payload.delivery_mode),
        propagation_selector=lambda: PropagationNodeCandidate(
            destination_hash=b"\x22" * 16,
            destination_hex=(b"\x22" * 16).hex(),
            hops=1,
            stamp_cost=None,
            transfer_limit=None,
            sync_limit=None,
            last_announced_at=1.0,
            propagation_enabled=True,
        ),
    )
    payload = _make_payload()

    queue._handle_delivery_attempt_failure(payload, reason="send_error")

    assert retry_events == []
    assert direct_failures == ["send_error"]
    assert propagation_events == ["propagated"]
    assert payload.attempts == 1
    assert payload.delivery_mode == "propagated"
    assert queue.stats()["retry_total"] == 0
    assert queue.stats()["propagation_fallback_total"] == 1


def test_send_timeout_marks_direct_failure_before_dispatch_finishes() -> None:
    """Ensure direct-send timeouts immediately enter delivery-policy cooldown."""

    direct_failures: list[str] = []
    router = _RouterStub()
    queue = OutboundMessageQueue(
        router,
        object(),
        send_timeout=0.1,
        direct_failure_callback=lambda payload, reason: direct_failures.append(reason),
    )
    payload = _make_payload()

    class _MessageStub:
        def register_delivery_callback(self, callback) -> None:  # noqa: ANN001
            self.delivery_callback = callback

        def register_failed_callback(self, callback) -> None:  # noqa: ANN001
            self.failed_callback = callback

    queue._build_message = lambda queued_payload: _MessageStub()  # type: ignore[method-assign]
    router.handle_outbound = lambda message: time.sleep(0.15)

    try:
        queue._send_with_timeout(payload)
        assert direct_failures == ["send_timeout"]
        time.sleep(0.16)
    finally:
        queue._send_executor.shutdown(wait=True, cancel_futures=True)  # type: ignore[attr-defined]
