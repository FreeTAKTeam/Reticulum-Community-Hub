"""REM peer registry routes for the northbound API."""

from __future__ import annotations

from typing import Callable

from fastapi import Depends
from fastapi import FastAPI

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI


def register_rem_routes(
    app: FastAPI,
    *,
    api: ReticulumTelemetryHubAPI,
    require_protected: Callable[[], None],
) -> None:
    """Register protected REM peer registry routes."""

    @app.get("/api/rem/peers", dependencies=[Depends(require_protected)])
    def list_rem_peers() -> dict[str, object]:
        """Return the backend-computed REM peer registry."""

        return api.rem_peer_registry()
