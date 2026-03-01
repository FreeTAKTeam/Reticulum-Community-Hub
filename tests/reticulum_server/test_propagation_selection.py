import time

import RNS
import RNS.vendor.umsgpack as msgpack

from reticulum_telemetry_hub.reticulum_server.propagation_selection import (
    PropagationNodeAnnounceHandler,
)
from reticulum_telemetry_hub.reticulum_server.propagation_selection import (
    PropagationNodeRegistry,
)


def _build_propagation_announce(
    *,
    enabled: bool,
    transfer_limit: int = 512,
    sync_limit: int = 2048,
    stamp_cost: int = 3,
) -> bytes:
    return msgpack.packb(
        [
            False,
            int(time.time()),
            enabled,
            transfer_limit,
            sync_limit,
            [stamp_cost, 0, 0],
            {},
        ]
    )


def test_propagation_announce_handler_records_valid_candidates(monkeypatch):
    monkeypatch.setattr(RNS.Transport, "has_path", lambda destination_hash: True)
    monkeypatch.setattr(RNS.Transport, "hops_to", lambda destination_hash: 2)
    registry = PropagationNodeRegistry()
    handler = PropagationNodeAnnounceHandler(registry)
    destination_hash = b"\x11" * 16

    handler.received_announce(
        destination_hash,
        None,
        _build_propagation_announce(enabled=True, stamp_cost=7),
    )

    snapshot = registry.snapshot()
    assert destination_hash.hex() in snapshot
    candidate = registry.best_candidate()
    assert candidate is not None
    assert candidate.destination_hash == destination_hash
    assert candidate.hops == 2
    assert candidate.stamp_cost == 7
    assert candidate.transfer_limit == 512
    assert candidate.sync_limit == 2048


def test_propagation_announce_handler_ignores_disabled_nodes(monkeypatch):
    monkeypatch.setattr(RNS.Transport, "has_path", lambda destination_hash: True)
    monkeypatch.setattr(RNS.Transport, "hops_to", lambda destination_hash: 1)
    registry = PropagationNodeRegistry()
    handler = PropagationNodeAnnounceHandler(registry)

    handler.received_announce(
        b"\x22" * 16,
        None,
        _build_propagation_announce(enabled=False),
    )

    assert registry.snapshot() == {}
    assert registry.best_candidate() is None


def test_propagation_registry_prefers_hops_then_cost_then_freshness():
    now = 5000.0
    reachable = {
        (b"\x33" * 16).hex(): 1,
        (b"\x44" * 16).hex(): 1,
        (b"\x55" * 16).hex(): 2,
    }
    registry = PropagationNodeRegistry(
        time_fn=lambda: now,
        has_path=lambda destination_hash: destination_hash.hex() in reachable,
        hops_to=lambda destination_hash: reachable[destination_hash.hex()],
    )
    registry.record_announce(
        destination_hash=b"\x55" * 16,
        hops=2,
        stamp_cost=1,
        transfer_limit=512,
        sync_limit=1024,
        propagation_enabled=True,
        last_announced_at=now - 5,
    )
    registry.record_announce(
        destination_hash=b"\x33" * 16,
        hops=1,
        stamp_cost=5,
        transfer_limit=512,
        sync_limit=1024,
        propagation_enabled=True,
        last_announced_at=now - 10,
    )
    registry.record_announce(
        destination_hash=b"\x44" * 16,
        hops=1,
        stamp_cost=5,
        transfer_limit=512,
        sync_limit=1024,
        propagation_enabled=True,
        last_announced_at=now - 1,
    )

    best = registry.best_candidate()

    assert best is not None
    assert best.destination_hash == b"\x44" * 16


def test_propagation_registry_skips_stale_and_pathless_candidates():
    now = 100.0
    registry = PropagationNodeRegistry(
        ttl_seconds=10,
        time_fn=lambda: now,
        has_path=lambda destination_hash: destination_hash == b"\x77" * 16,
        hops_to=lambda destination_hash: 1,
    )
    registry.record_announce(
        destination_hash=b"\x66" * 16,
        hops=1,
        stamp_cost=1,
        transfer_limit=512,
        sync_limit=1024,
        propagation_enabled=True,
        last_announced_at=0.0,
    )
    registry.record_announce(
        destination_hash=b"\x88" * 16,
        hops=1,
        stamp_cost=1,
        transfer_limit=512,
        sync_limit=1024,
        propagation_enabled=True,
        last_announced_at=now - 1,
    )

    assert registry.best_candidate() is None
