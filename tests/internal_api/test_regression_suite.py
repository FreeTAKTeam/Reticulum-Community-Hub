"""Regression suite covering the internal API flow end to end."""

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
from reticulum_telemetry_hub.internal_api.core import InternalApiCore
from reticulum_telemetry_hub.internal_api.v1.enums import CommandStatus
from reticulum_telemetry_hub.internal_api.v1.schemas import CommandEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import EventEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import QueryEnvelope


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_async(coro: Callable[[], Awaitable[None]]) -> None:
    asyncio.run(coro())


def _make_command(
    command_type: str, payload: dict, *, issuer_type: str, issuer_id: str
) -> CommandEnvelope:
    return CommandEnvelope.model_validate(
        {
            "api_version": "1.0",
            "command_id": str(uuid4()),
            "command_type": command_type,
            "issued_at": _iso_now(),
            "issuer": {"type": issuer_type, "id": issuer_id},
            "payload": payload,
        }
    )


def _make_query(query_type: str, payload: dict) -> QueryEnvelope:
    return QueryEnvelope.model_validate(
        {
            "api_version": "1.0",
            "query_id": str(uuid4()),
            "query_type": query_type,
            "issued_at": _iso_now(),
            "payload": payload,
        }
    )


def test_internal_api_regression_flow() -> None:
    async def _exercise() -> None:
        event_bus = InProcessEventBus()
        core = InternalApiCore(event_bus)
        command_bus = InProcessCommandBus()
        query_bus = InProcessQueryBus()
        command_bus.register_handler(core.handle_command)
        query_bus.register_handler(core.handle_query)

        events: list[EventEnvelope] = []
        delivered = asyncio.Event()

        async def _record(event: EventEnvelope) -> None:
            events.append(event)
            if len(events) >= 4:
                delivered.set()

        event_bus.subscribe(_record)
        await event_bus.start()
        await command_bus.start()
        await query_bus.start()
        try:
            register = _make_command(
                "RegisterNode",
                {
                    "node_id": "node-1",
                    "node_type": "reticulum",
                    "metadata": {"name": "Node One"},
                },
                issuer_type="reticulum",
                issuer_id="node-1",
            )
            create_topic = _make_command(
                "CreateTopic",
                {
                    "topic_path": "ops.alpha",
                    "retention": "ephemeral",
                    "visibility": "public",
                },
                issuer_type="api",
                issuer_id="gateway",
            )
            subscribe = _make_command(
                "SubscribeTopic",
                {"subscriber_id": "node-1", "topic_path": "ops.alpha"},
                issuer_type="api",
                issuer_id="gateway",
            )
            publish = _make_command(
                "PublishMessage",
                {
                    "topic_path": "ops.alpha",
                    "message_type": "text",
                    "content": {
                        "message_type": "text",
                        "text": "hello",
                        "encoding": "utf-8",
                    },
                    "qos": "best_effort",
                },
                issuer_type="api",
                issuer_id="gateway",
            )

            for command in (register, create_topic, subscribe, publish):
                result = await command_bus.send(command)
                assert result.status == CommandStatus.ACCEPTED

            await asyncio.wait_for(delivered.wait(), timeout=1.0)

            topics_query = _make_query("GetTopics", {"prefix": None})
            topics_result = await query_bus.execute(topics_query)
            assert topics_result.ok
            topics_data = topics_result.result.data
            assert any(
                topic["topic_id"] == "ops.alpha" for topic in topics_data.get("topics", [])
            )

            subscribers_query = _make_query("GetSubscribers", {"topic_path": "ops.alpha"})
            subscribers_result = await query_bus.execute(subscribers_query)
            assert subscribers_result.ok
            subscribers_data = subscribers_result.result.data
            assert subscribers_data["topic_id"] == "ops.alpha"
            assert any(
                entry["node_id"] == "node-1"
                for entry in subscribers_data.get("subscribers", [])
            )

            node_query = _make_query("GetNodeStatus", {"node_id": "node-1"})
            node_result = await query_bus.execute(node_query)
            assert node_result.ok
            node_data = node_result.result.data
            assert node_data["node_id"] == "node-1"
            assert node_data["status"] == "online"
            assert "ops.alpha" in node_data.get("topics", [])
        finally:
            await command_bus.stop()
            await query_bus.stop()
            await event_bus.stop()

    _run_async(_exercise)
