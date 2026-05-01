from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

import LXMF
import RNS

from reticulum_telemetry_hub.config.manager import HubConfigurationManager
from reticulum_telemetry_hub.embedded_lxmd.embedded_config import EmbeddedLxmdConfig
from reticulum_telemetry_hub.embedded_lxmd.embedded_prune import EmbeddedStartupPruneMixin
from reticulum_telemetry_hub.embedded_lxmd.embedded_stats import (
    EmbeddedPropagationStatsMixin,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.lxmf_propagation import (
    LXMFPropagation,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_enum import (
    SID_LXMF_PROPAGATION,
)
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog
from reticulum_telemetry_hub.reticulum_server.runtime_events import (
    report_nonfatal_exception,
)

if TYPE_CHECKING:
    from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
        TelemetryController,
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class EmbeddedLxmd(EmbeddedStartupPruneMixin, EmbeddedPropagationStatsMixin):
    """Run the LXMF router propagation loop within the current process.

    The stock ``lxmd`` daemon starts a couple of helper threads that periodically
    announces the delivery destination and, when configured, runs the propagation
    node loop. When the hub is executed in *embedded* mode those responsibilities
    need to run side-by-side with the main application instead of being spawned
    as a separate process. ``EmbeddedLxmd`` mirrors the subset of ``lxmd``'s
    behaviour that ReticulumTelemetryHub relies on and provides an explicit
    lifecycle so the threads can be shut down gracefully.
    """

    DEFERRED_JOBS_DELAY = 10
    JOBS_INTERVAL_SECONDS = 5

    PROPAGATION_UPTIME_GRANULARITY = 30

    def __init__(
        self,
        router: LXMF.LXMRouter,
        destination: RNS.Destination,
        config_manager: Optional[HubConfigurationManager] = None,
        telemetry_controller: Optional[TelemetryController] = None,
        event_log: EventLog | None = None,
    ) -> None:
        self.router = router
        self.destination = destination
        self.config_manager = config_manager or HubConfigurationManager()
        self.config = EmbeddedLxmdConfig.from_manager(self.config_manager)
        self.telemetry_controller = telemetry_controller
        self.event_log = event_log
        self._propagation_observers: list[Callable[[dict[str, Any]], None]] = []
        self._propagation_snapshot: bytes | None = None
        self._propagation_lock = threading.Lock()
        if self.telemetry_controller is not None:
            self.add_propagation_observer(self._persist_propagation_snapshot)
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self._started = False
        self._last_peer_announce: float | None = None
        self._last_node_announce: float | None = None
        self._propagation_state_lock = threading.Lock()
        self._propagation_state = (
            "idle" if self.config.enable_propagation_node else "disabled"
        )
        self._propagation_last_error: str | None = None
        self._propagation_started_monotonic: float | None = None
        self._propagation_finished_monotonic: float | None = None
        self._startup_prune_summary: dict[str, int] | None = None

    def start(self) -> None:
        """Start the embedded propagation threads if not already running."""

        if self._started:
            return

        if self.config.enable_propagation_node:
            mode = self.config.propagation_start_mode
            if mode == "blocking":
                self._enable_propagation()
                self._started = True
                self._start_thread(self._deferred_start_jobs)
                return

        self._started = True
        self._start_thread(self._deferred_start_jobs)

        if self.config.enable_propagation_node:
            self._start_thread(self._enable_propagation)

    def stop(self) -> None:
        """Request the helper threads to stop and wait for them to finish."""

        if not self._started:
            return

        self._stop_event.set()
        for thread in self._threads:
            thread.join()
        self._threads.clear()
        # Allow future ``start`` calls to run the deferred jobs loop again.
        self._stop_event.clear()
        self._started = False
        self._last_peer_announce = None
        self._last_node_announce = None
        next_state = "disabled" if not self.config.enable_propagation_node else "idle"
        self._set_propagation_state(next_state)
        self._maybe_emit_propagation_update(force=True)

    def add_propagation_observer(
        self, observer: Callable[[dict[str, Any]], None]
    ) -> None:
        """Register a callback notified whenever propagation state changes."""

        self._propagation_observers.append(observer)

    def _report_propagation_exception(
        self,
        message: str,
        exc: Exception,
        *,
        metadata: dict[str, object] | None = None,
        log_level: int | None = None,
    ) -> dict[str, object] | None:
        """Record a handled embedded-LXMD failure in logs and the event feed."""

        return report_nonfatal_exception(
            self.event_log,
            "propagation_error",
            message,
            exc,
            metadata=metadata,
            log_level=log_level if log_level is not None else getattr(RNS, "LOG_ERROR", 1),
        )

    def propagation_startup_status(self) -> dict[str, Any]:
        """Return propagation startup state for control/status endpoints."""

        with self._propagation_state_lock:
            state = self._propagation_state
            last_error = self._propagation_last_error
            started_at = self._propagation_started_monotonic
            finished_at = self._propagation_finished_monotonic
            prune_summary = (
                dict(self._startup_prune_summary)
                if self._startup_prune_summary is not None
                else None
            )

        elapsed = None
        if started_at is not None:
            end = finished_at if finished_at is not None else time.monotonic()
            elapsed = max(0.0, end - started_at)

        return {
            "enabled": self.config.enable_propagation_node,
            "start_mode": self.config.propagation_start_mode,
            "state": state,
            "ready": state == "ready" or not self.config.enable_propagation_node,
            "last_error": last_error,
            "index_duration_seconds": elapsed,
            "startup_prune": prune_summary,
        }

    # ------------------------------------------------------------------ #
    # private helpers
    # ------------------------------------------------------------------ #
    def _set_propagation_state(
        self,
        state: str,
        *,
        error: str | None = None,
        mark_started: bool = False,
        mark_finished: bool = False,
    ) -> None:
        now = time.monotonic()
        with self._propagation_state_lock:
            self._propagation_state = state
            if error is not None:
                self._propagation_last_error = error
            elif state != "error":
                self._propagation_last_error = None
            if mark_started:
                self._propagation_started_monotonic = now
                self._propagation_finished_monotonic = None
            if mark_finished:
                self._propagation_finished_monotonic = now
            if state == "indexing":
                self._startup_prune_summary = None

    def _is_propagation_ready(self) -> bool:
        if not self.config.enable_propagation_node:
            return False
        with self._propagation_state_lock:
            return self._propagation_state == "ready"

    def _enable_propagation(self) -> None:
        self._set_propagation_state("indexing", mark_started=True)
        startup_prune_started = time.monotonic()
        startup_prune_summary = self._prune_message_store_at_startup()
        if startup_prune_summary is not None:
            self._startup_prune_summary = startup_prune_summary
            startup_prune_elapsed = time.monotonic() - startup_prune_started
            RNS.log(
                "Startup messagestore pruning scanned "
                f"{startup_prune_summary['scanned']} files, removed "
                f"{startup_prune_summary['removed_invalid'] + startup_prune_summary['removed_expired'] + startup_prune_summary['removed_overflow']} "
                f"in {startup_prune_elapsed:.2f}s",
                RNS.LOG_NOTICE,
            )

        start = time.monotonic()
        try:
            self.router.enable_propagation()
        except Exception as exc:  # pragma: no cover - defensive logging
            self._set_propagation_state(
                "error",
                error=str(exc),
                mark_finished=True,
            )
            self._report_propagation_exception(
                f"Failed to enable LXMF propagation node in embedded mode: {exc}",
                exc,
                metadata={"operation": "enable_propagation"},
            )
            return

        elapsed = time.monotonic() - start
        self._set_propagation_state("ready", mark_finished=True)
        self._apply_propagation_runtime_config()
        RNS.log(
            f"LXMF propagation node ready in {elapsed:.2f}s",
            RNS.LOG_NOTICE,
        )

        if self._started and not self._stop_event.is_set():
            now = time.monotonic()
            if self._last_node_announce is None:
                if self.config.node_announce_at_start:
                    self._announce_propagation()
                    self._last_node_announce = now
                elif self.config.node_announce_interval_seconds is not None:
                    self._last_node_announce = now
            self._maybe_emit_propagation_update(force=True)

    def _start_thread(self, target) -> None:
        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        self._threads.append(thread)

    def _announce_delivery(self) -> None:
        try:
            self.router.announce(self.destination.hash)
        except Exception as exc:  # pragma: no cover - logging guard
            self._report_propagation_exception(
                f"Failed to announce embedded LXMF destination: {exc}",
                exc,
                metadata={"operation": "announce_delivery"},
            )

    def _announce_propagation(self) -> None:
        try:
            self.router.announce_propagation_node()
        except Exception as exc:  # pragma: no cover - logging guard
            self._report_propagation_exception(
                f"Failed to announce embedded propagation node: {exc}",
                exc,
                metadata={"operation": "announce_propagation"},
            )

    def _apply_propagation_runtime_config(self) -> None:
        if self.config.auth_required:
            try:
                self.router.set_authentication(required=True)
            except Exception as exc:  # pragma: no cover - logging guard
                self._report_propagation_exception(
                    f"Failed to enable LXMF propagation authentication: {exc}",
                    exc,
                    metadata={"operation": "set_authentication"},
                )

        for identity_hash in self.config.control_allowed_identities:
            try:
                self.router.allow_control(bytes.fromhex(identity_hash))
            except Exception as exc:  # pragma: no cover - logging guard
                self._report_propagation_exception(
                    f"Failed to add LXMF propagation control identity '{identity_hash}': {exc}",
                    exc,
                    metadata={
                        "operation": "allow_control",
                        "identity_hash": identity_hash,
                    },
                    log_level=RNS.LOG_WARNING,
                )

    def _persist_propagation_snapshot(self, payload: dict[str, Any]) -> None:
        if self.telemetry_controller is None:
            return

        sensor = LXMFPropagation()
        sensor.unpack(payload)
        packed_payload = sensor.pack()
        if packed_payload is None:
            return

        peer_hash = (
            RNS.hexrep(self.destination.hash, False)
            if hasattr(self.destination, "hash")
            else ""
        )

        try:
            self.telemetry_controller.save_telemetry(
                {SID_LXMF_PROPAGATION: packed_payload},
                peer_hash,
                _utcnow(),
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            self._report_propagation_exception(
                f"Failed to persist propagation telemetry: {exc}",
                exc,
                metadata={
                    "operation": "persist_telemetry",
                    "peer_hash": peer_hash,
                },
            )

    def _deferred_start_jobs(self) -> None:
        if self._stop_event.wait(self.DEFERRED_JOBS_DELAY):
            return

        now = time.monotonic()
        if self.config.peer_announce_at_start:
            self._announce_delivery()
            self._last_peer_announce = now
        elif self.config.peer_announce_interval_seconds is not None:
            self._last_peer_announce = now

        if self._is_propagation_ready():
            if self._last_node_announce is None:
                if self.config.node_announce_at_start:
                    self._announce_propagation()
                    self._last_node_announce = now
                elif self.config.node_announce_interval_seconds is not None:
                    self._last_node_announce = now

        self._maybe_emit_propagation_update(force=True)
        self._start_thread(self._jobs)

    def _jobs(self) -> None:
        peer_interval = self.config.peer_announce_interval_seconds
        node_interval = self.config.node_announce_interval_seconds
        while not self._stop_event.wait(self.JOBS_INTERVAL_SECONDS):
            self._maybe_emit_propagation_update()
            now = time.monotonic()
            if (
                peer_interval is not None
                and (
                    self._last_peer_announce is None
                    or now - self._last_peer_announce >= peer_interval
                )
            ):
                self._announce_delivery()
                self._last_peer_announce = now

            if not self._is_propagation_ready():
                continue

            if (
                node_interval is not None
                and (
                    self._last_node_announce is None
                    or now - self._last_node_announce >= node_interval
                )
            ):
                self._announce_propagation()
                self._last_node_announce = now

    # Allow usage as a context manager for convenience
    def __enter__(self) -> "EmbeddedLxmd":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
