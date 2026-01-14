"""Tests for internal API transport buses."""

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
    """Return a UTC ISO-8601 timestamp."""

    return datetime.now(timezone.utc).isoformat()


def _make_command() -> CommandEnvelope:
    """Build a valid RegisterNode command envelope."""

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


def _make_event() -> EventEnvelope:
    """Build a valid NodeRegistered event envelope."""

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


def _make_query() -> QueryEnvelope:
    """Build a valid GetTopics query envelope."""

    return QueryEnvelope.model_validate(
        {
            "api_version": "1.0",
            "query_id": str(uuid4()),
            "query_type": "GetTopics",
            "issued_at": _iso_now(),
            "payload": {"prefix": "ops"},
        }
    )


def _run_async(coro: Callable[[], Awaitable[None]]) -> None:
    """Run an async test helper in a fresh event loop."""

    asyncio.run(coro())


def test_command_bus_dispatch_order() -> None:
    """Ensure command dispatch preserves FIFO ordering."""

    async def _exercise() -> None:
        bus = InProcessCommandBus(max_queue_size=8)
        seen: list[str] = []

        def _handler(command: CommandEnvelope) -> CommandResult:
            seen.append(str(command.command_id))
            return CommandResult(
                command_id=command.command_id,
                status=CommandStatus.ACCEPTED,
            )

        bus.register_handler(_handler)
        await bus.start()
        try:
            commands = [_make_command() for _ in range(3)]
            for command in commands:
                result = await bus.send(command)
                assert result.command_id == command.command_id
            assert seen == [str(command.command_id) for command in commands]
        finally:
            await bus.stop()

    _run_async(_exercise)


def test_command_bus_handler_failure_isolated() -> None:
    """Ensure command handler failures do not stop the bus."""

    async def _exercise() -> None:
        bus = InProcessCommandBus()
        calls = 0

        def _handler(command: CommandEnvelope) -> CommandResult:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ValueError("boom")
            return CommandResult(
                command_id=command.command_id,
                status=CommandStatus.ACCEPTED,
            )

        bus.register_handler(_handler)
        await bus.start()
        try:
            with pytest.raises(ValueError):
                await bus.send(_make_command())
            result = await bus.send(_make_command())
            assert result.status == CommandStatus.ACCEPTED
        finally:
            await bus.stop()

    _run_async(_exercise)


def test_query_bus_round_trip() -> None:
    """Ensure query bus dispatches and returns results."""

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
        await bus.start()
        try:
            query = _make_query()
            result = await bus.execute(query)
            assert result.query_id == query.query_id
            assert result.result is not None
            assert result.result.data["ok"] is True
        finally:
            await bus.stop()

    _run_async(_exercise)


def test_event_bus_fan_out() -> None:
    """Ensure events are delivered to multiple subscribers."""

    async def _exercise() -> None:
        bus = InProcessEventBus()
        received = asyncio.Event()
        counts = {"first": 0, "second": 0}

        async def _handler_first(_: EventEnvelope) -> None:
            counts["first"] += 1
            if counts["first"] and counts["second"]:
                received.set()

        async def _handler_second(_: EventEnvelope) -> None:
            counts["second"] += 1
            if counts["first"] and counts["second"]:
                received.set()

        bus.subscribe(_handler_first)
        bus.subscribe(_handler_second)
        await bus.start()
        try:
            await bus.publish(_make_event())
            await asyncio.wait_for(received.wait(), timeout=0.5)
            assert counts == {"first": 1, "second": 1}
        finally:
            await bus.stop()

    _run_async(_exercise)


def test_event_bus_handler_failure_isolated() -> None:
    """Ensure a failing handler does not block others."""

    async def _exercise() -> None:
        bus = InProcessEventBus()
        received = asyncio.Event()
        seen: list[str] = []

        def _failing_handler(_: EventEnvelope) -> None:
            raise RuntimeError("boom")

        async def _ok_handler(event: EventEnvelope) -> None:
            seen.append(str(event.event_id))
            received.set()

        bus.subscribe(_failing_handler)
        bus.subscribe(_ok_handler)
        await bus.start()
        try:
            await bus.publish(_make_event())
            await asyncio.wait_for(received.wait(), timeout=0.5)
            received.clear()
            await bus.publish(_make_event())
            await asyncio.wait_for(received.wait(), timeout=0.5)
            assert len(seen) == 2
        finally:
            await bus.stop()

    _run_async(_exercise)


def test_event_bus_backpressure_blocks() -> None:
    """Ensure publish awaits when the event queue is full."""

    async def _exercise() -> None:
        bus = InProcessEventBus(max_queue_size=1)
        started = asyncio.Event()
        release = asyncio.Event()

        async def _handler(_: EventEnvelope) -> None:
            started.set()
            await release.wait()

        bus.subscribe(_handler)
        await bus.start()
        try:
            await bus.publish(_make_event())
            await asyncio.wait_for(started.wait(), timeout=0.5)
            await bus.publish(_make_event())
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(bus.publish(_make_event()), timeout=0.05)
            release.set()
            await asyncio.sleep(0)
        finally:
            await bus.stop()

    _run_async(_exercise)
