"""Run the Reticulum hub and northbound API in a single process."""
# pylint: disable=import-error

from __future__ import annotations

import argparse
import os
import threading
import time
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Callable
from typing import Optional
from typing import Protocol

import RNS
import uvicorn
from fastapi import FastAPI

from reticulum_telemetry_hub.config.constants import DEFAULT_HUB_TELEMETRY_INTERVAL
from reticulum_telemetry_hub.config.constants import DEFAULT_LOG_LEVEL_NAME
from reticulum_telemetry_hub.config.constants import DEFAULT_SERVICE_TELEMETRY_INTERVAL
from reticulum_telemetry_hub.config.constants import DEFAULT_STORAGE_PATH
from reticulum_telemetry_hub.config.manager import HubConfigurationManager
from reticulum_telemetry_hub.config.manager import _expand_user_path
from reticulum_telemetry_hub.northbound.app import create_app
from reticulum_telemetry_hub.northbound.auth import ApiAuth
from reticulum_telemetry_hub.reticulum_server.__main__ import ReticulumTelemetryHub


LOCAL_API_HOST = "127.0.0.1"


class GatewayHub(Protocol):
    """Protocol for hub dependencies consumed by the gateway app."""

    api: object
    tel_controller: object
    event_log: object
    command_manager: Optional[object]
    marker_service: Optional[object]

    def dispatch_northbound_message(
        self,
        message: str,
        topic_id: Optional[str] = None,
        destination: Optional[str] = None,
        fields: Optional[dict] = None,
    ) -> object:
        """Send a northbound message through the hub."""

    def dispatch_marker_event(self, marker, event_type: str) -> bool:
        """Record a marker telemetry event through the hub."""

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
    parser.add_argument("--data-dir", dest="storage_dir", help="Storage directory path", default=None)
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
        default=LOCAL_API_HOST,
        help="Host address for the northbound API (always 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
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
        api_host=LOCAL_API_HOST,
        api_port=int(args.api_port),
    )


@dataclass
class GatewayControl:
    """Control surface for the gateway runtime."""

    hub: ReticulumTelemetryHub
    hub_thread: threading.Thread
    host: str
    port: int
    started_at: datetime
    server: Optional[uvicorn.Server] = None
    _shutdown_requested: threading.Event = field(default_factory=threading.Event)

    def attach_server(self, server: uvicorn.Server) -> None:
        """Attach the running uvicorn server."""

        self.server = server

    def request_shutdown(self) -> None:
        """Request a graceful shutdown of the gateway."""

        if not self._shutdown_requested.is_set():
            self._shutdown_requested.set()
        self.hub.shutdown()
        if self.server is not None:
            self.server.should_exit = True

    def request_start(self) -> None:
        """No-op start hook for parity with control endpoints."""

        return

    def request_announce(self) -> bool:
        """Request an immediate Reticulum announce."""

        announce = getattr(self.hub, "send_announce", None)
        if callable(announce):
            return bool(announce())
        return False

    def status(self) -> dict[str, object]:
        """Return a snapshot of the gateway status."""

        uptime = datetime.now(timezone.utc) - self.started_at
        if self._shutdown_requested.is_set():
            status = "stopping"
        elif self.hub_thread.is_alive():
            status = "running"
        else:
            status = "stopped"
        propagation = None
        status_provider = getattr(self.hub, "get_propagation_startup_status", None)
        if callable(status_provider):
            try:
                propagation = status_provider()
            except Exception as exc:  # pragma: no cover - defensive logging
                RNS.log(
                    f"Failed to fetch propagation startup status: {exc}",
                    getattr(RNS, "LOG_WARNING", 2),
                )
        return {
            "status": status,
            "pid": os.getpid(),
            "host": self.host,
            "port": self.port,
            "uptime_seconds": int(uptime.total_seconds()),
            "hub_thread_alive": self.hub_thread.is_alive(),
            "propagation": propagation,
        }


def build_gateway_app(
    hub: GatewayHub,
    *,
    auth: Optional[ApiAuth] = None,
    started_at: Optional[datetime] = None,
    control: Optional[GatewayControl] = None,
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
        command_manager=getattr(hub, "command_manager", None),
        routing_provider=lambda: _routing_destinations_from_hub(hub),
        message_dispatcher=hub.dispatch_northbound_message,
        marker_dispatcher=hub.dispatch_marker_event,
        marker_service=getattr(hub, "marker_service", None),
        origin_rch=getattr(hub, "_origin_rch_hex", lambda: "")(),
        message_listener=hub.register_message_listener,
        started_at=started_at or datetime.now(timezone.utc),
        auth=auth,
        control=control,
    )
    app.state.hub = hub
    return app


def _routing_destinations_from_hub(hub: GatewayHub) -> list[dict[str, str]]:
    """Return connected routing entries with destination, identity, and label."""

    provider = getattr(hub, "routing_destinations", None)
    if callable(provider):
        try:
            normalized: list[dict[str, str]] = []
            for value in provider():
                entry = _normalize_routing_entry(value)
                if entry is None:
                    continue
                normalized.append(entry)
            deduped: list[dict[str, str]] = []
            seen: set[str] = set()
            for entry in normalized:
                destination = entry["destination"]
                if destination in seen:
                    continue
                seen.add(destination)
                deduped.append(entry)
            return deduped
        except Exception as exc:  # pragma: no cover - defensive logging
            RNS.log(
                f"Failed to fetch hub routing destinations: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )

    connections = getattr(hub, "connections", None)
    if connections is None:
        return []
    if hasattr(connections, "values"):
        entries = list(connections.values())
    else:
        entries = list(connections)

    routes: list[dict[str, str]] = []
    for connection in entries:
        destination = _normalize_hash_hex(getattr(connection, "hash", None))
        identity = getattr(connection, "identity", None)
        identity_hash = _normalize_hash_hex(getattr(identity, "hash", None))
        if destination is None:
            destination = identity_hash
        if destination is None:
            continue
        if identity_hash is None:
            identity_hash = destination
        route: dict[str, str] = {
            "destination": destination,
            "identity": identity_hash,
        }
        display_name = _resolve_routing_display_name(
            hub, destination=destination, identity=identity_hash
        )
        if display_name:
            route["display_name"] = display_name
        routes.append(route)

    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for route in routes:
        destination = route["destination"]
        if destination in seen:
            continue
        seen.add(destination)
        deduped.append(route)
    return deduped


def _normalize_hash_hex(value: object) -> str | None:
    """Return a lowercase hex hash string when available."""

    if isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
        return data.hex().lower() if data else None
    if isinstance(value, str):
        cleaned = value.strip().lower()
        return cleaned or None
    hash_value = getattr(value, "hash", None)
    if isinstance(hash_value, (bytes, bytearray, memoryview)):
        data = bytes(hash_value)
        return data.hex().lower() if data else None
    if isinstance(hash_value, str):
        cleaned = hash_value.strip().lower()
        return cleaned or None
    return None


def _resolve_routing_display_name(
    hub: GatewayHub, *, destination: str, identity: str
) -> str | None:
    """Resolve a human-readable label for a routing entry."""

    identities = getattr(hub, "identities", None)
    if isinstance(identities, dict):
        for key in (destination, identity):
            value = identities.get(key) or identities.get(key.lower())
            if isinstance(value, str):
                label = value.strip()
                if label:
                    return label

    api = getattr(hub, "api", None)
    resolver = getattr(api, "resolve_identity_display_name", None)
    if callable(resolver):
        for key in (identity, destination):
            try:
                value = resolver(key)
            except Exception:  # pragma: no cover - defensive
                value = None
            if isinstance(value, str):
                label = value.strip()
                if label:
                    return label
    return None


def _normalize_routing_entry(value: object) -> dict[str, str] | None:
    """Normalize provider values into routing-entry dictionaries."""

    if isinstance(value, str):
        destination = _normalize_hash_hex(value)
        if destination is None:
            return None
        return {"destination": destination, "identity": destination}
    if not isinstance(value, dict):
        return None
    destination = _normalize_hash_hex(
        value.get("destination")
        or value.get("Destination")
        or value.get("destination_hash")
        or value.get("destinationHash")
        or value.get("lxmf_destination")
        or value.get("lxmfDestination")
    )
    identity = _normalize_hash_hex(
        value.get("identity")
        or value.get("Identity")
        or value.get("identity_hash")
        or value.get("identityHash")
        or value.get("source_identity")
        or value.get("sourceIdentity")
    )
    if destination is None:
        destination = identity
    if destination is None:
        return None
    if identity is None:
        identity = destination
    normalized: dict[str, str] = {"destination": destination, "identity": identity}
    display_name = value.get("display_name") or value.get("displayName")
    if isinstance(display_name, str):
        label = display_name.strip()
        if label:
            normalized["display_name"] = label
    return normalized


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

    startup_started = time.monotonic()
    args = _parse_args()
    config_started = time.monotonic()
    config = _build_gateway_config(args)
    config_elapsed = time.monotonic() - config_started
    RNS.log(
        f"Gateway configuration loaded in {config_elapsed:.2f}s",
        getattr(RNS, "LOG_NOTICE", 3),
    )
    config_manager = HubConfigurationManager(
        storage_path=config.storage_path,
        config_path=config.config_path,
    )
    hub_init_started = time.monotonic()
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
    hub_init_elapsed = time.monotonic() - hub_init_started
    RNS.log(
        f"Hub object constructed in {hub_init_elapsed:.2f}s",
        getattr(RNS, "LOG_NOTICE", 3),
    )
    hub_thread = _start_hub_thread(
        hub,
        daemon_mode=config.daemon_mode,
        services=config.services,
    )
    started_at = datetime.now(timezone.utc)
    control = GatewayControl(
        hub=hub,
        hub_thread=hub_thread,
        host=config.api_host,
        port=config.api_port,
        started_at=started_at,
    )
    app_started = time.monotonic()
    app = build_gateway_app(hub, started_at=started_at, control=control)
    app_elapsed = time.monotonic() - app_started
    total_elapsed = time.monotonic() - startup_started
    RNS.log(
        f"Gateway app wiring completed in {app_elapsed:.2f}s (total startup {total_elapsed:.2f}s)",
        getattr(RNS, "LOG_NOTICE", 3),
    )
    server_config = uvicorn.Config(
        app,
        host=config.api_host,
        port=config.api_port,
        log_level="info",
    )
    server = uvicorn.Server(server_config)
    control.attach_server(server)
    try:
        server.run()
    finally:
        control.request_shutdown()
        hub_thread.join(timeout=5)


if __name__ == "__main__":
    main()
