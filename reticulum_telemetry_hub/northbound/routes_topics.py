"""Topic routes for the northbound API."""

from __future__ import annotations

from typing import Callable

from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Query
from fastapi import status

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI

from .models import SubscribeTopicRequest
from .models import TopicPayload
from .serializers import build_topic
from .serializers import serialize_subscriber
from .serializers import serialize_topic
from .services import NorthboundServices


def register_topic_routes(
    app: FastAPI,
    *,
    services: NorthboundServices,
    api: ReticulumTelemetryHubAPI,
    require_protected: Callable[[], None],
) -> None:
    """Register topic routes on the FastAPI app.

    Args:
        app (FastAPI): FastAPI application instance.
        services (NorthboundServices): Aggregated services.
        api (ReticulumTelemetryHubAPI): API service instance.
        require_protected (Callable[[], None]): Dependency for protected routes.

    Returns:
        None: Routes are registered on the application.
    """

    @app.get("/Topic/{topic_id}")
    def retrieve_topic(topic_id: str) -> dict:
        """Retrieve a topic by ID.

        Args:
            topic_id (str): Topic identifier.

        Returns:
            dict: Topic payload.
        """

        try:
            topic = api.retrieve_topic(topic_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return serialize_topic(topic)

    @app.post("/Topic", dependencies=[Depends(require_protected)])
    def create_topic(payload: TopicPayload) -> dict:
        """Create a new topic.

        Args:
            payload (TopicPayload): Topic request payload.

        Returns:
            dict: Created topic payload.
        """

        topic = build_topic(payload)
        try:
            created = api.create_topic(topic)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        services.record_event("topic_created", f"Topic created: {created.topic_id}")
        return serialize_topic(created)

    @app.delete("/Topic", dependencies=[Depends(require_protected)])
    def delete_topic(topic_id: str = Query(alias="id")) -> dict:
        """Delete a topic.

        Args:
            topic_id (str): Topic identifier.

        Returns:
            dict: Deleted topic payload.
        """

        try:
            topic = api.delete_topic(topic_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        services.record_event("topic_deleted", f"Topic deleted: {topic.topic_id}")
        return serialize_topic(topic)

    @app.get("/Topic")
    def list_topics() -> list[dict]:
        """List topics.

        Returns:
            list[dict]: Topic entries.
        """

        return [serialize_topic(topic) for topic in services.list_topics()]

    @app.patch("/Topic", dependencies=[Depends(require_protected)])
    def patch_topic(payload: TopicPayload) -> dict:
        """Update a topic.

        Args:
            payload (TopicPayload): Topic update payload.

        Returns:
            dict: Updated topic payload.
        """

        if not payload.topic_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="TopicID is required",
            )
        try:
            topic = api.patch_topic(payload.topic_id, **payload.dict(by_alias=True, exclude_unset=True))
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        services.record_event("topic_updated", f"Topic updated: {topic.topic_id}")
        return serialize_topic(topic)

    @app.post("/Topic/Subscribe")
    def subscribe_topic(payload: SubscribeTopicRequest) -> dict:
        """Subscribe a destination to a topic.

        Args:
            payload (SubscribeTopicRequest): Subscription payload.

        Returns:
            dict: Subscriber payload.
        """

        if not payload.destination:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Destination is required when authentication identity is unavailable",
            )
        try:
            subscriber = api.subscribe_topic(
                payload.topic_id,
                payload.destination,
                reject_tests=payload.reject_tests,
                metadata=payload.metadata,
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        services.record_event(
            "topic_subscribed",
            f"Subscriber added: {subscriber.subscriber_id}",
            metadata={"topic_id": subscriber.topic_id},
        )
        return serialize_subscriber(subscriber)

    @app.post("/Topic/Associate", dependencies=[Depends(require_protected)])
    def associate_topic(payload: TopicPayload) -> dict:
        """Return the topic association payload.

        Args:
            payload (TopicPayload): Topic association payload.

        Returns:
            dict: Topic association payload.
        """

        if not payload.topic_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="TopicID is required",
            )
        return {"TopicID": payload.topic_id}
