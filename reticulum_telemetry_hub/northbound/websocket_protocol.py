"""WebSocket protocol, auth, and lifecycle helpers."""
# pylint: disable=import-error

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from contextlib import suppress
from datetime import datetime
from datetime import timezone
from typing import Any
from typing import Awaitable
from typing import Callable
from typing import Dict
from typing import Optional
from typing import TypeAlias

from fastapi import WebSocket

from .auth import ApiAuth
from .websocket_delivery import _metrics_observe_ms

DEFAULT_WS_PING_INTERVAL_SECONDS = 30.0
DEFAULT_WS_INACTIVITY_TIMEOUT_SECONDS = 90.0
DEFAULT_WS_STATUS_REFRESH_INTERVAL_SECONDS = 3.0
DEFAULT_WS_STATUS_FANOUT_MODE = "event_only"
_WS_STATUS_FANOUT_MODES = {"event_only", "periodic", "event_plus_periodic"}
WS_INACTIVITY_CLOSE_CODE = 4004
LOGGER = logging.getLogger(__name__)

# Contract: providers used by websocket handlers must be non-blocking
# (async-native or internally offloaded with ``asyncio.to_thread``).
TelemetrySnapshotProvider: TypeAlias = Callable[
    [int, Optional[str]],
    Awaitable[list[Dict[str, object]]],
]

def _normalize_peer(peer_hash: str | bytes | None) -> str:
    """Return a normalized peer destination string.

    Args:
        peer_hash (str | bytes | None): Peer hash input.

    Returns:
        str: Normalized peer destination.
    """

    if peer_hash is None:
        return ""
    if isinstance(peer_hash, (bytes, bytearray)):
        return peer_hash.hex()
    return str(peer_hash)


def _utcnow_iso() -> str:
    """Return an RFC3339 timestamp string in UTC.

    Returns:
        str: Current timestamp string.
    """

    return datetime.now(timezone.utc).isoformat()


def build_ws_message(message_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a WebSocket envelope payload.

    Args:
        message_type (str): Message type identifier.
        data (Dict[str, Any]): Payload data.

    Returns:
        Dict[str, Any]: Envelope payload.
    """

    return {"type": message_type, "ts": _utcnow_iso(), "data": data}


def build_error_message(code: str, message: str) -> Dict[str, Any]:
    """Create a standardized error message envelope.

    Args:
        code (str): Error code.
        message (str): Error message.

    Returns:
        Dict[str, Any]: Error message envelope.
    """

    return build_ws_message("error", {"code": code, "message": message})


def build_ping_message() -> Dict[str, Any]:
    """Create a ping message envelope.

    Returns:
        Dict[str, Any]: Ping message payload.
    """

    return build_ws_message("ping", {"nonce": uuid.uuid4().hex})


def parse_ws_message(payload: str) -> Dict[str, Any]:
    """Parse a WebSocket JSON payload.

    Args:
        payload (str): JSON message string.

    Returns:
        Dict[str, Any]: Parsed JSON payload.

    Raises:
        ValueError: If parsing fails or payload is not a JSON object.
    """

    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("WebSocket payload must be a JSON object")
    return data


def _extract_auth_data(message: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """Extract auth credentials from a message.

    Args:
        message (Dict[str, Any]): Parsed message payload.

    Returns:
        tuple[Optional[str], Optional[str]]: Token and API key values.
    """

    data = message.get("data")
    if not isinstance(data, dict):
        return None, None
    token = data.get("token")
    api_key = data.get("api_key")
    return token, api_key


def _is_auth_message(message: Dict[str, Any]) -> bool:
    """Return ``True`` when the message is an auth payload.

    Args:
        message (Dict[str, Any]): Parsed message payload.

    Returns:
        bool: ``True`` when the message is an auth payload.
    """

    return message.get("type") == "auth"


def _get_message_type(message: Dict[str, Any]) -> str:
    """Return the message type string.

    Args:
        message (Dict[str, Any]): Parsed message payload.

    Returns:
        str: Message type string.
    """

    msg_type = message.get("type")
    return str(msg_type) if msg_type is not None else ""


def _get_message_data(message: Dict[str, Any]) -> Dict[str, Any]:
    """Return the message data dict.

    Args:
        message (Dict[str, Any]): Parsed message payload.

    Returns:
        Dict[str, Any]: Payload data.
    """

    data = message.get("data")
    return data if isinstance(data, dict) else {}


def _validated_auth(
    auth: ApiAuth,
    token: Optional[str],
    api_key: Optional[str],
    *,
    client_host: Optional[str] = None,
) -> bool:
    """Return ``True`` when auth credentials are valid.

    Args:
        auth (ApiAuth): Auth validator.
        token (Optional[str]): Bearer token.
        api_key (Optional[str]): API key header.

    Returns:
        bool: ``True`` when credentials are valid.
    """

    try:
        return auth.validate_credentials(api_key, token, client_host=client_host)
    except TypeError:
        # Compatibility for tests/stubs that still expose the legacy signature.
        return auth.validate_credentials(api_key, token)


def _resolve_client_host(websocket: WebSocket) -> Optional[str]:
    """Return the client host for a websocket when available."""

    client = getattr(websocket, "client", None)
    if client is None:
        return None
    host = getattr(client, "host", None)
    if host is None:
        return None
    return str(host)


def _auth_failure_detail(auth: ApiAuth, client_host: Optional[str]) -> str:
    """Return an auth failure detail with compatibility fallback."""

    detail_builder = getattr(auth, "failure_detail", None)
    if callable(detail_builder):
        return str(detail_builder(client_host))
    return "Unauthorized"


def _get_subscribe_flags(
    data: Dict[str, Any],
    *,
    default_include_status: bool,
    default_include_events: bool,
) -> tuple[bool, bool, int]:
    """Return subscription flags for system events.

    Args:
        data (Dict[str, Any]): Subscription payload.

    Returns:
        tuple[bool, bool, int]: include_status, include_events, events_limit.
    """

    include_status = data.get("include_status")
    include_events = data.get("include_events")
    include_status_flag = default_include_status if include_status is None else bool(include_status)
    include_events_flag = default_include_events if include_events is None else bool(include_events)
    events_limit = data.get("events_limit")
    if not isinstance(events_limit, int) or events_limit <= 0:
        events_limit = 50
    return include_status_flag, include_events_flag, events_limit


def _normalize_status_fanout_mode(mode: str) -> str:
    """Return a supported status fan-out mode."""

    normalized = str(mode).strip().lower()
    if normalized in _WS_STATUS_FANOUT_MODES:
        return normalized
    return DEFAULT_WS_STATUS_FANOUT_MODE


def _get_telemetry_subscription(data: Dict[str, Any]) -> tuple[int, Optional[str], bool]:
    """Return telemetry subscription settings.

    Args:
        data (Dict[str, Any]): Subscription payload.

    Returns:
        tuple[int, Optional[str], bool]: since timestamp, topic ID, follow flag.

    Raises:
        ValueError: If required fields are missing.
    """

    since = data.get("since")
    if not isinstance(since, int):
        raise ValueError("Telemetry subscription requires a numeric 'since' field")
    topic_id = data.get("topic_id")
    follow = data.get("follow")
    follow_flag = True if follow is None else bool(follow)
    return since, topic_id, follow_flag


def _get_message_subscription(data: Dict[str, Any]) -> tuple[Optional[str], Optional[str], bool]:
    """Return message subscription settings."""

    topic_id = data.get("topic_id")
    source_hash = data.get("source_hash") or data.get("source")
    follow = data.get("follow")
    follow_flag = True if follow is None else bool(follow)
    return topic_id, source_hash, follow_flag


def _get_message_send_payload(data: Dict[str, Any]) -> tuple[str, Optional[str], Optional[str]]:
    """Return message send parameters from the payload."""

    content = data.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Message send requires non-empty 'content'")
    topic_id = data.get("topic_id")
    destination = data.get("destination")
    if destination is not None and not isinstance(destination, str):
        raise ValueError("Message destination must be a string")
    return content, topic_id, destination


async def authenticate_websocket(
    websocket: WebSocket,
    *,
    auth: ApiAuth,
    timeout_seconds: float = 5.0,
) -> bool:
    """Authenticate a WebSocket connection.

    Args:
        websocket (WebSocket): WebSocket connection.
        auth (ApiAuth): Auth validator.
        timeout_seconds (float): Timeout for the auth message.

    Returns:
        bool: ``True`` when authentication succeeds.
    """

    try:
        payload = await asyncio.wait_for(websocket.receive_text(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        await websocket.send_json(build_error_message("timeout", "Authentication timed out"))
        await websocket.close(code=4001)
        return False

    try:
        message = parse_ws_message(payload)
    except ValueError as exc:
        await websocket.send_json(build_error_message("bad_request", str(exc)))
        await websocket.close(code=4002)
        return False

    if not _is_auth_message(message):
        await websocket.send_json(build_error_message("bad_request", "Auth message required"))
        await websocket.close(code=4002)
        return False

    token, api_key = _extract_auth_data(message)
    client_host = _resolve_client_host(websocket)
    if not _validated_auth(auth, token, api_key, client_host=client_host):
        await websocket.send_json(
            build_error_message("unauthorized", _auth_failure_detail(auth, client_host))
        )
        await websocket.close(code=4003)
        return False

    await websocket.send_json(build_ws_message("auth.ok", {}))
    return True


async def ping_loop(
    websocket: WebSocket,
    *,
    interval_seconds: float = DEFAULT_WS_PING_INTERVAL_SECONDS,
) -> None:
    """Send periodic ping messages to a WebSocket.

    Args:
        websocket (WebSocket): WebSocket connection.
        interval_seconds (float): Ping interval in seconds.
    """

    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await websocket.send_json(build_ping_message())
        except Exception:  # pragma: no cover - socket shutdown varies
            return


def _remaining_inactivity_timeout(
    last_activity_at: float,
    *,
    inactivity_timeout_seconds: float,
) -> float:
    """Return the remaining time before a websocket is considered stale.

    Args:
        last_activity_at (float): ``time.monotonic()`` timestamp of the most
            recent client payload.
        inactivity_timeout_seconds (float): Maximum idle time allowed.

    Returns:
        float: Positive timeout to use for the next receive call.
    """

    elapsed = time.monotonic() - last_activity_at
    remaining = inactivity_timeout_seconds - elapsed
    return max(0.1, remaining)


async def _receive_text_with_inactivity_timeout(
    websocket: WebSocket,
    *,
    last_activity_at: float,
    inactivity_timeout_seconds: float,
) -> str:
    """Read the next websocket text payload with inactivity enforcement.

    Args:
        websocket (WebSocket): Active websocket connection.
        last_activity_at (float): ``time.monotonic()`` timestamp of the most
            recent inbound message.
        inactivity_timeout_seconds (float): Maximum idle time allowed.

    Returns:
        str: Next inbound websocket payload.
    """

    timeout_seconds = _remaining_inactivity_timeout(
        last_activity_at,
        inactivity_timeout_seconds=inactivity_timeout_seconds,
    )
    return await asyncio.wait_for(websocket.receive_text(), timeout=timeout_seconds)


async def _close_inactive_websocket(websocket: WebSocket) -> None:
    """Close a websocket that stopped responding to keepalive traffic.

    Args:
        websocket (WebSocket): WebSocket to close.
    """

    try:
        await websocket.send_json(
            build_error_message("timeout", "WebSocket client timed out waiting for keepalive pong")
        )
    except Exception:  # pragma: no cover - best effort on broken sockets
        pass

    try:
        await websocket.close(code=WS_INACTIVITY_CLOSE_CODE)
    except Exception:  # pragma: no cover - close failures are non-fatal
        pass


async def _cancel_task(task: asyncio.Task[Any] | None) -> None:
    """Cancel and await a background task.

    Args:
        task (asyncio.Task[Any] | None): Task to cancel.
    """

    if task is None:
        return

    task.cancel()
    with suppress(asyncio.CancelledError):
        try:
            await task
        except Exception:
            return


async def _send_json_timed(
    websocket: WebSocket,
    payload: Dict[str, Any],
    *,
    runtime_metrics: object | None = None,
    metric_key: str,
) -> None:
    """Send websocket JSON while recording send latency."""

    started = time.perf_counter()
    await websocket.send_json(payload)
    _metrics_observe_ms(runtime_metrics, metric_key, (time.perf_counter() - started) * 1000.0)


