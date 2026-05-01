"""Propagation stats normalization and observer notification helpers."""

from __future__ import annotations

from typing import Any

from msgpack import packb


class EmbeddedPropagationStatsMixin:
    """Build normalized LXMF propagation payloads and emit changes."""

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
            self._report_propagation_exception(
                f"Failed to compile LXMF propagation stats: {exc}",
                exc,
                metadata={"operation": "compile_stats"},
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
                self._report_propagation_exception(
                    f"Propagation observer failed: {exc}",
                    exc,
                    metadata={
                        "operation": "observer",
                        "observer": repr(observer),
                    },
                )
