from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
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
    propagation_start_mode: str
    propagation_startup_prune_enabled: bool
    propagation_startup_max_messages: int | None
    propagation_startup_max_age_days: int | None

    @classmethod
    def from_manager(cls, manager: HubConfigurationManager) -> "EmbeddedLxmdConfig":
        lxmf_config = manager.config.lxmf_router
        interval = max(1, int(lxmf_config.announce_interval_minutes) * 60)
        startup_mode = str(
            getattr(lxmf_config, "propagation_start_mode", "background")
        ).strip().lower()
        if startup_mode not in {"blocking", "background"}:
            startup_mode = "background"
        return cls(
            enable_propagation_node=lxmf_config.enable_node,
            announce_interval_seconds=interval,
            propagation_start_mode=startup_mode,
            propagation_startup_prune_enabled=bool(
                getattr(lxmf_config, "propagation_startup_prune_enabled", False)
            ),
            propagation_startup_max_messages=getattr(
                lxmf_config, "propagation_startup_max_messages", None
            ),
            propagation_startup_max_age_days=getattr(
                lxmf_config, "propagation_startup_max_age_days", None
            ),
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
        next_state = "disabled" if not self.config.enable_propagation_node else "idle"
        self._set_propagation_state(next_state)
        self._maybe_emit_propagation_update(force=True)

    def add_propagation_observer(
        self, observer: Callable[[dict[str, Any]], None]
    ) -> None:
        """Register a callback notified whenever propagation state changes."""

        self._propagation_observers.append(observer)

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

    def _message_store_path(self) -> Path | None:
        storage_path = getattr(self.router, "storagepath", None)
        if storage_path is None:
            return None
        return Path(str(storage_path)) / "messagestore"

    @staticmethod
    def _parse_store_filename(filename: str) -> float | None:
        components = filename.split("_")
        if len(components) < 3:
            return None

        expected_hash_hex_length = (RNS.Identity.HASHLENGTH // 8) * 2
        if len(components[0]) != expected_hash_hex_length:
            return None

        try:
            received = float(components[1])
            if received <= 0:
                return None
            int(components[2])
        except (TypeError, ValueError):
            return None

        return received

    @staticmethod
    def _remove_startup_files(
        paths: list[str],
        *,
        reason: str,
    ) -> int:
        removed = 0
        for path in paths:
            try:
                os.unlink(path)
                removed += 1
            except FileNotFoundError:
                continue
            except Exception as exc:  # pragma: no cover - defensive logging
                RNS.log(
                    f"Failed to remove {reason} startup message file '{path}': {exc}",
                    RNS.LOG_WARNING,
                )
        return removed

    def _prune_message_store_at_startup(self) -> dict[str, int] | None:
        if not self.config.propagation_startup_prune_enabled:
            return None

        message_store = self._message_store_path()
        if message_store is None or not message_store.is_dir():
            return {
                "scanned": 0,
                "kept": 0,
                "removed_invalid": 0,
                "removed_expired": 0,
                "removed_overflow": 0,
            }

        max_messages = self.config.propagation_startup_max_messages
        max_age_days = self.config.propagation_startup_max_age_days
        now = time.time()
        expiry_seconds = max_age_days * 24 * 60 * 60 if max_age_days else None
        cutoff = (now - expiry_seconds) if expiry_seconds else None

        scanned = 0
        valid_entries: list[tuple[float, str]] = []
        invalid_paths: list[str] = []

        with os.scandir(message_store) as iterator:
            for entry in iterator:
                if not entry.is_file():
                    continue
                scanned += 1
                received = self._parse_store_filename(entry.name)
                if received is None:
                    invalid_paths.append(entry.path)
                    continue
                valid_entries.append((received, entry.path))

        removed_invalid = self._remove_startup_files(
            invalid_paths,
            reason="invalid",
        )

        removed_expired = 0
        filtered_entries = valid_entries
        if cutoff is not None:
            expired_paths = [path for received, path in filtered_entries if received < cutoff]
            filtered_entries = [
                (received, path)
                for received, path in filtered_entries
                if received >= cutoff
            ]
            removed_expired = self._remove_startup_files(
                expired_paths,
                reason="expired",
            )

        removed_overflow = 0
        if max_messages is not None and len(filtered_entries) > max_messages:
            filtered_entries.sort(key=lambda item: item[0], reverse=True)
            overflow_paths = [
                path for _, path in filtered_entries[max_messages:]
            ]
            filtered_entries = filtered_entries[:max_messages]
            removed_overflow = self._remove_startup_files(
                overflow_paths,
                reason="overflow",
            )

        return {
            "scanned": scanned,
            "kept": len(filtered_entries),
            "removed_invalid": removed_invalid,
            "removed_expired": removed_expired,
            "removed_overflow": removed_overflow,
        }

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
            RNS.log(
                f"Failed to enable LXMF propagation node in embedded mode: {exc}",
                RNS.LOG_ERROR,
            )
            return

        elapsed = time.monotonic() - start
        self._set_propagation_state("ready", mark_finished=True)
        RNS.log(
            f"LXMF propagation node ready in {elapsed:.2f}s",
            RNS.LOG_NOTICE,
        )

        if self._started and not self._stop_event.is_set():
            self._announce_propagation()
            self._last_node_announce = time.monotonic()
            self._maybe_emit_propagation_update(force=True)

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

        if self._is_propagation_ready():
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

            if not self._is_propagation_ready():
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
