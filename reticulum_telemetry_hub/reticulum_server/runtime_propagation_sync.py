"""Announce capability and propagation sync helpers."""
# ruff: noqa: F403,F405

from __future__ import annotations

import threading
import time
from typing import cast

import RNS

import reticulum_telemetry_hub.lxmf_runtime  # noqa: F401
from reticulum_telemetry_hub.config.constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.announce_capabilities import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.delivery_defaults import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.propagation_selection import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_support import *  # noqa: F403

class RuntimePropagationSyncMixin:
    """Propagation sync worker helpers."""

    def _current_propagation_sync_interval_seconds(self) -> int:
        """Return the active propagation sync interval in seconds."""

        lxmf_config = getattr(getattr(self.config_manager, "config", None), "lxmf_router", None)
        minutes = getattr(lxmf_config, "propagation_sync_interval_minutes", 10)
        try:
            parsed = int(minutes)
        except (TypeError, ValueError):
            parsed = 10
        return max(1, parsed) * 60

    def request_propagation_sync(self, *, reason: str = "manual") -> dict[str, object]:
        """Request LXMF messages from the best reachable propagation node."""

        if not hasattr(self, "_propagation_sync_lock"):
            self._propagation_sync_lock = threading.Lock()
        if not self._propagation_sync_lock.acquire(blocking=False):
            return {
                "status": "sync_in_progress",
                "detail": "Propagation sync already running",
            }
        try:
            candidate = self._select_best_propagation_node()
            if candidate is None:
                return {
                    "status": "unavailable",
                    "detail": "No reachable propagation node",
                }
            destination = getattr(self, "my_lxmf_dest", None)
            identity = getattr(destination, "identity", None)
            if identity is None:
                return {
                    "status": "unavailable",
                    "detail": "No LXMF delivery identity available",
                }
            router = getattr(self, "lxm_router", None)
            if router is None:
                return {"status": "unavailable", "detail": "LXMF router unavailable"}

            router.set_active_propagation_node(candidate.destination_hash)
            router.request_messages_from_propagation_node(identity)
            return {
                "status": "sync_requested",
                "reason": reason,
                "propagation_node": candidate.destination_hex,
                "transfer_state": getattr(router, "propagation_transfer_state", None),
                "transfer_progress": getattr(router, "propagation_transfer_progress", None),
                "last_result": getattr(router, "propagation_transfer_last_result", None),
                "last_duplicates": getattr(
                    router,
                    "propagation_transfer_last_duplicates",
                    None,
                ),
            }
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            RNS.log(
                f"Propagation sync failed: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return {"status": "error", "detail": str(exc)}
        finally:
            self._propagation_sync_lock.release()

    def _start_propagation_sync_worker(self) -> None:
        """Start the automatic propagation sync worker once."""

        if not hasattr(self, "_propagation_sync_stop_event"):
            self._propagation_sync_stop_event = threading.Event()
        existing = getattr(self, "_propagation_sync_thread", None)
        if existing is not None and existing.is_alive():
            return
        self._propagation_sync_stop_event.clear()
        self._propagation_sync_thread = threading.Thread(
            target=self._propagation_sync_worker,
            name="rch-propagation-sync",
            daemon=True,
        )
        self._propagation_sync_thread.start()

    def _stop_propagation_sync_worker(self) -> None:
        """Stop the automatic propagation sync worker."""

        stop_event = getattr(self, "_propagation_sync_stop_event", None)
        if stop_event is not None:
            stop_event.set()
        thread = getattr(self, "_propagation_sync_thread", None)
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
        self._propagation_sync_thread = None

    def _propagation_sync_worker(self) -> None:
        """Periodically retrieve pending LXMF messages from propagation."""

        last_sync = time.monotonic()
        while not self._shutdown:
            stop_event = getattr(self, "_propagation_sync_stop_event", None)
            if stop_event is not None and stop_event.wait(5.0):
                return
            interval = self._current_propagation_sync_interval_seconds()
            now = time.monotonic()
            if now - last_sync < interval:
                continue
            last_sync = now
            result = self.request_propagation_sync(reason="automatic")
            if result.get("status") not in {
                "sync_requested",
                "sync_in_progress",
                "unavailable",
            }:
                RNS.log(
                    f"Automatic propagation sync result: {result}",
                    getattr(RNS, "LOG_WARNING", 2),
                )

    def get_propagation_startup_status(self) -> dict[str, object]:
        """Return the embedded propagation startup state."""

        embedded = self.embedded_lxmd
        if embedded is None:
            return {
                "enabled": False,
                "start_mode": "external",
                "state": "unmanaged",
                "ready": False,
                "last_error": None,
                "index_duration_seconds": None,
                "startup_prune": None,
            }
        status = embedded.propagation_startup_status()
        return cast(dict[str, object], status)

