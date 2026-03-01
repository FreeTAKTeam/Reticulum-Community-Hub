"""Propagation-node discovery and selection helpers."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable

import RNS
import RNS.vendor.umsgpack as msgpack

from reticulum_telemetry_hub.lxmf_daemon.LXMF import APP_NAME as LXMF_APP_NAME
from reticulum_telemetry_hub.lxmf_daemon.LXMF import pn_announce_data_is_valid

PROPAGATION_NODE_TTL_SECONDS = 3600


@dataclass(frozen=True)
class PropagationNodeCandidate:
    """Describe a remote propagation node observed from announces."""

    destination_hash: bytes
    destination_hex: str
    hops: int | None
    stamp_cost: int | None
    transfer_limit: int | None
    sync_limit: int | None
    last_announced_at: float
    propagation_enabled: bool


class PropagationNodeRegistry:
    """Track propagation-node announces and choose the best current candidate."""

    def __init__(
        self,
        *,
        ttl_seconds: int = PROPAGATION_NODE_TTL_SECONDS,
        time_fn: Callable[[], float] | None = None,
        has_path: Callable[[bytes], bool] | None = None,
        hops_to: Callable[[bytes], int | None] | None = None,
    ) -> None:
        self._ttl_seconds = max(int(ttl_seconds), 1)
        self._time_fn = time_fn or time.time
        self._has_path = has_path or self._default_has_path
        self._hops_to = hops_to or self._default_hops_to
        self._lock = threading.Lock()
        self._candidates: dict[str, PropagationNodeCandidate] = {}

    @staticmethod
    def _default_has_path(destination_hash: bytes) -> bool:
        """Return True when Reticulum currently knows a path to the node."""

        return bool(RNS.Transport.has_path(destination_hash))

    @staticmethod
    def _default_hops_to(destination_hash: bytes) -> int | None:
        """Return the current Reticulum hop count for the node."""

        return RNS.Transport.hops_to(destination_hash)

    def record_announce(
        self,
        *,
        destination_hash: bytes,
        hops: int | None,
        stamp_cost: int | None,
        transfer_limit: int | None,
        sync_limit: int | None,
        propagation_enabled: bool,
        last_announced_at: float | None = None,
    ) -> PropagationNodeCandidate:
        """Store or replace a propagation-node candidate."""

        candidate = PropagationNodeCandidate(
            destination_hash=bytes(destination_hash),
            destination_hex=bytes(destination_hash).hex().lower(),
            hops=hops,
            stamp_cost=stamp_cost,
            transfer_limit=transfer_limit,
            sync_limit=sync_limit,
            last_announced_at=last_announced_at
            if last_announced_at is not None
            else self._time_fn(),
            propagation_enabled=bool(propagation_enabled),
        )
        with self._lock:
            self._candidates[candidate.destination_hex] = candidate
        return candidate

    def has_path(self, destination_hash: bytes) -> bool:
        """Return True when Reticulum currently knows a path to the node."""

        return self._has_path(destination_hash)

    def hops_to(self, destination_hash: bytes) -> int | None:
        """Return the current Reticulum hop count for the node."""

        return self._hops_to(destination_hash)

    def snapshot(self) -> dict[str, PropagationNodeCandidate]:
        """Return a copy of the current candidate map."""

        with self._lock:
            return dict(self._candidates)

    def best_candidate(self) -> PropagationNodeCandidate | None:
        """Return the best reachable propagation node for fallback delivery."""

        now = self._time_fn()
        with self._lock:
            candidates = list(self._candidates.values())

        eligible: list[PropagationNodeCandidate] = []
        for candidate in candidates:
            if not candidate.propagation_enabled:
                continue
            if now - candidate.last_announced_at > self._ttl_seconds:
                continue
            if not self._has_path(candidate.destination_hash):
                continue
            hops = self._hops_to(candidate.destination_hash)
            if hops is None or hops < 0:
                continue
            if candidate.hops != hops:
                candidate = PropagationNodeCandidate(
                    destination_hash=candidate.destination_hash,
                    destination_hex=candidate.destination_hex,
                    hops=hops,
                    stamp_cost=candidate.stamp_cost,
                    transfer_limit=candidate.transfer_limit,
                    sync_limit=candidate.sync_limit,
                    last_announced_at=candidate.last_announced_at,
                    propagation_enabled=candidate.propagation_enabled,
                )
            eligible.append(candidate)

        if not eligible:
            return None

        eligible.sort(
            key=lambda candidate: (
                candidate.hops if candidate.hops is not None else 1 << 30,
                candidate.stamp_cost
                if candidate.stamp_cost is not None
                else 1 << 30,
                -candidate.last_announced_at,
            )
        )
        return eligible[0]

    def best_candidate_hash(self) -> bytes | None:
        """Return the raw destination hash for the best candidate."""

        candidate = self.best_candidate()
        if candidate is None:
            return None
        return candidate.destination_hash


class PropagationNodeAnnounceHandler:
    """Reticulum announce handler that records remote propagation nodes."""

    def __init__(self, registry: PropagationNodeRegistry) -> None:
        self.aspect_filter = f"{LXMF_APP_NAME}.propagation"
        self._registry = registry

    def received_announce(self, destination_hash, announced_identity, app_data) -> None:
        """Process propagation announces and update the registry."""

        del announced_identity
        if not isinstance(destination_hash, (bytes, bytearray, memoryview)):
            return
        if not isinstance(app_data, bytes) or not pn_announce_data_is_valid(app_data):
            return

        try:
            decoded = msgpack.unpackb(app_data)
        except Exception:
            return
        if not isinstance(decoded, list) or len(decoded) < 7:
            return

        propagation_enabled = bool(decoded[2])
        if not propagation_enabled:
            return

        raw_hash = bytes(destination_hash)
        hops = None
        if self._registry.has_path(raw_hash):
            hops = self._registry.hops_to(raw_hash)

        stamp_cost = None
        if isinstance(decoded[5], list) and decoded[5]:
            try:
                stamp_cost = int(decoded[5][0])
            except (TypeError, ValueError):
                stamp_cost = None

        transfer_limit = None
        sync_limit = None
        try:
            transfer_limit = int(decoded[3])
        except (TypeError, ValueError):
            transfer_limit = None
        try:
            sync_limit = int(decoded[4])
        except (TypeError, ValueError):
            sync_limit = None

        self._registry.record_announce(
            destination_hash=raw_hash,
            hops=hops,
            stamp_cost=stamp_cost,
            transfer_limit=transfer_limit,
            sync_limit=sync_limit,
            propagation_enabled=propagation_enabled,
        )
