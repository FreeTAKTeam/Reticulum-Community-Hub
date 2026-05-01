"""Outbound queue delivery, receipt, and failure helpers."""

from __future__ import annotations

import time
from concurrent.futures import Future
from concurrent.futures import TimeoutError

import LXMF
import RNS

from reticulum_telemetry_hub.reticulum_server.appearance import apply_icon_appearance
from reticulum_telemetry_hub.reticulum_server.outbound_types import _PendingDispatch
from reticulum_telemetry_hub.reticulum_server.outbound_types import OutboundPayload
from reticulum_telemetry_hub.reticulum_server.propagation_selection import PropagationNodeCandidate


class OutboundQueueDeliveryMixin:
    """Build, send, and finalize outbound LXMF deliveries."""

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

        attempt_id = self._begin_attempt(payload)

        def _mark_receipt(
            delivered_message: LXMF.LXMessage,
            outbound_payload: OutboundPayload = payload,
            token: int = attempt_id,
        ) -> None:
            self._notify_delivery_receipt(
                delivered_message,
                outbound_payload,
                token,
            )

        def _mark_failure(
            failed_message: LXMF.LXMessage,
            outbound_payload: OutboundPayload = payload,
            token: int = attempt_id,
        ) -> None:
            self._notify_delivery_failure(
                failed_message,
                outbound_payload,
                token,
            )

        def _send() -> None:
            with self._active_dispatch_lock:
                self._active_dispatches += 1
            try:
                message = self._build_message(payload)
                message.register_delivery_callback(_mark_receipt)
                message.register_failed_callback(_mark_failure)
                self._lxm_router.handle_outbound(message)
            finally:
                with self._active_dispatch_lock:
                    self._active_dispatches -= 1

        future = self._send_executor.submit(_send)
        with self._in_progress_futures_lock:
            self._in_progress_futures += 1

        try:
            future.result(timeout=self._send_timeout)
        except TimeoutError:
            with self._timed_out_sends_lock:
                self._timed_out_sends += 1
            with self._stats_lock:
                self._timeout_total += 1
            self._record_counter("outbound_timeout_total")
            if payload.delivery_mode != "propagated":
                self._notify_direct_failure(payload, "send_timeout")
            key = (id(payload), attempt_id)
            pending = _PendingDispatch(payload, attempt_id, future, time.monotonic())
            with self._pending_dispatches_lock:
                self._pending_dispatches[key] = pending
            future.add_done_callback(lambda _future, k=key: self._on_pending_dispatch_done(k))
            RNS.log(
                (
                    "Timed out delivering outbound message to"
                    f" {payload.destination_hex or 'unknown destination'}; "
                    "waiting for dispatch completion before retrying"
                ),
                getattr(RNS, "LOG_WARNING", 2),
            )
            return None
        except Exception:
            return self._finalize_dispatch(payload, attempt_id, future)

        return self._finalize_dispatch(payload, attempt_id, future)

    def _on_pending_dispatch_done(self, key: tuple[int, int]) -> None:
        """Finalize a dispatch that previously timed out waiting on the caller thread."""

        with self._pending_dispatches_lock:
            pending = self._pending_dispatches.pop(key, None)
        if pending is None:
            return
        self._finalize_dispatch(pending.payload, pending.attempt_id, pending.future)

    def _finalize_dispatch(
        self,
        payload: OutboundPayload,
        attempt_id: int,
        future: Future[None],
    ) -> str | None:
        """Finalize a dispatch attempt after the router call completes."""

        with self._in_progress_futures_lock:
            self._in_progress_futures = max(self._in_progress_futures - 1, 0)
        try:
            future.result()
        except Exception as exc:
            RNS.log(
                (
                    "Failed to deliver outbound message to"
                    f" {payload.destination_hex or 'unknown destination'}: {exc}"
                ),
                getattr(RNS, "LOG_WARNING", 2),
            )
            if self._claim_attempt(payload, attempt_id):
                self._handle_delivery_attempt_failure(payload, reason="send_error")
                return None
            self._invalidate_attempt(payload, attempt_id)
            return "send_error"

        if self._delivery_receipt_timeout is None:
            return None
        if not self._attempt_is_active(payload, attempt_id):
            return None
        self._register_pending_receipt(payload, attempt_id)
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

        self._pop_pending_receipt(payload, attempt_id)
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

        self._pop_pending_receipt(payload, attempt_id)
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

    def _notify_direct_failure(self, payload: OutboundPayload, reason: str) -> None:
        """Emit the optional direct-failure callback."""

        callback = self._direct_failure_callback
        if callback is None:
            return
        try:
            callback(payload, reason)
        except Exception as exc:
            RNS.log(
                f"Outbound direct-failure callback failed: {exc}",
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

    def _notify_attempt_started(self, payload: OutboundPayload) -> None:
        """Emit the optional attempt-started callback."""

        callback = self._attempt_started_callback
        if callback is None:
            return
        try:
            callback(payload)
        except Exception as exc:
            RNS.log(
                f"Outbound attempt callback failed: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )

    def _notify_payload_dropped(self, payload: OutboundPayload, reason: str) -> None:
        """Emit the optional payload-dropped callback."""

        callback = self._payload_dropped_callback
        if callback is None:
            return
        try:
            callback(payload, reason)
        except Exception as exc:
            RNS.log(
                f"Outbound drop callback failed: {exc}",
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
            with self._stats_lock:
                self._propagation_fallback_total += 1
            self._record_counter("outbound_propagation_fallback_total")
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

        self._notify_direct_failure(payload, reason)
        payload.attempts += 1
        if payload.attempts < self._max_attempts:
            payload.next_attempt_at = (
                time.monotonic() + self._backoff_seconds * payload.attempts
            )
            if not self._enqueue_payload(payload):
                self._finalize_terminal_failure(payload, callback_message=callback_message)
                return
            with self._stats_lock:
                self._retry_total += 1
            self._record_counter("outbound_retry_total")
            self._notify_retry_scheduled(payload)
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
                if not self._enqueue_payload(payload):
                    self._finalize_terminal_failure(
                        payload,
                        callback_message=callback_message,
                    )
                    return
                with self._stats_lock:
                    self._propagation_fallback_total += 1
                self._record_counter("outbound_propagation_fallback_total")
                self._notify_propagation_fallback(payload)
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
