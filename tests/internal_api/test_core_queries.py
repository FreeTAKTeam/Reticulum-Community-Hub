"""Tests for internal API query handling."""

from __future__ import annotations

import asyncio
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
    """Return a UTC ISO-8601 timestamp."""

    return datetime.now(timezone.utc).isoformat()


def _make_command(
    command_type: str,
    payload: dict,
    *,
    issuer_id: str,
    issuer_type: str = "reticulum",
) -> CommandEnvelope:
    """Build a command envelope."""

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
    """Build a query envelope."""

    return QueryEnvelope.model_validate(
        {
            "api_version": "1.0",
            "query_id": str(uuid4()),
            "query_type": query_type,
            "issued_at": _iso_now(),
            "payload": payload,
        }
    )


def _run_async(coro: Callable[[], Awaitable[None]]) -> None:
    """Run an async test helper in a fresh event loop."""

    asyncio.run(coro())


class _EventBusStub:
    """Event bus stub for query tests."""

    def subscribe(self, handler):
        """Return a no-op unsubscribe callback."""

        return lambda: None

    async def start(self) -> None:
        """No-op start."""

        return None

    async def stop(self) -> None:
        """No-op stop."""

        return None

    async def publish(self, event: EventEnvelope) -> None:
        """No-op publish."""

        await asyncio.sleep(0)


def test_get_topics_empty_state() -> None:
    """Ensure GetTopics returns an empty list with cache hints."""

    async def _exercise() -> None:
        core = InternalApiCore(_EventBusStub())
        query = _make_query("GetTopics", {})
        result = await core.handle_query(query)

        assert result.ok is True
        assert result.result is not None
        assert result.result.data["topics"] == []
        assert result.result.cache is not None
        assert result.result.cache.ttl_seconds == 5
        assert result.result.cache.scope == "hub"

    _run_async(_exercise)


def test_get_subscribers_topic_not_found() -> None:
    """Ensure GetSubscribers rejects missing topics."""

    async def _exercise() -> None:
        core = InternalApiCore(_EventBusStub())
        query = _make_query("GetSubscribers", {"topic_path": "missing"})
        result = await core.handle_query(query)

        assert result.ok is False
        assert result.error is not None
        assert result.error.code.value == "TOPIC_NOT_FOUND"

    _run_async(_exercise)


def test_get_node_status_unknown() -> None:
    """Ensure unknown nodes return ok with status unknown."""

    async def _exercise() -> None:
        core = InternalApiCore(_EventBusStub())
        query = _make_query("GetNodeStatus", {"node_id": "node-unknown"})
        result = await core.handle_query(query)

        assert result.ok is True
        assert result.result is not None
        data = result.result.data
        assert data["status"] == "unknown"
        assert data["last_seen_ts"] is None
        assert data["topics"] == []
        assert data["metrics"] == {}

    _run_async(_exercise)


def test_get_topics_returns_stats() -> None:
    """Ensure GetTopics includes visibility mapping and message rate."""

    async def _exercise() -> None:
        core = InternalApiCore(_EventBusStub())
        create = _make_command(
            "CreateTopic",
            {
                "topic_path": "ops.alpha",
                "retention": "ephemeral",
                "visibility": "restricted",
            },
            issuer_id="gateway",
            issuer_type="api",
        )
        await core.handle_command(create)
        publish_one = _make_command(
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
            issuer_id="node-1",
        )
        publish_two = _make_command(
            "PublishMessage",
            {
                "topic_path": "ops.alpha",
                "message_type": "text",
                "content": {
                    "message_type": "text",
                    "text": "hello again",
                    "encoding": "utf-8",
                },
                "qos": "best_effort",
            },
            issuer_id="node-1",
        )
        await core.handle_command(publish_one)
        await core.handle_command(publish_two)

        query = _make_query("GetTopics", {})
        result = await core.handle_query(query)

        assert result.ok is True
        topic = result.result.data["topics"][0]
        assert topic["visibility"] == "private"
        assert topic["subscriber_count"] == 0
        assert topic["message_rate"] == pytest.approx(2 / 60.0, rel=0.2)

    _run_async(_exercise)


def test_get_subscribers_filters_offline() -> None:
    """Ensure subscribers only include active/stale/blackholed nodes."""

    async def _exercise() -> None:
        core = InternalApiCore(_EventBusStub())
        await core.handle_command(
            _make_command(
                "CreateTopic",
                {
                    "topic_path": "ops.beta",
                    "retention": "ephemeral",
                    "visibility": "public",
                },
                issuer_id="gateway",
                issuer_type="api",
            )
        )
        await core.handle_command(
            _make_command(
                "RegisterNode",
                {"node_id": "node-1", "node_type": "reticulum"},
                issuer_id="node-1",
            )
        )
        await core.handle_command(
            _make_command(
                "SubscribeTopic",
                {"subscriber_id": "node-1", "topic_path": "ops.beta"},
                issuer_id="node-1",
            )
        )
        await core.handle_command(
            _make_command(
                "SubscribeTopic",
                {"subscriber_id": "node-2", "topic_path": "ops.beta"},
                issuer_id="gateway",
            )
        )

        query = _make_query("GetSubscribers", {"topic_path": "ops.beta"})
        result = await core.handle_query(query)

        assert result.ok is True
        subscribers = result.result.data["subscribers"]
        assert len(subscribers) == 1
        assert subscribers[0]["node_id"] == "node-1"
        assert subscribers[0]["status"] == "active"

    _run_async(_exercise)


def test_get_node_status_metrics_mapped() -> None:
    """Ensure telemetry metrics populate node status metrics."""

    async def _exercise() -> None:
        core = InternalApiCore(_EventBusStub())
        await core.handle_command(
            _make_command(
                "CreateTopic",
                {
                    "topic_path": "ops.gamma",
                    "retention": "ephemeral",
                    "visibility": "public",
                },
                issuer_id="gateway",
                issuer_type="api",
            )
        )
        await core.handle_command(
            _make_command(
                "PublishMessage",
                {
                    "topic_path": "ops.gamma",
                    "message_type": "telemetry",
                    "content": {
                        "message_type": "telemetry",
                        "telemetry_type": None,
                        "data": {"battery": 72, "rssi": -81},
                    },
                    "qos": "best_effort",
                },
                issuer_id="node-3",
            )
        )

        query = _make_query("GetNodeStatus", {"node_id": "node-3"})
        result = await core.handle_query(query)

        metrics = result.result.data["metrics"]
        assert metrics["battery_pct"] == 72.0
        assert metrics["signal_quality"] == -81.0
        assert metrics["telemetry_rate"] > 0
        assert metrics["lxmf_rate"] > 0

    _run_async(_exercise)


def test_query_results_deterministic_for_snapshot() -> None:
    """Ensure repeated queries return consistent results."""

    async def _exercise() -> None:
        core = InternalApiCore(_EventBusStub())
        await core.handle_command(
            _make_command(
                "CreateTopic",
                {
                    "topic_path": "ops.delta",
                    "retention": "ephemeral",
                    "visibility": "public",
                },
                issuer_id="gateway",
                issuer_type="api",
            )
        )
        query = _make_query("GetTopics", {})
        first = await core.handle_query(query)
        second = await core.handle_query(query)

        assert first.ok is True
        assert second.ok is True
        assert first.result.data == second.result.data

    _run_async(_exercise)


def test_query_concurrency_safe() -> None:
    """Ensure queries during command handling do not fail."""

    async def _exercise() -> None:
        core = InternalApiCore(_EventBusStub())

        async def _send_commands() -> None:
            for index in range(3):
                await core.handle_command(
                    _make_command(
                        "CreateTopic",
                        {
                            "topic_path": f"ops.concurrent.{index}",
                            "retention": "ephemeral",
                            "visibility": "public",
                        },
                        issuer_id="gateway",
                        issuer_type="api",
                    )
                )

        async def _run_queries() -> None:
            for _ in range(3):
                await core.handle_query(_make_query("GetTopics", {}))

        await asyncio.gather(_send_commands(), _run_queries())

    _run_async(_exercise)
