"""Tests for WebSocket helper utilities."""

import json
import pytest

from reticulum_telemetry_hub.northbound.websocket import _get_subscribe_flags
from reticulum_telemetry_hub.northbound.websocket import _get_telemetry_subscription
from reticulum_telemetry_hub.northbound.websocket import build_error_message
from reticulum_telemetry_hub.northbound.websocket import build_ping_message
from reticulum_telemetry_hub.northbound.websocket import build_ws_message
from reticulum_telemetry_hub.northbound.websocket import parse_ws_message


def test_build_ws_message_includes_type_and_data() -> None:
    """Ensure WebSocket envelopes include type and data."""

    message = build_ws_message("test", {"k": "v"})

    assert message["type"] == "test"
    assert message["data"]["k"] == "v"


def test_build_error_message_sets_error_type() -> None:
    """Ensure error messages use the error type."""

    message = build_error_message("code", "message")

    assert message["type"] == "error"
    assert message["data"]["code"] == "code"


def test_build_ping_message_contains_nonce() -> None:
    """Ensure ping messages include a nonce."""

    message = build_ping_message()

    assert message["type"] == "ping"
    assert "nonce" in message["data"]


def test_parse_ws_message_requires_object() -> None:
    """Ensure parse_ws_message rejects non-object payloads."""

    payload = json.dumps(["bad"])

    with pytest.raises(ValueError):
        parse_ws_message(payload)


def test_get_subscribe_flags_defaults() -> None:
    """Ensure subscription flags default sensibly."""

    include_status, include_events, events_limit = _get_subscribe_flags({})

    assert include_status is True
    assert include_events is True
    assert events_limit == 50


def test_get_telemetry_subscription_requires_since() -> None:
    """Ensure telemetry subscription requires a numeric since value."""

    with pytest.raises(ValueError):
        _get_telemetry_subscription({"since": "bad"})

    since, topic_id, follow = _get_telemetry_subscription({"since": 10, "follow": False})

    assert since == 10
    assert topic_id is None
    assert follow is False
