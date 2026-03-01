"""Threaded outbound LXMF delivery queue."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from dataclasses import field
from queue import Empty
from queue import Full
from queue import Queue
from typing import Callable

import LXMF
import RNS

from reticulum_telemetry_hub.reticulum_server.appearance import apply_icon_appearance
from reticulum_telemetry_hub.reticulum_server.propagation_selection import (
    PropagationNodeCandidate,
)


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
        attempts (int): Number of direct-delivery failures observed so far.
        next_attempt_at (float): Monotonic timestamp before the next attempt.
        delivery_mode (str): ``"direct"`` or ``"propagated"``.
        propagation_node_hash (bytes | None): Selected propagation-node hash.
        propagation_node_hex (str | None): Selected propagation-node hash as hex.
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
    delivery_mode: str = "direct"
    propagation_node_hash: bytes | None = None
    propagation_node_hex: str | None = None
    local_propagation_fallback: bool = False
    _attempt_sequence: int = field(default=0, init=False, repr=False)
    _active_attempt_id: int = field(default=0, init=False, repr=False)
    _attempt_lock: threading.Lock = field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
        compare=False,
    )


class OutboundMessageQueue:
    """Threaded dispatcher that delivers LXMF messages without blocking callers."""

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
        propagation_selector: (
            Callable[[], PropagationNodeCandidate | None] | None
        ) = None,
        retry_scheduled_callback: Callable[[OutboundPayload], None] | None = None,
        propagation_fallback_callback: (
            Callable[[OutboundPayload], None] | None
        ) = None,
    ) -> None:
        """
        Initialize a bounded outbound queue.

        Args:
            lxm_router (LXMF.LXMRouter): Router responsible for delivery.
            sender (RNS.Destination): Sender identity to attach to messages.
            queue_size (int): Maximum queued payloads before applying backpressure.
            worker_count (int): Parallel worker threads processing the queue.
            send_timeout (float): Seconds to wait for a send before timing out.
            backoff_seconds (float): Base delay between retry attempts.
            max_attempts (int): Maximum direct-delivery failures before fallback.
            delivery_receipt_callback (Callable[[LXMF.LXMessage, OutboundPayload], None] | None):
                Optional callback invoked when LXMF reports successful delivery.
            delivery_failure_callback (Callable[[LXMF.LXMessage, OutboundPayload], None] | None):
                Optional callback invoked after all delivery paths fail.
            propagation_selector (Callable[[], PropagationNodeCandidate | None] | None):
                Optional callback returning the best remote propagation node.
            retry_scheduled_callback (Callable[[OutboundPayload], None] | None):
                Optional callback invoked when direct delivery is requeued.
            propagation_fallback_callback (Callable[[OutboundPayload], None] | None):
                Optional callback invoked when propagation fallback is selected.
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
        self._propagation_selector = propagation_selector
        self._retry_scheduled_callback = retry_scheduled_callback
        self._propagation_fallback_callback = propagation_fallback_callback

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
            failure_reason = self._send_with_timeout(payload)
            if failure_reason is not None:
                self._handle_delivery_attempt_failure(payload, reason=failure_reason)
        finally:
            with self._inflight_lock:
                self._inflight -= 1

    def _begin_attempt(self, payload: OutboundPayload) -> int:
        """Mark a payload attempt as active and return its token."""

        with payload._attempt_lock:
            payload._attempt_sequence += 1
            payload._active_attempt_id = payload._attempt_sequence
            return payload._active_attempt_id

    def _claim_attempt(self, payload: OutboundPayload, attempt_id: int) -> bool:
        """Claim the active attempt token if it is still current."""

        with payload._attempt_lock:
            if payload._active_attempt_id != attempt_id:
                return False
            payload._active_attempt_id = 0
            return True

    def _invalidate_attempt(self, payload: OutboundPayload, attempt_id: int) -> None:
        """Invalidate a timed-out or failed attempt token."""

        with payload._attempt_lock:
            if payload._active_attempt_id == attempt_id:
                payload._active_attempt_id = 0

    def _build_message(self, payload: OutboundPayload) -> LXMF.LXMessage:
        """Construct an LXMF message for the current payload mode."""

        desired_method = (
            LXMF.LXMessage.PROPAGATED
            if payload.delivery_mode == "propagated"
            else LXMF.LXMessage.DIRECT
        )
        message = LXMF.LXMessage(
            payload.connection,
            payload.sender or self._sender,
            payload.message_text,
            fields=apply_icon_appearance(payload.fields),
            desired_method=desired_method,
        )
        if payload.destination_hash:
            message.destination_hash = payload.destination_hash
        return message

    def _send_with_timeout(self, payload: OutboundPayload) -> str | None:
        """Dispatch a payload and return a failure reason when dispatch fails."""

        error: list[Exception | None] = [None]
        attempt_id = self._begin_attempt(payload)

        def _send() -> None:
            try:
                message = self._build_message(payload)
                message.register_delivery_callback(
                    lambda delivered_message, outbound_payload=payload, token=attempt_id: self._notify_delivery_receipt(
                        delivered_message,
                        outbound_payload,
                        token,
                    )
                )
                message.register_failed_callback(
                    lambda failed_message, outbound_payload=payload, token=attempt_id: self._notify_delivery_failure(
                        failed_message,
                        outbound_payload,
                        token,
                    )
                )
                self._lxm_router.handle_outbound(message)
            except Exception as exc:
                error[0] = exc

        sender = threading.Thread(target=_send, name="lxmf-send", daemon=True)
        sender.start()
        sender.join(timeout=self._send_timeout)
        if sender.is_alive():
            self._invalidate_attempt(payload, attempt_id)
            RNS.log(
                (
                    "Timed out delivering outbound message to"
                    f" {payload.destination_hex or 'unknown destination'}"
                ),
                getattr(RNS, "LOG_WARNING", 2),
            )
            return "send_timeout"

        if error[0] is not None:
            self._invalidate_attempt(payload, attempt_id)
            RNS.log(
                (
                    "Failed to deliver outbound message to"
                    f" {payload.destination_hex or 'unknown destination'}: {error[0]}"
                ),
                getattr(RNS, "LOG_WARNING", 2),
            )
            return "send_error"

        return None

    def _emit_delivery_receipt_callback(
        self,
        message: LXMF.LXMessage,
        payload: OutboundPayload,
    ) -> None:
        """Forward delivery receipts to the configured callback."""

        callback = self._delivery_receipt_callback
        if callback is None:
            return
        try:
            callback(message, payload)
        except Exception as exc:
            RNS.log(
                f"Outbound delivery receipt callback failed: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )

    def _emit_delivery_failure_callback(
        self,
        message: LXMF.LXMessage,
        payload: OutboundPayload,
    ) -> None:
        """Forward terminal delivery failures to the configured callback."""

        callback = self._delivery_failure_callback
        if callback is None:
            return
        try:
            callback(message, payload)
        except Exception as exc:
            RNS.log(
                f"Outbound delivery failure callback failed: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )

    def _notify_delivery_receipt(
        self,
        message: LXMF.LXMessage,
        payload: OutboundPayload,
        attempt_id: int,
    ) -> None:
        """Handle an LXMF delivery receipt for the current active attempt."""

        if not self._claim_attempt(payload, attempt_id):
            return
        self._emit_delivery_receipt_callback(message, payload)

    def _notify_delivery_failure(
        self,
        message: LXMF.LXMessage,
        payload: OutboundPayload,
        attempt_id: int,
    ) -> None:
        """Handle an LXMF delivery failure for the current active attempt."""

        if not self._claim_attempt(payload, attempt_id):
            return
        self._handle_delivery_attempt_failure(
            payload,
            reason="delivery_failed",
            callback_message=message,
        )

    def _notify_retry_scheduled(self, payload: OutboundPayload) -> None:
        """Emit the optional retry callback."""

        callback = self._retry_scheduled_callback
        if callback is None:
            return
        try:
            callback(payload)
        except Exception as exc:
            RNS.log(
                f"Outbound retry callback failed: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )

    def _notify_propagation_fallback(self, payload: OutboundPayload) -> None:
        """Emit the optional propagation fallback callback."""

        callback = self._propagation_fallback_callback
        if callback is None:
            return
        try:
            callback(payload)
        except Exception as exc:
            RNS.log(
                f"Outbound propagation fallback callback failed: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )

    def _select_propagation_candidate(self) -> PropagationNodeCandidate | None:
        """Return the currently preferred remote propagation node."""

        selector = self._propagation_selector
        if selector is None:
            return None
        try:
            return selector()
        except Exception as exc:
            RNS.log(
                f"Failed to select propagation node: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return None

    def _finalize_terminal_failure(
        self,
        payload: OutboundPayload,
        callback_message: LXMF.LXMessage | None = None,
    ) -> None:
        """Invoke terminal failure callbacks after all retries are exhausted."""

        message = callback_message
        if message is None:
            try:
                message = self._build_message(payload)
            except Exception as exc:
                RNS.log(
                    (
                        "Failed to create terminal failure message for"
                        f" {payload.destination_hex or 'unknown destination'}: {exc}"
                    ),
                    getattr(RNS, "LOG_WARNING", 2),
                )
                return
        self._emit_delivery_failure_callback(message, payload)

    def _store_for_local_propagation(self, payload: OutboundPayload) -> None:
        """Store a failed message in the local propagation node."""

        try:
            payload.delivery_mode = "propagated"
            payload.propagation_node_hash = None
            payload.propagation_node_hex = None
            payload.local_propagation_fallback = True
            message = self._build_message(payload)
            message.pack()
            if not message.packed:
                raise RuntimeError("packed LXMF payload is empty")
            result = self._lxm_router.lxmf_propagation(message.packed)
            if result is False:
                raise RuntimeError("local propagation storage rejected payload")
            message.state = LXMF.LXMessage.SENT
            self._notify_propagation_fallback(payload)
            self._emit_delivery_receipt_callback(message, payload)
        except Exception as exc:
            RNS.log(
                (
                    "Failed to store outbound message for local propagation to"
                    f" {payload.destination_hex or 'unknown destination'}: {exc}"
                ),
                getattr(RNS, "LOG_WARNING", 2),
            )
            self._finalize_terminal_failure(payload)

    def _handle_delivery_attempt_failure(
        self,
        payload: OutboundPayload,
        *,
        reason: str,
        callback_message: LXMF.LXMessage | None = None,
    ) -> None:
        """Process a failed direct or propagated delivery attempt."""

        if payload.delivery_mode == "propagated":
            RNS.log(
                (
                    "Dropping propagated outbound message to"
                    f" {payload.destination_hex or 'unknown destination'} after"
                    f" propagation fallback failed ({reason})"
                ),
                getattr(RNS, "LOG_WARNING", 2),
            )
            self._finalize_terminal_failure(payload, callback_message=callback_message)
            return

        payload.attempts += 1
        if payload.attempts < self._max_attempts:
            payload.next_attempt_at = (
                time.monotonic() + self._backoff_seconds * payload.attempts
            )
            self._notify_retry_scheduled(payload)
            self._enqueue_payload(payload)
            return

        candidate = self._select_propagation_candidate()
        if candidate is not None:
            try:
                self._lxm_router.set_active_propagation_node(candidate.destination_hash)
            except Exception as exc:
                RNS.log(
                    (
                        "Failed to activate propagation node"
                        f" {candidate.destination_hex}: {exc}"
                    ),
                    getattr(RNS, "LOG_WARNING", 2),
                )
            else:
                payload.delivery_mode = "propagated"
                payload.propagation_node_hash = candidate.destination_hash
                payload.propagation_node_hex = candidate.destination_hex
                payload.local_propagation_fallback = False
                payload.next_attempt_at = time.monotonic()
                self._notify_propagation_fallback(payload)
                self._enqueue_payload(payload)
                return

        if getattr(self._lxm_router, "propagation_node", False):
            self._store_for_local_propagation(payload)
            return

        RNS.log(
            (
                "Dropping outbound message to"
                f" {payload.destination_hex or 'unknown destination'} after"
                f" {payload.attempts} direct delivery failures"
            ),
            getattr(RNS, "LOG_WARNING", 2),
        )
        self._finalize_terminal_failure(payload, callback_message=callback_message)
