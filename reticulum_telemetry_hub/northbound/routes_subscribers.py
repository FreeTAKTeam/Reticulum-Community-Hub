"""Subscriber routes for the northbound API."""
# pylint: disable=import-error

from __future__ import annotations

from typing import Callable

from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Query
from fastapi import status

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI

from .models import SubscriberPayload
from .serializers import build_subscriber
from .serializers import serialize_subscriber
from .services import NorthboundServices


def register_subscriber_routes(
    app: FastAPI,
    *,
    services: NorthboundServices,
    api: ReticulumTelemetryHubAPI,
    require_protected: Callable[[], None],
) -> None:
    """Register subscriber routes on the FastAPI app.

    Args:
        app (FastAPI): FastAPI application instance.
        services (NorthboundServices): Aggregated services.
        api (ReticulumTelemetryHubAPI): API service instance.
        require_protected (Callable[[], None]): Dependency for protected routes.

    Returns:
        None: Routes are registered on the application.
    """

    @app.get("/Subscriber/{subscriber_id}", dependencies=[Depends(require_protected)])
    def retrieve_subscriber(subscriber_id: str) -> dict:
        """Retrieve a subscriber by ID.

        Args:
            subscriber_id (str): Subscriber identifier.

        Returns:
            dict: Subscriber payload.
        """

        try:
            subscriber = api.retrieve_subscriber(subscriber_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return serialize_subscriber(subscriber)

    @app.post("/Subscriber/Add", dependencies=[Depends(require_protected)])
    def add_subscriber(payload: SubscriberPayload) -> dict:
        """Add a subscriber mapping.

        Args:
            payload (SubscriberPayload): Subscriber payload.

        Returns:
            dict: Subscriber payload.
        """

        subscriber = build_subscriber(payload)
        try:
            created = api.add_subscriber(subscriber)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        services.record_event("subscriber_added", f"Subscriber added: {created.subscriber_id}")
        return serialize_subscriber(created)

    @app.post("/Subscriber", dependencies=[Depends(require_protected)])
    def create_subscriber(payload: SubscriberPayload) -> dict:
        """Create a subscriber.

        Args:
            payload (SubscriberPayload): Subscriber payload.

        Returns:
            dict: Subscriber payload.
        """

        subscriber = build_subscriber(payload)
        try:
            created = api.create_subscriber(subscriber)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        services.record_event("subscriber_created", f"Subscriber created: {created.subscriber_id}")
        return serialize_subscriber(created)

    @app.delete("/Subscriber", dependencies=[Depends(require_protected)])
    def delete_subscriber(subscriber_id: str = Query(alias="id")) -> dict:
        """Delete a subscriber.

        Args:
            subscriber_id (str): Subscriber identifier.

        Returns:
            dict: Deleted subscriber payload.
        """

        try:
            subscriber = api.delete_subscriber(subscriber_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        services.record_event("subscriber_deleted", f"Subscriber deleted: {subscriber.subscriber_id}")
        return serialize_subscriber(subscriber)

    @app.get("/Subscriber", dependencies=[Depends(require_protected)])
    def list_subscribers() -> list[dict]:
        """List subscribers.

        Returns:
            list[dict]: Subscriber entries.
        """

        return [serialize_subscriber(subscriber) for subscriber in services.list_subscribers()]

    @app.patch("/Subscriber", dependencies=[Depends(require_protected)])
    def patch_subscriber(payload: SubscriberPayload) -> dict:
        """Update a subscriber.

        Args:
            payload (SubscriberPayload): Subscriber update payload.

        Returns:
            dict: Updated subscriber payload.
        """

        if not payload.subscriber_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="SubscriberID is required",
            )
        try:
            subscriber = api.patch_subscriber(
                payload.subscriber_id,
                **payload.dict(by_alias=True, exclude_unset=True),
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        services.record_event("subscriber_updated", f"Subscriber updated: {subscriber.subscriber_id}")
        return serialize_subscriber(subscriber)
