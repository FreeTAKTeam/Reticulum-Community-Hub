"""Threaded outbound LXMF delivery queue."""

from __future__ import annotations

import heapq
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from queue import Empty
from queue import Queue
from typing import Callable

import LXMF
import RNS

from reticulum_telemetry_hub.reticulum_server.outbound_queue_delivery import OutboundQueueDeliveryMixin
from reticulum_telemetry_hub.reticulum_server.outbound_queue_stats import OutboundQueueStatsMixin
from reticulum_telemetry_hub.reticulum_server.outbound_types import _PendingDispatch
from reticulum_telemetry_hub.reticulum_server.outbound_types import _PendingReceipt
from reticulum_telemetry_hub.reticulum_server.outbound_types import OutboundPayload
from reticulum_telemetry_hub.reticulum_server.propagation_selection import (
    PropagationNodeCandidate,
)
from reticulum_telemetry_hub.reticulum_server.runtime_metrics_store import (
    RuntimeMetricsStore,
)


class OutboundMessageQueue(OutboundQueueStatsMixin, OutboundQueueDeliveryMixin):
    """Threaded dispatcher that delivers LXMF messages without blocking callers."""

    def __init__(
        self,
        lxm_router: LXMF.LXMRouter,
        sender: RNS.Destination,
        *,
        queue_size: int = 64,
        worker_count: int = 2,
        send_timeout: float = 5.0,
        delivery_receipt_timeout: float | None = None,
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
        direct_failure_callback: (
            Callable[[OutboundPayload, str], None] | None
        ) = None,
        propagation_fallback_callback: (
            Callable[[OutboundPayload], None] | None
        ) = None,
        attempt_started_callback: Callable[[OutboundPayload], None] | None = None,
        payload_dropped_callback: (
            Callable[[OutboundPayload, str], None] | None
        ) = None,
        runtime_metrics: RuntimeMetricsStore | None = None,
    ) -> None:
        """
        Initialize a bounded outbound queue.

        Args:
            lxm_router (LXMF.LXMRouter): Router responsible for delivery.
            sender (RNS.Destination): Sender identity to attach to messages.
            queue_size (int): Maximum queued payloads before applying backpressure.
            worker_count (int): Parallel worker threads processing the queue.
            send_timeout (float): Seconds to wait for a send before timing out.
            delivery_receipt_timeout (float | None): Optional number of seconds
                to wait for an LXMF delivery or failure callback after dispatch.
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
            direct_failure_callback (Callable[[OutboundPayload, str], None] | None):
                Optional callback invoked when a direct attempt fails.
            propagation_fallback_callback (Callable[[OutboundPayload], None] | None):
                Optional callback invoked when propagation fallback is selected.
            attempt_started_callback (Callable[[OutboundPayload], None] | None):
                Optional callback invoked when a delivery attempt begins.
            payload_dropped_callback (Callable[[OutboundPayload, str], None] | None):
                Optional callback invoked when queue backpressure drops a payload.
            runtime_metrics (RuntimeMetricsStore | None): Optional runtime metrics sink.
        """

        self._lxm_router = lxm_router
        self._sender = sender
        self._max_queue_size = max(int(queue_size), 1)
        self._queue: Queue[OutboundPayload] = Queue(maxsize=self._max_queue_size)
        self._worker_count = max(worker_count, 1)
        self._send_executor = ThreadPoolExecutor(
            max_workers=self._worker_count,
            thread_name_prefix="lxmf-send",
        )
        self._send_timeout = max(send_timeout, 0.1)
        self._delivery_receipt_timeout = (
            max(delivery_receipt_timeout, 0.01)
            if delivery_receipt_timeout is not None
            else None
        )
        self._backoff_seconds = max(backoff_seconds, 0.01)
        self._max_attempts = max(max_attempts, 1)
        self._stop_event = threading.Event()
        self._workers: list[threading.Thread] = []
        self._receipt_monitor: threading.Thread | None = None
        self._delayed_scheduler: threading.Thread | None = None
        self._delayed_heap: list[tuple[float, int, OutboundPayload]] = []
        self._delayed_lock = threading.Lock()
        self._delayed_event = threading.Event()
        self._delayed_seq = 0
        self._inflight = 0
        self._inflight_lock = threading.Lock()
        self._active_dispatches = 0
        self._active_dispatch_lock = threading.Lock()
        self._in_progress_futures = 0
        self._in_progress_futures_lock = threading.Lock()
        self._timed_out_sends = 0
        self._timed_out_sends_lock = threading.Lock()
        self._pending_dispatches: dict[tuple[int, int], _PendingDispatch] = {}
        self._pending_dispatches_lock = threading.Lock()
        self._pending_receipts: dict[tuple[int, int], _PendingReceipt] = {}
        self._pending_receipt_deadlines: list[tuple[float, tuple[int, int]]] = []
        self._pending_receipts_lock = threading.Lock()
        self._receipt_wakeup = threading.Event()
        self._delivery_receipt_callback = delivery_receipt_callback
        self._delivery_failure_callback = delivery_failure_callback
        self._propagation_selector = propagation_selector
        self._retry_scheduled_callback = retry_scheduled_callback
        self._direct_failure_callback = direct_failure_callback
        self._propagation_fallback_callback = propagation_fallback_callback
        self._attempt_started_callback = attempt_started_callback
        self._payload_dropped_callback = payload_dropped_callback
        self._runtime_metrics = runtime_metrics
        self._max_queue_depth = 0
        self._enqueued_total = 0
        self._dropped_total = 0
        self._retry_total = 0
        self._timeout_total = 0
        self._receipt_timeout_total = 0
        self._propagation_fallback_total = 0
        self._dropped_by_reason: dict[str, int] = defaultdict(int)
        self._stats_lock = threading.Lock()

    def start(self) -> None:
        """Start background worker threads if they are not already running."""

        if self._workers:
            return

        self._stop_event.clear()
        self._delayed_event.clear()
        self._receipt_wakeup.clear()
        for index in range(self._worker_count):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"lxmf-outbound-{index}",
                daemon=True,
            )
            worker.start()
            self._workers.append(worker)
        if self._delayed_scheduler is None:
            self._delayed_scheduler = threading.Thread(
                target=self._delayed_scheduler_loop,
                name="lxmf-outbound-delayed",
                daemon=True,
            )
            self._delayed_scheduler.start()
        if self._receipt_monitor is None:
            self._receipt_monitor = threading.Thread(
                target=self._receipt_monitor_loop,
                name="lxmf-outbound-receipts",
                daemon=True,
            )
            self._receipt_monitor.start()

    def stop(self) -> None:
        """Signal workers to stop and wait for them to exit."""

        if not self._workers:
            return

        self._stop_event.set()
        self._delayed_event.set()
        self._receipt_wakeup.set()
        for worker in self._workers:
            worker.join(timeout=0.5)
        self._workers.clear()
        if self._delayed_scheduler is not None:
            self._delayed_scheduler.join(timeout=0.5)
            self._delayed_scheduler = None
        if self._receipt_monitor is not None:
            self._receipt_monitor.join(timeout=0.5)
            self._receipt_monitor = None

    def queue_message(
        self,
        connection: RNS.Destination,
        message_text: str,
        destination_hash: bytes | None,
        destination_hex: str | None,
        fields: dict | None = None,
        sender: RNS.Destination | None = None,
        chat_message_id: str | None = None,
        message_id: str | None = None,
        topic_id: str | None = None,
        route_type: str = "broadcast",
    ) -> bool:
        """Enqueue a message for delivery."""

        payload = OutboundPayload(
            connection=connection,
            message_text=message_text,
            destination_hash=destination_hash,
            destination_hex=destination_hex,
            fields=fields,
            sender=sender or self._sender,
            chat_message_id=chat_message_id,
            message_id=message_id,
            topic_id=topic_id,
            route_type=route_type,
        )
        return self._enqueue_payload(payload)

    def queue_messages(self, payloads: list[OutboundPayload]) -> list[bool]:
        """Enqueue a batch of outbound payloads and return per-item outcomes."""

        return [self._enqueue_payload(payload) for payload in payloads]

    def wait_for_flush(self, timeout: float = 1.0) -> bool:
        """Wait until the queue and inflight sends complete."""

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._inflight_lock:
                inflight = self._inflight
            with self._active_dispatch_lock:
                active_dispatches = self._active_dispatches
            with self._in_progress_futures_lock:
                in_progress_futures = self._in_progress_futures
            with self._pending_dispatches_lock:
                pending_dispatches = len(self._pending_dispatches)
            with self._pending_receipts_lock:
                pending_receipts = len(self._pending_receipts)
            with self._delayed_lock:
                delayed = len(self._delayed_heap)
            if (
                self._queue.empty()
                and delayed == 0
                and inflight == 0
                and active_dispatches == 0
                and in_progress_futures == 0
                and pending_dispatches == 0
                and pending_receipts == 0
            ):
                return True
            time.sleep(0.01)
        return False

    def _delayed_scheduler_loop(self) -> None:
        """Promote delayed payloads when their retry deadline is due."""

        while not self._stop_event.is_set():
            due_payloads: list[OutboundPayload] = []
            wait_seconds = 0.5
            now = time.monotonic()
            with self._delayed_lock:
                while self._delayed_heap and self._delayed_heap[0][0] <= now:
                    _, _, payload = heapq.heappop(self._delayed_heap)
                    due_payloads.append(payload)
                if self._delayed_heap:
                    wait_seconds = max(min(self._delayed_heap[0][0] - now, 0.5), 0.01)
            for payload in due_payloads:
                if not self._enqueue_ready_payload(payload):
                    self._finalize_terminal_failure(payload)
            self._delayed_event.wait(wait_seconds)
            self._delayed_event.clear()

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                payload = self._queue.get(timeout=0.1)
            except Empty:
                continue

            try:
                self._process_payload(payload)
            finally:
                self._queue.task_done()

    def _process_payload(self, payload: OutboundPayload) -> None:
        with self._inflight_lock:
            self._inflight += 1

        try:
            self._notify_attempt_started(payload)
            started_at = time.monotonic()
            failure_reason = self._send_with_timeout(payload)
            self._record_timer(
                "outbound_dispatch_latency_ms",
                (time.monotonic() - started_at) * 1000,
            )
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

    def _attempt_is_active(self, payload: OutboundPayload, attempt_id: int) -> bool:
        """Return whether the current attempt is still active."""

        with payload._attempt_lock:
            return payload._active_attempt_id == attempt_id

    def _register_pending_receipt(
        self,
        payload: OutboundPayload,
        attempt_id: int,
    ) -> None:
        """Track a dispatched payload until a delivery callback or timeout arrives."""

        if self._delivery_receipt_timeout is None:
            return
        now = time.monotonic()
        deadline = now + self._delivery_receipt_timeout
        key = (id(payload), attempt_id)
        with self._pending_receipts_lock:
            self._pending_receipts[key] = _PendingReceipt(payload, attempt_id, deadline, now)
            heapq.heappush(self._pending_receipt_deadlines, (deadline, key))
        self._receipt_wakeup.set()

    def _pop_pending_receipt(
        self,
        payload: OutboundPayload,
        attempt_id: int,
    ) -> _PendingReceipt | None:
        """Remove and return the pending receipt entry for an attempt."""

        key = (id(payload), attempt_id)
        with self._pending_receipts_lock:
            pending = self._pending_receipts.pop(key, None)
        if pending is not None:
            self._receipt_wakeup.set()
        return pending

    def _receipt_monitor_loop(self) -> None:
        """Handle receipt deadline expirations without fixed dictionary scans."""

        while not self._stop_event.is_set():
            now = time.monotonic()
            expired: list[_PendingReceipt] = []
            wait_seconds = 0.5
            with self._pending_receipts_lock:
                while self._pending_receipt_deadlines:
                    deadline, key = self._pending_receipt_deadlines[0]
                    if deadline > now:
                        wait_seconds = max(min(deadline - now, 0.5), 0.01)
                        break
                    heapq.heappop(self._pending_receipt_deadlines)
                    pending = self._pending_receipts.get(key)
                    if pending is None:
                        continue
                    if abs(pending.deadline - deadline) > 1e-9:
                        continue
                    expired.append(self._pending_receipts.pop(key))
                if not self._pending_receipt_deadlines:
                    wait_seconds = 0.5
            for pending in expired:
                self._handle_receipt_timeout(pending.payload, pending.attempt_id)
            self._receipt_wakeup.wait(wait_seconds)
            self._receipt_wakeup.clear()

    def _handle_receipt_timeout(
        self,
        payload: OutboundPayload,
        attempt_id: int,
    ) -> None:
        """Convert a missing delivery callback into a retry/failure transition."""

        if not self._claim_attempt(payload, attempt_id):
            return
        with self._stats_lock:
            self._receipt_timeout_total += 1
        self._record_counter("outbound_receipt_timeout_total")
        RNS.log(
            (
                "Timed out waiting for LXMF delivery acknowledgement from"
                f" {payload.destination_hex or 'unknown destination'}"
            ),
            getattr(RNS, "LOG_WARNING", 2),
        )
        self._handle_delivery_attempt_failure(
            payload,
            reason="delivery_receipt_timeout",
        )

