"""Outbound queue stats, enqueue, and backpressure helpers."""

from __future__ import annotations

import heapq
import time
from queue import Empty
from queue import Full

import RNS

from reticulum_telemetry_hub.reticulum_server.outbound_types import OutboundPayload


class OutboundQueueStatsMixin:
    """Record queue metrics and handle enqueue/backpressure paths."""

    def stats(self) -> dict[str, int | float]:
        """Return queue counters for routing and backpressure metrics."""

        with self._inflight_lock:
            inflight = self._inflight
        with self._active_dispatch_lock:
            active_dispatches = self._active_dispatches
        with self._in_progress_futures_lock:
            in_progress_futures = self._in_progress_futures
        with self._timed_out_sends_lock:
            timed_out_sends = self._timed_out_sends
        with self._pending_dispatches_lock:
            pending_dispatches = len(self._pending_dispatches)
            oldest_pending_dispatch_age_ms = 0.0
            now = time.monotonic()
            if self._pending_dispatches:
                oldest_pending_dispatch_age_ms = max(
                    (now - dispatch.timed_out_at) * 1000
                    for dispatch in self._pending_dispatches.values()
                )
        with self._pending_receipts_lock:
            pending_receipts = len(self._pending_receipts)
            oldest_pending_receipt_age_ms = 0.0
            if self._pending_receipts:
                oldest_pending_receipt_age_ms = max(
                    (now - receipt.registered_at) * 1000
                    for receipt in self._pending_receipts.values()
                )
        with self._delayed_lock:
            delayed_depth = len(self._delayed_heap)
        queue_depth = self._queue.qsize()
        with self._stats_lock:
            enqueued_total = self._enqueued_total
            dropped_total = self._dropped_total
            retry_total = self._retry_total
            timeout_total = self._timeout_total
            receipt_timeout_total = self._receipt_timeout_total
            propagation_fallback_total = self._propagation_fallback_total
            max_queue_depth = self._max_queue_depth

        stats: dict[str, int | float] = {
            "queue_depth": queue_depth,
            "delayed_depth": delayed_depth,
            "inflight": inflight,
            "active_dispatches": active_dispatches,
            "in_progress_futures": in_progress_futures,
            "pending_dispatches": pending_dispatches,
            "pending_receipts": pending_receipts,
            "timed_out_sends": timed_out_sends,
            "worker_count": self._worker_count,
            "max_queue_depth": max_queue_depth,
            "enqueued_total": enqueued_total,
            "dropped_total": dropped_total,
            "retry_total": retry_total,
            "timeout_total": timeout_total,
            "receipt_timeout_total": receipt_timeout_total,
            "propagation_fallback_total": propagation_fallback_total,
            "oldest_pending_dispatch_age_ms": round(oldest_pending_dispatch_age_ms, 3),
            "oldest_pending_receipt_age_ms": round(oldest_pending_receipt_age_ms, 3),
        }
        self._publish_stats(stats)
        return stats

    def _publish_stats(self, stats: dict[str, int | float]) -> None:
        """Mirror runtime queue gauges into the shared metrics store."""

        metrics = self._runtime_metrics
        if metrics is None:
            return
        metrics.set_gauge("queue_depth", float(stats["queue_depth"]))
        metrics.set_gauge("queue_max_depth", float(stats["max_queue_depth"]))
        metrics.set_gauge("queue_delayed_depth", float(stats["delayed_depth"]))
        metrics.set_gauge("queue_pending_dispatches", float(stats["pending_dispatches"]))
        metrics.set_gauge("queue_pending_receipts", float(stats["pending_receipts"]))
        metrics.set_gauge(
            "queue_oldest_pending_dispatch_age_ms",
            float(stats["oldest_pending_dispatch_age_ms"]),
        )
        metrics.set_gauge(
            "queue_oldest_pending_receipt_age_ms",
            float(stats["oldest_pending_receipt_age_ms"]),
        )

    def _record_counter(self, key: str, value: int = 1) -> None:
        metrics = self._runtime_metrics
        if metrics is None:
            return
        metrics.increment(key, value)

    def _record_timer(self, key: str, value_ms: float) -> None:
        metrics = self._runtime_metrics
        if metrics is None:
            return
        metrics.observe_ms(key, value_ms)

    def _enqueue_payload(self, payload: OutboundPayload) -> bool:
        payload.enqueued_at = time.monotonic()
        if payload.next_attempt_at > payload.enqueued_at:
            delayed_depth = 0
            saturated = False
            with self._delayed_lock:
                total_depth = self._queue.qsize() + len(self._delayed_heap)
                if total_depth >= self._max_queue_size:
                    saturated = True
                else:
                    self._delayed_seq += 1
                    seq = self._delayed_seq
                    heapq.heappush(self._delayed_heap, (payload.next_attempt_at, seq, payload))
                    delayed_depth = len(self._delayed_heap)
            if saturated:
                self._notify_payload_dropped(payload, "queue_saturated")
                self._record_drop("queue_saturated")
                RNS.log(
                    (
                        "Outbound queue is saturated; dropping delayed payload"
                        f" destined for {payload.destination_hex or 'unknown destination'}"
                    ),
                    getattr(RNS, "LOG_WARNING", 2),
                )
                return False
            self._delayed_event.set()
            if self._runtime_metrics is not None:
                self._runtime_metrics.set_gauge("queue_delayed_depth", float(delayed_depth))
            return True
        return self._enqueue_ready_payload(payload)

    def _enqueue_ready_payload(self, payload: OutboundPayload) -> bool:
        with self._delayed_lock:
            total_depth = self._queue.qsize() + len(self._delayed_heap)
            ready_has_capacity = self._queue.qsize() < self._max_queue_size
        if total_depth >= self._max_queue_size and ready_has_capacity:
            self._notify_payload_dropped(payload, "queue_saturated")
            self._record_drop("queue_saturated")
            RNS.log(
                (
                    "Outbound queue is saturated; dropping payload destined for"
                    f" {payload.destination_hex or 'unknown destination'}"
                ),
                getattr(RNS, "LOG_WARNING", 2),
            )
            return False
        try:
            self._queue.put_nowait(payload)
            self._record_queue_enqueued()
            return True
        except Full:
            dropped = self._drop_oldest_ready()
            if dropped is not None:
                self._notify_payload_dropped(dropped, "queue_backpressure_drop_oldest")
                self._record_drop("queue_backpressure_drop_oldest")
                RNS.log(
                    (
                        "Outbound queue is full; dropped oldest payload destined for"
                        f" {dropped.destination_hex or 'unknown destination'}"
                    ),
                    getattr(RNS, "LOG_WARNING", 2),
                )
            try:
                self._queue.put_nowait(payload)
                self._record_queue_enqueued()
                return True
            except Full:
                self._notify_payload_dropped(payload, "queue_saturated")
                self._record_drop("queue_saturated")
                RNS.log(
                    (
                        "Outbound queue is saturated; dropping payload destined for"
                        f" {payload.destination_hex or 'unknown destination'}"
                    ),
                    getattr(RNS, "LOG_WARNING", 2),
                )
                return False

    def _record_queue_enqueued(self) -> None:
        depth = self._queue.qsize()
        with self._stats_lock:
            self._enqueued_total += 1
            self._max_queue_depth = max(self._max_queue_depth, depth)
        self._record_counter("outbound_enqueued_total")
        if self._runtime_metrics is not None:
            self._runtime_metrics.set_gauge("queue_depth", float(depth))
            self._runtime_metrics.set_gauge("queue_max_depth", float(self._max_queue_depth))

    def _record_drop(self, reason: str) -> None:
        with self._stats_lock:
            self._dropped_total += 1
            self._dropped_by_reason[reason] += 1
        self._record_counter("outbound_dropped_total")
        self._record_counter(f"outbound_dropped_{reason}")

    def _drop_oldest_ready(self) -> OutboundPayload | None:
        try:
            oldest = self._queue.get_nowait()
            self._queue.task_done()
            return oldest
        except Empty:
            return None

