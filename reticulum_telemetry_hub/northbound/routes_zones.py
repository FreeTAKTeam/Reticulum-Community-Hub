"""Zone routes for the northbound API."""
# pylint: disable=import-error

from __future__ import annotations

from typing import Callable
from datetime import datetime
from datetime import timezone

from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import status

from reticulum_telemetry_hub.api.models import ZonePoint

from .models import ZoneCreatePayload
from .models import ZoneUpdatePayload
from .services import NorthboundServices


def register_zone_routes(
    app: FastAPI,
    *,
    services: NorthboundServices,
    require_protected: Callable[[], None],
) -> None:
    """Register zone routes on the FastAPI app."""

    @app.get("/api/zones", dependencies=[Depends(require_protected)])
    def list_zones() -> list[dict]:
        """Return stored zones."""

        return [zone.to_dict() for zone in services.list_zones()]

    @app.post(
        "/api/zones",
        dependencies=[Depends(require_protected)],
        status_code=status.HTTP_201_CREATED,
    )
    def create_zone(payload: ZoneCreatePayload) -> dict:
        """Create a new zone."""

        points = [ZonePoint(lat=point.lat, lon=point.lon) for point in payload.points]
        try:
            zone = services.create_zone(name=payload.name, points=points)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        return {"zone_id": zone.zone_id, "created_at": zone.created_at.isoformat()}

    @app.patch("/api/zones/{zone_id}", dependencies=[Depends(require_protected)])
    def update_zone(zone_id: str, payload: ZoneUpdatePayload) -> dict:
        """Update zone metadata and/or geometry."""

        points = None
        if payload.points is not None:
            points = [ZonePoint(lat=point.lat, lon=point.lon) for point in payload.points]
        try:
            result = services.update_zone(zone_id, name=payload.name, points=points)
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        return {"status": "ok", "updated_at": result.zone.updated_at.isoformat()}

    @app.delete("/api/zones/{zone_id}", dependencies=[Depends(require_protected)])
    def delete_zone(zone_id: str) -> dict:
        """Delete a zone."""

        try:
            services.delete_zone(zone_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        return {"status": "ok", "deleted_at": datetime.now(timezone.utc).isoformat()}
