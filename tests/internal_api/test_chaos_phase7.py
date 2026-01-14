"""Chaos tests for transport failures and recovery."""

from __future__ import annotations

import asyncio
from datetime import datetime
from datetime import timezone
from typing import Awaitable
from typing import Callable
from uuid import uuid4

import pytest

from reticulum_telemetry_hub.internal_api.bus import InProcessCommandBus
from reticulum_telemetry_hub.internal_api.bus import InProcessEventBus
from reticulum_telemetry_hub.internal_api.bus import InProcessQueryBus
from reticulum_telemetry_hub.internal_api.v1.enums import CommandStatus
from reticulum_telemetry_hub.internal_api.v1.schemas import CommandEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import CommandResult
from reticulum_telemetry_hub.internal_api.v1.schemas import EventEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import QueryEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import QueryResult


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


def _make_event() -> EventEnvelope:
    return EventEnvelope.model_validate(
        {
            "api_version": "1.0",
            "event_id": str(uuid4()),
            "event_type": "NodeRegistered",
            "occurred_at": _iso_now(),
            "origin": "hub-core",
            "payload": {"node_id": "node-1", "node_type": "reticulum"},
        }
    )


def test_command_bus_requires_start() -> None:
    async def _exercise() -> None:
        bus = InProcessCommandBus()

        def _handler(command: CommandEnvelope) -> CommandResult:
            return CommandResult(
                command_id=command.command_id,
                status=CommandStatus.ACCEPTED,
            )

        bus.register_handler(_handler)
        with pytest.raises(RuntimeError):
            await bus.send(_make_command())

        await bus.start()
        try:
            result = await bus.send(_make_command())
            assert result.status == CommandStatus.ACCEPTED
        finally:
            await bus.stop()

    _run_async(_exercise)


def test_query_bus_requires_start() -> None:
    async def _exercise() -> None:
        bus = InProcessQueryBus()

        def _handler(query: QueryEnvelope) -> QueryResult:
            return QueryResult(
                query_id=query.query_id,
                ok=True,
                result={"data": {"ok": True}},
                error=None,
            )

        bus.register_handler(_handler)
        with pytest.raises(RuntimeError):
            await bus.execute(_make_query())

        await bus.start()
        try:
            result = await bus.execute(_make_query())
            assert result.ok
        finally:
            await bus.stop()

    _run_async(_exercise)


def test_event_bus_requires_start() -> None:
    async def _exercise() -> None:
        bus = InProcessEventBus()
        with pytest.raises(RuntimeError):
            await bus.publish(_make_event())

        await bus.start()
        try:
            await bus.publish(_make_event())
        finally:
            await bus.stop()

    _run_async(_exercise)
