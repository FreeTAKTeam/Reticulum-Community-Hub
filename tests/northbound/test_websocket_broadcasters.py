"""Tests for northbound websocket broadcasters."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import threading
from typing import Awaitable
from typing import Callable
from typing import Optional

import pytest

from reticulum_telemetry_hub.northbound.websocket import EventBroadcaster
from reticulum_telemetry_hub.northbound.websocket import TelemetryBroadcaster
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog


@dataclass(frozen=True)
class _FakeSubscriber:
    """Fake subscriber record for topic filtering."""

    destination: str


class _FakeApi:
    """Fake API service returning topic subscribers."""

    def __init__(self, destinations: list[str]) -> None:
        """Initialize with a list of destinations."""

        self._destinations = destinations

    def list_subscribers_for_topic(self, topic_id: str) -> list[_FakeSubscriber]:
        """Return fake topic subscribers."""

        return [_FakeSubscriber(destination=value) for value in self._destinations]


class _FakeTelemetryController:
    """Fake telemetry controller that forwards telemetry callbacks."""

    def __init__(self) -> None:
        """Initialize the fake controller."""

        self._listener: Optional[
            Callable[[dict, str | bytes | None, Optional[object]], None]
        ] = None

    def register_listener(
        self,
        listener: Callable[[dict, str | bytes | None, Optional[object]], None],
    ) -> None:
        """Register a telemetry listener."""

        self._listener = listener

    def emit(self, telemetry: dict, peer_hash: str, timestamp: Optional[object]) -> None:
        """Emit telemetry to the registered listener."""

        if self._listener is not None:
            self._listener(telemetry, peer_hash, timestamp)


def test_topic_subscription_uses_frozenset() -> None:
    """Ensure topic-filtered subscriptions store hashable filters."""

    controller = _FakeTelemetryController()
    api = _FakeApi(["abc", "def"])
    broadcaster = TelemetryBroadcaster(controller, api)

    async def _callback(_: dict) -> None:
        """No-op callback for subscription."""

        return None

    broadcaster.subscribe(_callback, topic_id="topic")

    subscriber = next(iter(broadcaster._subscribers))

    assert isinstance(subscriber.allowed_destinations, frozenset)


def test_topic_subscription_requires_api() -> None:
    """Ensure topic filtering requires an API service."""

    controller = _FakeTelemetryController()
    broadcaster = TelemetryBroadcaster(controller, None)

    async def _callback(_: dict) -> None:
        """No-op callback for subscription."""

        return None

    with pytest.raises(ValueError):
        broadcaster.subscribe(_callback, topic_id="topic")


def _run_async(coro: Callable[[], Awaitable[None]]) -> None:
    """Run an async coroutine in a fresh event loop."""

    asyncio.run(coro())


def test_event_broadcaster_dispatches_without_loop() -> None:
    """Ensure event broadcaster uses the captured loop from threads."""

    async def _exercise() -> None:
        event_log = EventLog()
        broadcaster = EventBroadcaster(event_log)
        received = asyncio.Event()
        seen: dict[str, object] = {}

        async def _callback(entry: dict) -> None:
            """Store the event entry."""

            seen.update(entry)
            received.set()

        broadcaster.subscribe(_callback)

        def _emit() -> None:
            """Emit an event from a non-async thread."""

            event_log.add_event("test", "message")

        thread = threading.Thread(target=_emit)
        thread.start()
        thread.join()

        await asyncio.wait_for(received.wait(), timeout=1.0)

        assert seen["type"] == "test"

    _run_async(_exercise)


def test_telemetry_broadcaster_dispatches_without_loop() -> None:
    """Ensure telemetry broadcaster uses the captured loop from threads."""

    async def _exercise() -> None:
        controller = _FakeTelemetryController()
        broadcaster = TelemetryBroadcaster(controller, None)
        received = asyncio.Event()
        result: dict[str, object] = {}

        async def _callback(entry: dict) -> None:
            """Store the telemetry entry."""

            result.update(entry)
            received.set()

        broadcaster.subscribe(_callback)

        def _emit() -> None:
            """Emit telemetry from a non-async thread."""

            controller.emit({"foo": "bar"}, "peer", None)

        thread = threading.Thread(target=_emit)
        thread.start()
        thread.join()

        await asyncio.wait_for(received.wait(), timeout=1.0)

        assert result["peer_destination"] == "peer"

    _run_async(_exercise)


def test_telemetry_subscription_filters_peer_destinations() -> None:
    """Ensure telemetry filters respect allowed destinations."""

    async def _exercise() -> None:
        controller = _FakeTelemetryController()
        api = _FakeApi(["peer-1"])
        broadcaster = TelemetryBroadcaster(controller, api)
        received: list[str] = []

        async def _callback(entry: dict) -> None:
            """Store the peer destination."""

            received.append(str(entry["peer_destination"]))

        broadcaster.subscribe(_callback, topic_id="topic")

        controller.emit({"foo": "bar"}, "peer-1", None)
        controller.emit({"foo": "bar"}, "peer-2", None)

        await asyncio.sleep(0)

        assert received == ["peer-1"]

    _run_async(_exercise)
