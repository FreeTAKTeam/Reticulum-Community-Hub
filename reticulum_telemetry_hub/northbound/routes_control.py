"""Control routes for managing the gateway lifecycle."""
# pylint: disable=import-error

from __future__ import annotations

from typing import Callable
from typing import Protocol

from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException


class ControlService(Protocol):
    """Protocol for the gateway control surface."""

    def status(self) -> dict[str, object]:
        """Return a control status payload."""

    def request_shutdown(self) -> None:
        """Request a graceful shutdown."""

    def request_announce(self) -> bool:
        """Trigger a Reticulum announce."""


def register_control_routes(
    app: FastAPI,
    *,
    control: ControlService,
    require_protected: Callable[[], None],
) -> None:
    """Register control routes on the FastAPI app.

    Args:
        app (FastAPI): FastAPI application instance.
        control (ControlService): Control surface implementation.
        require_protected (Callable[[], None]): Dependency for protected routes.

    Returns:
        None: Routes are registered on the application.
    """

    @app.get("/Control/Status", dependencies=[Depends(require_protected)])
    def control_status() -> dict[str, object]:
        """Return the current gateway status."""

        return control.status()

    @app.post("/Control/Stop", dependencies=[Depends(require_protected)])
    def control_stop() -> dict[str, object]:
        """Request a graceful gateway shutdown."""

        control.request_shutdown()
        return {"status": "stopping"}

    @app.post("/Control/Start", dependencies=[Depends(require_protected)])
    def control_start() -> dict[str, object]:
        """Return the gateway status after a start request."""

        request_start = getattr(control, "request_start", None)
        if callable(request_start):
            request_start()
        return control.status()

    @app.post("/Control/Announce", dependencies=[Depends(require_protected)])
    def control_announce() -> dict[str, object]:
        """Send an immediate Reticulum announce."""

        if not control.request_announce():
            raise HTTPException(status_code=503, detail="Announce unavailable")
        return {"status": "announce sent"}
