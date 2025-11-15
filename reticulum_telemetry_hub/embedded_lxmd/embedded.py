from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

import LXMF
import RNS

from reticulum_telemetry_hub.config.manager import HubConfigurationManager


@dataclass
class EmbeddedLxmdConfig:
    """Runtime configuration for the embedded LXMD service."""

    enable_propagation_node: bool
    announce_interval_seconds: int

    @classmethod
    def from_manager(cls, manager: HubConfigurationManager) -> "EmbeddedLxmdConfig":
        lxmf_config = manager.config.lxmf_router
        interval = max(1, int(lxmf_config.announce_interval_minutes) * 60)
        return cls(
            enable_propagation_node=lxmf_config.enable_node,
            announce_interval_seconds=interval,
        )


class EmbeddedLxmd:
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

    def __init__(
        self,
        router: LXMF.LXMRouter,
        destination: RNS.Destination,
        config_manager: Optional[HubConfigurationManager] = None,
    ) -> None:
        self.router = router
        self.destination = destination
        self.config_manager = config_manager or HubConfigurationManager()
        self.config = EmbeddedLxmdConfig.from_manager(self.config_manager)
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self._started = False
        self._last_peer_announce: float | None = None
        self._last_node_announce: float | None = None

    def start(self) -> None:
        """Start the embedded propagation threads if not already running."""

        if self._started:
            return

        if self.config.enable_propagation_node:
            try:
                self.router.enable_propagation()
            except Exception as exc:  # pragma: no cover - defensive logging
                RNS.log(
                    f"Failed to enable LXMF propagation node in embedded mode: {exc}",
                    RNS.LOG_ERROR,
                )

        self._started = True
        self._start_thread(self._deferred_start_jobs)

    def stop(self) -> None:
        """Request the helper threads to stop and wait for them to finish."""

        if not self._started:
            return

        self._stop_event.set()
        for thread in self._threads:
            thread.join(timeout=1)
        self._threads.clear()
        self._started = False

    # ------------------------------------------------------------------ #
    # private helpers
    # ------------------------------------------------------------------ #
    def _start_thread(self, target) -> None:
        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        self._threads.append(thread)

    def _announce_delivery(self) -> None:
        try:
            self.router.announce(self.destination.hash)
        except Exception as exc:  # pragma: no cover - logging guard
            RNS.log(
                f"Failed to announce embedded LXMF destination: {exc}",
                RNS.LOG_ERROR,
            )

    def _announce_propagation(self) -> None:
        try:
            self.router.announce_propagation_node()
        except Exception as exc:  # pragma: no cover - logging guard
            RNS.log(
                f"Failed to announce embedded propagation node: {exc}",
                RNS.LOG_ERROR,
            )

    def _deferred_start_jobs(self) -> None:
        if self._stop_event.wait(self.DEFERRED_JOBS_DELAY):
            return

        self._announce_delivery()
        self._last_peer_announce = time.monotonic()

        if self.config.enable_propagation_node:
            self._announce_propagation()
            self._last_node_announce = self._last_peer_announce

        self._start_thread(self._jobs)

    def _jobs(self) -> None:
        interval = self.config.announce_interval_seconds
        while not self._stop_event.wait(self.JOBS_INTERVAL_SECONDS):
            now = time.monotonic()
            if (
                self._last_peer_announce is None
                or now - self._last_peer_announce >= interval
            ):
                self._announce_delivery()
                self._last_peer_announce = now

            if not self.config.enable_propagation_node:
                continue

            if (
                self._last_node_announce is None
                or now - self._last_node_announce >= interval
            ):
                self._announce_propagation()
                self._last_node_announce = now

    # Allow usage as a context manager for convenience
    def __enter__(self) -> "EmbeddedLxmd":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
