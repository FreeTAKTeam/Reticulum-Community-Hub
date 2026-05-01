"""WebSocket broadcaster classes."""
# pylint: disable=import-error

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Awaitable
from typing import Callable
from typing import Dict
from typing import Optional

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import TelemetryController
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog

from .websocket_delivery import DEFAULT_WS_DELIVERY_QUEUE_SIZE
from .websocket_delivery import _MessageSubscriber
from .websocket_delivery import _QueuedDelivery
from .websocket_delivery import _TelemetrySubscriber
from .websocket_delivery import _metrics_increment
from .websocket_delivery import _metrics_set_gauge
from .websocket_protocol import LOGGER
from .websocket_protocol import _normalize_peer


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


