"""Tests for the Reticulum internal API adapter."""

from __future__ import annotations

import asyncio
from datetime import datetime
from datetime import timezone

import LXMF
from msgpack import packb

from reticulum_telemetry_hub.internal_api.v1.enums import EventType
from reticulum_telemetry_hub.internal_api.v1.enums import RetentionPolicy
from reticulum_telemetry_hub.internal_api.v1.enums import Visibility
from reticulum_telemetry_hub.internal_api.v1.schemas import CommandEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import QueryEnvelope
from reticulum_telemetry_hub.reticulum_server.internal_adapter import LxmfInbound
from reticulum_telemetry_hub.reticulum_server.internal_adapter import ReticulumInternalAdapter


def _run(coro):
    return asyncio.run(coro)


def _build_create_topic(topic_id: str) -> CommandEnvelope:
    return CommandEnvelope.model_validate(
        {
            "api_version": "1.0",
            "command_id": "00000000-0000-0000-0000-000000000001",
            "command_type": "CreateTopic",
            "issued_at": datetime.now(timezone.utc),
            "issuer": {"type": "api", "id": "gateway"},
            "payload": {
                "topic_path": topic_id,
                "retention": RetentionPolicy.EPHEMERAL,
                "visibility": Visibility.PUBLIC,
            },
        }
    )


def _build_query(query_type: str, payload: dict) -> QueryEnvelope:
    return QueryEnvelope.model_validate(
        {
            "api_version": "1.0",
            "query_id": "00000000-0000-0000-0000-000000000002",
            "query_type": query_type,
            "issued_at": datetime.now(timezone.utc),
            "payload": payload,
        }
    )


def test_join_registers_once() -> None:
    """Ensure join messages register nodes only once."""

    sent: list[tuple[str | None, str]] = []
    events: list[object] = []

    def _send(message: str, destination: str | None) -> None:
        sent.append((destination, message))

    adapter = ReticulumInternalAdapter(send_message=_send)
    adapter.event_bus.subscribe(lambda event: events.append(event))

    adapter.handle_inbound(
        LxmfInbound(
            message_id="msg-1",
            source_id="node-1",
            topic_id=None,
            text=None,
            fields={},
            commands=[{"Command": "join"}],
        )
    )
    adapter.handle_inbound(
        LxmfInbound(
            message_id="msg-2",
            source_id="node-1",
            topic_id=None,
            text=None,
            fields={},
            commands=[{"Command": "join"}],
        )
    )

    node_events = [
        event for event in events if getattr(event, "event_type", None) == EventType.NODE_REGISTERED
    ]
    assert len(node_events) == 1

    result = _run(adapter.core.handle_query(_build_query("GetNodeStatus", {"node_id": "node-1"})))
    assert result.ok is True
    assert result.result.data["status"] == "online"


def test_subscribe_topic_mapping() -> None:
    """Ensure SubscribeTopic commands map to internal subscriptions."""

    sent: list[tuple[str | None, str]] = []

    def _send(message: str, destination: str | None) -> None:
        sent.append((destination, message))

    adapter = ReticulumInternalAdapter(send_message=_send)
    _run(adapter.core.handle_command(_build_create_topic("ops.alpha")))

    adapter.handle_inbound(
        LxmfInbound(
            message_id="msg-3",
            source_id="node-2",
            topic_id=None,
            text=None,
            fields={},
            commands=[{"Command": "SubscribeTopic", "TopicID": "ops.alpha"}],
        )
    )

    result = _run(adapter.core.handle_query(_build_query("GetSubscribers", {"topic_path": "ops.alpha"})))
    assert result.ok is True
    subscribers = result.result.data["subscribers"]
    assert subscribers[0]["node_id"] == "node-2"


def test_create_topic_ignored() -> None:
    """Ensure CreateTopic commands from LXMF are ignored."""

    sent: list[tuple[str | None, str]] = []

    def _send(message: str, destination: str | None) -> None:
        sent.append((destination, message))

    adapter = ReticulumInternalAdapter(send_message=_send)
    adapter.handle_inbound(
        LxmfInbound(
            message_id="msg-4",
            source_id="node-3",
            topic_id=None,
            text=None,
            fields={},
            commands=[{"Command": "CreateTopic", "TopicPath": "ops.beta"}],
        )
    )

    result = _run(adapter.core.handle_query(_build_query("GetTopics", {})))
    assert result.ok is True
    assert result.result.data["topics"] == []


def test_publish_message_text_fanout() -> None:
    """Ensure text messages publish and fan out as plain text."""

    sent: list[tuple[str | None, str]] = []

    def _send(message: str, destination: str | None) -> None:
        sent.append((destination, message))

    adapter = ReticulumInternalAdapter(send_message=_send)
    _run(adapter.core.handle_command(_build_create_topic("ops.chat")))
    adapter.handle_inbound(
        LxmfInbound(
            message_id="msg-5",
            source_id="node-4",
            topic_id=None,
            text=None,
            fields={},
            commands=[{"Command": "SubscribeTopic", "TopicID": "ops.chat"}],
        )
    )
    adapter.handle_inbound(
        LxmfInbound(
            message_id="msg-6",
            source_id="node-4",
            topic_id="ops.chat",
            text="hello",
            fields={},
            commands=[],
        )
    )

    assert sent == [("node-4", "[topic:ops.chat]\nhello")]


def test_telemetry_mapping_updates_metrics() -> None:
    """Ensure telemetry payloads update node metrics without outbound text."""

    sent: list[tuple[str | None, str]] = []

    def _send(message: str, destination: str | None) -> None:
        sent.append((destination, message))

    adapter = ReticulumInternalAdapter(send_message=_send)
    _run(adapter.core.handle_command(_build_create_topic("ops.telemetry")))
    payload = {"battery": 80, "rssi": -70}
    fields = {LXMF.FIELD_TELEMETRY: packb(payload, use_bin_type=True)}
    adapter.handle_inbound(
        LxmfInbound(
            message_id="msg-7",
            source_id="node-5",
            topic_id="ops.telemetry",
            text=None,
            fields=fields,
            commands=[],
        )
    )

    result = _run(adapter.core.handle_query(_build_query("GetNodeStatus", {"node_id": "node-5"})))
    metrics = result.result.data["metrics"]
    assert metrics["battery_pct"] == 80.0
    assert metrics["signal_quality"] == -70.0
    assert sent == []


def test_duplicate_message_ids_ignored() -> None:
    """Ensure duplicate LXMF message IDs are ignored."""

    sent: list[tuple[str | None, str]] = []
    events: list[object] = []

    def _send(message: str, destination: str | None) -> None:
        sent.append((destination, message))

    adapter = ReticulumInternalAdapter(send_message=_send)
    adapter.event_bus.subscribe(lambda event: events.append(event))
    _run(adapter.core.handle_command(_build_create_topic("ops.dupe")))

    inbound = LxmfInbound(
        message_id="dup-1",
        source_id="node-6",
        topic_id="ops.dupe",
        text="hello",
        fields={},
        commands=[],
    )
    adapter.handle_inbound(inbound)
    adapter.handle_inbound(inbound)

    message_events = [
        event
        for event in events
        if getattr(event, "event_type", None) == EventType.MESSAGE_PUBLISHED
    ]
    assert len(message_events) == 1


def test_dedupe_ttl_allows_late_delivery() -> None:
    """Ensure de-duplication expires after the TTL window."""

    sent: list[tuple[str | None, str]] = []
    events: list[object] = []

    class _Clock:
        def __init__(self) -> None:
            self.now = 0.0

        def __call__(self) -> float:
            return self.now

    clock = _Clock()

    def _send(message: str, destination: str | None) -> None:
        sent.append((destination, message))

    adapter = ReticulumInternalAdapter(send_message=_send, clock=clock)
    adapter.event_bus.subscribe(lambda event: events.append(event))
    _run(adapter.core.handle_command(_build_create_topic("ops.delay")))

    inbound = LxmfInbound(
        message_id="delay-1",
        source_id="node-7",
        topic_id="ops.delay",
        text="hello",
        fields={},
        commands=[],
    )
    adapter.handle_inbound(inbound)
    clock.now = 601.0
    adapter.handle_inbound(inbound)

    message_events = [
        event
        for event in events
        if getattr(event, "event_type", None) == EventType.MESSAGE_PUBLISHED
    ]
    assert len(message_events) == 2
