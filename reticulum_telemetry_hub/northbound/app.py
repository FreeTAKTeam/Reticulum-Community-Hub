"""FastAPI application for the northbound interface."""
# pylint: disable=import-error

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Optional

from dotenv import load_dotenv as load_env
from fastapi import FastAPI

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog

from .auth import ApiAuth
from .auth import build_protected_dependency
from .routes_files import register_file_routes
from .routes_rest import register_core_routes
from .routes_subscribers import register_subscriber_routes
from .routes_topics import register_topic_routes
from .routes_ws import register_ws_routes
from .services import NorthboundServices
from .websocket import EventBroadcaster
from .websocket import TelemetryBroadcaster


def _resolve_openapi_spec() -> Optional[Path]:
    """Return the OpenAPI YAML path when available.

    Returns:
        Optional[Path]: Path to the OpenAPI YAML file when present.
    """

    repo_root = Path(__file__).resolve().parents[2]
    spec_path = repo_root / "API" / "ReticulumTelemetryHub-OAS.yaml"
    if spec_path.exists():
        return spec_path
    return None


def create_app(
    *,
    api: Optional[ReticulumTelemetryHubAPI] = None,
    telemetry_controller: Optional[TelemetryController] = None,
    event_log: Optional[EventLog] = None,
    command_manager: Optional[Any] = None,
    routing_provider: Optional[Callable[[], list[str]]] = None,
    started_at: Optional[datetime] = None,
    auth: Optional[ApiAuth] = None,
) -> FastAPI:
    """Create the northbound FastAPI application.

    Args:
        api (Optional[ReticulumTelemetryHubAPI]): API service instance.
        telemetry_controller (Optional[TelemetryController]): Telemetry controller instance.
        event_log (Optional[EventLog]): Event log instance.
        command_manager (Optional[Any]): Command manager for help/examples text.
        routing_provider (Optional[Callable[[], list[str]]]): Provider for routing destinations.
        started_at (Optional[datetime]): Start time for uptime calculations.
        auth (Optional[ApiAuth]): Auth validator.

    Returns:
        FastAPI: Configured FastAPI application.
    """

    load_env()
    api = api or ReticulumTelemetryHubAPI()
    event_log = event_log or EventLog()
    telemetry_controller = telemetry_controller or TelemetryController(
        api=api,
        event_log=event_log,
    )
    services = NorthboundServices(
        api=api,
        telemetry=telemetry_controller,
        event_log=event_log,
        started_at=started_at or datetime.now(timezone.utc),
        command_manager=command_manager,
        routing_provider=routing_provider,
    )
    auth = auth or ApiAuth()
    require_protected = build_protected_dependency(auth)

    app = FastAPI(title="ReticulumTelemetryHub", version="northbound")
    event_broadcaster = EventBroadcaster(event_log)
    telemetry_broadcaster = TelemetryBroadcaster(telemetry_controller, api)

    register_core_routes(
        app,
        services=services,
        api=api,
        telemetry_controller=telemetry_controller,
        require_protected=require_protected,
        resolve_openapi_spec=_resolve_openapi_spec,
    )
    register_file_routes(app, services=services, api=api)
    register_topic_routes(
        app,
        services=services,
        api=api,
        require_protected=require_protected,
    )
    register_subscriber_routes(
        app,
        services=services,
        api=api,
        require_protected=require_protected,
    )
    register_ws_routes(
        app,
        services=services,
        auth=auth,
        event_broadcaster=event_broadcaster,
        telemetry_broadcaster=telemetry_broadcaster,
    )

    return app


app = create_app()
