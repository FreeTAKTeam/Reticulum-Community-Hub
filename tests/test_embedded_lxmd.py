"""Tests for EmbeddedLxmd propagation telemetry hooks."""
from __future__ import annotations

import threading
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest
import RNS

from reticulum_telemetry_hub.embedded_lxmd.embedded import EmbeddedLxmd
from reticulum_telemetry_hub.lxmf_telemetry import telemetry_controller as tc_mod
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.lxmf_propagation import (
    LXMFPropagation,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.telemeter import Telemeter


class DummyConfigManager:
    """Provide the minimal configuration structure expected by EmbeddedLxmd."""

    def __init__(self, *, enable_node: bool = True, interval_minutes: int = 1) -> None:
        lxmf_router = SimpleNamespace(
            enable_node=enable_node, announce_interval_minutes=interval_minutes
        )
        self.config = SimpleNamespace(lxmf_router=lxmf_router)


class DummyDestination:
    def __init__(self, hash_value: bytes) -> None:
        self.hash = hash_value


class DummyRouter:
    """Router stub exposing the propagation attributes accessed by EmbeddedLxmd."""

    def __init__(self, stats: dict[str, Any] | None) -> None:
        self._stats = stats
        self.identity = SimpleNamespace(hash=b"\x33" * 16)
        self.propagation_destination = SimpleNamespace(hash=b"\x44" * 16)
        self.delivery_per_transfer_limit = 1024
        self.propagation_per_transfer_limit = 2048
        self.autopeer_maxdepth = 3
        self.from_static_only = False
        self.unpeered_propagation_incoming = 0
        self.unpeered_propagation_rx_bytes = 0
        self.static_peers: list[bytes] = []
        self.peers: dict[bytes, Any] = {}
        self.max_peers = 5
        self._enabled = False
        self.announce_calls: list[bytes] = []
        self.announce_propagation_count = 0

    def enable_propagation(self) -> None:
        self._enabled = True

    def announce(self, destination_hash: bytes) -> None:
        self.announce_calls.append(destination_hash)

    def announce_propagation_node(self) -> None:
        self.announce_propagation_count += 1

    def compile_stats(self) -> dict[str, Any] | None:
        return self._stats

    def set_stats(self, stats: dict[str, Any] | None) -> None:
        self._stats = stats


@pytest.mark.usefixtures("session_factory")
def test_embedded_lxmd_persists_propagation_stats(telemetry_controller):
    stats = {
        "destination_hash": b"\xaa" * 16,
        "identity_hash": b"\xbb" * 16,
        "uptime": 42.0,
        "delivery_limit": 4096,
        "propagation_limit": 2048,
        "autopeer_maxdepth": 4,
        "from_static_only": True,
        "messagestore": {"count": 3, "bytes": 1024, "limit": 2048},
        "clients": {
            "client_propagation_messages_received": 1,
            "client_propagation_messages_served": 2,
        },
        "unpeered_propagation_incoming": 1,
        "unpeered_propagation_rx_bytes": 16,
        "static_peers": 1,
        "max_peers": 5,
        "peers": {
            b"peer-a": {
                "type": "static",
                "state": "active",
                "alive": True,
                "last_heard": 123,
                "next_sync_attempt": 456,
                "last_sync_attempt": 111,
                "sync_backoff": 0,
                "peering_timebase": 22,
                "ler": 10,
                "str": 5,
                "transfer_limit": 128,
                "network_distance": 1,
                "rx_bytes": 64,
                "tx_bytes": 32,
                "messages": {
                    "offered": 2,
                    "outgoing": 1,
                    "incoming": 1,
                    "unhandled": 0,
                },
            }
        },
    }
    router = DummyRouter(stats)
    destination = DummyDestination(b"\x11" * 16)
    embedded = EmbeddedLxmd(
        router,
        destination,
        config_manager=DummyConfigManager(),
        telemetry_controller=telemetry_controller,
    )

    embedded._maybe_emit_propagation_update(force=True)

    with tc_mod.Session_cls() as session:
        telemeter = session.query(Telemeter).one()
        assert telemeter.peer_dest == RNS.hexrep(destination.hash, False)
        sensor = session.query(LXMFPropagation).one()
        payload = sensor.pack()

    assert payload is not None
    assert payload["from_static_only"] is True
    assert payload["total_peers"] == 1
    assert payload["active_peers"] == 1
    assert payload["peered_propagation_rx_bytes"] == 64
    assert b"peer-a" in payload["peers"]


@pytest.mark.usefixtures("session_factory")
def test_embedded_lxmd_deduplicates_snapshots(telemetry_controller):
    stats = {
        "destination_hash": b"\xaa" * 16,
        "identity_hash": b"\xbb" * 16,
        "uptime": 100.0,
        "delivery_limit": 4096,
        "propagation_limit": 2048,
        "autopeer_maxdepth": 4,
        "from_static_only": False,
        "messagestore": None,
        "clients": None,
        "unpeered_propagation_incoming": 0,
        "unpeered_propagation_rx_bytes": 0,
        "static_peers": 0,
        "max_peers": 5,
        "peers": {},
        "total_peers": 0,
    }
    router = DummyRouter(stats)
    destination = DummyDestination(b"\x22" * 16)
    embedded = EmbeddedLxmd(
        router,
        destination,
        config_manager=DummyConfigManager(),
        telemetry_controller=telemetry_controller,
    )

    calls: list[datetime] = []
    lock = threading.Lock()

    def observer(payload: dict[str, Any]) -> None:
        with lock:
            calls.append(datetime.utcnow())

    embedded.add_propagation_observer(observer)

    embedded._maybe_emit_propagation_update(force=True)
    embedded._maybe_emit_propagation_update()

    with lock:
        assert len(calls) == 1
