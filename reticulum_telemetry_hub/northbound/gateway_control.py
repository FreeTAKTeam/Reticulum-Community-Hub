"""Runtime control surface for the northbound gateway."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timezone
from typing import Optional

import RNS
import uvicorn

from reticulum_telemetry_hub.reticulum_server.__main__ import ReticulumTelemetryHub


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

    def request_sync(self) -> dict[str, object]:
        """Request an immediate LXMF propagation sync."""

        sync = getattr(self.hub, "request_propagation_sync", None)
        if callable(sync):
            result = sync()
            if isinstance(result, dict):
                return result
            if result:
                return {"status": "sync_requested"}
        return {"status": "unavailable", "detail": "Sync unavailable"}

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
