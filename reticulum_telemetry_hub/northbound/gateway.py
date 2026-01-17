"""Run the Reticulum hub and northbound API in a single process."""
# pylint: disable=import-error

from __future__ import annotations

import argparse
import threading
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Callable
from typing import Optional
from typing import Protocol

import RNS
import uvicorn
from fastapi import FastAPI

from reticulum_telemetry_hub.config.constants import DEFAULT_ANNOUNCE_INTERVAL
from reticulum_telemetry_hub.config.constants import DEFAULT_HUB_TELEMETRY_INTERVAL
from reticulum_telemetry_hub.config.constants import DEFAULT_LOG_LEVEL_NAME
from reticulum_telemetry_hub.config.constants import DEFAULT_SERVICE_TELEMETRY_INTERVAL
from reticulum_telemetry_hub.config.constants import DEFAULT_STORAGE_PATH
from reticulum_telemetry_hub.config.manager import HubConfigurationManager
from reticulum_telemetry_hub.config.manager import _expand_user_path
from reticulum_telemetry_hub.northbound.app import create_app
from reticulum_telemetry_hub.northbound.auth import ApiAuth
from reticulum_telemetry_hub.reticulum_server.__main__ import ReticulumTelemetryHub


class GatewayHub(Protocol):
    """Protocol for hub dependencies consumed by the gateway app."""

    api: object
    tel_controller: object
    event_log: object
    command_manager: Optional[object]

    def dispatch_northbound_message(
        self,
        message: str,
        topic_id: Optional[str] = None,
        destination: Optional[str] = None,
        fields: Optional[dict] = None,
    ) -> object:
        """Send a northbound message through the hub."""

    def register_message_listener(
        self, listener: Callable[[dict[str, object]], None]
    ) -> Callable[[], None]:
        """Register an inbound message listener."""


@dataclass(frozen=True)
class GatewayConfig:
    """Configuration bundle for the gateway runner."""

    storage_path: Path
    identity_path: Path
    config_path: Path
    display_name: str
    announce_interval: int
    hub_telemetry_interval: int
    service_telemetry_interval: int
    loglevel: int
    embedded: bool
    daemon_mode: bool
    services: list[str]
    api_host: str
    api_port: int


def _resolve_interval(value: int | None, fallback: int) -> int:
    """Return the positive interval derived from CLI/config values."""

    if value is not None:
        return max(0, int(value))
    return max(0, int(fallback))


def _build_log_levels() -> dict[str, int]:
    """Return the supported log level mapping for RNS."""

    default_level = getattr(RNS, "LOG_DEBUG", getattr(RNS, "LOG_INFO", 3))
    return {
        "error": getattr(RNS, "LOG_ERROR", 1),
        "warning": getattr(RNS, "LOG_WARNING", 2),
        "info": getattr(RNS, "LOG_INFO", 3),
        "debug": getattr(RNS, "LOG_DEBUG", default_level),
    }


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the gateway runner."""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c",
        "--config",
        dest="config_path",
        help="Path to a unified config.ini file",
        default=None,
    )
    parser.add_argument("-s", "--storage_dir", help="Storage directory path", default=None)
    parser.add_argument("--display_name", help="Display name for the server", default=None)
    parser.add_argument(
        "--announce-interval",
        type=int,
        default=None,
        help="Seconds between announcement broadcasts",
    )
    parser.add_argument(
        "--hub-telemetry-interval",
        type=int,
        default=None,
        help="Seconds between local telemetry snapshots.",
    )
    parser.add_argument(
        "--service-telemetry-interval",
        type=int,
        default=None,
        help="Seconds between remote telemetry collector polls.",
    )
    parser.add_argument(
        "--log-level",
        choices=list(_build_log_levels().keys()),
        default=None,
        help="Log level to emit RNS traffic to stdout",
    )
    parser.add_argument(
        "--embedded",
        "--embedded-lxmd",
        dest="embedded",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Run the LXMF router/propagation threads in-process.",
    )
    parser.add_argument(
        "--daemon",
        dest="daemon",
        action="store_true",
        help="Start local telemetry collectors and optional services.",
    )
    parser.add_argument(
        "--service",
        dest="services",
        action="append",
        default=[],
        metavar="NAME",
        help=(
            "Enable an optional daemon service (e.g., gpsd). Repeat the flag for"
            " multiple services."
        ),
    )
    parser.add_argument(
        "--api-host",
        dest="api_host",
        default="127.0.0.1",
        help="Host address for the northbound API.",
    )
    parser.add_argument(
        "--api-port",
        dest="api_port",
        type=int,
        default=8000,
        help="Port for the northbound API.",
    )
    return parser.parse_args()


def _build_gateway_config(args: argparse.Namespace) -> GatewayConfig:
    """Build runtime configuration for the gateway runner."""

    storage_path = _expand_user_path(args.storage_dir or DEFAULT_STORAGE_PATH)
    identity_path = storage_path / "identity"
    config_path = (
        _expand_user_path(args.config_path)
        if args.config_path
        else storage_path / "config.ini"
    )
    config_manager = HubConfigurationManager(
        storage_path=storage_path,
        config_path=config_path,
    )
    runtime_config = config_manager.config.runtime
    display_name = args.display_name or runtime_config.display_name
    announce_interval = args.announce_interval or runtime_config.announce_interval
    hub_interval = _resolve_interval(
        args.hub_telemetry_interval,
        runtime_config.hub_telemetry_interval or DEFAULT_HUB_TELEMETRY_INTERVAL,
    )
    service_interval = _resolve_interval(
        args.service_telemetry_interval,
        runtime_config.service_telemetry_interval or DEFAULT_SERVICE_TELEMETRY_INTERVAL,
    )
    log_level_name = (
        args.log_level or runtime_config.log_level or DEFAULT_LOG_LEVEL_NAME
    ).lower()
    log_levels = _build_log_levels()
    loglevel = log_levels.get(log_level_name, log_levels["info"])
    embedded = runtime_config.embedded_lxmd if args.embedded is None else args.embedded
    requested_services = list(runtime_config.default_services)
    requested_services.extend(args.services or [])
    services = list(dict.fromkeys(requested_services))
    return GatewayConfig(
        storage_path=storage_path,
        identity_path=identity_path,
        config_path=config_path,
        display_name=display_name,
        announce_interval=announce_interval,
        hub_telemetry_interval=hub_interval,
        service_telemetry_interval=service_interval,
        loglevel=loglevel,
        embedded=embedded,
        daemon_mode=bool(args.daemon),
        services=services,
        api_host=str(args.api_host),
        api_port=int(args.api_port),
    )


def build_gateway_app(
    hub: GatewayHub,
    *,
    auth: Optional[ApiAuth] = None,
    started_at: Optional[datetime] = None,
) -> FastAPI:
    """Create a northbound API app wired to the hub instance.

    Args:
        hub (GatewayHub): Active hub instance used for dispatching messages.
        auth (Optional[ApiAuth]): Auth override.
        started_at (Optional[datetime]): Optional start time override.

    Returns:
        FastAPI: Configured FastAPI application.
    """

    app = create_app(
        api=hub.api,
        telemetry_controller=hub.tel_controller,
        event_log=hub.event_log,
        command_manager=hub.command_manager,
        message_dispatcher=hub.dispatch_northbound_message,
        message_listener=hub.register_message_listener,
        started_at=started_at or datetime.now(timezone.utc),
        auth=auth,
    )
    app.state.hub = hub
    return app


def _start_hub_thread(
    hub: ReticulumTelemetryHub,
    *,
    daemon_mode: bool,
    services: list[str],
) -> threading.Thread:
    """Start the hub run loop in a background thread."""

    thread = threading.Thread(
        target=hub.run,
        kwargs={"daemon_mode": daemon_mode, "services": services},
        daemon=True,
    )
    thread.start()
    return thread


def main() -> None:
    """Start the hub + northbound API gateway."""

    args = _parse_args()
    config = _build_gateway_config(args)
    config_manager = HubConfigurationManager(
        storage_path=config.storage_path,
        config_path=config.config_path,
    )
    hub = ReticulumTelemetryHub(
        config.display_name,
        config.storage_path,
        config.identity_path,
        embedded=config.embedded,
        announce_interval=config.announce_interval,
        loglevel=config.loglevel,
        hub_telemetry_interval=config.hub_telemetry_interval,
        service_telemetry_interval=config.service_telemetry_interval,
        config_manager=config_manager,
    )
    hub_thread = _start_hub_thread(
        hub,
        daemon_mode=config.daemon_mode,
        services=config.services,
    )
    app = build_gateway_app(hub)
    try:
        uvicorn.run(
            app,
            host=config.api_host,
            port=config.api_port,
            log_level="info",
        )
    finally:
        hub.shutdown()
        hub_thread.join(timeout=5)


if __name__ == "__main__":
    main()
