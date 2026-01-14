"""Enumerations for the internal API v1 contract."""

from __future__ import annotations

from enum import Enum


class IssuerType(str, Enum):
    """Issuer types for internal API commands."""

    API = "api"
    RETICULUM = "reticulum"
    INTERNAL = "internal"


class CommandType(str, Enum):
    """Supported command types."""

    REGISTER_NODE = "RegisterNode"
    CREATE_TOPIC = "CreateTopic"
    SUBSCRIBE_TOPIC = "SubscribeTopic"
    PUBLISH_MESSAGE = "PublishMessage"


class EventType(str, Enum):
    """Supported event types."""

    NODE_REGISTERED = "NodeRegistered"
    TOPIC_CREATED = "TopicCreated"
    MESSAGE_PUBLISHED = "MessagePublished"
    SUBSCRIBER_UPDATED = "SubscriberUpdated"


class QueryType(str, Enum):
    """Supported query types."""

    GET_TOPICS = "GetTopics"
    GET_SUBSCRIBERS = "GetSubscribers"
    GET_NODE_STATUS = "GetNodeStatus"


class ErrorCode(str, Enum):
    """Error codes for internal API responses."""

    API_VERSION_UNSUPPORTED = "API_VERSION_UNSUPPORTED"
    UNAUTHORIZED_COMMAND = "UNAUTHORIZED_COMMAND"
    TOPIC_NOT_FOUND = "TOPIC_NOT_FOUND"
    INVALID_QUERY = "INVALID_QUERY"
    UNAUTHORIZED = "UNAUTHORIZED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class Severity(str, Enum):
    """Severity levels for errors."""

    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


class NodeType(str, Enum):
    """Supported node types for RegisterNode."""

    RETICULUM = "reticulum"
    GATEWAY = "gateway"
    SERVICE = "service"


class RetentionPolicy(str, Enum):
    """Retention policy for topics."""

    EPHEMERAL = "ephemeral"
    PERSISTENT = "persistent"


class Visibility(str, Enum):
    """Visibility for topics."""

    PUBLIC = "public"
    RESTRICTED = "restricted"


class MessageType(str, Enum):
    """Message content types."""

    TELEMETRY = "telemetry"
    EVENT = "event"
    TEXT = "text"


class Qos(str, Enum):
    """Quality of service options."""

    BEST_EFFORT = "best_effort"
    GUARANTEED = "guaranteed"


class SubscriberAction(str, Enum):
    """Subscriber update actions."""

    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"


class CommandStatus(str, Enum):
    """Command status values."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
