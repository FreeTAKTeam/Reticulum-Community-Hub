"""Pytest fixtures shared across telemetry tests."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from reticulum_telemetry_hub.lxmf_telemetry import telemetry_controller as tc_mod
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance import Base
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import TelemetryController


@pytest.fixture
def session_factory():
    """Provide an isolated in-memory database and session factory per test."""

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    old_engine = tc_mod._engine
    old_session_cls = tc_mod.Session_cls
    tc_mod._engine = engine
    tc_mod.Session_cls = SessionLocal

    try:
        yield SessionLocal
    finally:
        tc_mod._engine = old_engine
        tc_mod.Session_cls = old_session_cls
        engine.dispose()


@pytest.fixture
def telemetry_controller(session_factory):
    """Return a ``TelemetryController`` bound to the in-memory database."""

    return TelemetryController()

