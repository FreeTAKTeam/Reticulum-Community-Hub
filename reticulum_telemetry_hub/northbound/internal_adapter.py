"""Internal API adapter routes for the northbound gateway."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Query
from fastapi import WebSocket
from fastapi import WebSocketDisconnect
from fastapi import status
from pydantic import BaseModel
from pydantic import ConfigDict

from reticulum_telemetry_hub.internal_api import InProcessCommandBus
from reticulum_telemetry_hub.internal_api import InProcessEventBus
from reticulum_telemetry_hub.internal_api import InProcessQueryBus
from reticulum_telemetry_hub.internal_api import InternalApiCore
from reticulum_telemetry_hub.internal_api.bus import CommandBus
from reticulum_telemetry_hub.internal_api.bus import EventBus
from reticulum_telemetry_hub.internal_api.bus import QueryBus
from reticulum_telemetry_hub.internal_api.v1.enums import CommandStatus
from reticulum_telemetry_hub.internal_api.v1.enums import CommandType
from reticulum_telemetry_hub.internal_api.v1.enums import ErrorCode
from reticulum_telemetry_hub.internal_api.v1.enums import IssuerType
from reticulum_telemetry_hub.internal_api.v1.enums import MessageType
from reticulum_telemetry_hub.internal_api.v1.enums import Qos
from reticulum_telemetry_hub.internal_api.v1.enums import QueryType
from reticulum_telemetry_hub.internal_api.v1.schemas import CommandEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import CommandResult
from reticulum_telemetry_hub.internal_api.v1.schemas import QueryEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import QueryResult
from reticulum_telemetry_hub.internal_api.versioning import select_api_version


_ISSUER_ID = "internal-adapter"
_LOGGER = logging.getLogger(__name__)


class InternalMessageRequest(BaseModel):
    """Request payload for sending a text message."""

    model_config = ConfigDict(extra="forbid")

    destination: str
    text: str


@dataclass
class InternalAdapter:
    """Container for internal API adapter dependencies."""

    command_bus: CommandBus
    query_bus: QueryBus
    event_bus: EventBus
    core: InternalApiCore

    async def start(self) -> None:
        """Start in-process buses."""

        await self.event_bus.start()
        await self.command_bus.start()
        await self.query_bus.start()

    async def stop(self) -> None:
        """Stop in-process buses."""

        await self.command_bus.stop()
        await self.query_bus.stop()
        await self.event_bus.stop()


def build_internal_adapter() -> InternalAdapter:
    """Build an internal adapter backed by in-process buses."""

    event_bus = InProcessEventBus()
    core = InternalApiCore(event_bus)
    command_bus = InProcessCommandBus()
    query_bus = InProcessQueryBus()
    command_bus.register_handler(core.handle_command)
    query_bus.register_handler(core.handle_query)
    return InternalAdapter(
        command_bus=command_bus,
        query_bus=query_bus,
        event_bus=event_bus,
        core=core,
    )


def register_internal_adapter(app: FastAPI, *, adapter: InternalAdapter) -> None:
    """Register internal adapter routes on the FastAPI app."""

    router = APIRouter(prefix="/internal")

    @app.on_event("startup")
    async def _start_internal_buses() -> None:
        await adapter.start()

    @app.on_event("shutdown")
    async def _stop_internal_buses() -> None:
        await adapter.stop()

    @router.get("/topics")
    async def list_topics(prefix: Optional[str] = Query(default=None)) -> list[str]:
        """Return topic identifiers using the internal query API."""

        query = _build_query(QueryType.GET_TOPICS, {"prefix": prefix} if prefix else {})
        result = await adapter.query_bus.execute(query)
        data = _unwrap_query(result)
        return [topic["topic_id"] for topic in data.get("topics", [])]

    @router.get("/topics/{topic_id}/subscribers")
    async def list_subscribers(topic_id: str) -> list[str]:
        """Return subscriber node IDs for a topic."""

        query = _build_query(QueryType.GET_SUBSCRIBERS, {"topic_path": topic_id})
        result = await adapter.query_bus.execute(query)
        data = _unwrap_query(result)
        return [entry["node_id"] for entry in data.get("subscribers", [])]

    @router.get("/nodes/{node_id}")
    async def get_node_status(node_id: str) -> dict:
        """Return collapsed node status details."""

        query = _build_query(QueryType.GET_NODE_STATUS, {"node_id": node_id})
        result = await adapter.query_bus.execute(query)
        data = _unwrap_query(result)
        status_value = data.get("status")
        return {
            "node_id": data.get("node_id", node_id),
            "online": status_value == "online",
            "topics": data.get("topics", []),
        }

    @router.post("/message")
    async def post_message(payload: InternalMessageRequest) -> dict:
        """Publish a text message using the internal command API."""

        command = _build_command(
            CommandType.PUBLISH_MESSAGE,
            {
                "topic_path": payload.destination,
                "message_type": MessageType.TEXT,
                "content": {
                    "message_type": MessageType.TEXT,
                    "text": payload.text,
                    "encoding": "utf-8",
                },
                "qos": Qos.BEST_EFFORT,
            },
        )
        result = await adapter.command_bus.send(command)
        _raise_for_command(result)
        return {"accepted": True}

    @router.websocket("/events/stream")
    async def stream_events(websocket: WebSocket) -> None:
        """Stream internal API events over WebSocket."""

        await websocket.accept()
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=32)

        async def _handler(event) -> None:
            await queue.put(event.model_dump(mode="json"))

        unsubscribe = adapter.event_bus.subscribe(_handler)
        try:
            while True:
                message = await queue.get()
                await websocket.send_json(message)
        except WebSocketDisconnect:
            return
        finally:
            unsubscribe()

    app.include_router(router)
    app.state.internal_adapter = adapter


def _build_command(command_type: CommandType, payload: dict) -> CommandEnvelope:
    """Build a command envelope with API issuer metadata."""

    command = CommandEnvelope.model_validate(
        {
            "api_version": select_api_version(),
            "command_id": uuid4(),
            "command_type": command_type,
            "issued_at": _utc_now(),
            "issuer": {"type": IssuerType.API, "id": _ISSUER_ID},
            "payload": payload,
        }
    )
    _LOGGER.debug(
        "Internal adapter command built",
        extra={
            "command_id": str(command.command_id),
            "command_type": command.command_type.value,
            "correlation_id": str(command.command_id),
        },
    )
    return command


def _build_query(query_type: QueryType, payload: dict) -> QueryEnvelope:
    """Build a query envelope."""

    query = QueryEnvelope.model_validate(
        {
            "api_version": select_api_version(),
            "query_id": uuid4(),
            "query_type": query_type,
            "issued_at": _utc_now(),
            "payload": payload,
        }
    )
    _LOGGER.debug(
        "Internal adapter query built",
        extra={
            "query_id": str(query.query_id),
            "query_type": query.query_type.value,
            "correlation_id": str(query.query_id),
        },
    )
    return query


def _unwrap_query(result: QueryResult) -> dict:
    """Return query data or raise an HTTP error."""

    if result.ok and result.result is not None:
        return result.result.data
    error = result.error
    if error is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Query failed without an error payload",
        )
    status_code = _map_query_error(error.code)
    raise HTTPException(
        status_code=status_code,
        detail={"code": error.code.value, "message": error.message},
    )


def _raise_for_command(result: CommandResult) -> None:
    """Raise HTTP errors for rejected commands."""

    if result.status == CommandStatus.ACCEPTED:
        return
    if result.reason:
        status_code = _map_command_error(result.reason)
        raise HTTPException(
            status_code=status_code,
            detail={"code": result.reason, "message": "Command rejected"},
        )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": "COMMAND_REJECTED", "message": "Command rejected"},
    )


def _map_query_error(error_code: ErrorCode) -> int:
    """Map query error codes to HTTP status codes."""

    if error_code == ErrorCode.TOPIC_NOT_FOUND:
        return status.HTTP_404_NOT_FOUND
    if error_code == ErrorCode.INVALID_QUERY:
        return status.HTTP_400_BAD_REQUEST
    if error_code == ErrorCode.UNAUTHORIZED:
        return status.HTTP_403_FORBIDDEN
    if error_code == ErrorCode.INTERNAL_ERROR:
        return status.HTTP_500_INTERNAL_SERVER_ERROR
    return status.HTTP_500_INTERNAL_SERVER_ERROR


def _map_command_error(reason: str) -> int:
    """Map command rejection reasons to HTTP status codes."""

    try:
        error_code = ErrorCode(reason)
    except ValueError:
        return status.HTTP_400_BAD_REQUEST
    if error_code == ErrorCode.TOPIC_NOT_FOUND:
        return status.HTTP_404_NOT_FOUND
    if error_code == ErrorCode.UNAUTHORIZED_COMMAND:
        return status.HTTP_403_FORBIDDEN
    return status.HTTP_400_BAD_REQUEST


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc)
