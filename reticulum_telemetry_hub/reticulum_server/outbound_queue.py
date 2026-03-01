import threading
import time
from dataclasses import dataclass, field
from queue import Empty, Full, Queue
from typing import Callable

import LXMF
import RNS

from reticulum_telemetry_hub.reticulum_server.appearance import apply_icon_appearance

@dataclass
class OutboundPayload:
    """
    Message payload scheduled for outbound delivery.

    Args:
        connection (RNS.Destination): Destination to deliver the message to.
        message_text (str): Plaintext message body to deliver.
        destination_hash (bytes | None): Raw destination hash for diagnostics.
        destination_hex (str | None): Hex-encoded destination hash for logging.
        fields (dict | None): Optional LXMF fields to include with the message.
        sender (RNS.Destination): Sender identity for the message.
        chat_message_id (str | None): Optional persisted chat message identifier.
        attempts (int): Number of delivery attempts performed.
        next_attempt_at (float): Monotonic timestamp before the next attempt.
    """

    connection: RNS.Destination
    message_text: str
    destination_hash: bytes | None
    destination_hex: str | None
    fields: dict | None = None
    sender: RNS.Destination | None = None
    chat_message_id: str | None = None
    attempts: int = 0
    next_attempt_at: float = field(default_factory=time.monotonic)


class OutboundMessageQueue:
    """
    Threaded dispatcher that delivers LXMF messages without blocking callers.
    """

    def __init__(
        self,
        lxm_router: LXMF.LXMRouter,
        sender: RNS.Destination,
        *,
        queue_size: int = 64,
        worker_count: int = 2,
        send_timeout: float = 5.0,
        backoff_seconds: float = 0.5,
        max_attempts: int = 3,
        delivery_receipt_callback: (
            Callable[[LXMF.LXMessage, OutboundPayload], None] | None
        ) = None,
        delivery_failure_callback: (
            Callable[[LXMF.LXMessage, OutboundPayload], None] | None
        ) = None,
    ):
        """
        Initialize a bounded outbound queue.

        Args:
            lxm_router (LXMF.LXMRouter): Router responsible for delivery.
            sender (RNS.Destination): Sender identity to attach to messages.
            queue_size (int): Maximum queued payloads before applying backpressure.
            worker_count (int): Parallel worker threads processing the queue.
            send_timeout (float): Seconds to wait for a send before timing out.
            backoff_seconds (float): Base delay between retry attempts.
            max_attempts (int): Maximum attempts before dropping a message.
            delivery_receipt_callback (Callable[[LXMF.LXMessage, OutboundPayload], None] | None):
                Optional callback invoked when LXMF reports successful delivery.
            delivery_failure_callback (Callable[[LXMF.LXMessage, OutboundPayload], None] | None):
                Optional callback invoked when LXMF reports delivery failure.
        """
        self._lxm_router = lxm_router
        self._sender = sender
        self._queue: Queue[OutboundPayload] = Queue(maxsize=max(queue_size, 1))
        self._worker_count = max(worker_count, 1)
        self._send_timeout = max(send_timeout, 0.1)
        self._backoff_seconds = max(backoff_seconds, 0.01)
        self._max_attempts = max(max_attempts, 1)
        self._stop_event = threading.Event()
        self._workers: list[threading.Thread] = []
        self._inflight = 0
        self._inflight_lock = threading.Lock()
        self._delivery_receipt_callback = delivery_receipt_callback
        self._delivery_failure_callback = delivery_failure_callback

    def start(self) -> None:
        """Start background worker threads if they are not already running."""

        if self._workers:
            return

        self._stop_event.clear()
        for index in range(self._worker_count):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"lxmf-outbound-{index}",
                daemon=True,
            )
            worker.start()
            self._workers.append(worker)

    def stop(self) -> None:
        """Signal workers to stop and wait for them to exit."""

        if not self._workers:
            return

        self._stop_event.set()
        for worker in self._workers:
            worker.join(timeout=0.5)
        self._workers.clear()

    def queue_message(
        self,
        connection: RNS.Destination,
        message_text: str,
        destination_hash: bytes | None,
        destination_hex: str | None,
        fields: dict | None = None,
        sender: RNS.Destination | None = None,
        chat_message_id: str | None = None,
    ) -> bool:
        """
        Enqueue a message for delivery.

        Args:
            connection (RNS.Destination): Destination to deliver the message to.
            message_text (str): Plaintext message body to deliver.
            destination_hash (bytes | None): Raw destination hash for diagnostics.
            destination_hex (str | None): Hex-encoded destination hash for logging.
            fields (dict | None): Optional LXMF message fields.
            chat_message_id (str | None): Optional persisted chat message identifier.

        Returns:
            bool: ``True`` when the message was queued successfully.
        """

        payload = OutboundPayload(
            connection=connection,
            message_text=message_text,
            destination_hash=destination_hash,
            destination_hex=destination_hex,
            fields=fields,
            sender=sender or self._sender,
            chat_message_id=chat_message_id,
        )
        return self._enqueue_payload(payload)

    def wait_for_flush(self, timeout: float = 1.0) -> bool:
        """
        Wait until the queue and inflight sends complete.

        Args:
            timeout (float): Seconds to wait before giving up.

        Returns:
            bool: ``True`` when the queue drained before the timeout elapsed.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._inflight_lock:
                inflight = self._inflight
            if self._queue.empty() and inflight == 0:
                return True
            time.sleep(0.01)
        return False

    def _enqueue_payload(self, payload: OutboundPayload) -> bool:
        try:
            self._queue.put_nowait(payload)
            return True
        except Full:
            dropped = self._drop_oldest()
            if dropped is not None:
                RNS.log(
                    (
                        "Outbound queue is full; dropped oldest payload destined for"
                        f" {dropped.destination_hex or 'unknown destination'}"
                    ),
                    getattr(RNS, "LOG_WARNING", 2),
                )
            try:
                self._queue.put_nowait(payload)
                return True
            except Full:
                RNS.log(
                    (
                        "Outbound queue is saturated; dropping payload destined for"
                        f" {payload.destination_hex or 'unknown destination'}"
                    ),
                    getattr(RNS, "LOG_WARNING", 2),
                )
                return False

    def _drop_oldest(self) -> OutboundPayload | None:
        try:
            oldest = self._queue.get_nowait()
            self._queue.task_done()
            return oldest
        except Empty:
            return None

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                payload = self._queue.get(timeout=0.1)
            except Empty:
                continue

            now = time.monotonic()
            if payload.next_attempt_at > now:
                delay = min(payload.next_attempt_at - now, 0.1)
                time.sleep(delay)
                self._enqueue_payload(payload)
                self._queue.task_done()
                continue

            try:
                self._process_payload(payload)
            finally:
                self._queue.task_done()

    def _process_payload(self, payload: OutboundPayload) -> None:
        with self._inflight_lock:
            self._inflight += 1

        try:
            success = self._send_with_timeout(payload)
            if not success:
                self._handle_failure(payload)
        finally:
            with self._inflight_lock:
                self._inflight -= 1

    def _send_with_timeout(self, payload: OutboundPayload) -> bool:
        error: list[Exception | None] = [None]

        def _send() -> None:
            try:
                message = LXMF.LXMessage(
                    payload.connection,
                    payload.sender or self._sender,
                    payload.message_text,
                    fields=apply_icon_appearance(payload.fields),
                    desired_method=LXMF.LXMessage.DIRECT,
                )
                if payload.destination_hash:
                    message.destination_hash = payload.destination_hash
                if self._delivery_receipt_callback is not None:
                    message.register_delivery_callback(
                        lambda delivered_message, outbound_payload=payload: self._notify_delivery_receipt(
                            delivered_message,
                            outbound_payload,
                        )
                    )
                if self._delivery_failure_callback is not None:
                    message.register_failed_callback(
                        lambda failed_message, outbound_payload=payload: self._notify_delivery_failure(
                            failed_message,
                            outbound_payload,
                        )
                    )
                self._lxm_router.handle_outbound(message)
            except Exception as exc:  # pragma: no cover - defensive logging
                error[0] = exc

        sender = threading.Thread(target=_send, name="lxmf-send", daemon=True)
        sender.start()
        sender.join(timeout=self._send_timeout)
        if sender.is_alive():
            RNS.log(
                (
                    "Timed out delivering outbound message to"
                    f" {payload.destination_hex or 'unknown destination'}"
                ),
                getattr(RNS, "LOG_WARNING", 2),
            )
            return False

        if error[0] is not None:
            RNS.log(
                (
                    "Failed to deliver outbound message to"
                    f" {payload.destination_hex or 'unknown destination'}: {error[0]}"
                ),
                getattr(RNS, "LOG_WARNING", 2),
            )
            return False
        return True

    def _notify_delivery_receipt(
        self,
        message: LXMF.LXMessage,
        payload: OutboundPayload,
    ) -> None:
        """Forward LXMF delivery receipts to the configured callback."""

        callback = self._delivery_receipt_callback
        if callback is None:
            return
        try:
            callback(message, payload)
        except Exception as exc:  # pragma: no cover - defensive logging
            RNS.log(
                f"Outbound delivery receipt callback failed: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )

    def _notify_delivery_failure(
        self,
        message: LXMF.LXMessage,
        payload: OutboundPayload,
    ) -> None:
        """Forward LXMF delivery failures to the configured callback."""

        callback = self._delivery_failure_callback
        if callback is None:
            return
        try:
            callback(message, payload)
        except Exception as exc:  # pragma: no cover - defensive logging
            RNS.log(
                f"Outbound delivery failure callback failed: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )

    def _handle_failure(self, payload: OutboundPayload) -> None:
        payload.attempts += 1
        if payload.attempts >= self._max_attempts:
            RNS.log(
                (
                    "Dropping outbound message to"
                    f" {payload.destination_hex or 'unknown destination'} after"
                    f" {payload.attempts} attempts"
                ),
                getattr(RNS, "LOG_WARNING", 2),
            )
            self._propagate_failed_message(payload)
            return

        payload.next_attempt_at = (
            time.monotonic() + self._backoff_seconds * payload.attempts
        )
        # Reason: requeue with backoff so slower destinations do not halt others.
        self._enqueue_payload(payload)

    def _propagate_failed_message(self, payload: OutboundPayload) -> None:
        if not getattr(self._lxm_router, "propagation_node", False):
            return

        try:
            message = LXMF.LXMessage(
                payload.connection,
                payload.sender or self._sender,
                payload.message_text,
                fields=apply_icon_appearance(payload.fields),
                desired_method=LXMF.LXMessage.DIRECT,
            )
            if payload.destination_hash:
                message.destination_hash = payload.destination_hash
            message.pack()
            if not message.packed:
                return
            self._lxm_router.lxmf_propagation(message.packed)
            RNS.log(
                (
                    "Stored failed outbound message for propagation to"
                    f" {payload.destination_hex or 'unknown destination'}"
                ),
                getattr(RNS, "LOG_INFO", 4),
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            RNS.log(
                (
                    "Failed to store outbound message for propagation to"
                    f" {payload.destination_hex or 'unknown destination'}: {exc}"
                ),
                getattr(RNS, "LOG_WARNING", 2),
            )
