"""Pytest fixtures shared across telemetry tests."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from reticulum_telemetry_hub.embedded_lxmd.embedded import EmbeddedLxmd
from reticulum_telemetry_hub.lxmf_telemetry import telemetry_controller as tc_mod
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance import Base
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import TelemetryController


@pytest.fixture
def telemetry_db_engine():
    """Return an isolated in-memory SQLite engine per test."""

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session_factory(telemetry_db_engine):
    """Provide a session factory bound to the per-test in-memory engine."""

    return sessionmaker(bind=telemetry_db_engine, expire_on_commit=False)


@pytest.fixture
def telemetry_controller(telemetry_db_engine):
    """Return a ``TelemetryController`` bound to the in-memory database."""

    return TelemetryController(engine=telemetry_db_engine)


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

    def __init__(self, stats: dict[str, Any] | None = None) -> None:
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


@dataclass
class EmbeddedTestHarness:
    embedded: EmbeddedLxmd
    router: DummyRouter
    destination: DummyDestination


@pytest.fixture
def embedded_lxmd_factory(telemetry_controller):
    """Return a factory that builds ``EmbeddedLxmd`` test harnesses."""

    def factory(
        *,
        stats: dict[str, Any] | None = None,
        destination_hash: bytes | None = None,
        enable_node: bool = True,
        interval_minutes: int = 1,
    ) -> EmbeddedTestHarness:
        router = DummyRouter(stats)
        destination = DummyDestination(destination_hash or b"\x11" * 16)
        config_manager = DummyConfigManager(
            enable_node=enable_node, interval_minutes=interval_minutes
        )
        embedded = EmbeddedLxmd(
            router,
            destination,
            config_manager=config_manager,
            telemetry_controller=telemetry_controller,
        )
        return EmbeddedTestHarness(embedded, router, destination)

    return factory


@pytest.fixture
def running_embedded_lxmd(embedded_lxmd_factory):
    """Provide a context manager that starts/stops the embedded daemon quickly."""

    @contextmanager
    def factory(**kwargs) -> Iterator[EmbeddedTestHarness]:
        harness = embedded_lxmd_factory(**kwargs)
        harness.embedded.DEFERRED_JOBS_DELAY = 0
        harness.embedded.JOBS_INTERVAL_SECONDS = 0.01
        try:
            yield harness
        finally:
            harness.embedded.stop()

    return factory

