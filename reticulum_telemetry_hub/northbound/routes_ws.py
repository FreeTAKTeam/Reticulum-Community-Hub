"""WebSocket route registrations for the northbound API."""
# pylint: disable=import-error

from __future__ import annotations

from fastapi import FastAPI
from fastapi import WebSocket

from .auth import ApiAuth
from .services import NorthboundServices
from .websocket import EventBroadcaster
from .websocket import TelemetryBroadcaster
from .websocket import handle_system_socket
from .websocket import handle_telemetry_socket


def register_ws_routes(
    app: FastAPI,
    *,
    services: NorthboundServices,
    auth: ApiAuth,
    event_broadcaster: EventBroadcaster,
    telemetry_broadcaster: TelemetryBroadcaster,
) -> None:
    """Register WebSocket routes on the FastAPI app.

    Args:
        app (FastAPI): FastAPI application instance.
        services (NorthboundServices): Aggregated services.
        auth (ApiAuth): Auth validator.
        event_broadcaster (EventBroadcaster): Event broadcaster.
        telemetry_broadcaster (TelemetryBroadcaster): Telemetry broadcaster.

    Returns:
        None: Routes are registered on the application.
    """

    @app.websocket("/events/system")
    async def system_websocket(websocket: WebSocket) -> None:
        """WebSocket stream for system status and events.

        Args:
            websocket (WebSocket): WebSocket connection.
        """

        def _event_list_provider(limit: int) -> list[dict]:
            """Return recent events with the provided limit.

            Args:
                limit (int): Maximum number of events to return.

            Returns:
                list[dict]: Event entries.
            """

            return services.list_events(limit=limit)

        await handle_system_socket(
            websocket,
            auth=auth,
            event_broadcaster=event_broadcaster,
            status_provider=services.status_snapshot,
            event_list_provider=_event_list_provider,
        )

    @app.websocket("/telemetry/stream")
    async def telemetry_websocket(websocket: WebSocket) -> None:
        """WebSocket stream for telemetry updates.

        Args:
            websocket (WebSocket): WebSocket connection.
        """

        def _telemetry_snapshot(since: int, topic_id: str | None) -> list[dict]:
            """Return telemetry snapshots for WebSocket clients.

            Args:
                since (int): Unix timestamp (seconds) for the earliest entries.
                topic_id (str | None): Optional topic filter.

            Returns:
                list[dict]: Telemetry entries.
            """

            return services.telemetry_entries(since=since, topic_id=topic_id)

        await handle_telemetry_socket(
            websocket,
            auth=auth,
            telemetry_broadcaster=telemetry_broadcaster,
            telemetry_snapshot=_telemetry_snapshot,
        )
