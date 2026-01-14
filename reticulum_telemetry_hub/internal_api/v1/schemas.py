"""Pydantic schemas for the internal API v1 contract."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Annotated
from typing import Dict
from typing import List
from typing import Literal
from typing import Optional
from typing import Union
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator
from pydantic_core import PydanticCustomError

from .enums import CommandStatus
from .enums import CommandType
from .enums import ErrorCode
from .enums import EventType
from .enums import IssuerType
from .enums import MessageType
from .enums import NodeType
from .enums import Qos
from .enums import QueryType
from .enums import RetentionPolicy
from .enums import Severity
from .enums import SubscriberAction
from .enums import Visibility


SUPPORTED_API_VERSION = "1.0"


def _parse_api_version(value: str) -> tuple[int, int]:
    """Parse and validate an API version string.

    Args:
        value (str): Version string.

    Returns:
        tuple[int, int]: Major and minor versions.
    """

    match = re.fullmatch(r"(\d+)\.(\d+)", value)
    if not match:
        raise PydanticCustomError(
            ErrorCode.API_VERSION_UNSUPPORTED.value,
            "API version unsupported",
        )
    return int(match.group(1)), int(match.group(2))


def _supported_version_parts() -> tuple[int, int]:
    """Return the supported API version parts."""

    return _parse_api_version(SUPPORTED_API_VERSION)


def _reject_numeric_timestamp(value: object) -> object:
    """Reject numeric timestamps to enforce ISO-8601 strings."""

    if isinstance(value, (int, float)):
        raise ValueError("timestamp must be ISO-8601")
    return value


class ApiEnvelopeBase(BaseModel):
    """Base class for API envelopes with version enforcement."""

    model_config = ConfigDict(extra="forbid")

    api_version: str

    @model_validator(mode="after")
    def _validate_api_version(self):
        """Validate API version compatibility."""

        major, minor = _parse_api_version(self.api_version)
        supported_major, supported_minor = _supported_version_parts()
        if major != supported_major:
            raise PydanticCustomError(
                ErrorCode.API_VERSION_UNSUPPORTED.value,
                "API version unsupported",
            )
        if minor < supported_minor:
            raise PydanticCustomError(
                ErrorCode.API_VERSION_UNSUPPORTED.value,
                "API version unsupported",
            )
        return self


class Issuer(BaseModel):
    """Issuer metadata for commands."""

    model_config = ConfigDict(extra="forbid")

    type: IssuerType
    id: str


class Location(BaseModel):
    """Location metadata for registered nodes."""

    model_config = ConfigDict(extra="forbid")

    lat: Optional[float] = None
    lon: Optional[float] = None


class RegisterNodeMetadata(BaseModel):
    """Metadata for RegisterNode."""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, max_length=64)
    description: Optional[str] = Field(default=None, max_length=256)
    capabilities: Optional[List[str]] = None
    location: Optional[Location] = None


class RegisterNodePayload(BaseModel):
    """Payload for RegisterNode."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    node_type: NodeType
    metadata: Optional[RegisterNodeMetadata] = None


class CreateTopicPayload(BaseModel):
    """Payload for CreateTopic."""

    model_config = ConfigDict(extra="forbid")

    topic_path: str
    retention: RetentionPolicy
    visibility: Visibility


class SubscribeTopicPayload(BaseModel):
    """Payload for SubscribeTopic."""

    model_config = ConfigDict(extra="forbid")

    subscriber_id: str
    topic_path: str


class TextContent(BaseModel):
    """Text message content."""

    model_config = ConfigDict(extra="forbid")

    message_type: Literal[MessageType.TEXT] = MessageType.TEXT
    text: str = Field(max_length=4096)
    encoding: Literal["utf-8"] = "utf-8"


class Metric(BaseModel):
    """Telemetry metric."""

    model_config = ConfigDict(extra="forbid")

    name: str
    value: Union[float, int, str, bool]
    unit: Optional[str] = None


class TelemetryContent(BaseModel):
    """Telemetry message content."""

    model_config = ConfigDict(extra="forbid")

    message_type: Literal[MessageType.TELEMETRY] = MessageType.TELEMETRY
    telemetry_type: Optional[str] = None
    data: Dict[str, object]
    timestamp: Optional[datetime] = None


class EventContent(BaseModel):
    """Event message content."""

    model_config = ConfigDict(extra="forbid")

    message_type: Literal[MessageType.EVENT] = MessageType.EVENT
    event_name: str
    attributes: Dict[str, Union[str, float, int, bool]]


MessageContent = Annotated[
    Union[TextContent, TelemetryContent, EventContent],
    Field(discriminator="message_type"),
]


class PublishMessagePayload(BaseModel):
    """Payload for PublishMessage."""

    model_config = ConfigDict(extra="forbid")

    topic_path: str
    message_type: MessageType
    content: MessageContent
    qos: Qos

    @model_validator(mode="after")
    def _validate_message_type(self):
        """Ensure message_type matches content."""

        if self.content.message_type != self.message_type:
            raise PydanticCustomError(
                "MESSAGE_TYPE_MISMATCH",
                "message_type does not match content",
            )
        return self


CommandPayload = Union[
    RegisterNodePayload,
    CreateTopicPayload,
    SubscribeTopicPayload,
    PublishMessagePayload,
]


_COMMAND_PAYLOAD_MAP = {
    CommandType.REGISTER_NODE: RegisterNodePayload,
    CommandType.CREATE_TOPIC: CreateTopicPayload,
    CommandType.SUBSCRIBE_TOPIC: SubscribeTopicPayload,
    CommandType.PUBLISH_MESSAGE: PublishMessagePayload,
}


class CommandEnvelope(ApiEnvelopeBase):
    """Envelope for commands."""

    command_id: UUID
    command_type: CommandType
    issued_at: datetime
    issuer: Issuer
    payload: CommandPayload

    @field_validator("issued_at", mode="before")
    @classmethod
    def _validate_issued_at(cls, value: object) -> object:
        return _reject_numeric_timestamp(value)

    @model_validator(mode="after")
    def _validate_payload(self):
        """Ensure payload type matches command_type."""

        expected = _COMMAND_PAYLOAD_MAP.get(self.command_type)
        if expected and not isinstance(self.payload, expected):
            raise PydanticCustomError(
                "COMMAND_PAYLOAD_MISMATCH",
                "Payload does not match command_type",
            )
        return self


class NodeRegisteredPayload(BaseModel):
    """Payload for NodeRegistered event."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    node_type: NodeType


class TopicCreatedPayload(BaseModel):
    """Payload for TopicCreated event."""

    model_config = ConfigDict(extra="forbid")

    topic_path: str


class MessagePublishedPayload(BaseModel):
    """Payload for MessagePublished event."""

    model_config = ConfigDict(extra="forbid")

    topic_path: str
    message_id: str
    originator: str


class SubscriberUpdatedPayload(BaseModel):
    """Payload for SubscriberUpdated event."""

    model_config = ConfigDict(extra="forbid")

    subscriber_id: str
    topic_path: str
    action: SubscriberAction


EventPayload = Union[
    NodeRegisteredPayload,
    TopicCreatedPayload,
    MessagePublishedPayload,
    SubscriberUpdatedPayload,
]


_EVENT_PAYLOAD_MAP = {
    EventType.NODE_REGISTERED: NodeRegisteredPayload,
    EventType.TOPIC_CREATED: TopicCreatedPayload,
    EventType.MESSAGE_PUBLISHED: MessagePublishedPayload,
    EventType.SUBSCRIBER_UPDATED: SubscriberUpdatedPayload,
}


class EventEnvelope(ApiEnvelopeBase):
    """Envelope for events."""

    event_id: UUID
    event_type: EventType
    occurred_at: datetime
    origin: Literal["hub-core"]
    payload: EventPayload

    @field_validator("occurred_at", mode="before")
    @classmethod
    def _validate_occurred_at(cls, value: object) -> object:
        return _reject_numeric_timestamp(value)

    @model_validator(mode="after")
    def _validate_payload(self):
        """Ensure payload type matches event_type."""

        expected = _EVENT_PAYLOAD_MAP.get(self.event_type)
        if expected and not isinstance(self.payload, expected):
            raise PydanticCustomError(
                "EVENT_PAYLOAD_MISMATCH",
                "Payload does not match event_type",
            )
        return self


class GetTopicsPayload(BaseModel):
    """Payload for GetTopics."""

    model_config = ConfigDict(extra="forbid")

    prefix: Optional[str] = None


class GetSubscribersPayload(BaseModel):
    """Payload for GetSubscribers."""

    model_config = ConfigDict(extra="forbid")

    topic_path: str


class GetNodeStatusPayload(BaseModel):
    """Payload for GetNodeStatus."""

    model_config = ConfigDict(extra="forbid")

    node_id: str


QueryPayload = Union[GetTopicsPayload, GetSubscribersPayload, GetNodeStatusPayload]


_QUERY_PAYLOAD_MAP = {
    QueryType.GET_TOPICS: GetTopicsPayload,
    QueryType.GET_SUBSCRIBERS: GetSubscribersPayload,
    QueryType.GET_NODE_STATUS: GetNodeStatusPayload,
}


class QueryEnvelope(ApiEnvelopeBase):
    """Envelope for queries."""

    query_id: UUID
    query_type: QueryType
    issued_at: datetime
    payload: QueryPayload

    @field_validator("issued_at", mode="before")
    @classmethod
    def _validate_issued_at(cls, value: object) -> object:
        return _reject_numeric_timestamp(value)

    @model_validator(mode="after")
    def _validate_payload(self):
        """Ensure payload type matches query_type."""

        expected = _QUERY_PAYLOAD_MAP.get(self.query_type)
        if expected and not isinstance(self.payload, expected):
            raise PydanticCustomError(
                "QUERY_PAYLOAD_MISMATCH",
                "Payload does not match query_type",
            )
        return self


class CommandResult(BaseModel):
    """Result for command execution."""

    model_config = ConfigDict(extra="forbid")

    command_id: UUID
    status: CommandStatus
    reason: Optional[str] = None


class QueryResult(BaseModel):
    """Result for query execution."""

    model_config = ConfigDict(extra="forbid")

    query_id: UUID
    ok: bool
    result: Optional["QueryResultPayload"] = None
    error: Optional["QueryError"] = None

    @model_validator(mode="after")
    def _validate_outcome(self):
        """Ensure ok/error/result coherence."""

        if self.ok:
            if self.error is not None or self.result is None:
                raise ValueError("ok results must include result and no error")
        else:
            if self.error is None:
                raise ValueError("error results must include error")
        return self


class QueryCacheHint(BaseModel):
    """Cache hints for query results."""

    model_config = ConfigDict(extra="forbid")

    ttl_seconds: int
    scope: Literal["node", "hub", "network"]
    stale_while_revalidate: bool


class QueryResultPayload(BaseModel):
    """Query result payload with optional cache hints."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    data: Dict[str, object]
    cache: Optional[QueryCacheHint] = Field(default=None, alias="_cache")


class QueryError(BaseModel):
    """Query error payload."""

    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str


class ErrorDetail(BaseModel):
    """Error payload for command/query failures."""

    model_config = ConfigDict(extra="forbid")

    error_code: ErrorCode
    severity: Severity
    message: str

