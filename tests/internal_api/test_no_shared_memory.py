"""Tests ensuring buses do not share mutable envelopes."""

from __future__ import annotations

import asyncio
from datetime import datetime
from datetime import timezone
from typing import Awaitable
from typing import Callable
from uuid import uuid4

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


def test_command_bus_defensive_copy() -> None:
    async def _exercise() -> None:
        bus = InProcessCommandBus()

        def _handler(command: CommandEnvelope) -> CommandResult:
            command.payload.node_id = "mutated"
            return CommandResult(
                command_id=command.command_id,
                status=CommandStatus.ACCEPTED,
            )

        bus.register_handler(_handler)
        await bus.start()
        try:
            command = _make_command()
            await bus.send(command)
            assert command.payload.node_id == "node-1"
        finally:
            await bus.stop()

    _run_async(_exercise)


def test_query_bus_defensive_copy() -> None:
    async def _exercise() -> None:
        bus = InProcessQueryBus()

        def _handler(query: QueryEnvelope) -> QueryResult:
            query.payload.prefix = "mutated"
            return QueryResult(
                query_id=query.query_id,
                ok=True,
                result={"data": {"ok": True}},
                error=None,
            )

        bus.register_handler(_handler)
        await bus.start()
        try:
            query = _make_query()
            await bus.execute(query)
            assert query.payload.prefix == "ops"
        finally:
            await bus.stop()

    _run_async(_exercise)


def test_event_bus_defensive_copy() -> None:
    async def _exercise() -> None:
        bus = InProcessEventBus()
        check_done = asyncio.Event()

        async def _mutate(event: EventEnvelope) -> None:
            event.payload.node_id = "mutated"

        async def _check(event: EventEnvelope) -> None:
            assert event.payload.node_id == "node-1"
            check_done.set()

        bus.subscribe(_mutate)
        bus.subscribe(_check)
        await bus.start()
        try:
            event = _make_event()
            await bus.publish(event)
            await asyncio.wait_for(check_done.wait(), timeout=0.5)
            assert event.payload.node_id == "node-1"
        finally:
            await bus.stop()

    _run_async(_exercise)
