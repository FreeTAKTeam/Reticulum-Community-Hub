"""Marker routes for the northbound API."""
# pylint: disable=import-error

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from typing import Callable
from typing import Optional

from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import status

from reticulum_telemetry_hub.api.marker_symbols import list_marker_symbols

from .models import MarkerCreatePayload
from .models import MarkerPositionPayload
from .models import MarkerUpdatePayload
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

    @app.get("/api/markers/symbols", dependencies=[Depends(require_protected)])
    def list_marker_symbols_route() -> list[dict[str, Optional[str]]]:
        """Return available marker symbol definitions."""

        return list_marker_symbols()

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
                marker_type=payload.marker_type,
                symbol=payload.symbol,
                category=payload.category or payload.symbol,
                lat=payload.lat,
                lon=payload.lon,
                origin_rch=services.origin_rch,
                notes=payload.notes,
                ttl_seconds=payload.ttl_seconds,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        return {
            "object_destination_hash": marker.object_destination_hash,
            "created_at": marker.created_at.isoformat(),
        }

    @app.patch(
        "/api/markers/{object_destination_hash}/position",
        dependencies=[Depends(require_protected)],
    )
    def update_marker_position(
        object_destination_hash: str, payload: MarkerPositionPayload
    ) -> dict:
        """Update marker coordinates."""

        try:
            result = services.update_marker_position(
                object_destination_hash,
                lat=payload.lat,
                lon=payload.lon,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from exc
        return {"status": "ok", "updated_at": result.marker.updated_at.isoformat()}

    @app.patch(
        "/api/markers/{object_destination_hash}",
        dependencies=[Depends(require_protected)],
    )
    def update_marker(
        object_destination_hash: str, payload: MarkerUpdatePayload
    ) -> dict:
        """Update marker metadata."""

        try:
            result = services.update_marker_name(
                object_destination_hash,
                name=payload.name,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        return {"status": "ok", "updated_at": result.marker.updated_at.isoformat()}

    @app.delete(
        "/api/markers/{object_destination_hash}",
        dependencies=[Depends(require_protected)],
    )
    def delete_marker(object_destination_hash: str) -> dict:
        """Delete a marker."""

        try:
            services.delete_marker(object_destination_hash)
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from exc
        return {"status": "ok", "deleted_at": datetime.now(timezone.utc).isoformat()}
