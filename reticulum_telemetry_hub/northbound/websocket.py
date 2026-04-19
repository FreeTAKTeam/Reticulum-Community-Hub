"""WebSocket helpers for the northbound API."""
# pylint: disable=import-error

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timezone
from typing import Any
from typing import Awaitable
from typing import Callable
from typing import Dict
from typing import Optional
from typing import TypeAlias

from fastapi import WebSocketDisconnect
from fastapi import WebSocket

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog

from .auth import ApiAuth


DEFAULT_WS_PING_INTERVAL_SECONDS = 30.0
DEFAULT_WS_INACTIVITY_TIMEOUT_SECONDS = 90.0
DEFAULT_WS_DELIVERY_QUEUE_SIZE = 64
DEFAULT_WS_STATUS_REFRESH_INTERVAL_SECONDS = 3.0
DEFAULT_WS_STATUS_FANOUT_MODE = "event_only"
_WS_STATUS_FANOUT_MODES = {"event_only", "periodic", "event_plus_periodic"}
WS_INACTIVITY_CLOSE_CODE = 4004
LOGGER = logging.getLogger(__name__)


def _metrics_increment(metrics: object | None, key: str, value: int = 1) -> None:
    """Increment a runtime metric counter when supported by ``metrics``."""

    if metrics is None:
        return
    increment = getattr(metrics, "increment", None)
    if callable(increment):
        increment(key, value)


def _metrics_set_gauge(metrics: object | None, key: str, value: float) -> None:
    """Set a runtime metric gauge when supported by ``metrics``."""

    if metrics is None:
        return
    setter = getattr(metrics, "set_gauge", None)
    if callable(setter):
        setter(key, value)


def _metrics_observe_ms(metrics: object | None, key: str, value_ms: float) -> None:
    """Record a runtime timer metric (in milliseconds) when supported."""

    if metrics is None:
        return
    observer = getattr(metrics, "observe_ms", None)
    if callable(observer):
        observer(key, value_ms)


# Contract: providers used by websocket handlers must be non-blocking
# (async-native or internally offloaded with ``asyncio.to_thread``).
TelemetrySnapshotProvider: TypeAlias = Callable[
    [int, Optional[str]],
    Awaitable[list[Dict[str, object]]],
]


@dataclass(eq=False)
class _QueuedDelivery:
    """Bounded delivery queue for a websocket subscriber callback."""

    callback: Callable[[Dict[str, object]], Awaitable[None]]
    loop: Optional[asyncio.AbstractEventLoop]
    queue_size: int = DEFAULT_WS_DELIVERY_QUEUE_SIZE
    on_terminal_failure: Optional[Callable[["_QueuedDelivery", Exception], None]] = None
    on_drop_oldest: Optional[Callable[[], None]] = None
    _queue: asyncio.Queue[object] | None = field(
        init=False, default=None, repr=False, compare=False
    )
    _worker: asyncio.Task[None] | None = field(
        init=False, default=None, repr=False, compare=False
    )
    _closed: bool = field(init=False, default=False, repr=False, compare=False)
    _failed: bool = field(init=False, default=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Initialize the worker queue when a loop is available."""

        if self.loop is None:
            return
        self._queue = asyncio.Queue(maxsize=max(int(self.queue_size), 1))
        self._worker = self.loop.create_task(self._run())

    async def _run(self) -> None:
        """Drain queued entries sequentially for a subscriber."""

        if self._queue is None:
            return
        while True:
            item = await self._queue.get()
            try:
                if item is None:
                    return
                await self.callback(item)
            except Exception as exc:
                self._handle_terminal_failure(exc)
                return
            finally:
                self._queue.task_done()

    def enqueue(self, entry: Dict[str, object]) -> None:
        """Queue an entry for bounded delivery."""

        if self._closed:
            return
        if self._queue is None or self.loop is None or not self.loop.is_running():
            self._dispatch_direct(entry)
            return
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is self.loop:
            self._enqueue_on_loop(entry)
            return
        self.loop.call_soon_threadsafe(self._enqueue_on_loop, entry)

    def _enqueue_on_loop(self, entry: Dict[str, object]) -> None:
        """Enqueue an entry on the subscriber loop, dropping oldest on overflow."""

        if self._closed or self._queue is None:
            return
        if self._queue.full():
            with suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
                self._queue.task_done()
                callback = self.on_drop_oldest
                if callback is not None:
                    callback()
        with suppress(asyncio.QueueFull):
            self._queue.put_nowait(entry)

    def _dispatch_direct(self, entry: Dict[str, object]) -> None:
        """Fallback direct dispatch when no loop-backed queue exists."""

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(self.callback(entry))

        def _on_done(completed: asyncio.Task[None]) -> None:
            with suppress(asyncio.CancelledError):
                exc = completed.exception()
                if exc is not None:
                    self._handle_terminal_failure(exc)

        task.add_done_callback(_on_done)

    def _handle_terminal_failure(self, exc: Exception) -> None:
        """Signal terminal callback failure once for this subscriber."""

        if self._failed:
            return
        self._failed = True
        callback = self.on_terminal_failure
        if callback is None:
            return
        callback(self, exc)

    def close(self) -> None:
        """Stop the worker queue for this subscriber."""

        if self._closed:
            return
        self._closed = True
        if self._queue is None or self.loop is None or not self.loop.is_running():
            if self._worker is not None:
                self._worker.cancel()
            return
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is self.loop:
            self._close_on_loop()
            return
        self.loop.call_soon_threadsafe(self._close_on_loop)

    def _close_on_loop(self) -> None:
        """Close the queue on its owning event loop."""

        if self._queue is None:
            if self._worker is not None:
                self._worker.cancel()
            return
        while self._queue.full():
            with suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
                self._queue.task_done()
        with suppress(asyncio.QueueFull):
            self._queue.put_nowait(None)


@dataclass(eq=False)
class _TelemetrySubscriber:
    """Configuration for a telemetry WebSocket subscriber."""

    delivery: _QueuedDelivery
    allowed_destinations: Optional[frozenset[str]]


@dataclass(eq=False)
class _MessageSubscriber:
    """Configuration for a message WebSocket subscriber."""

    delivery: _QueuedDelivery
    topic_id: Optional[str]
    source_hash: Optional[str]


class EventBroadcaster:
    """Fan out events to active WebSocket subscribers."""

    def __init__(
        self,
        event_log: EventLog,
        *,
        delivery_queue_size: int = DEFAULT_WS_DELIVERY_QUEUE_SIZE,
        runtime_metrics: object | None = None,
    ) -> None:
        """Initialize the event broadcaster.

        Args:
            event_log (EventLog): Event log used for event updates.
        """

        self._event_log = event_log
        self._subscribers: set[_QueuedDelivery] = set()
        self._delivery_queue_size = max(int(delivery_queue_size), 1)
        self._runtime_metrics = runtime_metrics
        self._event_log.add_listener(self._handle_event)
        self._publish_subscriber_gauge()

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

        delivery = _QueuedDelivery(
            callback=callback,
            loop=self._running_loop(),
            queue_size=self._delivery_queue_size,
            on_terminal_failure=self._on_delivery_failure,
            on_drop_oldest=self._record_drop_oldest,
        )
        self._subscribers.add(delivery)
        self._publish_subscriber_gauge()

        def _unsubscribe() -> None:
            """Remove the event callback subscription.

            Returns:
                None: Removes the callback.
            """

            self._remove_delivery(delivery)

        return _unsubscribe

    def _publish_subscriber_gauge(self) -> None:
        """Publish current websocket subscriber counts to runtime metrics."""

        count = float(len(self._subscribers))
        _metrics_set_gauge(self._runtime_metrics, "ws_event_subscribers", count)

    def _record_drop_oldest(self) -> None:
        """Track bounded-queue oldest-drop events."""

        _metrics_increment(self._runtime_metrics, "ws_dropped_oldest_total")
        _metrics_increment(self._runtime_metrics, "ws_event_dropped_oldest_total")

    def _remove_delivery(self, delivery: _QueuedDelivery) -> None:
        """Remove and close a queued delivery subscription."""

        self._subscribers.discard(delivery)
        delivery.close()
        self._publish_subscriber_gauge()

    def _on_delivery_failure(self, delivery: _QueuedDelivery, exc: Exception) -> None:
        """Handle terminal subscriber callback failures."""

        LOGGER.warning("WebSocket event subscriber callback failed: %s", exc)
        _metrics_increment(self._runtime_metrics, "ws_callback_failures_total")
        _metrics_increment(self._runtime_metrics, "ws_event_callback_failures_total")
        self._remove_delivery(delivery)

    @staticmethod
    def _running_loop() -> Optional[asyncio.AbstractEventLoop]:
        """Return the current loop when called from async context."""

        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return None

    def _handle_event(self, entry: Dict[str, object]) -> None:
        """Dispatch a new event to subscribers.

        Args:
            entry (Dict[str, object]): Recorded event entry.
        """

        for delivery in list(self._subscribers):
            _metrics_increment(self._runtime_metrics, "ws_event_enqueued_total")
            delivery.enqueue(entry)


class TelemetryBroadcaster:
    """Fan out telemetry updates to WebSocket subscribers."""

    def __init__(
        self,
        controller: TelemetryController,
        api: Optional[ReticulumTelemetryHubAPI],
        *,
        delivery_queue_size: int = DEFAULT_WS_DELIVERY_QUEUE_SIZE,
        runtime_metrics: object | None = None,
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
        self._delivery_queue_size = max(int(delivery_queue_size), 1)
        self._unsubscribe_source: Optional[Callable[[], None]] = None
        self._runtime_metrics = runtime_metrics
        self._unsubscribe_source = self._controller.register_listener(
            self._handle_telemetry
        )
        self._publish_subscriber_gauge()

    def close(self) -> None:
        """Unsubscribe from telemetry and close subscriber deliveries."""

        if self._unsubscribe_source is not None:
            self._unsubscribe_source()
            self._unsubscribe_source = None
        for subscriber in list(self._subscribers):
            self._remove_subscriber(subscriber)

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
        subscriber = _TelemetrySubscriber(
            delivery=_QueuedDelivery(
                callback=callback,
                loop=EventBroadcaster._running_loop(),
                queue_size=self._delivery_queue_size,
                on_terminal_failure=lambda delivery, exc: self._on_delivery_failure(
                    delivery,
                    exc,
                ),
                on_drop_oldest=self._record_drop_oldest,
            ),
            allowed_destinations=allowed,
        )
        self._subscribers.add(subscriber)
        self._publish_subscriber_gauge()

        def _unsubscribe() -> None:
            """Remove the telemetry callback subscription.

            Returns:
                None: Removes the callback.
            """

            self._remove_subscriber(subscriber)

        return _unsubscribe

    def _publish_subscriber_gauge(self) -> None:
        """Publish telemetry websocket subscriber count."""

        _metrics_set_gauge(
            self._runtime_metrics,
            "ws_telemetry_subscribers",
            float(len(self._subscribers)),
        )

    def _remove_subscriber(self, subscriber: _TelemetrySubscriber) -> None:
        """Remove and close a telemetry subscriber."""

        self._subscribers.discard(subscriber)
        subscriber.delivery.close()
        self._publish_subscriber_gauge()

    def _record_drop_oldest(self) -> None:
        """Track dropped-oldest events for telemetry websocket queues."""

        _metrics_increment(self._runtime_metrics, "ws_dropped_oldest_total")
        _metrics_increment(self._runtime_metrics, "ws_telemetry_dropped_oldest_total")

    def _on_delivery_failure(self, delivery: _QueuedDelivery, exc: Exception) -> None:
        """Handle terminal telemetry subscriber callback failures."""

        LOGGER.warning("WebSocket telemetry subscriber callback failed: %s", exc)
        _metrics_increment(self._runtime_metrics, "ws_callback_failures_total")
        _metrics_increment(self._runtime_metrics, "ws_telemetry_callback_failures_total")
        for subscriber in list(self._subscribers):
            if subscriber.delivery is delivery:
                self._remove_subscriber(subscriber)
                break

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
            _metrics_increment(self._runtime_metrics, "ws_telemetry_enqueued_total")
            subscriber.delivery.enqueue(entry)


class MessageBroadcaster:
    """Fan out inbound messages to WebSocket subscribers."""

    def __init__(
        self,
        register_listener: Optional[
            Callable[[Callable[[Dict[str, object]], None]], Callable[[], None]]
        ] = None,
        *,
        delivery_queue_size: int = DEFAULT_WS_DELIVERY_QUEUE_SIZE,
        runtime_metrics: object | None = None,
    ) -> None:
        """Initialize the message broadcaster."""

        self._subscribers: set[_MessageSubscriber] = set()
        self._delivery_queue_size = max(int(delivery_queue_size), 1)
        self._unsubscribe_source: Optional[Callable[[], None]] = None
        self._runtime_metrics = runtime_metrics
        if register_listener is not None:
            self._unsubscribe_source = register_listener(self._handle_message)
        self._publish_subscriber_gauge()

    def subscribe(
        self,
        callback: Callable[[Dict[str, object]], Awaitable[None]],
        *,
        topic_id: Optional[str] = None,
        source_hash: Optional[str] = None,
    ) -> Callable[[], None]:
        """Register a message callback."""

        subscriber = _MessageSubscriber(
            delivery=_QueuedDelivery(
                callback=callback,
                loop=EventBroadcaster._running_loop(),
                queue_size=self._delivery_queue_size,
                on_terminal_failure=lambda delivery, exc: self._on_delivery_failure(
                    delivery,
                    exc,
                ),
                on_drop_oldest=self._record_drop_oldest,
            ),
            topic_id=topic_id,
            source_hash=_normalize_peer(source_hash) if source_hash else None,
        )
        self._subscribers.add(subscriber)
        self._publish_subscriber_gauge()

        def _unsubscribe() -> None:
            """Remove the message callback subscription."""

            self._remove_subscriber(subscriber)

        return _unsubscribe

    def _publish_subscriber_gauge(self) -> None:
        """Publish message websocket subscriber count."""

        _metrics_set_gauge(
            self._runtime_metrics,
            "ws_message_subscribers",
            float(len(self._subscribers)),
        )

    def _remove_subscriber(self, subscriber: _MessageSubscriber) -> None:
        """Remove and close a message subscriber."""

        self._subscribers.discard(subscriber)
        subscriber.delivery.close()
        self._publish_subscriber_gauge()

    def _record_drop_oldest(self) -> None:
        """Track dropped-oldest events for message websocket queues."""

        _metrics_increment(self._runtime_metrics, "ws_dropped_oldest_total")
        _metrics_increment(self._runtime_metrics, "ws_message_dropped_oldest_total")

    def _on_delivery_failure(self, delivery: _QueuedDelivery, exc: Exception) -> None:
        """Handle terminal message subscriber callback failures."""

        LOGGER.warning("WebSocket message subscriber callback failed: %s", exc)
        _metrics_increment(self._runtime_metrics, "ws_callback_failures_total")
        _metrics_increment(self._runtime_metrics, "ws_message_callback_failures_total")
        for subscriber in list(self._subscribers):
            if subscriber.delivery is delivery:
                self._remove_subscriber(subscriber)
                break

    def _handle_message(self, entry: Dict[str, object]) -> None:
        """Dispatch inbound messages to subscribers."""

        entry_topic = entry.get("topic_id")
        entry_source = _normalize_peer(entry.get("source_hash"))
        for subscriber in list(self._subscribers):
            if subscriber.topic_id and subscriber.topic_id != entry_topic:
                continue
            if subscriber.source_hash and subscriber.source_hash != entry_source:
                continue
            _metrics_increment(self._runtime_metrics, "ws_message_enqueued_total")
            subscriber.delivery.enqueue(entry)


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


async def handle_system_socket(
    websocket: WebSocket,
    *,
    auth: ApiAuth,
    event_broadcaster: EventBroadcaster,
    status_provider: Callable[[], Dict[str, object]],
    event_list_provider: Callable[[int], list[Dict[str, object]]],
    status_refresh_interval_seconds: float = DEFAULT_WS_STATUS_REFRESH_INTERVAL_SECONDS,
    status_fanout_mode: str = DEFAULT_WS_STATUS_FANOUT_MODE,
    ping_interval_seconds: float = DEFAULT_WS_PING_INTERVAL_SECONDS,
    inactivity_timeout_seconds: float = DEFAULT_WS_INACTIVITY_TIMEOUT_SECONDS,
) -> None:
    """Handle the system events WebSocket.

    Args:
        websocket (WebSocket): WebSocket connection.
        auth (ApiAuth): Auth validator.
        event_broadcaster (EventBroadcaster): Event broadcaster.
        status_provider (Callable[[], Dict[str, object]]): Status snapshot provider.
        event_list_provider (Callable[[int], list[Dict[str, object]]]): Event list provider.
        status_refresh_interval_seconds (float): Periodic status refresh cadence.
        status_fanout_mode (str): Status fan-out mode. Supported values:
            ``event_only``, ``periodic``, ``event_plus_periodic``.
        ping_interval_seconds (float): Interval between keepalive ping payloads.
        inactivity_timeout_seconds (float): Maximum idle time allowed before the
            socket is closed.
    """

    await websocket.accept()
    if not await authenticate_websocket(websocket, auth=auth):
        return

    include_status = False
    include_events = True
    events_limit = 50
    last_activity_at = time.monotonic()
    fanout_mode = _normalize_status_fanout_mode(status_fanout_mode)
    include_status = fanout_mode != "event_only"
    status_interval = max(float(status_refresh_interval_seconds), 2.0)

    async def _send_event(entry: Dict[str, object]) -> None:
        """Send event updates to the WebSocket client.

        Args:
            entry (Dict[str, object]): Event entry payload.

        Returns:
            None: Sends messages to the WebSocket client.
        """

        if include_events:
            await websocket.send_json(build_ws_message("system.event", entry))
        if include_status and fanout_mode == "event_plus_periodic":
            await websocket.send_json(build_ws_message("system.status", status_provider()))

    async def _periodic_status_loop() -> None:
        """Send periodic status updates when enabled."""

        if fanout_mode not in {"periodic", "event_plus_periodic"}:
            return
        while True:
            await asyncio.sleep(status_interval)
            if include_status:
                await websocket.send_json(build_ws_message("system.status", status_provider()))

    unsubscribe = event_broadcaster.subscribe(_send_event)
    ping_task = asyncio.create_task(
        ping_loop(websocket, interval_seconds=ping_interval_seconds)
    )
    status_task = asyncio.create_task(_periodic_status_loop())

    try:
        if include_status:
            await websocket.send_json(build_ws_message("system.status", status_provider()))
        if include_events:
            for event in event_list_provider(events_limit):
                await websocket.send_json(build_ws_message("system.event", event))

        while True:
            try:
                payload = await _receive_text_with_inactivity_timeout(
                    websocket,
                    last_activity_at=last_activity_at,
                    inactivity_timeout_seconds=inactivity_timeout_seconds,
                )
            except asyncio.TimeoutError:
                await _close_inactive_websocket(websocket)
                return

            last_activity_at = time.monotonic()
            try:
                message = parse_ws_message(payload)
            except ValueError as exc:
                await websocket.send_json(build_error_message("bad_request", str(exc)))
                continue
            msg_type = _get_message_type(message)
            if msg_type == "system.subscribe":
                data = _get_message_data(message)
                include_status, include_events, events_limit = _get_subscribe_flags(
                    data,
                    default_include_status=(fanout_mode != "event_only"),
                    default_include_events=True,
                )
                if include_status:
                    await websocket.send_json(build_ws_message("system.status", status_provider()))
            elif msg_type == "pong":
                continue
            else:
                await websocket.send_json(build_error_message("bad_request", "Unsupported message"))
    except (WebSocketDisconnect, RuntimeError):  # pragma: no cover - websocket disconnects vary
        return
    except Exception as exc:  # pragma: no cover - defensive logging
        LOGGER.warning("System websocket loop terminated with error: %s", exc)
        return
    finally:
        unsubscribe()
        await _cancel_task(ping_task)
        await _cancel_task(status_task)


async def handle_telemetry_socket(
    websocket: WebSocket,
    *,
    auth: ApiAuth,
    telemetry_broadcaster: TelemetryBroadcaster,
    telemetry_snapshot: TelemetrySnapshotProvider,
    runtime_metrics: object | None = None,
    ping_interval_seconds: float = DEFAULT_WS_PING_INTERVAL_SECONDS,
    inactivity_timeout_seconds: float = DEFAULT_WS_INACTIVITY_TIMEOUT_SECONDS,
) -> None:
    """Handle the telemetry WebSocket.

    Args:
        websocket (WebSocket): WebSocket connection.
        auth (ApiAuth): Auth validator.
        telemetry_broadcaster (TelemetryBroadcaster): Telemetry broadcaster.
        telemetry_snapshot (TelemetrySnapshotProvider): Non-blocking snapshot
            provider for initial history replies.
        runtime_metrics (object | None): Optional runtime metrics sink.
        ping_interval_seconds (float): Interval between keepalive ping payloads.
        inactivity_timeout_seconds (float): Maximum idle time allowed before the
            socket is closed.
    """

    await websocket.accept()
    if not await authenticate_websocket(websocket, auth=auth):
        return

    ping_task = asyncio.create_task(
        ping_loop(websocket, interval_seconds=ping_interval_seconds)
    )
    unsubscribe = None
    last_activity_at = time.monotonic()

    try:
        while True:
            try:
                payload = await _receive_text_with_inactivity_timeout(
                    websocket,
                    last_activity_at=last_activity_at,
                    inactivity_timeout_seconds=inactivity_timeout_seconds,
                )
            except asyncio.TimeoutError:
                await _close_inactive_websocket(websocket)
                return

            last_activity_at = time.monotonic()
            try:
                message = parse_ws_message(payload)
            except ValueError as exc:
                await websocket.send_json(build_error_message("bad_request", str(exc)))
                continue
            msg_type = _get_message_type(message)
            if msg_type == "telemetry.subscribe":
                data = _get_message_data(message)
                try:
                    since, topic_id, follow = _get_telemetry_subscription(data)
                except ValueError as exc:
                    await websocket.send_json(build_error_message("bad_request", str(exc)))
                    continue
                snapshot_started = time.perf_counter()
                entries = await telemetry_snapshot(since, topic_id)
                _metrics_observe_ms(
                    runtime_metrics,
                    "ws_telemetry_snapshot_generation_ms",
                    (time.perf_counter() - snapshot_started) * 1000.0,
                )
                await _send_json_timed(
                    websocket,
                    build_ws_message("telemetry.snapshot", {"entries": entries}),
                    runtime_metrics=runtime_metrics,
                    metric_key="ws_telemetry_snapshot_send_latency_ms",
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

                            await _send_json_timed(
                                websocket,
                                build_ws_message("telemetry.update", {"entry": entry}),
                                runtime_metrics=runtime_metrics,
                                metric_key="ws_telemetry_update_send_latency_ms",
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
    except (WebSocketDisconnect, RuntimeError):  # pragma: no cover - websocket disconnects vary
        return
    except Exception as exc:  # pragma: no cover - defensive logging
        LOGGER.warning("Telemetry websocket loop terminated with error: %s", exc)
        return
    finally:
        if unsubscribe:
            unsubscribe()
        await _cancel_task(ping_task)


async def handle_message_socket(
    websocket: WebSocket,
    *,
    auth: ApiAuth,
    message_broadcaster: MessageBroadcaster,
    message_sender: Callable[[str, Optional[str], Optional[str]], None],
    ping_interval_seconds: float = DEFAULT_WS_PING_INTERVAL_SECONDS,
    inactivity_timeout_seconds: float = DEFAULT_WS_INACTIVITY_TIMEOUT_SECONDS,
) -> None:
    """Handle the messages WebSocket."""

    await websocket.accept()
    if not await authenticate_websocket(websocket, auth=auth):
        return

    ping_task = asyncio.create_task(
        ping_loop(websocket, interval_seconds=ping_interval_seconds)
    )
    unsubscribe = None
    last_activity_at = time.monotonic()

    try:
        while True:
            try:
                payload = await _receive_text_with_inactivity_timeout(
                    websocket,
                    last_activity_at=last_activity_at,
                    inactivity_timeout_seconds=inactivity_timeout_seconds,
                )
            except asyncio.TimeoutError:
                await _close_inactive_websocket(websocket)
                return

            last_activity_at = time.monotonic()
            try:
                message = parse_ws_message(payload)
            except ValueError as exc:
                await websocket.send_json(build_error_message("bad_request", str(exc)))
                continue
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
                    await asyncio.to_thread(
                        message_sender,
                        content,
                        topic_id=topic_id,
                        destination=destination,
                    )
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
    except (WebSocketDisconnect, RuntimeError):  # pragma: no cover - websocket disconnects vary
        return
    except Exception as exc:  # pragma: no cover - defensive logging
        LOGGER.warning("Message websocket loop terminated with error: %s", exc)
        return
    finally:
        if unsubscribe:
            unsubscribe()
        await _cancel_task(ping_task)
