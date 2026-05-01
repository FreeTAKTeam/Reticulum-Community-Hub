"""Runtime state, metrics, identity, and persisted-client helpers."""
# ruff: noqa: F403,F405

from __future__ import annotations


import RNS

import reticulum_telemetry_hub.lxmf_runtime  # noqa: F401
from reticulum_telemetry_hub.config.constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.announce_capabilities import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.delivery_defaults import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.outbound_queue import OutboundMessageQueue
from reticulum_telemetry_hub.reticulum_server.propagation_selection import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_metrics_store import RuntimeMetricsStore
from reticulum_telemetry_hub.reticulum_server.runtime_constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_support import *  # noqa: F403


class RuntimeStateMixin:
    """Runtime state, metrics, identity, and persisted-client helpers."""

    def _announce_active_markers(self) -> None:
        """Announce non-expired marker objects on schedule."""

        manager = getattr(self, "marker_manager", None)
        service = getattr(self, "marker_service", None)
        if manager is None or service is None:
            return
        try:
            markers = service.list_markers()
        except Exception as exc:  # pragma: no cover - defensive logging
            RNS.log(
                f"Failed to list markers for announce: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return
        manager.announce_active_markers(markers)

    def _origin_rch_hex(self) -> str:
        """Return the local collector identity hash as lowercase hex."""

        destination = getattr(self, "my_lxmf_dest", None)
        identity_hash = getattr(destination, "hash", None)
        if isinstance(identity_hash, (bytes, bytearray, memoryview)):
            return bytes(identity_hash).hex()
        return ""

    def _ensure_outbound_queue(self) -> OutboundMessageQueue | None:
        """Initialize and start the outbound worker queue."""

        return self._delivery_service().ensure_outbound_queue()


    def wait_for_outbound_flush(self, timeout: float = 1.0) -> bool:
        """
        Wait until outbound messages clear the queue.

        Args:
            timeout (float): Seconds to wait before giving up.

        Returns:
            bool: ``True`` when the queue drained before the timeout elapsed.
        """

        queue = getattr(self, "_outbound_queue", None)
        if queue is None:
            return True
        return queue.wait_for_flush(timeout=timeout)

    def _runtime_metrics_store(self) -> RuntimeMetricsStore:
        """Return the runtime metrics store, creating one for test stubs if missing."""

        metrics = getattr(self, "runtime_metrics", None)
        if metrics is None:
            metrics = RuntimeMetricsStore()
            self.runtime_metrics = metrics
        return metrics

    @property
    def outbound_queue(self) -> OutboundMessageQueue | None:
        """Return the active outbound queue instance for diagnostics/testing."""

        return self._outbound_queue

    def runtime_metrics_snapshot(self) -> dict[str, object]:
        """Return runtime counters, gauges, timers, and queue state."""

        snapshot = self._runtime_metrics_store().snapshot()
        queue = getattr(self, "_outbound_queue", None)
        if queue is not None:
            try:
                snapshot["queue"] = queue.stats()
            except Exception as exc:  # pragma: no cover - defensive
                RNS.log(
                    f"Failed to collect outbound queue diagnostics: {exc}",
                    getattr(RNS, "LOG_WARNING", 2),
                )
        return snapshot

    def log_delivery_details(self, message, time_string, signature_string):
        RNS.log("\t+--- LXMF Delivery ---------------------------------------------")
        RNS.log(f"\t| Source hash            : {RNS.prettyhexrep(message.source_hash)}")
        RNS.log(f"\t| Source instance        : {message.get_source()}")
        RNS.log(
            f"\t| Destination hash       : {RNS.prettyhexrep(message.destination_hash)}"
        )
        # RNS.log(f"\t| Destination identity   : {message.source_identity}")
        RNS.log(f"\t| Destination instance   : {message.get_destination()}")
        RNS.log(f"\t| Transport Encryption   : {message.transport_encryption}")
        RNS.log(f"\t| Timestamp              : {time_string}")
        RNS.log(f"\t| Title                  : {message.title_as_string()}")
        RNS.log(f"\t| Content                : {message.content_as_string()}")
        RNS.log(f"\t| Fields                 : {message.fields}")
        RNS.log(f"\t| Message signature      : {signature_string}")
        RNS.log("\t+---------------------------------------------------------------")

    def _lookup_identity_label(self, source_hash) -> str:
        if isinstance(source_hash, (bytes, bytearray)):
            hash_key = source_hash.hex().lower()
            pretty = RNS.prettyhexrep(source_hash)
        elif source_hash:
            hash_key = str(source_hash).lower()
            pretty = hash_key
        else:
            return "unknown"
        label = self.identities.get(hash_key)
        if not label:
            api = getattr(self, "api", None)
            if api is not None and hasattr(api, "resolve_identity_display_name"):
                try:
                    label = api.resolve_identity_display_name(hash_key)
                except Exception as exc:  # pragma: no cover - defensive log
                    RNS.log(
                        f"Failed to resolve announce display name for {hash_key}: {exc}",
                        getattr(RNS, "LOG_WARNING", 2),
                    )
                if label:
                    self.identities[hash_key] = label
        return label or pretty

    def _backfill_identity_announces(self) -> None:
        api = getattr(self, "api", None)
        storage = getattr(api, "_storage", None)
        if storage is None:
            return
        try:
            records = storage.list_identity_announces()
        except Exception as exc:  # pragma: no cover - defensive log
            RNS.log(
                f"Failed to load announce records for backfill: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return

        if not records:
            return

        existing = {record.destination_hash.lower() for record in records}
        created = 0
        for record in records:
            if not record.display_name:
                continue
            try:
                destination_bytes = bytes.fromhex(record.destination_hash)
            except ValueError:
                continue
            identity = RNS.Identity.recall(destination_bytes)
            if identity is None:
                continue
            identity_hash = identity.hash.hex().lower()
            if identity_hash in existing:
                continue
            try:
                api.record_identity_announce(
                    identity_hash,
                    display_name=record.display_name,
                    source_interface="identity",
                )
            except Exception as exc:  # pragma: no cover - defensive log
                RNS.log(
                    (
                        "Failed to backfill announce metadata for "
                        f"{identity_hash}: {exc}"
                    ),
                    getattr(RNS, "LOG_WARNING", 2),
                )
                continue
            existing.add(identity_hash)
            created += 1

        if created:
            RNS.log(
                f"Backfilled {created} identity announce records for display names.",
                getattr(RNS, "LOG_INFO", 3),
            )

    def _load_persisted_clients(self) -> None:
        api = getattr(self, "api", None)
        if api is None:
            return
        try:
            clients = api.list_clients()
        except Exception as exc:  # pragma: no cover - defensive log
            RNS.log(
                f"Failed to load persisted clients: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return

        loaded = 0
        for client in clients:
            identity = getattr(client, "identity", None)
            if not identity:
                continue
            try:
                identity_hash = bytes.fromhex(identity)
            except ValueError:
                continue
            if identity_hash in self.connections:
                continue
            try:
                recalled = RNS.Identity.recall(identity_hash, from_identity_hash=True)
            except Exception:
                recalled = None
            if recalled is None:
                continue
            try:
                dest = RNS.Destination(
                    recalled,
                    RNS.Destination.OUT,
                    RNS.Destination.SINGLE,
                    "lxmf",
                    "delivery",
                )
            except Exception:
                continue
            setattr(dest, "_rch_cold_cache", True)
            self.connections[dest.identity.hash] = dest
            self._cache_destination(dest)
            loaded += 1

        if loaded:
            RNS.log(
                f"Loaded {loaded} persisted clients into the connection cache.",
                getattr(RNS, "LOG_INFO", 3),
            )

