"""Internal API core command handling and in-memory state."""

from __future__ import annotations

from collections import deque
import logging
from typing import Deque
from typing import Dict
from typing import Optional
from typing import Set
from typing import Tuple
from uuid import UUID
from uuid import uuid4

from reticulum_telemetry_hub.internal_api.bus import EventBus
from reticulum_telemetry_hub.internal_api.core_queries import InternalApiQueryMixin
from reticulum_telemetry_hub.internal_api.v1.enums import CommandStatus
from reticulum_telemetry_hub.internal_api.v1.enums import CommandType
from reticulum_telemetry_hub.internal_api.v1.enums import ErrorCode
from reticulum_telemetry_hub.internal_api.v1.enums import EventType
from reticulum_telemetry_hub.internal_api.v1.enums import MessageType
from reticulum_telemetry_hub.internal_api.v1.enums import QueryType
from reticulum_telemetry_hub.internal_api.v1.enums import SubscriberAction
from reticulum_telemetry_hub.internal_api.core_state import COMMAND_AUTHORIZATION
from reticulum_telemetry_hub.internal_api.core_state import CommandRejection
from reticulum_telemetry_hub.internal_api.core_state import NodeRecord
from reticulum_telemetry_hub.internal_api.core_state import NodeStats
from reticulum_telemetry_hub.internal_api.core_state import TopicRecord
from reticulum_telemetry_hub.internal_api.core_state import coerce_metric_value as _coerce_metric_value
from reticulum_telemetry_hub.internal_api.core_state import command_log_context as _command_log_context
from reticulum_telemetry_hub.internal_api.core_state import epoch_now as _epoch_now
from reticulum_telemetry_hub.internal_api.core_state import event_log_context as _event_log_context
from reticulum_telemetry_hub.internal_api.core_state import prune_timestamps as _prune_timestamps
from reticulum_telemetry_hub.internal_api.core_state import query_log_context as _query_log_context
from reticulum_telemetry_hub.internal_api.core_state import utc_now as _utc_now
from reticulum_telemetry_hub.internal_api.v1.schemas import CommandEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import CommandResult
from reticulum_telemetry_hub.internal_api.v1.schemas import CreateTopicPayload
from reticulum_telemetry_hub.internal_api.v1.schemas import EventEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import MessagePublishedPayload
from reticulum_telemetry_hub.internal_api.v1.schemas import NodeRegisteredPayload
from reticulum_telemetry_hub.internal_api.v1.schemas import PublishMessagePayload
from reticulum_telemetry_hub.internal_api.v1.schemas import RegisterNodePayload
from reticulum_telemetry_hub.internal_api.v1.schemas import QueryEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import QueryResult
from reticulum_telemetry_hub.internal_api.v1.schemas import SubscribeTopicPayload
from reticulum_telemetry_hub.internal_api.v1.schemas import SubscriberUpdatedPayload
from reticulum_telemetry_hub.internal_api.v1.schemas import SUPPORTED_API_VERSION
from reticulum_telemetry_hub.internal_api.v1.schemas import TopicCreatedPayload


_LOGGER = logging.getLogger(__name__)


class InternalApiCore(InternalApiQueryMixin):
    """Handle internal API commands and emit events."""

    _AUTHORIZATION = COMMAND_AUTHORIZATION

    def __init__(self, event_bus: EventBus) -> None:
        """Initialize the core with an event bus."""

        self._event_bus = event_bus
        self._nodes: Dict[str, NodeRecord] = {}
        self._topics: Dict[str, TopicRecord] = {}
        self._subscriptions: Set[Tuple[str, str]] = set()
        self._command_results: Dict[UUID, CommandResult] = {}
        self._node_stats: Dict[str, NodeStats] = {}
        self._topic_messages: Dict[str, Deque[float]] = {}
        self._blackholed: Set[str] = set()

    async def handle_command(self, command: CommandEnvelope) -> CommandResult:
        """Process a command and emit the corresponding event."""

        _LOGGER.info("Command received", extra=_command_log_context(command))
        cached = self._command_results.get(command.command_id)
        if cached is not None:
            _LOGGER.info("Command replayed", extra=_command_log_context(command))
            return cached

        if not self._is_authorized(command):
            _LOGGER.info(
                "Command rejected",
                extra={
                    **_command_log_context(command),
                    "reason": ErrorCode.UNAUTHORIZED_COMMAND.value,
                },
            )
            return self._cache_result(
                command,
                CommandStatus.REJECTED,
                ErrorCode.UNAUTHORIZED_COMMAND.value,
            )

        self._record_last_seen(self._node_id_for_seen(command))

        try:
            event = await self._apply_command(command)
        except CommandRejection as exc:
            _LOGGER.info(
                "Command rejected",
                extra={**_command_log_context(command), "reason": exc.error_code.value},
            )
            return self._cache_result(
                command,
                CommandStatus.REJECTED,
                exc.error_code.value,
            )

        await self._event_bus.publish(event)
        _LOGGER.info(
            "Event emitted",
            extra=_event_log_context(event, str(command.command_id)),
        )
        _LOGGER.info("Command accepted", extra=_command_log_context(command))
        return self._cache_result(command, CommandStatus.ACCEPTED, None)

    def _cache_result(
        self,
        command: CommandEnvelope,
        status: CommandStatus,
        reason: Optional[str],
    ) -> CommandResult:
        """Store and return a command result."""

        result = CommandResult(
            command_id=command.command_id,
            status=status,
            reason=reason,
        )
        self._command_results[command.command_id] = result
        return result

    def _is_authorized(self, command: CommandEnvelope) -> bool:
        """Return ``True`` when the issuer may run the command."""

        allowed = self._AUTHORIZATION.get(command.command_type, set())
        return command.issuer.type in allowed

    def _node_id_for_seen(self, command: CommandEnvelope) -> str:
        """Return the node identifier to update for last-seen."""

        if (
            command.command_type == CommandType.REGISTER_NODE
            and isinstance(command.payload, RegisterNodePayload)
        ):
            return command.payload.node_id
        return command.issuer.id

    def _record_last_seen(self, node_id: str) -> None:
        """Update node last-seen timestamps."""

        now = _epoch_now()
        stats = self._node_stats.get(node_id)
        if stats is None:
            stats = NodeStats(
                first_seen_ts=now,
                last_seen_ts=now,
                telemetry_timestamps=deque(),
                message_timestamps=deque(),
            )
            self._node_stats[node_id] = stats
        else:
            stats.last_seen_ts = now

    def touch_node(self, node_id: str) -> None:
        """Update last-seen timestamps without emitting events."""

        if node_id:
            self._record_last_seen(node_id)

    async def _apply_command(self, command: CommandEnvelope) -> EventEnvelope:
        """Apply command state changes and return the emitted event."""

        if command.command_type == CommandType.REGISTER_NODE:
            payload = command.payload
            if not isinstance(payload, RegisterNodePayload):
                raise CommandRejection(ErrorCode.UNAUTHORIZED_COMMAND)
            return self._register_node(payload)
        if command.command_type == CommandType.CREATE_TOPIC:
            payload = command.payload
            if not isinstance(payload, CreateTopicPayload):
                raise CommandRejection(ErrorCode.UNAUTHORIZED_COMMAND)
            return self._create_topic(payload)
        if command.command_type == CommandType.SUBSCRIBE_TOPIC:
            payload = command.payload
            if not isinstance(payload, SubscribeTopicPayload):
                raise CommandRejection(ErrorCode.UNAUTHORIZED_COMMAND)
            return self._subscribe_topic(payload)
        if command.command_type == CommandType.PUBLISH_MESSAGE:
            payload = command.payload
            if not isinstance(payload, PublishMessagePayload):
                raise CommandRejection(ErrorCode.UNAUTHORIZED_COMMAND)
            return self._publish_message(command, payload)

        raise CommandRejection(ErrorCode.UNAUTHORIZED_COMMAND)

    def _register_node(self, payload: RegisterNodePayload) -> EventEnvelope:
        """Register or update a node."""

        self._nodes[payload.node_id] = NodeRecord(
            node_id=payload.node_id,
            node_type=payload.node_type,
            metadata=payload.metadata,
        )
        event_payload = NodeRegisteredPayload(
            node_id=payload.node_id,
            node_type=payload.node_type,
        )
        return EventEnvelope(
            api_version=SUPPORTED_API_VERSION,
            event_id=uuid4(),
            event_type=EventType.NODE_REGISTERED,
            occurred_at=_utc_now(),
            origin="hub-core",
            payload=event_payload,
        )

    def _create_topic(self, payload: CreateTopicPayload) -> EventEnvelope:
        """Create or update a topic."""

        now = _epoch_now()
        self._topics[payload.topic_path] = TopicRecord(
            topic_path=payload.topic_path,
            retention=payload.retention,
            visibility=payload.visibility,
            created_ts=now,
            last_activity_ts=now,
        )
        self._topic_messages.setdefault(payload.topic_path, deque())
        event_payload = TopicCreatedPayload(topic_path=payload.topic_path)
        return EventEnvelope(
            api_version=SUPPORTED_API_VERSION,
            event_id=uuid4(),
            event_type=EventType.TOPIC_CREATED,
            occurred_at=_utc_now(),
            origin="hub-core",
            payload=event_payload,
        )

    def _subscribe_topic(self, payload: SubscribeTopicPayload) -> EventEnvelope:
        """Subscribe a destination to a topic."""

        if payload.topic_path not in self._topics:
            raise CommandRejection(ErrorCode.TOPIC_NOT_FOUND)
        self._subscriptions.add((payload.subscriber_id, payload.topic_path))
        event_payload = SubscriberUpdatedPayload(
            subscriber_id=payload.subscriber_id,
            topic_path=payload.topic_path,
            action=SubscriberAction.SUBSCRIBED,
        )
        return EventEnvelope(
            api_version=SUPPORTED_API_VERSION,
            event_id=uuid4(),
            event_type=EventType.SUBSCRIBER_UPDATED,
            occurred_at=_utc_now(),
            origin="hub-core",
            payload=event_payload,
        )

    def _publish_message(
        self, command: CommandEnvelope, payload: PublishMessagePayload
    ) -> EventEnvelope:
        """Publish a message to a topic."""

        if payload.topic_path not in self._topics:
            raise CommandRejection(ErrorCode.TOPIC_NOT_FOUND)
        now = _epoch_now()
        self._record_topic_message(payload.topic_path, now)
        self._record_node_message(command.issuer.id, payload, now)
        event_payload = MessagePublishedPayload(
            topic_path=payload.topic_path,
            message_id=command.command_id.hex,
            originator=command.issuer.id,
        )
        return EventEnvelope(
            api_version=SUPPORTED_API_VERSION,
            event_id=uuid4(),
            event_type=EventType.MESSAGE_PUBLISHED,
            occurred_at=_utc_now(),
            origin="hub-core",
            payload=event_payload,
        )

    def _record_topic_message(self, topic_path: str, now: float) -> None:
        """Update topic message activity."""

        stats = self._topics.get(topic_path)
        if stats is not None:
            stats.last_activity_ts = now
        timestamps = self._topic_messages.setdefault(topic_path, deque())
        timestamps.append(now)
        _prune_timestamps(timestamps, now)

    def _record_node_message(
        self, node_id: str, payload: PublishMessagePayload, now: float
    ) -> None:
        """Update node message activity and metrics."""

        stats = self._node_stats.get(node_id)
        if stats is None:
            stats = NodeStats(
                first_seen_ts=now,
                last_seen_ts=now,
                telemetry_timestamps=deque(),
                message_timestamps=deque(),
            )
            self._node_stats[node_id] = stats
        stats.last_seen_ts = now
        stats.message_timestamps.append(now)
        _prune_timestamps(stats.message_timestamps, now)

        if payload.message_type == MessageType.TELEMETRY:
            stats.telemetry_timestamps.append(now)
            _prune_timestamps(stats.telemetry_timestamps, now)
            self._update_metrics_from_telemetry(stats, payload)

    def _update_metrics_from_telemetry(
        self, stats: NodeStats, payload: PublishMessagePayload
    ) -> None:
        """Map telemetry metrics to node status metrics."""

        data = getattr(payload.content, "data", None)
        if not isinstance(data, dict):
            return
        if "battery" in data:
            stats.battery_pct = _coerce_metric_value(data.get("battery"), stats.battery_pct)
        if "battery_pct" in data:
            stats.battery_pct = _coerce_metric_value(data.get("battery_pct"), stats.battery_pct)
        if "rssi" in data:
            stats.signal_quality = _coerce_metric_value(data.get("rssi"), stats.signal_quality)
        if "snr" in data:
            stats.signal_quality = _coerce_metric_value(data.get("snr"), stats.signal_quality)

    async def handle_query(self, query: QueryEnvelope) -> QueryResult:
        """Process a query without mutating state or emitting events."""

        _LOGGER.info("Query received", extra=_query_log_context(query))
        if query.query_type == QueryType.GET_TOPICS:
            result = self._build_query_result(
                query, {"topics": self._get_topics_snapshot()}, scope="hub"
            )
            _LOGGER.info("Query completed", extra=_query_log_context(query))
            return result
        if query.query_type == QueryType.GET_SUBSCRIBERS:
            result = self._handle_get_subscribers(query)
            _LOGGER.info("Query completed", extra=_query_log_context(query))
            return result
        if query.query_type == QueryType.GET_NODE_STATUS:
            result = self._handle_get_node_status(query)
            _LOGGER.info("Query completed", extra=_query_log_context(query))
            return result
        result = self._build_query_error(
            query,
            ErrorCode.INVALID_QUERY,
            "Query type is not supported",
        )
        _LOGGER.info("Query completed", extra=_query_log_context(query))
        return result
