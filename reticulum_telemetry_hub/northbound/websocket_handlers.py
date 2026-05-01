"""WebSocket endpoint handlers."""
# pylint: disable=import-error

from __future__ import annotations

import asyncio
import time
from typing import Callable
from typing import Dict
from typing import Optional

from fastapi import WebSocket
from fastapi import WebSocketDisconnect

from .auth import ApiAuth
from .websocket_broadcasters import EventBroadcaster
from .websocket_broadcasters import MessageBroadcaster
from .websocket_broadcasters import TelemetryBroadcaster
from .websocket_delivery import _metrics_observe_ms
from .websocket_protocol import DEFAULT_WS_INACTIVITY_TIMEOUT_SECONDS
from .websocket_protocol import DEFAULT_WS_PING_INTERVAL_SECONDS
from .websocket_protocol import DEFAULT_WS_STATUS_FANOUT_MODE
from .websocket_protocol import DEFAULT_WS_STATUS_REFRESH_INTERVAL_SECONDS
from .websocket_protocol import LOGGER
from .websocket_protocol import TelemetrySnapshotProvider
from .websocket_protocol import _cancel_task
from .websocket_protocol import _close_inactive_websocket
from .websocket_protocol import _get_message_data
from .websocket_protocol import _get_message_send_payload
from .websocket_protocol import _get_message_subscription
from .websocket_protocol import _get_message_type
from .websocket_protocol import _get_subscribe_flags
from .websocket_protocol import _get_telemetry_subscription
from .websocket_protocol import _normalize_status_fanout_mode
from .websocket_protocol import _receive_text_with_inactivity_timeout
from .websocket_protocol import _send_json_timed
from .websocket_protocol import authenticate_websocket
from .websocket_protocol import build_error_message
from .websocket_protocol import build_ws_message
from .websocket_protocol import parse_ws_message
from .websocket_protocol import ping_loop


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
