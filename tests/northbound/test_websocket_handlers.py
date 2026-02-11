"""Tests for northbound websocket socket handlers."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from reticulum_telemetry_hub.northbound.websocket import authenticate_websocket
from reticulum_telemetry_hub.northbound.websocket import handle_message_socket
from reticulum_telemetry_hub.northbound.websocket import handle_system_socket
from reticulum_telemetry_hub.northbound.websocket import handle_telemetry_socket


class _FakeWebSocket:
    """Minimal async websocket test double."""

    def __init__(self, inbound: list[dict[str, Any] | str]) -> None:
        self._inbound = [item if isinstance(item, str) else json.dumps(item) for item in inbound]
        self.sent: list[dict[str, Any]] = []
        self.closed: list[int] = []
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def receive_text(self) -> str:
        if not self._inbound:
            raise RuntimeError("disconnect")
        return self._inbound.pop(0)

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)

    async def close(self, code: int) -> None:
        self.closed.append(code)


class _FakeAuth:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed

    def validate_credentials(self, api_key, token) -> bool:
        return self.allowed and token == "ok-token" and api_key == "ok-key"


class _FakeEventBroadcaster:
    def __init__(self) -> None:
        self.unsubscribed = False

    def subscribe(self, callback):
        self.callback = callback

        def _unsubscribe() -> None:
            self.unsubscribed = True

        return _unsubscribe


class _FakeTelemetryBroadcaster:
    def __init__(self) -> None:
        self.unsubscribed = False
        self.calls: list[tuple[str | None]] = []

    def subscribe(self, callback, *, topic_id=None):
        self.calls.append((topic_id,))

        def _unsubscribe() -> None:
            self.unsubscribed = True

        return _unsubscribe


class _FakeMessageBroadcaster:
    def __init__(self) -> None:
        self.unsubscribed = False
        self.calls: list[dict[str, str | None]] = []

    def subscribe(self, callback, *, topic_id=None, source_hash=None):
        self.calls.append({"topic_id": topic_id, "source_hash": source_hash})

        def _unsubscribe() -> None:
            self.unsubscribed = True

        return _unsubscribe


def test_authenticate_websocket_error_paths_and_success() -> None:
    """Exercise auth timeout/request/unauthorized/success branches."""

    async def _exercise() -> None:
        timeout_ws = _FakeWebSocket([])
        ok = await authenticate_websocket(timeout_ws, auth=_FakeAuth(True), timeout_seconds=0)
        assert ok is False
        assert timeout_ws.closed == [4001]

        bad_payload_ws = _FakeWebSocket(["[]"])
        ok = await authenticate_websocket(bad_payload_ws, auth=_FakeAuth(True))
        assert ok is False
        assert bad_payload_ws.closed == [4002]

        missing_auth_ws = _FakeWebSocket([{"type": "noop", "data": {}}])
        ok = await authenticate_websocket(missing_auth_ws, auth=_FakeAuth(True))
        assert ok is False
        assert missing_auth_ws.closed == [4002]

        unauthorized_ws = _FakeWebSocket(
            [{"type": "auth", "data": {"token": "ok-token", "api_key": "wrong"}}]
        )
        ok = await authenticate_websocket(unauthorized_ws, auth=_FakeAuth(True))
        assert ok is False
        assert unauthorized_ws.closed == [4003]

        success_ws = _FakeWebSocket(
            [{"type": "auth", "data": {"token": "ok-token", "api_key": "ok-key"}}]
        )
        ok = await authenticate_websocket(success_ws, auth=_FakeAuth(True))
        assert ok is True
        assert success_ws.closed == []
        assert success_ws.sent[-1]["type"] == "auth.ok"

    asyncio.run(_exercise())


def test_handle_system_socket_handles_subscribe_and_bad_request(monkeypatch) -> None:
    """Exercise system socket message handling and cleanup."""

    async def _exercise() -> None:
        websocket = _FakeWebSocket(
            [
                {
                    "type": "system.subscribe",
                    "data": {"include_status": True, "include_events": False, "events_limit": 1},
                },
                {"type": "unsupported"},
            ]
        )
        broadcaster = _FakeEventBroadcaster()

        async def _fake_ping_loop(*_args, **_kwargs):
            await asyncio.sleep(999)

        monkeypatch.setattr(
            "reticulum_telemetry_hub.northbound.websocket.authenticate_websocket",
            lambda *args, **kwargs: asyncio.sleep(0, result=True),
        )
        monkeypatch.setattr(
            "reticulum_telemetry_hub.northbound.websocket.ping_loop",
            _fake_ping_loop,
        )

        await handle_system_socket(
            websocket,
            auth=_FakeAuth(True),
            event_broadcaster=broadcaster,
            status_provider=lambda: {"ok": True},
            event_list_provider=lambda limit: [{"n": limit}],
        )

        assert websocket.accepted is True
        assert broadcaster.unsubscribed is True
        assert any(item["type"] == "system.status" for item in websocket.sent)
        assert any(item["type"] == "error" for item in websocket.sent)

    asyncio.run(_exercise())


def test_handle_telemetry_socket_subscribe_variants(monkeypatch) -> None:
    """Exercise telemetry subscription validation and follow wiring."""

    async def _exercise() -> None:
        websocket = _FakeWebSocket(
            [
                {"type": "telemetry.subscribe", "data": {"since": "bad"}},
                {"type": "telemetry.subscribe", "data": {"since": 7, "topic_id": "t1", "follow": True}},
            ]
        )
        broadcaster = _FakeTelemetryBroadcaster()

        async def _fake_ping_loop(*_args, **_kwargs):
            await asyncio.sleep(999)

        monkeypatch.setattr(
            "reticulum_telemetry_hub.northbound.websocket.authenticate_websocket",
            lambda *args, **kwargs: asyncio.sleep(0, result=True),
        )
        monkeypatch.setattr(
            "reticulum_telemetry_hub.northbound.websocket.ping_loop",
            _fake_ping_loop,
        )

        await handle_telemetry_socket(
            websocket,
            auth=_FakeAuth(True),
            telemetry_broadcaster=broadcaster,
            telemetry_snapshot=lambda since, topic_id: [{"since": since, "topic": topic_id}],
        )

        assert websocket.accepted is True
        assert any(item["type"] == "telemetry.snapshot" for item in websocket.sent)
        assert any(item["type"] == "error" for item in websocket.sent)
        assert broadcaster.calls == [("t1",)]
        assert broadcaster.unsubscribed is True

    asyncio.run(_exercise())


def test_handle_message_socket_subscribe_send_and_errors(monkeypatch) -> None:
    """Exercise message subscription and send command branches."""

    async def _exercise() -> None:
        websocket = _FakeWebSocket(
            [
                {"type": "message.subscribe", "data": {"topic_id": "chat", "source_hash": "abc", "follow": True}},
                {"type": "message.send", "data": {"content": "   "}},
                {"type": "message.send", "data": {"content": "hi", "topic_id": "chat", "destination": "abcd"}},
                {"type": "unsupported"},
            ]
        )
        broadcaster = _FakeMessageBroadcaster()
        sent_payloads: list[dict[str, str | None]] = []

        async def _fake_ping_loop(*_args, **_kwargs):
            await asyncio.sleep(999)

        monkeypatch.setattr(
            "reticulum_telemetry_hub.northbound.websocket.authenticate_websocket",
            lambda *args, **kwargs: asyncio.sleep(0, result=True),
        )
        monkeypatch.setattr(
            "reticulum_telemetry_hub.northbound.websocket.ping_loop",
            _fake_ping_loop,
        )

        def _message_sender(content: str, topic_id: str | None = None, destination: str | None = None):
            sent_payloads.append({"content": content, "topic_id": topic_id, "destination": destination})

        await handle_message_socket(
            websocket,
            auth=_FakeAuth(True),
            message_broadcaster=broadcaster,
            message_sender=_message_sender,
        )

        assert websocket.accepted is True
        assert broadcaster.calls == [{"topic_id": "chat", "source_hash": "abc"}]
        assert broadcaster.unsubscribed is True
        assert sent_payloads == [{"content": "hi", "topic_id": "chat", "destination": "abcd"}]
        response_types = [item["type"] for item in websocket.sent]
        assert "message.subscribed" in response_types
        assert "message.sent" in response_types
        assert "error" in response_types

    asyncio.run(_exercise())
