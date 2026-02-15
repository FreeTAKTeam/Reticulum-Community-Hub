"""WebSocket helpers for the northbound API."""
# pylint: disable=import-error

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from typing import Any
from typing import Awaitable
from typing import Callable
from typing import Dict
from typing import Optional

from fastapi import WebSocket

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog

from .auth import ApiAuth


@dataclass(frozen=True)
class _TelemetrySubscriber:
    """Configuration for a telemetry WebSocket subscriber."""

    callback: Callable[[Dict[str, object]], Awaitable[None]]
    allowed_destinations: Optional[frozenset[str]]


@dataclass(frozen=True)
class _MessageSubscriber:
    """Configuration for a message WebSocket subscriber."""

    callback: Callable[[Dict[str, object]], Awaitable[None]]
    topic_id: Optional[str]
    source_hash: Optional[str]


class EventBroadcaster:
    """Fan out events to active WebSocket subscribers."""

    def __init__(self, event_log: EventLog) -> None:
        """Initialize the event broadcaster.

        Args:
            event_log (EventLog): Event log used for event updates.
        """

        self._event_log = event_log
        self._subscribers: set[Callable[[Dict[str, object]], Awaitable[None]]] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._event_log.add_listener(self._handle_event)

    def subscribe(
        self, callback: Callable[[Dict[str, object]], Awaitable[None]]
    ) -> Callable[[], None]:
        """Register an async event callback.

        Args:
            callback (Callable[[Dict[str, object]], Awaitable[None]]): Callback
                invoked for each new event.

        Returns:
            Callable[[], None]: Unsubscribe callback.
        """

        self._subscribers.add(callback)
        self._capture_loop()

        def _unsubscribe() -> None:
            """Remove the event callback subscription.

            Returns:
                None: Removes the callback.
            """

            self._subscribers.discard(callback)

        return _unsubscribe

    def _capture_loop(self) -> None:
        """Capture the running event loop for cross-thread dispatch."""

        if self._loop is not None and self._loop.is_running():
            return
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

    def _create_task(
        self,
        callback: Callable[[Dict[str, object]], Awaitable[None]],
        entry: Dict[str, object],
    ) -> None:
        """Create an asyncio task for a callback on the current loop."""

        loop = asyncio.get_running_loop()
        loop.create_task(callback(entry))

    def _handle_event(self, entry: Dict[str, object]) -> None:
        """Dispatch a new event to subscribers.

        Args:
            entry (Dict[str, object]): Recorded event entry.
        """

        for callback in list(self._subscribers):
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(callback(entry))
                continue
            except RuntimeError:
                pass
            if self._loop is None or not self._loop.is_running():
                # Reason: skip async dispatch when no loop is running.
                continue
            self._loop.call_soon_threadsafe(self._create_task, callback, entry)


class TelemetryBroadcaster:
    """Fan out telemetry updates to WebSocket subscribers."""

    def __init__(
        self,
        controller: TelemetryController,
        api: Optional[ReticulumTelemetryHubAPI],
    ) -> None:
        """Initialize the telemetry broadcaster.

        Args:
            controller (TelemetryController): Telemetry controller instance.
            api (Optional[ReticulumTelemetryHubAPI]): API service for topic
                filtering.
        """

        self._controller = controller
        self._api = api
        self._subscribers: set[_TelemetrySubscriber] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._controller.register_listener(self._handle_telemetry)

    def subscribe(
        self,
        callback: Callable[[Dict[str, object]], Awaitable[None]],
        *,
        topic_id: Optional[str] = None,
    ) -> Callable[[], None]:
        """Register a telemetry callback.

        Args:
            callback (Callable[[Dict[str, object]], Awaitable[None]]): Callback
                invoked with telemetry entries.
            topic_id (Optional[str]): Optional topic filter for telemetry.

        Returns:
            Callable[[], None]: Unsubscribe callback.
        """

        allowed = None
        if topic_id:
            if self._api is None:
                raise ValueError("Topic filtering requires an API service")
            subscribers = self._api.list_subscribers_for_topic(topic_id)
            allowed = frozenset(
                subscriber.destination for subscriber in subscribers
            )
        subscriber = _TelemetrySubscriber(callback=callback, allowed_destinations=allowed)
        self._subscribers.add(subscriber)
        self._capture_loop()

        def _unsubscribe() -> None:
            """Remove the telemetry callback subscription.

            Returns:
                None: Removes the callback.
            """

            self._subscribers.discard(subscriber)

        return _unsubscribe

    def _capture_loop(self) -> None:
        """Capture the running event loop for cross-thread dispatch."""

        if self._loop is not None and self._loop.is_running():
            return
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

    def _create_task(
        self,
        callback: Callable[[Dict[str, object]], Awaitable[None]],
        entry: Dict[str, object],
    ) -> None:
        """Create an asyncio task for a callback on the current loop."""

        loop = asyncio.get_running_loop()
        loop.create_task(callback(entry))

    def _handle_telemetry(
        self,
        telemetry: dict,
        peer_hash: str | bytes | None,
        timestamp: Optional[datetime],
    ) -> None:
        """Dispatch telemetry updates to subscribers.

        Args:
            telemetry (dict): Telemetry payload.
            peer_hash (str | bytes | None): Peer identifier.
            timestamp (Optional[datetime]): Telemetry timestamp.
        """

        peer_dest = _normalize_peer(peer_hash)
        display_name = None
        if self._api is not None and hasattr(
            self._api, "resolve_identity_display_name"
        ):
            try:
                display_name = self._api.resolve_identity_display_name(peer_dest)
            except Exception:  # pragma: no cover - defensive
                display_name = None
        entry = {
            "peer_destination": peer_dest,
            "timestamp": int(timestamp.timestamp()) if timestamp else 0,
            "telemetry": telemetry,
            "display_name": display_name,
            "identity_label": display_name,
        }
        for subscriber in list(self._subscribers):
            if subscriber.allowed_destinations is not None:
                if peer_dest not in subscriber.allowed_destinations:
                    continue
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(subscriber.callback(entry))
                continue
            except RuntimeError:
                pass
            if self._loop is None or not self._loop.is_running():
                # Reason: skip async dispatch when no loop is running.
                continue
            self._loop.call_soon_threadsafe(
                self._create_task,
                subscriber.callback,
                entry,
            )


class MessageBroadcaster:
    """Fan out inbound messages to WebSocket subscribers."""

    def __init__(
        self,
        register_listener: Optional[
            Callable[[Callable[[Dict[str, object]], None]], Callable[[], None]]
        ] = None,
    ) -> None:
        """Initialize the message broadcaster."""

        self._subscribers: set[_MessageSubscriber] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._unsubscribe_source: Optional[Callable[[], None]] = None
        if register_listener is not None:
            self._unsubscribe_source = register_listener(self._handle_message)

    def subscribe(
        self,
        callback: Callable[[Dict[str, object]], Awaitable[None]],
        *,
        topic_id: Optional[str] = None,
        source_hash: Optional[str] = None,
    ) -> Callable[[], None]:
        """Register a message callback."""

        subscriber = _MessageSubscriber(
            callback=callback,
            topic_id=topic_id,
            source_hash=_normalize_peer(source_hash) if source_hash else None,
        )
        self._subscribers.add(subscriber)
        self._capture_loop()

        def _unsubscribe() -> None:
            """Remove the message callback subscription."""

            self._subscribers.discard(subscriber)

        return _unsubscribe

    def _capture_loop(self) -> None:
        """Capture the running event loop for cross-thread dispatch."""

        if self._loop is not None and self._loop.is_running():
            return
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

    def _create_task(
        self,
        callback: Callable[[Dict[str, object]], Awaitable[None]],
        entry: Dict[str, object],
    ) -> None:
        """Create an asyncio task for a callback on the current loop."""

        loop = asyncio.get_running_loop()
        loop.create_task(callback(entry))

    def _handle_message(self, entry: Dict[str, object]) -> None:
        """Dispatch inbound messages to subscribers."""

        entry_topic = entry.get("topic_id")
        entry_source = _normalize_peer(entry.get("source_hash"))
        for subscriber in list(self._subscribers):
            if subscriber.topic_id and subscriber.topic_id != entry_topic:
                continue
            if subscriber.source_hash and subscriber.source_hash != entry_source:
                continue
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(subscriber.callback(entry))
                continue
            except RuntimeError:
                pass
            if self._loop is None or not self._loop.is_running():
                # Reason: skip async dispatch when no loop is running.
                continue
            self._loop.call_soon_threadsafe(
                self._create_task,
                subscriber.callback,
                entry,
            )


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


def _get_subscribe_flags(data: Dict[str, Any]) -> tuple[bool, bool, int]:
    """Return subscription flags for system events.

    Args:
        data (Dict[str, Any]): Subscription payload.

    Returns:
        tuple[bool, bool, int]: include_status, include_events, events_limit.
    """

    include_status = bool(data.get("include_status", True))
    include_events = bool(data.get("include_events", True))
    events_limit = data.get("events_limit")
    if not isinstance(events_limit, int) or events_limit <= 0:
        events_limit = 50
    return include_status, include_events, events_limit


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


async def ping_loop(websocket: WebSocket, *, interval_seconds: float = 30.0) -> None:
    """Send periodic ping messages to a WebSocket.

    Args:
        websocket (WebSocket): WebSocket connection.
        interval_seconds (float): Ping interval in seconds.
    """

    while True:
        await asyncio.sleep(interval_seconds)
        await websocket.send_json(build_ping_message())


async def handle_system_socket(
    websocket: WebSocket,
    *,
    auth: ApiAuth,
    event_broadcaster: EventBroadcaster,
    status_provider: Callable[[], Dict[str, object]],
    event_list_provider: Callable[[int], list[Dict[str, object]]],
) -> None:
    """Handle the system events WebSocket.

    Args:
        websocket (WebSocket): WebSocket connection.
        auth (ApiAuth): Auth validator.
        event_broadcaster (EventBroadcaster): Event broadcaster.
        status_provider (Callable[[], Dict[str, object]]): Status snapshot provider.
        event_list_provider (Callable[[int], list[Dict[str, object]]]): Event list provider.
    """

    await websocket.accept()
    if not await authenticate_websocket(websocket, auth=auth):
        return

    include_status = True
    include_events = True
    events_limit = 50

    async def _send_event(entry: Dict[str, object]) -> None:
        """Send event updates to the WebSocket client.

        Args:
            entry (Dict[str, object]): Event entry payload.

        Returns:
            None: Sends messages to the WebSocket client.
        """

        if include_events:
            await websocket.send_json(build_ws_message("system.event", entry))
        if include_status:
            await websocket.send_json(build_ws_message("system.status", status_provider()))

    unsubscribe = event_broadcaster.subscribe(_send_event)
    ping_task = asyncio.create_task(ping_loop(websocket))

    try:
        if include_status:
            await websocket.send_json(build_ws_message("system.status", status_provider()))
        if include_events:
            for event in event_list_provider(events_limit):
                await websocket.send_json(build_ws_message("system.event", event))

        while True:
            payload = await websocket.receive_text()
            message = parse_ws_message(payload)
            msg_type = _get_message_type(message)
            if msg_type == "system.subscribe":
                data = _get_message_data(message)
                include_status, include_events, events_limit = _get_subscribe_flags(data)
                if include_status:
                    await websocket.send_json(build_ws_message("system.status", status_provider()))
            elif msg_type == "pong":
                continue
            else:
                await websocket.send_json(build_error_message("bad_request", "Unsupported message"))
    except Exception:  # pragma: no cover - websocket disconnects vary
        return
    finally:
        unsubscribe()
        ping_task.cancel()


async def handle_telemetry_socket(
    websocket: WebSocket,
    *,
    auth: ApiAuth,
    telemetry_broadcaster: TelemetryBroadcaster,
    telemetry_snapshot: Callable[[int, Optional[str]], list[Dict[str, object]]],
) -> None:
    """Handle the telemetry WebSocket.

    Args:
        websocket (WebSocket): WebSocket connection.
        auth (ApiAuth): Auth validator.
        telemetry_broadcaster (TelemetryBroadcaster): Telemetry broadcaster.
        telemetry_snapshot (Callable[[int, Optional[str]], list[Dict[str, object]]]): Snapshot provider.
    """

    await websocket.accept()
    if not await authenticate_websocket(websocket, auth=auth):
        return

    ping_task = asyncio.create_task(ping_loop(websocket))
    unsubscribe = None

    try:
        while True:
            payload = await websocket.receive_text()
            message = parse_ws_message(payload)
            msg_type = _get_message_type(message)
            if msg_type == "telemetry.subscribe":
                data = _get_message_data(message)
                try:
                    since, topic_id, follow = _get_telemetry_subscription(data)
                except ValueError as exc:
                    await websocket.send_json(build_error_message("bad_request", str(exc)))
                    continue
                entries = telemetry_snapshot(since, topic_id)
                await websocket.send_json(
                    build_ws_message("telemetry.snapshot", {"entries": entries})
                )
                if follow:
                    if unsubscribe:
                        unsubscribe()
                    try:
                        async def _send_update(entry: Dict[str, object]) -> None:
                            """Send telemetry updates to the WebSocket client.

                            Args:
                                entry (Dict[str, object]): Telemetry entry payload.

                            Returns:
                                None: Sends messages to the WebSocket client.
                            """

                            await websocket.send_json(
                                build_ws_message("telemetry.update", {"entry": entry})
                            )

                        unsubscribe = telemetry_broadcaster.subscribe(
                            _send_update,
                            topic_id=topic_id,
                        )
                    except KeyError:
                        await websocket.send_json(
                            build_error_message("not_found", "Topic not found")
                        )
                    except ValueError as exc:
                        await websocket.send_json(build_error_message("bad_request", str(exc)))
            elif msg_type == "pong":
                continue
            else:
                await websocket.send_json(build_error_message("bad_request", "Unsupported message"))
    except Exception:  # pragma: no cover - websocket disconnects vary
        return
    finally:
        if unsubscribe:
            unsubscribe()
        ping_task.cancel()


async def handle_message_socket(
    websocket: WebSocket,
    *,
    auth: ApiAuth,
    message_broadcaster: MessageBroadcaster,
    message_sender: Callable[[str, Optional[str], Optional[str]], None],
) -> None:
    """Handle the messages WebSocket."""

    await websocket.accept()
    if not await authenticate_websocket(websocket, auth=auth):
        return

    ping_task = asyncio.create_task(ping_loop(websocket))
    unsubscribe = None

    try:
        while True:
            payload = await websocket.receive_text()
            message = parse_ws_message(payload)
            msg_type = _get_message_type(message)
            if msg_type == "message.subscribe":
                data = _get_message_data(message)
                topic_id, source_hash, follow = _get_message_subscription(data)
                if follow:
                    if unsubscribe:
                        unsubscribe()

                    async def _send_update(entry: Dict[str, object]) -> None:
                        """Send message updates to the WebSocket client."""

                        await websocket.send_json(
                            build_ws_message("message.receive", {"entry": entry})
                        )

                    unsubscribe = message_broadcaster.subscribe(
                        _send_update,
                        topic_id=topic_id,
                        source_hash=source_hash,
                    )
                await websocket.send_json(
                    build_ws_message(
                        "message.subscribed",
                        {
                            "topic_id": topic_id,
                            "source_hash": source_hash,
                            "follow": follow,
                        },
                    )
                )
            elif msg_type == "message.send":
                data = _get_message_data(message)
                try:
                    content, topic_id, destination = _get_message_send_payload(data)
                    message_sender(content, topic_id=topic_id, destination=destination)
                except RuntimeError as exc:
                    await websocket.send_json(
                        build_error_message("service_unavailable", str(exc))
                    )
                except ValueError as exc:
                    await websocket.send_json(build_error_message("bad_request", str(exc)))
                else:
                    await websocket.send_json(
                        build_ws_message("message.sent", {"ok": True})
                    )
            elif msg_type == "pong":
                continue
            else:
                await websocket.send_json(
                    build_error_message("bad_request", "Unsupported message")
                )
    except Exception:  # pragma: no cover - websocket disconnects vary
        return
    finally:
        if unsubscribe:
            unsubscribe()
        ping_task.cancel()
