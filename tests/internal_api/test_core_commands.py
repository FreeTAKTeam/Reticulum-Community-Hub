"""Tests for internal API command handling."""

from __future__ import annotations

import asyncio
from datetime import datetime
from datetime import timezone
from typing import Awaitable
from typing import Callable
from uuid import UUID
from uuid import uuid4

from reticulum_telemetry_hub.internal_api.core import InternalApiCore
from reticulum_telemetry_hub.internal_api.v1.enums import CommandStatus
from reticulum_telemetry_hub.internal_api.v1.enums import ErrorCode
from reticulum_telemetry_hub.internal_api.v1.enums import EventType
from reticulum_telemetry_hub.internal_api.v1.schemas import CommandEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import EventEnvelope


def _iso_now() -> str:
    """Return a UTC ISO-8601 timestamp."""

    return datetime.now(timezone.utc).isoformat()


def _make_command(
    command_type: str,
    payload: dict,
    *,
    issuer_type: str,
    issuer_id: str,
    command_id: UUID | None = None,
) -> CommandEnvelope:
    """Build a command envelope with the provided payload."""

    return CommandEnvelope.model_validate(
        {
            "api_version": "1.0",
            "command_id": str(command_id or uuid4()),
            "command_type": command_type,
            "issued_at": _iso_now(),
            "issuer": {"type": issuer_type, "id": issuer_id},
            "payload": payload,
        }
    )


def _run_async(coro: Callable[[], Awaitable[None]]) -> None:
    """Run an async test helper in a fresh event loop."""

    asyncio.run(coro())


class RecordingEventBus:
    """Capture published events for assertions."""

    def __init__(self) -> None:
        """Initialize an empty event list."""

        self.events: list[EventEnvelope] = []

    def subscribe(self, handler):
        """Return a no-op unsubscribe callback."""

        return lambda: None

    async def start(self) -> None:
        """No-op start for the recorder."""

        return None

    async def stop(self) -> None:
        """No-op stop for the recorder."""

        return None

    async def publish(self, event: EventEnvelope) -> None:
        """Record an event."""

        self.events.append(event)


def test_register_node_happy_path() -> None:
    """Ensure RegisterNode updates state and emits NodeRegistered."""

    async def _exercise() -> None:
        event_bus = RecordingEventBus()
        core = InternalApiCore(event_bus)
        command = _make_command(
            "RegisterNode",
            {
                "node_id": "node-1",
                "node_type": "reticulum",
                "metadata": {"name": "Node One"},
            },
            issuer_type="reticulum",
            issuer_id="node-1",
        )

        result = await core.handle_command(command)

        assert result.status == CommandStatus.ACCEPTED
        assert "node-1" in core._nodes
        assert len(event_bus.events) == 1
        assert event_bus.events[0].event_type == EventType.NODE_REGISTERED

    _run_async(_exercise)


def test_create_topic_happy_path() -> None:
    """Ensure CreateTopic updates state and emits TopicCreated."""

    async def _exercise() -> None:
        event_bus = RecordingEventBus()
        core = InternalApiCore(event_bus)
        command = _make_command(
            "CreateTopic",
            {
                "topic_path": "ops.alpha",
                "retention": "ephemeral",
                "visibility": "public",
            },
            issuer_type="api",
            issuer_id="gateway",
        )

        result = await core.handle_command(command)

        assert result.status == CommandStatus.ACCEPTED
        assert "ops.alpha" in core._topics
        assert len(event_bus.events) == 1
        assert event_bus.events[0].event_type == EventType.TOPIC_CREATED

    _run_async(_exercise)


def test_subscribe_topic_happy_path() -> None:
    """Ensure SubscribeTopic records subscriptions and emits SubscriberUpdated."""

    async def _exercise() -> None:
        event_bus = RecordingEventBus()
        core = InternalApiCore(event_bus)
        create_topic = _make_command(
            "CreateTopic",
            {
                "topic_path": "ops.beta",
                "retention": "persistent",
                "visibility": "restricted",
            },
            issuer_type="api",
            issuer_id="gateway",
        )
        subscribe = _make_command(
            "SubscribeTopic",
            {
                "subscriber_id": "dest-1",
                "topic_path": "ops.beta",
            },
            issuer_type="api",
            issuer_id="gateway",
        )

        await core.handle_command(create_topic)
        result = await core.handle_command(subscribe)

        assert result.status == CommandStatus.ACCEPTED
        assert ("dest-1", "ops.beta") in core._subscriptions
        assert len(event_bus.events) == 2
        assert event_bus.events[1].event_type == EventType.SUBSCRIBER_UPDATED

    _run_async(_exercise)


def test_publish_message_happy_path() -> None:
    """Ensure PublishMessage emits MessagePublished."""

    async def _exercise() -> None:
        event_bus = RecordingEventBus()
        core = InternalApiCore(event_bus)
        create_topic = _make_command(
            "CreateTopic",
            {
                "topic_path": "ops.gamma",
                "retention": "ephemeral",
                "visibility": "public",
            },
            issuer_type="api",
            issuer_id="gateway",
        )
        publish = _make_command(
            "PublishMessage",
            {
                "topic_path": "ops.gamma",
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

        await core.handle_command(create_topic)
        result = await core.handle_command(publish)

        assert result.status == CommandStatus.ACCEPTED
        assert len(event_bus.events) == 2
        event = event_bus.events[1]
        assert event.event_type == EventType.MESSAGE_PUBLISHED
        assert event.payload.originator == "gateway"
        assert event.payload.message_id == publish.command_id.hex

    _run_async(_exercise)


def test_duplicate_command_replay_emits_once() -> None:
    """Ensure duplicate commands do not emit duplicate events."""

    async def _exercise() -> None:
        event_bus = RecordingEventBus()
        core = InternalApiCore(event_bus)
        command_id = uuid4()
        command = _make_command(
            "CreateTopic",
            {
                "topic_path": "ops.delta",
                "retention": "ephemeral",
                "visibility": "public",
            },
            issuer_type="api",
            issuer_id="gateway",
            command_id=command_id,
        )

        first = await core.handle_command(command)
        second = await core.handle_command(command)

        assert first.status == CommandStatus.ACCEPTED
        assert second.status == CommandStatus.ACCEPTED
        assert len(event_bus.events) == 1

    _run_async(_exercise)


def test_authorization_failure_rejected() -> None:
    """Ensure unauthorized commands are rejected without events."""

    async def _exercise() -> None:
        event_bus = RecordingEventBus()
        core = InternalApiCore(event_bus)
        command = _make_command(
            "CreateTopic",
            {
                "topic_path": "ops.epsilon",
                "retention": "ephemeral",
                "visibility": "public",
            },
            issuer_type="reticulum",
            issuer_id="node-1",
        )

        result = await core.handle_command(command)

        assert result.status == CommandStatus.REJECTED
        assert result.reason == ErrorCode.UNAUTHORIZED_COMMAND.value
        assert not core._topics
        assert not event_bus.events

    _run_async(_exercise)


def test_invalid_state_transition_rejected() -> None:
    """Ensure missing topics cause rejection."""

    async def _exercise() -> None:
        event_bus = RecordingEventBus()
        core = InternalApiCore(event_bus)
        subscribe = _make_command(
            "SubscribeTopic",
            {
                "subscriber_id": "dest-2",
                "topic_path": "ops.missing",
            },
            issuer_type="api",
            issuer_id="gateway",
        )
        publish = _make_command(
            "PublishMessage",
            {
                "topic_path": "ops.missing",
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

        result_sub = await core.handle_command(subscribe)
        result_pub = await core.handle_command(publish)

        assert result_sub.status == CommandStatus.REJECTED
        assert result_sub.reason == ErrorCode.TOPIC_NOT_FOUND.value
        assert result_pub.status == CommandStatus.REJECTED
        assert result_pub.reason == ErrorCode.TOPIC_NOT_FOUND.value
        assert not event_bus.events

    _run_async(_exercise)
