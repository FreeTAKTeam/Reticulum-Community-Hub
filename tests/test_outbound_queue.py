import time

import RNS

from reticulum_telemetry_hub.reticulum_server.outbound_queue import (
    OutboundMessageQueue,
)


def _make_destination(direction=RNS.Destination.OUT) -> RNS.Destination:
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
        )
        queue.queue_message(
            recipient_two,
            "second",
            recipient_two.identity.hash,
            recipient_two.identity.hash.hex(),
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
        )
        queue.queue_message(
            recipient_two,
            "beta",
            recipient_two.identity.hash,
            recipient_two.identity.hash.hex(),
        )
        assert queue.wait_for_flush(timeout=1.0)
    finally:
        queue.stop()

    assert set(delivered) == {
        recipient_one.identity.hash,
        recipient_two.identity.hash,
    }
