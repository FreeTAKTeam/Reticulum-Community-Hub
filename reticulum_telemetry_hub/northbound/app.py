"""FastAPI application for the northbound interface."""
# pylint: disable=import-error

from __future__ import annotations

from datetime import datetime
from datetime import timezone
import os
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Optional

from dotenv import load_dotenv as load_env
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.config.manager import HubConfigurationManager
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog
from reticulum_telemetry_hub.reticulum_server.event_log import resolve_event_log_path

from .auth import ApiAuth
from .auth import build_protected_dependency
from .routes_files import register_file_routes
from .routes_rest import register_core_routes
from .routes_subscribers import register_subscriber_routes
from .routes_topics import register_topic_routes
from .routes_ws import register_ws_routes
from .internal_adapter import build_internal_adapter
from .internal_adapter import InternalAdapter
from .internal_adapter import register_internal_adapter
from .services import NorthboundServices
from .websocket import EventBroadcaster
from .websocket import MessageBroadcaster
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


def _resolve_storage_path() -> Path:
    """Return the storage path from environment defaults."""

    storage_dir = os.environ.get("RTH_STORAGE_DIR")
    if storage_dir:
        return Path(storage_dir)
    return HubConfigurationManager().storage_path


def create_app(
    *,
    api: Optional[ReticulumTelemetryHubAPI] = None,
    telemetry_controller: Optional[TelemetryController] = None,
    event_log: Optional[EventLog] = None,
    command_manager: Optional[Any] = None,
    routing_provider: Optional[Callable[[], list[str]]] = None,
    started_at: Optional[datetime] = None,
    auth: Optional[ApiAuth] = None,
    message_dispatcher: Optional[Callable[[str, Optional[str], Optional[str]], None]] = None,
    message_listener: Optional[
        Callable[[Callable[[dict[str, object]], None]], Callable[[], None]]
    ] = None,
    internal_adapter: Optional[InternalAdapter] = None,
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
    config_manager = None
    storage_path = None
    if api is None:
        storage_path = _resolve_storage_path()
        config_manager = HubConfigurationManager(storage_path=storage_path)
        api = ReticulumTelemetryHubAPI(config_manager=config_manager)
    else:
        config_manager = getattr(api, "_config_manager", None)
        storage_path = getattr(config_manager, "storage_path", None)

    if storage_path is None:
        storage_path = _resolve_storage_path()

    if event_log is None:
        event_log_path = resolve_event_log_path(storage_path)
        event_log = EventLog(event_path=event_log_path, tail=True)

    if telemetry_controller is None:
        telemetry_db_path = storage_path / "telemetry.db"
        telemetry_controller = TelemetryController(
            api=api,
            event_log=event_log,
            db_path=telemetry_db_path,
        )
    else:
        telemetry_controller.set_event_log(event_log)
    services = NorthboundServices(
        api=api,
        telemetry=telemetry_controller,
        event_log=event_log,
        started_at=started_at or datetime.now(timezone.utc),
        command_manager=command_manager,
        routing_provider=routing_provider,
        message_dispatcher=message_dispatcher,
    )
    auth = auth or ApiAuth()
    require_protected = build_protected_dependency(auth)

    app = FastAPI(title="ReticulumTelemetryHub", version="northbound")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        max_age=86400,
    )
    event_broadcaster = EventBroadcaster(event_log)
    telemetry_broadcaster = TelemetryBroadcaster(telemetry_controller, api)
    message_broadcaster = MessageBroadcaster(message_listener)

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
        message_broadcaster=message_broadcaster,
    )
    adapter = internal_adapter or build_internal_adapter()
    register_internal_adapter(app, adapter=adapter)

    return app


app = create_app()
