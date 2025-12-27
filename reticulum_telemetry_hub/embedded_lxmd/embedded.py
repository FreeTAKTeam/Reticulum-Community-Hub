from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

import LXMF
import RNS
from msgpack import packb

from reticulum_telemetry_hub.config.manager import HubConfigurationManager
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.lxmf_propagation import (
    LXMFPropagation,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_enum import (
    SID_LXMF_PROPAGATION,
)

if TYPE_CHECKING:
    from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
        TelemetryController,
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


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

    PROPAGATION_UPTIME_GRANULARITY = 30

    def __init__(
        self,
        router: LXMF.LXMRouter,
        destination: RNS.Destination,
        config_manager: Optional[HubConfigurationManager] = None,
        telemetry_controller: Optional[TelemetryController] = None,
    ) -> None:
        self.router = router
        self.destination = destination
        self.config_manager = config_manager or HubConfigurationManager()
        self.config = EmbeddedLxmdConfig.from_manager(self.config_manager)
        self.telemetry_controller = telemetry_controller
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
            thread.join()
        self._threads.clear()
        # Allow future ``start`` calls to run the deferred jobs loop again.
        self._stop_event.clear()
        self._started = False
        self._maybe_emit_propagation_update(force=True)

    def add_propagation_observer(
        self, observer: Callable[[dict[str, Any]], None]
    ) -> None:
        """Register a callback notified whenever propagation state changes."""

        self._propagation_observers.append(observer)

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

    def _baseline_propagation_payload(self) -> dict[str, Any]:
        peers = getattr(self.router, "peers", {}) or {}
        static_peers = getattr(self.router, "static_peers", []) or []
        destination_hash = getattr(
            getattr(self.router, "propagation_destination", None), "hash", None
        )
        identity_hash = getattr(getattr(self.router, "identity", None), "hash", None)

        total_peers = len(peers)
        return {
            "destination_hash": destination_hash,
            "identity_hash": identity_hash,
            "uptime": None,
            "delivery_limit": getattr(self.router, "delivery_per_transfer_limit", None),
            "propagation_limit": getattr(
                self.router, "propagation_per_transfer_limit", None
            ),
            "autopeer_maxdepth": getattr(self.router, "autopeer_maxdepth", None),
            "from_static_only": getattr(self.router, "from_static_only", None),
            "messagestore": None,
            "clients": None,
            "unpeered_propagation_incoming": getattr(
                self.router, "unpeered_propagation_incoming", None
            ),
            "unpeered_propagation_rx_bytes": getattr(
                self.router, "unpeered_propagation_rx_bytes", None
            ),
            "static_peers": len(static_peers),
            "total_peers": total_peers,
            "active_peers": 0,
            "unreachable_peers": total_peers,
            "max_peers": getattr(self.router, "max_peers", None),
            "peered_propagation_rx_bytes": 0,
            "peered_propagation_tx_bytes": 0,
            "peered_propagation_offered": 0,
            "peered_propagation_outgoing": 0,
            "peered_propagation_incoming": 0,
            "peered_propagation_unhandled": 0,
            "peered_propagation_max_unhandled": 0,
            "peers": {},
        }

    def _normalize_propagation_stats(
        self, stats: dict[str, Any] | None
    ) -> dict[str, Any]:
        payload = self._baseline_propagation_payload()
        if not stats:
            return payload

        payload.update(
            {
                "destination_hash": stats.get("destination_hash")
                or payload["destination_hash"],
                "identity_hash": stats.get("identity_hash") or payload["identity_hash"],
                "uptime": stats.get("uptime"),
                "delivery_limit": stats.get("delivery_limit"),
                "propagation_limit": stats.get("propagation_limit"),
                "autopeer_maxdepth": stats.get("autopeer_maxdepth"),
                "from_static_only": stats.get("from_static_only"),
                "messagestore": stats.get("messagestore"),
                "clients": stats.get("clients"),
                "unpeered_propagation_incoming": stats.get(
                    "unpeered_propagation_incoming"
                ),
                "unpeered_propagation_rx_bytes": stats.get(
                    "unpeered_propagation_rx_bytes"
                ),
                "static_peers": stats.get("static_peers", payload["static_peers"]),
                "max_peers": stats.get("max_peers", payload["max_peers"]),
            }
        )

        peers_payload: dict[bytes, dict[str, Any]] = {}
        active = 0
        rx_sum = tx_sum = offered_sum = outgoing_sum = incoming_sum = unhandled_sum = 0
        max_unhandled = 0

        peer_stats = stats.get("peers") or {}
        for peer_hash, peer_data in sorted(
            peer_stats.items(), key=lambda item: item[0]
        ):
            if not isinstance(peer_hash, (bytes, bytearray, memoryview)):
                continue
            key = bytes(peer_hash)
            messages = peer_data.get("messages") or {}
            peers_payload[key] = {
                "type": peer_data.get("type"),
                "state": peer_data.get("state"),
                "alive": peer_data.get("alive"),
                "last_heard": peer_data.get("last_heard"),
                "next_sync_attempt": peer_data.get("next_sync_attempt"),
                "last_sync_attempt": peer_data.get("last_sync_attempt"),
                "sync_backoff": peer_data.get("sync_backoff"),
                "peering_timebase": peer_data.get("peering_timebase"),
                "ler": peer_data.get("ler"),
                "str": peer_data.get("str"),
                "transfer_limit": peer_data.get("transfer_limit"),
                "network_distance": peer_data.get("network_distance"),
                "rx_bytes": peer_data.get("rx_bytes"),
                "tx_bytes": peer_data.get("tx_bytes"),
                "messages": {
                    "offered": messages.get("offered"),
                    "outgoing": messages.get("outgoing"),
                    "incoming": messages.get("incoming"),
                    "unhandled": messages.get("unhandled"),
                },
            }

            if peer_data.get("alive"):
                active += 1

            rx_sum += peer_data.get("rx_bytes") or 0
            tx_sum += peer_data.get("tx_bytes") or 0
            offered = messages.get("offered") or 0
            outgoing = messages.get("outgoing") or 0
            incoming = messages.get("incoming") or 0
            unhandled = messages.get("unhandled") or 0

            offered_sum += offered
            outgoing_sum += outgoing
            incoming_sum += incoming
            unhandled_sum += unhandled
            if unhandled > max_unhandled:
                max_unhandled = unhandled

        total_peers = stats.get("total_peers")
        if total_peers is None:
            total_peers = len(peers_payload)

        payload.update(
            {
                "peers": peers_payload,
                "total_peers": total_peers,
                "active_peers": active,
                "unreachable_peers": max(total_peers - active, 0),
                "peered_propagation_rx_bytes": rx_sum,
                "peered_propagation_tx_bytes": tx_sum,
                "peered_propagation_offered": offered_sum,
                "peered_propagation_outgoing": outgoing_sum,
                "peered_propagation_incoming": incoming_sum,
                "peered_propagation_unhandled": unhandled_sum,
                "peered_propagation_max_unhandled": max_unhandled,
            }
        )

        return payload

    def _build_propagation_payload(self) -> dict[str, Any] | None:
        try:
            stats = self.router.compile_stats()
        except Exception as exc:  # pragma: no cover - defensive logging
            RNS.log(
                f"Failed to compile LXMF propagation stats: {exc}",
                RNS.LOG_ERROR,
            )
            return None

        return self._normalize_propagation_stats(stats)

    def _maybe_emit_propagation_update(self, *, force: bool = False) -> None:
        if not self._propagation_observers:
            return

        payload = self._build_propagation_payload()
        if payload is None:
            return

        comparison_payload = dict(payload)
        uptime = comparison_payload.get("uptime")
        if uptime is not None:
            comparison_payload["uptime"] = (
                int(uptime) // self.PROPAGATION_UPTIME_GRANULARITY
            )

        packed = packb(comparison_payload, use_bin_type=True)

        with self._propagation_lock:
            if not force and packed == self._propagation_snapshot:
                return
            self._propagation_snapshot = packed

        self._notify_propagation_observers(payload)

    def _notify_propagation_observers(self, payload: dict[str, Any]) -> None:
        for observer in list(self._propagation_observers):
            try:
                observer(payload)
            except Exception as exc:  # pragma: no cover - defensive logging
                RNS.log(
                    f"Propagation observer failed: {exc}",
                    RNS.LOG_ERROR,
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
            RNS.log(
                f"Failed to persist propagation telemetry: {exc}",
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

        self._maybe_emit_propagation_update(force=True)
        self._start_thread(self._jobs)

    def _jobs(self) -> None:
        interval = self.config.announce_interval_seconds
        while not self._stop_event.wait(self.JOBS_INTERVAL_SECONDS):
            self._maybe_emit_propagation_update()
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
