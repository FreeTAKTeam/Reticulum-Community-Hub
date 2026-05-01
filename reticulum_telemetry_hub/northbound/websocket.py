"""WebSocket helpers for the northbound API."""
# pylint: disable=import-error

from __future__ import annotations

from . import websocket_handlers as _handlers
from .websocket_broadcasters import EventBroadcaster
from .websocket_broadcasters import MessageBroadcaster
from .websocket_broadcasters import TelemetryBroadcaster
from .websocket_protocol import DEFAULT_WS_STATUS_FANOUT_MODE
from .websocket_protocol import DEFAULT_WS_STATUS_REFRESH_INTERVAL_SECONDS
from .websocket_protocol import _get_telemetry_subscription
from .websocket_protocol import _get_subscribe_flags
from .websocket_protocol import authenticate_websocket
from .websocket_protocol import build_error_message
from .websocket_protocol import build_ping_message
from .websocket_protocol import build_ws_message
from .websocket_protocol import ping_loop
from .websocket_protocol import parse_ws_message


async def handle_system_socket(*args, **kwargs):
    """Compatibility wrapper for the system websocket handler."""

    _handlers.authenticate_websocket = authenticate_websocket
    _handlers.ping_loop = ping_loop
    return await _handlers.handle_system_socket(*args, **kwargs)


async def handle_telemetry_socket(*args, **kwargs):
    """Compatibility wrapper for the telemetry websocket handler."""

    _handlers.authenticate_websocket = authenticate_websocket
    _handlers.ping_loop = ping_loop
    return await _handlers.handle_telemetry_socket(*args, **kwargs)


async def handle_message_socket(*args, **kwargs):
    """Compatibility wrapper for the message websocket handler."""

    _handlers.authenticate_websocket = authenticate_websocket
    _handlers.ping_loop = ping_loop
    return await _handlers.handle_message_socket(*args, **kwargs)

__all__ = [
    "DEFAULT_WS_STATUS_FANOUT_MODE",
    "DEFAULT_WS_STATUS_REFRESH_INTERVAL_SECONDS",
    "EventBroadcaster",
    "MessageBroadcaster",
    "TelemetryBroadcaster",
    "_get_subscribe_flags",
    "_get_telemetry_subscription",
    "authenticate_websocket",
    "build_error_message",
    "build_ping_message",
    "build_ws_message",
    "handle_message_socket",
    "handle_system_socket",
    "handle_telemetry_socket",
    "ping_loop",
    "parse_ws_message",
]
