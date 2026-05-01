"""State records and helpers for the internal API core."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
import time
from typing import Deque
from typing import Dict
from typing import Optional

from reticulum_telemetry_hub.internal_api.v1.enums import CommandType
from reticulum_telemetry_hub.internal_api.v1.enums import ErrorCode
from reticulum_telemetry_hub.internal_api.v1.enums import IssuerType
from reticulum_telemetry_hub.internal_api.v1.enums import NodeType
from reticulum_telemetry_hub.internal_api.v1.enums import RetentionPolicy
from reticulum_telemetry_hub.internal_api.v1.enums import Visibility
from reticulum_telemetry_hub.internal_api.v1.schemas import CommandEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import EventEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import QueryEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import RegisterNodeMetadata


def utc_now() -> datetime:
    """Return the current UTC time."""

    return datetime.now(timezone.utc)


def epoch_now() -> float:
    """Return current time as epoch seconds."""

    return time.time()


@dataclass
class NodeRecord:
    """In-memory record for registered nodes."""

    node_id: str
    node_type: NodeType
    metadata: Optional[RegisterNodeMetadata]


@dataclass
class TopicRecord:
    """In-memory record for topics."""

    topic_path: str
    retention: RetentionPolicy
    visibility: Visibility
    created_ts: float
    last_activity_ts: float


@dataclass
class NodeStats:
    """In-memory telemetry and activity tracking for nodes."""

    first_seen_ts: float
    last_seen_ts: float
    telemetry_timestamps: Deque[float]
    message_timestamps: Deque[float]
    battery_pct: Optional[float] = None
    signal_quality: Optional[float] = None


class CommandRejection(Exception):
    """Raise when a command must be rejected with a specific error code."""

    def __init__(self, error_code: ErrorCode) -> None:
        """Initialize with a typed error code."""

        super().__init__(error_code.value)
        self.error_code = error_code


MESSAGE_WINDOW_SECONDS = 60.0
NODE_ONLINE_THRESHOLD_SECONDS = 30.0
NODE_STALE_THRESHOLD_SECONDS = 300.0
CACHE_TTL_SECONDS = 5

COMMAND_AUTHORIZATION: Dict[CommandType, set[IssuerType]] = {
    CommandType.REGISTER_NODE: {
        IssuerType.RETICULUM,
        IssuerType.INTERNAL,
    },
    CommandType.CREATE_TOPIC: {
        IssuerType.API,
        IssuerType.INTERNAL,
    },
    CommandType.SUBSCRIBE_TOPIC: {
        IssuerType.API,
        IssuerType.RETICULUM,
        IssuerType.INTERNAL,
    },
    CommandType.PUBLISH_MESSAGE: {
        IssuerType.API,
        IssuerType.RETICULUM,
        IssuerType.INTERNAL,
    },
}


def prune_timestamps(timestamps: Deque[float], now: float) -> None:
    """Remove timestamps outside the sliding window."""

    cutoff = now - MESSAGE_WINDOW_SECONDS
    while timestamps and timestamps[0] < cutoff:
        timestamps.popleft()


def rate_from_timestamps(timestamps: Deque[float], now: float) -> float:
    """Return the per-second rate for the sliding window."""

    prune_timestamps(timestamps, now)
    return len(timestamps) / MESSAGE_WINDOW_SECONDS


def coerce_metric_value(value: object, fallback: Optional[float]) -> Optional[float]:
    """Convert telemetry metric values to floats when possible."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def command_log_context(command: CommandEnvelope) -> Dict[str, object]:
    """Return structured logging context for commands."""

    return {
        "command_id": str(command.command_id),
        "command_type": command.command_type.value,
        "issuer_id": command.issuer.id,
        "correlation_id": str(command.command_id),
    }


def event_log_context(event: EventEnvelope, correlation_id: Optional[str]) -> Dict[str, object]:
    """Return structured logging context for events."""

    context = {
        "event_id": str(event.event_id),
        "event_type": event.event_type.value,
    }
    if correlation_id is not None:
        context["correlation_id"] = correlation_id
    return context


def query_log_context(query: QueryEnvelope) -> Dict[str, object]:
    """Return structured logging context for queries."""

    return {
        "query_id": str(query.query_id),
        "query_type": query.query_type.value,
        "correlation_id": str(query.query_id),
    }


def empty_timestamps() -> Deque[float]:
    """Return an empty timestamp deque for state records."""

    return deque()
