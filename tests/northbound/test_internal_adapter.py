"""Tests for the internal API adapter routes."""
# pylint: disable=import-error

from __future__ import annotations

import asyncio
from datetime import datetime
from datetime import timezone
from typing import Any
from uuid import uuid4

from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.api.storage import HubStorage
from reticulum_telemetry_hub.config import HubConfigurationManager
from reticulum_telemetry_hub.internal_api.v1.enums import CommandType
from reticulum_telemetry_hub.internal_api.v1.enums import IssuerType
from reticulum_telemetry_hub.internal_api.v1.enums import NodeType
from reticulum_telemetry_hub.internal_api.v1.enums import RetentionPolicy
from reticulum_telemetry_hub.internal_api.v1.enums import Visibility
from reticulum_telemetry_hub.internal_api.v1.schemas import CommandEnvelope
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.northbound.internal_adapter import handle_internal_event_socket
from reticulum_telemetry_hub.northbound.app import create_app
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog


class _FakeEventBus:
    """Minimal event bus for internal websocket handler tests."""

    def __init__(self) -> None:
        self._handlers: list = []
        self.unsubscribed = False

    def subscribe(self, handler):
        self._handlers.append(handler)

        def _unsubscribe() -> None:
            self.unsubscribed = True
            if handler in self._handlers:
                self._handlers.remove(handler)

        return _unsubscribe

    async def emit(self, event) -> None:
        """Invoke subscribed handlers with the provided event."""

        for handler in list(self._handlers):
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result


class _FakeEvent:
    """Simple event payload wrapper matching the handler contract."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        """Return the serialized event payload."""

        assert mode == "json"
        return dict(self._payload)


class _DisconnectingWebSocket:
    """Fake websocket that can emit a disconnect to the handler."""

    def __init__(self) -> None:
        self.accepted = False
        self.sent: list[dict[str, Any]] = []
        self._disconnect = asyncio.Event()

    async def accept(self) -> None:
        self.accepted = True

    async def receive_text(self) -> str:
        await self._disconnect.wait()
        raise WebSocketDisconnect()

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)

    def disconnect(self) -> None:
        """Trigger a websocket disconnect."""

        self._disconnect.set()


def _build_api(tmp_path) -> ReticulumTelemetryHubAPI:
    """Create an API instance backed by a temp database."""

    config_manager = HubConfigurationManager(storage_path=tmp_path)
    storage = HubStorage(tmp_path / "hub.sqlite")
    return ReticulumTelemetryHubAPI(config_manager=config_manager, storage=storage)


def _make_command(
    command_type: CommandType,
    payload: dict,
    *,
    issuer_id: str,
    issuer_type: IssuerType,
) -> CommandEnvelope:
    """Build a command envelope for adapter setup."""

    return CommandEnvelope.model_validate(
        {
            "api_version": "1.0",
            "command_id": uuid4(),
            "command_type": command_type,
            "issued_at": datetime.now(timezone.utc),
            "issuer": {"type": issuer_type, "id": issuer_id},
            "payload": payload,
        }
    )


def _send_command(client: TestClient, command: CommandEnvelope):
    """Send a command through the internal adapter bus."""

    adapter = client.app.state.internal_adapter
    return client.portal.call(adapter.command_bus.send, command)


def test_internal_topics_empty(tmp_path) -> None:
    """Ensure internal topics endpoint returns an empty list initially."""

    api = _build_api(tmp_path)
    telemetry = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)
    app = create_app(api=api, telemetry_controller=telemetry, event_log=EventLog())

    with TestClient(app) as client:
        response = client.get("/internal/topics")

    assert response.status_code == 200
    assert response.json() == []


def test_internal_topics_returns_ids(tmp_path) -> None:
    """Ensure internal topics endpoint flattens topic identifiers."""

    api = _build_api(tmp_path)
    telemetry = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)
    app = create_app(api=api, telemetry_controller=telemetry, event_log=EventLog())

    with TestClient(app) as client:
        command = _make_command(
            CommandType.CREATE_TOPIC,
            {
                "topic_path": "ops.alpha",
                "retention": RetentionPolicy.EPHEMERAL,
                "visibility": Visibility.PUBLIC,
            },
            issuer_id="gateway",
            issuer_type=IssuerType.API,
        )
        result = _send_command(client, command)

        assert result.status.value == "accepted"
        response = client.get("/internal/topics")

    assert response.status_code == 200
    assert response.json() == ["ops.alpha"]


def test_internal_subscribers_returns_ids(tmp_path) -> None:
    """Ensure internal subscribers endpoint returns node identifiers only."""

    api = _build_api(tmp_path)
    telemetry = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)
    app = create_app(api=api, telemetry_controller=telemetry, event_log=EventLog())

    with TestClient(app) as client:
        _send_command(
            client,
            _make_command(
                CommandType.CREATE_TOPIC,
                {
                    "topic_path": "ops.beta",
                    "retention": RetentionPolicy.EPHEMERAL,
                    "visibility": Visibility.PUBLIC,
                },
                issuer_id="gateway",
                issuer_type=IssuerType.API,
            ),
        )
        _send_command(
            client,
            _make_command(
                CommandType.REGISTER_NODE,
                {"node_id": "node-1", "node_type": NodeType.RETICULUM},
                issuer_id="node-1",
                issuer_type=IssuerType.RETICULUM,
            ),
        )
        _send_command(
            client,
            _make_command(
                CommandType.SUBSCRIBE_TOPIC,
                {"subscriber_id": "node-1", "topic_path": "ops.beta"},
                issuer_id="node-1",
                issuer_type=IssuerType.RETICULUM,
            ),
        )

        response = client.get("/internal/topics/ops.beta/subscribers")

    assert response.status_code == 200
    assert response.json() == ["node-1"]


def test_internal_subscribers_missing_topic(tmp_path) -> None:
    """Ensure missing topics return a 404 from internal subscribers."""

    api = _build_api(tmp_path)
    telemetry = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)
    app = create_app(api=api, telemetry_controller=telemetry, event_log=EventLog())

    with TestClient(app) as client:
        response = client.get("/internal/topics/missing/subscribers")

    assert response.status_code == 404


def test_internal_node_status_unknown(tmp_path) -> None:
    """Ensure unknown nodes return online false."""

    api = _build_api(tmp_path)
    telemetry = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)
    app = create_app(api=api, telemetry_controller=telemetry, event_log=EventLog())

    with TestClient(app) as client:
        response = client.get("/internal/nodes/node-unknown")

    assert response.status_code == 200
    payload = response.json()
    assert payload["online"] is False
    assert payload["topics"] == []


def test_internal_node_status_online(tmp_path) -> None:
    """Ensure registered nodes map to online true."""

    api = _build_api(tmp_path)
    telemetry = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)
    app = create_app(api=api, telemetry_controller=telemetry, event_log=EventLog())

    with TestClient(app) as client:
        _send_command(
            client,
            _make_command(
                CommandType.REGISTER_NODE,
                {"node_id": "node-2", "node_type": NodeType.RETICULUM},
                issuer_id="node-2",
                issuer_type=IssuerType.RETICULUM,
            ),
        )
        response = client.get("/internal/nodes/node-2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["online"] is True


def test_internal_message_requires_topic(tmp_path) -> None:
    """Ensure PublishMessage rejections map to 404s."""

    api = _build_api(tmp_path)
    telemetry = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)
    app = create_app(api=api, telemetry_controller=telemetry, event_log=EventLog())

    with TestClient(app) as client:
        response = client.post(
            "/internal/message",
            json={"destination": "ops.missing", "text": "hello"},
        )

    assert response.status_code == 404


def test_internal_message_accepts_text(tmp_path) -> None:
    """Ensure PublishMessage accepts text payloads."""

    api = _build_api(tmp_path)
    telemetry = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)
    app = create_app(api=api, telemetry_controller=telemetry, event_log=EventLog())

    with TestClient(app) as client:
        _send_command(
            client,
            _make_command(
                CommandType.CREATE_TOPIC,
                {
                    "topic_path": "ops.msg",
                    "retention": RetentionPolicy.EPHEMERAL,
                    "visibility": Visibility.PUBLIC,
                },
                issuer_id="gateway",
                issuer_type=IssuerType.API,
            ),
        )
        response = client.post(
            "/internal/message",
            json={"destination": "ops.msg", "text": "hello"},
        )

    assert response.status_code == 200
    assert response.json()["accepted"] is True


def test_internal_events_stream(tmp_path) -> None:
    """Ensure the internal event stream emits published events."""

    api = _build_api(tmp_path)
    telemetry = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)
    app = create_app(api=api, telemetry_controller=telemetry, event_log=EventLog())

    with TestClient(app) as client:
        with client.websocket_connect("/internal/events/stream") as websocket:
            _send_command(
                client,
                _make_command(
                    CommandType.CREATE_TOPIC,
                    {
                        "topic_path": "ops.events",
                        "retention": RetentionPolicy.EPHEMERAL,
                        "visibility": Visibility.PUBLIC,
                    },
                    issuer_id="gateway",
                    issuer_type=IssuerType.API,
                ),
            )
            event = websocket.receive_json()

    assert event["event_type"] == "TopicCreated"


def test_handle_internal_event_socket_reaps_disconnected_clients() -> None:
    """Ensure the internal event socket unsubscribes when the client disconnects."""

    async def _exercise() -> None:
        event_bus = _FakeEventBus()
        websocket = _DisconnectingWebSocket()
        task = asyncio.create_task(
            handle_internal_event_socket(websocket, event_bus=event_bus)
        )

        await asyncio.sleep(0)
        assert websocket.accepted is True

        await event_bus.emit(_FakeEvent({"event_type": "TopicCreated"}))
        for _ in range(10):
            if websocket.sent:
                break
            await asyncio.sleep(0)
        assert websocket.sent == [{"event_type": "TopicCreated"}]

        websocket.disconnect()
        await task

        assert event_bus.unsubscribed is True

    asyncio.run(_exercise())
