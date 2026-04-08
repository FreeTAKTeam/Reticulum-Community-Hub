"""File and image routes for the northbound API."""
# pylint: disable=import-error

from __future__ import annotations

from typing import Callable

from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import status
from fastapi.responses import FileResponse

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI

from .models import AttachmentTopicPayload
from .services import NorthboundServices


def register_file_routes(
    app: FastAPI,
    *,
    services: NorthboundServices,
    api: ReticulumTelemetryHubAPI,
    require_protected: Callable[[], None],
) -> None:
    """Register file and image routes on the FastAPI app.

    Args:
        app (FastAPI): FastAPI application instance.
        services (NorthboundServices): Aggregated services.
        api (ReticulumTelemetryHubAPI): API service instance.
        require_protected (Callable[[], None]): Dependency for protected routes.

    Returns:
        None: Routes are registered on the application.
    """

    @app.get("/File", dependencies=[Depends(require_protected)])
    def list_files() -> list[dict]:
        """List stored files.

        Returns:
            list[dict]: File attachment entries.
        """

        return [attachment.to_dict() for attachment in services.list_files()]

    @app.get("/File/{file_id}", dependencies=[Depends(require_protected)])
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

    @app.patch("/File/{file_id}", dependencies=[Depends(require_protected)])
    def patch_file(file_id: int, payload: AttachmentTopicPayload) -> dict:
        """Update the topic association for a stored file."""

        try:
            attachment = api.assign_file_to_topic(file_id, payload.topic_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return attachment.to_dict()

    @app.get("/File/{file_id}/raw", dependencies=[Depends(require_protected)])
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

    @app.delete("/File/{file_id}", dependencies=[Depends(require_protected)])
    def delete_file(file_id: int) -> dict:
        """Delete a stored file and its metadata."""

        try:
            attachment = services.delete_file(file_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return attachment.to_dict()

    @app.get("/Image", dependencies=[Depends(require_protected)])
    def list_images() -> list[dict]:
        """List stored images.

        Returns:
            list[dict]: Image attachment entries.
        """

        return [attachment.to_dict() for attachment in services.list_images()]

    @app.get("/Image/{file_id}", dependencies=[Depends(require_protected)])
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

    @app.patch("/Image/{file_id}", dependencies=[Depends(require_protected)])
    def patch_image(file_id: int, payload: AttachmentTopicPayload) -> dict:
        """Update the topic association for a stored image."""

        try:
            attachment = api.assign_image_to_topic(file_id, payload.topic_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return attachment.to_dict()

    @app.get("/Image/{file_id}/raw", dependencies=[Depends(require_protected)])
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

    @app.delete("/Image/{file_id}", dependencies=[Depends(require_protected)])
    def delete_image(file_id: int) -> dict:
        """Delete a stored image and its metadata."""

        try:
            attachment = services.delete_image(file_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return attachment.to_dict()
