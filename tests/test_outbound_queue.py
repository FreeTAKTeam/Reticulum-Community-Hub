import time

import LXMF
import RNS

from reticulum_telemetry_hub.reticulum_server.outbound_queue import (
    OutboundMessageQueue,
)
from reticulum_telemetry_hub.reticulum_server.propagation_selection import (
    PropagationNodeCandidate,
)


def _make_destination(direction=RNS.Destination.OUT) -> RNS.Destination:
    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()
    return RNS.Destination(
        RNS.Identity(), direction, RNS.Destination.SINGLE, "lxmf", "delivery"
    )


def test_outbound_queue_applies_backpressure():
    sender = _make_destination(RNS.Destination.IN)
    recipient_one = _make_destination()
    recipient_two = _make_destination()
    delivered: list[RNS.Destination] = []

    class DummyRouter:
        def handle_outbound(self, message):
            delivered.append(message.destination_hash)

    queue = OutboundMessageQueue(
        DummyRouter(),
        sender,
        queue_size=1,
        worker_count=1,
        send_timeout=0.1,
        backoff_seconds=0.01,
        max_attempts=1,
    )

    try:
        queue.queue_message(
            recipient_one,
            "first",
            recipient_one.identity.hash,
            recipient_one.identity.hash.hex(),
            None,
        )
        queue.queue_message(
            recipient_two,
            "second",
            recipient_two.identity.hash,
            recipient_two.identity.hash.hex(),
            None,
        )
        queue.start()
        assert queue.wait_for_flush(timeout=1.0)
    finally:
        queue.stop()

    assert delivered == [recipient_two.identity.hash]


def test_outbound_queue_retries_after_failure():
    sender = _make_destination(RNS.Destination.IN)
    recipient = _make_destination()
    attempts: list[float] = []

    class FlakyRouter:
        def __init__(self) -> None:
            self._fail_next = True

        def handle_outbound(self, message):
            attempts.append(time.monotonic())
            if self._fail_next:
                self._fail_next = False
                raise RuntimeError("temporary outage")

    queue = OutboundMessageQueue(
        FlakyRouter(),
        sender,
        queue_size=2,
        worker_count=1,
        send_timeout=0.1,
        backoff_seconds=0.01,
        max_attempts=2,
    )

    try:
        queue.start()
        queue.queue_message(
            recipient,
            "retry-message",
            recipient.identity.hash,
            recipient.identity.hash.hex(),
            None,
        )
        assert queue.wait_for_flush(timeout=1.0)
    finally:
        queue.stop()

    assert len(attempts) == 2
    assert attempts[1] >= attempts[0]


def test_outbound_queue_handles_multi_destination_fan_out():
    sender = _make_destination(RNS.Destination.IN)
    recipient_one = _make_destination()
    recipient_two = _make_destination()
    delivered: list[bytes] = []

    class CollectingRouter:
        def handle_outbound(self, message):
            delivered.append(message.destination_hash)

    queue = OutboundMessageQueue(
        CollectingRouter(),
        sender,
        queue_size=4,
        worker_count=2,
        send_timeout=0.1,
        backoff_seconds=0.01,
        max_attempts=1,
    )

    try:
        queue.start()
        queue.queue_message(
            recipient_one,
            "alpha",
            recipient_one.identity.hash,
            recipient_one.identity.hash.hex(),
            None,
        )
        queue.queue_message(
            recipient_two,
            "beta",
            recipient_two.identity.hash,
            recipient_two.identity.hash.hex(),
            None,
        )
        assert queue.wait_for_flush(timeout=1.0)
    finally:
        queue.stop()

    assert set(delivered) == {
        recipient_one.identity.hash,
        recipient_two.identity.hash,
    }


def test_outbound_queue_reports_delivery_receipts():
    if RNS.Reticulum.get_instance() is None:
        RNS.Reticulum()

    sender = _make_destination(RNS.Destination.IN)
    recipient = _make_destination()
    receipts: list[tuple[str | None, str | None, int]] = []

    class ReceiptRouter:
        def handle_outbound(self, message):
            callback = getattr(message, "_LXMessage__delivery_callback", None)
            if callable(callback):
                message.state = LXMF.LXMessage.DELIVERED
                callback(message)

    queue = OutboundMessageQueue(
        ReceiptRouter(),
        sender,
        queue_size=2,
        worker_count=1,
        send_timeout=0.1,
        backoff_seconds=0.01,
        max_attempts=1,
        delivery_receipt_callback=lambda message, payload: receipts.append(
            (payload.chat_message_id, payload.destination_hex, message.state)
        ),
    )

    try:
        queue.start()
        queue.queue_message(
            recipient,
            "tracked-message",
            recipient.identity.hash,
            recipient.identity.hash.hex(),
            None,
            chat_message_id="chat-message-1",
        )
        assert queue.wait_for_flush(timeout=1.0)
    finally:
        queue.stop()

    assert receipts == [
        ("chat-message-1", recipient.identity.hash.hex(), LXMF.LXMessage.DELIVERED)
    ]


def test_outbound_queue_retries_failed_callbacks_before_terminal_failure():
    sender = _make_destination(RNS.Destination.IN)
    recipient = _make_destination()
    retries: list[int] = []
    failures: list[tuple[int, str | None]] = []

    class CallbackFailingRouter:
        propagation_node = False

        def __init__(self) -> None:
            self.calls = 0

        def handle_outbound(self, message):
            self.calls += 1
            callback = getattr(message, "failed_callback", None)
            if callable(callback):
                callback(message)

    router = CallbackFailingRouter()
    queue = OutboundMessageQueue(
        router,
        sender,
        queue_size=2,
        worker_count=1,
        send_timeout=0.1,
        backoff_seconds=0.01,
        max_attempts=2,
        retry_scheduled_callback=lambda payload: retries.append(payload.attempts),
        delivery_failure_callback=lambda message, payload: failures.append(
            (payload.attempts, payload.destination_hex)
        ),
    )

    try:
        queue.start()
        queue.queue_message(
            recipient,
            "retry-callback",
            recipient.identity.hash,
            recipient.identity.hash.hex(),
            None,
        )
        assert queue.wait_for_flush(timeout=1.0)
    finally:
        queue.stop()

    assert router.calls == 2
    assert retries == [1]
    assert failures == [(2, recipient.identity.hash.hex())]


def test_outbound_queue_falls_back_to_remote_propagation_after_retry_cutoff():
    sender = _make_destination(RNS.Destination.IN)
    recipient = _make_destination()
    receipts: list[tuple[int, str, str | None, int]] = []
    failures: list[str] = []
    fallbacks: list[tuple[str, str | None]] = []
    candidate = PropagationNodeCandidate(
        destination_hash=b"\xAA" * 16,
        destination_hex=(b"\xAA" * 16).hex(),
        hops=1,
        stamp_cost=2,
        transfer_limit=1024,
        sync_limit=2048,
        last_announced_at=time.time(),
        propagation_enabled=True,
    )

    class PropagationRouter:
        propagation_node = False

        def __init__(self) -> None:
            self.methods: list[int | None] = []
            self.active_node: bytes | None = None

        def set_active_propagation_node(self, destination_hash: bytes) -> None:
            self.active_node = destination_hash

        def handle_outbound(self, message):
            method = getattr(message, "desired_method", None)
            if method is None:
                method = getattr(message, "method", None)
            self.methods.append(method)
            if method == LXMF.LXMessage.PROPAGATED:
                callback = getattr(message, "_LXMessage__delivery_callback", None)
                if callable(callback):
                    message.state = LXMF.LXMessage.SENT
                    callback(message)
                return
            callback = getattr(message, "failed_callback", None)
            if callable(callback):
                callback(message)

    router = PropagationRouter()
    queue = OutboundMessageQueue(
        router,
        sender,
        queue_size=4,
        worker_count=1,
        send_timeout=0.1,
        backoff_seconds=0.01,
        max_attempts=2,
        propagation_selector=lambda: candidate,
        propagation_fallback_callback=lambda payload: fallbacks.append(
            (
                "local" if payload.local_propagation_fallback else "remote",
                payload.propagation_node_hex,
            )
        ),
        delivery_receipt_callback=lambda message, payload: receipts.append(
            (
                payload.attempts,
                payload.delivery_mode,
                payload.propagation_node_hex,
                message.state,
            )
        ),
        delivery_failure_callback=lambda message, payload: failures.append(
            payload.destination_hex or ""
        ),
    )

    try:
        queue.start()
        queue.queue_message(
            recipient,
            "propagation-fallback",
            recipient.identity.hash,
            recipient.identity.hash.hex(),
            None,
        )
        assert queue.wait_for_flush(timeout=1.0)
    finally:
        queue.stop()

    assert router.methods == [
        LXMF.LXMessage.DIRECT,
        LXMF.LXMessage.DIRECT,
        LXMF.LXMessage.PROPAGATED,
    ]
    assert router.active_node == candidate.destination_hash
    assert fallbacks == [("remote", candidate.destination_hex)]
    assert receipts == [
        (
            2,
            "propagated",
            candidate.destination_hex,
            LXMF.LXMessage.SENT,
        )
    ]
    assert failures == []


def test_outbound_queue_uses_local_propagation_when_remote_node_unavailable():
    sender = _make_destination(RNS.Destination.IN)
    recipient = _make_destination()
    receipts: list[tuple[str, bool, int]] = []
    fallbacks: list[tuple[str, bool]] = []
    failures: list[str] = []

    class LocalPropagationRouter:
        propagation_node = True

        def __init__(self) -> None:
            self.stored: list[bytes] = []

        def handle_outbound(self, message):
            callback = getattr(message, "failed_callback", None)
            if callable(callback):
                callback(message)

        def lxmf_propagation(self, payload: bytes) -> bool:
            self.stored.append(payload)
            return True

    router = LocalPropagationRouter()
    queue = OutboundMessageQueue(
        router,
        sender,
        queue_size=2,
        worker_count=1,
        send_timeout=0.1,
        backoff_seconds=0.01,
        max_attempts=1,
        propagation_fallback_callback=lambda payload: fallbacks.append(
            (payload.delivery_mode, payload.local_propagation_fallback)
        ),
        delivery_receipt_callback=lambda message, payload: receipts.append(
            (payload.delivery_mode, payload.local_propagation_fallback, message.state)
        ),
        delivery_failure_callback=lambda message, payload: failures.append(
            payload.destination_hex or ""
        ),
    )

    try:
        queue.start()
        queue.queue_message(
            recipient,
            "local-propagation",
            recipient.identity.hash,
            recipient.identity.hash.hex(),
            None,
        )
        assert queue.wait_for_flush(timeout=1.0)
    finally:
        queue.stop()

    assert len(router.stored) == 1
    assert fallbacks == [("propagated", True)]
    assert receipts == [("propagated", True, LXMF.LXMessage.SENT)]
    assert failures == []


def test_outbound_queue_propagated_failure_is_terminal():
    sender = _make_destination(RNS.Destination.IN)
    recipient = _make_destination()
    failures: list[tuple[int, str]] = []
    selector_calls: list[int] = []
    candidate = PropagationNodeCandidate(
        destination_hash=b"\xBB" * 16,
        destination_hex=(b"\xBB" * 16).hex(),
        hops=1,
        stamp_cost=1,
        transfer_limit=1024,
        sync_limit=2048,
        last_announced_at=time.time(),
        propagation_enabled=True,
    )

    class PropagationFailureRouter:
        propagation_node = False

        def __init__(self) -> None:
            self.methods: list[int | None] = []

        def set_active_propagation_node(self, destination_hash: bytes) -> None:
            self.active_node = destination_hash

        def handle_outbound(self, message):
            method = getattr(message, "desired_method", None)
            if method is None:
                method = getattr(message, "method", None)
            self.methods.append(method)
            callback = getattr(message, "failed_callback", None)
            if callable(callback):
                callback(message)

    router = PropagationFailureRouter()
    queue = OutboundMessageQueue(
        router,
        sender,
        queue_size=2,
        worker_count=1,
        send_timeout=0.1,
        backoff_seconds=0.01,
        max_attempts=1,
        propagation_selector=lambda: selector_calls.append(1) or candidate,
        delivery_failure_callback=lambda message, payload: failures.append(
            (payload.attempts, payload.delivery_mode)
        ),
    )

    try:
        queue.start()
        queue.queue_message(
            recipient,
            "propagated-terminal",
            recipient.identity.hash,
            recipient.identity.hash.hex(),
            None,
        )
        assert queue.wait_for_flush(timeout=1.0)
    finally:
        queue.stop()

    assert selector_calls == [1]
    assert router.methods == [LXMF.LXMessage.DIRECT, LXMF.LXMessage.PROPAGATED]
    assert failures == [(1, "propagated")]
