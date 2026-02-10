"""Tests for EmbeddedLxmd propagation telemetry hooks."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

import pytest
import RNS
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.lxmf_propagation import (
    LXMFPropagation,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.telemeter import Telemeter


def test_embedded_lxmd_persists_propagation_stats(
    embedded_lxmd_factory, session_factory
):
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
    harness = embedded_lxmd_factory(stats=stats, destination_hash=b"\x11" * 16)

    harness.embedded._maybe_emit_propagation_update(force=True)

    Session = session_factory
    with Session() as session:
        telemeter = session.query(Telemeter).one()
        assert telemeter.peer_dest == RNS.hexrep(harness.destination.hash, False)
        sensor = session.query(LXMFPropagation).one()
        payload = sensor.pack()

    assert payload is not None
    assert payload["from_static_only"] is True
    assert payload["total_peers"] == 1
    assert payload["active_peers"] == 1
    assert payload["peered_propagation_rx_bytes"] == 64
    assert b"peer-a" in payload["peers"]


@pytest.mark.usefixtures("session_factory")
def test_embedded_lxmd_deduplicates_snapshots(embedded_lxmd_factory):
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
    harness = embedded_lxmd_factory(stats=stats, destination_hash=b"\x22" * 16)

    calls: list[datetime] = []
    lock = threading.Lock()

    def observer(payload: dict[str, Any]) -> None:
        with lock:
            calls.append(datetime.now(timezone.utc).replace(tzinfo=None))

    harness.embedded.add_propagation_observer(observer)

    harness.embedded._maybe_emit_propagation_update(force=True)
    harness.embedded._maybe_emit_propagation_update()

    with lock:
        assert len(calls) == 1


def test_embedded_lxmd_fixture_emits_and_persists(
    running_embedded_lxmd, session_factory
):
    stats = {
        "destination_hash": b"\xff" * 16,
        "identity_hash": b"\xee" * 16,
        "uptime": 5.0,
        "delivery_limit": 1024,
        "propagation_limit": 512,
        "autopeer_maxdepth": 2,
        "from_static_only": False,
        "messagestore": None,
        "clients": None,
        "unpeered_propagation_incoming": 0,
        "unpeered_propagation_rx_bytes": 0,
        "static_peers": 0,
        "max_peers": 5,
        "peers": {
            b"peer-b": {
                "type": "propagator",
                "state": "active",
                "alive": True,
                "last_heard": 1,
                "next_sync_attempt": 2,
                "last_sync_attempt": 3,
                "sync_backoff": 0,
                "peering_timebase": 4,
                "ler": 1,
                "str": 1,
                "transfer_limit": 64,
                "network_distance": 1,
                "rx_bytes": 8,
                "tx_bytes": 16,
                "messages": {
                    "offered": 1,
                    "outgoing": 1,
                    "incoming": 0,
                    "unhandled": 0,
                },
            }
        },
    }

    observed: list[dict[str, Any]] = []
    event = threading.Event()

    def observer(payload: dict[str, Any]) -> None:
        observed.append(payload)
        event.set()

    with running_embedded_lxmd(stats=stats, destination_hash=b"\x55" * 16) as harness:
        harness.embedded.add_propagation_observer(observer)
        harness.embedded.start()
        assert event.wait(1.0), "embedded daemon never emitted propagation stats"
        assert harness.router.announce_calls
        assert harness.router.announce_propagation_count == 1

    assert observed and observed[0]["destination_hash"] == stats["destination_hash"]

    Session = session_factory
    with Session() as session:
        telemeters = session.query(Telemeter).order_by(Telemeter.id).all()
        assert telemeters
        assert telemeters[-1].peer_dest == RNS.hexrep(b"\x55" * 16, False)
        sensors = session.query(LXMFPropagation).order_by(LXMFPropagation.id).all()
        assert sensors
        payload = sensors[-1].pack()

    assert payload is not None
    assert payload["active_peers"] == 1
    assert payload["peered_propagation_rx_bytes"] == 8


def test_embedded_lxmd_can_restart_after_stop(running_embedded_lxmd):
    stats = {
        "destination_hash": b"\x66" * 16,
        "identity_hash": b"\x77" * 16,
        "uptime": 10.0,
        "delivery_limit": 128,
        "propagation_limit": 128,
        "autopeer_maxdepth": 1,
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

    observed: list[dict[str, Any]] = []
    event = threading.Event()

    def observer(payload: dict[str, Any]) -> None:
        observed.append(payload)
        event.set()

    with running_embedded_lxmd(stats=stats) as harness:
        harness.embedded.add_propagation_observer(observer)

        harness.embedded.start()
        assert event.wait(1.0), "initial start never emitted propagation stats"
        event.clear()

        first_observed = len(observed)
        first_announces = len(harness.router.announce_calls)
        first_propagation_announces = harness.router.announce_propagation_count

        harness.embedded.stop()
        event.clear()
        post_stop_observed = len(observed)

        harness.embedded.start()
        assert event.wait(1.0), "second start never emitted propagation stats"

        assert len(observed) > post_stop_observed >= first_observed
        assert len(harness.router.announce_calls) > first_announces
        assert harness.router.announce_propagation_count > first_propagation_announces


def test_embedded_lxmd_background_start_is_non_blocking(
    embedded_lxmd_factory,
) -> None:
    stats = {
        "destination_hash": b"\xaa" * 16,
        "identity_hash": b"\xbb" * 16,
        "uptime": 0.0,
        "delivery_limit": 128,
        "propagation_limit": 128,
        "autopeer_maxdepth": 1,
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
    harness = embedded_lxmd_factory(
        stats=stats,
        propagation_start_mode="background",
        enable_delay_seconds=0.5,
    )
    harness.embedded.DEFERRED_JOBS_DELAY = 0
    harness.embedded.JOBS_INTERVAL_SECONDS = 0.01

    try:
        started = time.perf_counter()
        harness.embedded.start()
        elapsed = time.perf_counter() - started
        assert elapsed < 0.2

        initial_status = harness.embedded.propagation_startup_status()
        assert initial_status["enabled"] is True
        assert initial_status["start_mode"] == "background"
        assert initial_status["state"] in {"indexing", "ready"}

        deadline = time.time() + 2.0
        while time.time() < deadline:
            status = harness.embedded.propagation_startup_status()
            if status["ready"]:
                break
            time.sleep(0.02)

        status = harness.embedded.propagation_startup_status()
        assert status["state"] == "ready"
        assert status["ready"] is True
        assert status["index_duration_seconds"] is not None
    finally:
        harness.embedded.stop()


def test_embedded_lxmd_startup_prunes_messagestore(
    embedded_lxmd_factory,
    tmp_path,
) -> None:
    now = time.time()
    hash_hex = "a" * ((RNS.Identity.HASHLENGTH // 8) * 2)
    message_store = tmp_path / "messagestore"
    message_store.mkdir(parents=True, exist_ok=True)

    (message_store / f"{hash_hex}_{now - 10}_1").write_bytes(b"msg-a")
    (message_store / f"{hash_hex}_{now - 20}_1").write_bytes(b"msg-b")
    (message_store / f"{hash_hex}_{now - (40 * 24 * 60 * 60)}_1").write_bytes(b"msg-c")
    (message_store / "invalid-entry").write_bytes(b"bad")

    harness = embedded_lxmd_factory(
        propagation_start_mode="blocking",
        startup_prune_enabled=True,
        startup_max_messages=1,
        startup_max_age_days=30,
    )
    harness.router.storagepath = str(tmp_path)

    try:
        harness.embedded.start()
        status = harness.embedded.propagation_startup_status()
        prune = status["startup_prune"]
        assert prune is not None
        assert prune["scanned"] == 4
        assert prune["kept"] == 1
        assert prune["removed_invalid"] == 1
        assert prune["removed_expired"] == 1
        assert prune["removed_overflow"] == 1
        assert len(list(message_store.iterdir())) == 1
    finally:
        harness.embedded.stop()
