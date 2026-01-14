"""Tests for structured logging in the internal API core."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from datetime import timezone
from typing import Awaitable
from typing import Callable
from uuid import uuid4

import pytest

from reticulum_telemetry_hub.internal_api.core import InternalApiCore
from reticulum_telemetry_hub.internal_api.v1.schemas import CommandEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import EventEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import QueryEnvelope


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_async(coro: Callable[[], Awaitable[None]]) -> None:
    asyncio.run(coro())


def _make_command() -> CommandEnvelope:
    return CommandEnvelope.model_validate(
        {
            "api_version": "1.0",
            "command_id": str(uuid4()),
            "command_type": "RegisterNode",
            "issued_at": _iso_now(),
            "issuer": {"type": "reticulum", "id": "node-1"},
            "payload": {
                "node_id": "node-1",
                "node_type": "reticulum",
                "metadata": {"name": "Node One"},
            },
        }
    )


def _make_query() -> QueryEnvelope:
    return QueryEnvelope.model_validate(
        {
            "api_version": "1.0",
            "query_id": str(uuid4()),
            "query_type": "GetTopics",
            "issued_at": _iso_now(),
            "payload": {"prefix": "ops"},
        }
    )


class RecordingEventBus:
    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []

    def subscribe(self, handler):
        return lambda: None

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def publish(self, event: EventEnvelope) -> None:
        self.events.append(event)


def test_command_logging_includes_ids(caplog: pytest.LogCaptureFixture) -> None:
    async def _exercise() -> None:
        event_bus = RecordingEventBus()
        core = InternalApiCore(event_bus)
        command = _make_command()

        caplog.set_level(logging.INFO, logger="reticulum_telemetry_hub.internal_api.core")
        await core.handle_command(command)

        command_id = str(command.command_id)
        event_id = str(event_bus.events[0].event_id)

        assert any(
            getattr(record, "command_id", None) == command_id for record in caplog.records
        )
        assert any(
            getattr(record, "event_id", None) == event_id for record in caplog.records
        )
        assert any(
            getattr(record, "correlation_id", None) == command_id
            for record in caplog.records
            if getattr(record, "event_id", None) == event_id
        )

    _run_async(_exercise)


def test_query_logging_includes_ids(caplog: pytest.LogCaptureFixture) -> None:
    async def _exercise() -> None:
        event_bus = RecordingEventBus()
        core = InternalApiCore(event_bus)
        query = _make_query()

        caplog.set_level(logging.INFO, logger="reticulum_telemetry_hub.internal_api.core")
        await core.handle_query(query)

        query_id = str(query.query_id)
        assert any(
            getattr(record, "query_id", None) == query_id for record in caplog.records
        )

    _run_async(_exercise)
