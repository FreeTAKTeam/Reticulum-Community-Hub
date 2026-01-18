"""Marker routes for the northbound API."""
# pylint: disable=import-error

from __future__ import annotations

from typing import Callable

from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import status

from .models import MarkerCreatePayload
from .models import MarkerPositionPayload
from .services import NorthboundServices


def register_marker_routes(
    app: FastAPI,
    *,
    services: NorthboundServices,
    require_protected: Callable[[], None],
) -> None:
    """Register marker routes on the FastAPI app.

    Args:
        app (FastAPI): FastAPI application instance.
        services (NorthboundServices): Aggregated services.
        require_protected (Callable[[], None]): Dependency for protected routes.
    """

    @app.get("/api/markers", dependencies=[Depends(require_protected)])
    def list_markers() -> list[dict]:
        """Return stored operator markers."""

        return [marker.to_dict() for marker in services.list_markers()]

    @app.post(
        "/api/markers",
        dependencies=[Depends(require_protected)],
        status_code=status.HTTP_201_CREATED,
    )
    def create_marker(payload: MarkerCreatePayload) -> dict:
        """Create a new marker."""

        try:
            marker = services.create_marker(
                name=payload.name,
                category=payload.category,
                lat=payload.lat,
                lon=payload.lon,
                notes=payload.notes,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        return {
            "marker_id": marker.marker_id,
            "created_at": marker.created_at.isoformat(),
        }

    @app.patch(
        "/api/markers/{marker_id}/position",
        dependencies=[Depends(require_protected)],
    )
    def update_marker_position(marker_id: str, payload: MarkerPositionPayload) -> dict:
        """Update marker coordinates."""

        try:
            services.update_marker_position(
                marker_id,
                lat=payload.lat,
                lon=payload.lon,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from exc
        return {"status": "ok"}
