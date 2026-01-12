"""File and image routes for the northbound API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import status
from fastapi.responses import FileResponse

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI

from .services import NorthboundServices


def register_file_routes(
    app: FastAPI,
    *,
    services: NorthboundServices,
    api: ReticulumTelemetryHubAPI,
) -> None:
    """Register file and image routes on the FastAPI app.

    Args:
        app (FastAPI): FastAPI application instance.
        services (NorthboundServices): Aggregated services.
        api (ReticulumTelemetryHubAPI): API service instance.

    Returns:
        None: Routes are registered on the application.
    """

    @app.get("/File")
    def list_files() -> list[dict]:
        """List stored files.

        Returns:
            list[dict]: File attachment entries.
        """

        return [attachment.to_dict() for attachment in services.list_files()]

    @app.get("/File/{file_id}")
    def retrieve_file(file_id: int) -> dict:
        """Retrieve file metadata by ID.

        Args:
            file_id (int): File record identifier.

        Returns:
            dict: File attachment payload.
        """

        try:
            attachment = api.retrieve_file(file_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return attachment.to_dict()

    @app.get("/File/{file_id}/raw")
    def retrieve_file_raw(file_id: int) -> FileResponse:
        """Return raw file bytes by ID.

        Args:
            file_id (int): File record identifier.

        Returns:
            FileResponse: File response payload.
        """

        try:
            attachment = api.retrieve_file(file_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return FileResponse(path=attachment.path, media_type=attachment.media_type)

    @app.get("/Image")
    def list_images() -> list[dict]:
        """List stored images.

        Returns:
            list[dict]: Image attachment entries.
        """

        return [attachment.to_dict() for attachment in services.list_images()]

    @app.get("/Image/{file_id}")
    def retrieve_image(file_id: int) -> dict:
        """Retrieve image metadata by ID.

        Args:
            file_id (int): Image record identifier.

        Returns:
            dict: Image attachment payload.
        """

        try:
            attachment = api.retrieve_image(file_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return attachment.to_dict()

    @app.get("/Image/{file_id}/raw")
    def retrieve_image_raw(file_id: int) -> FileResponse:
        """Return raw image bytes by ID.

        Args:
            file_id (int): Image record identifier.

        Returns:
            FileResponse: Image response payload.
        """

        try:
            attachment = api.retrieve_image(file_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return FileResponse(path=attachment.path, media_type=attachment.media_type)
