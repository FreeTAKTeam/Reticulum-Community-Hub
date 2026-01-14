"""Performance baseline tests for command throughput."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from datetime import timezone
from typing import Awaitable
from typing import Callable
from uuid import uuid4

from reticulum_telemetry_hub.internal_api.bus import InProcessCommandBus
from reticulum_telemetry_hub.internal_api.bus import InProcessEventBus
from reticulum_telemetry_hub.internal_api.core import InternalApiCore
from reticulum_telemetry_hub.internal_api.v1.schemas import CommandEnvelope


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_async(coro: Callable[[], Awaitable[None]]) -> None:
    asyncio.run(coro())


def _make_command(node_id: str) -> CommandEnvelope:
    return CommandEnvelope.model_validate(
        {
            "api_version": "1.0",
            "command_id": str(uuid4()),
            "command_type": "RegisterNode",
            "issued_at": _iso_now(),
            "issuer": {"type": "reticulum", "id": node_id},
            "payload": {"node_id": node_id, "node_type": "reticulum"},
        }
    )


def test_command_throughput_baseline() -> None:
    async def _exercise() -> None:
        event_bus = InProcessEventBus()
        core = InternalApiCore(event_bus)
        command_bus = InProcessCommandBus(max_queue_size=256)
        command_bus.register_handler(core.handle_command)
        await event_bus.start()
        await command_bus.start()
        try:
            count = 100
            start = time.perf_counter()
            for index in range(count):
                command = _make_command(f"node-{index}")
                await command_bus.send(command)
            elapsed = time.perf_counter() - start
            assert elapsed < 5.0
        finally:
            await command_bus.stop()
            await event_bus.stop()

    _run_async(_exercise)
