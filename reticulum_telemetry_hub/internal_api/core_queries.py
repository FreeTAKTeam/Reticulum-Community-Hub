"""Internal API query handlers and snapshot builders."""

from __future__ import annotations

from collections import deque
from typing import Dict
from typing import Optional
from typing import Set

from reticulum_telemetry_hub.internal_api.core_state import CACHE_TTL_SECONDS
from reticulum_telemetry_hub.internal_api.core_state import NODE_ONLINE_THRESHOLD_SECONDS
from reticulum_telemetry_hub.internal_api.core_state import NODE_STALE_THRESHOLD_SECONDS
from reticulum_telemetry_hub.internal_api.core_state import epoch_now as _epoch_now
from reticulum_telemetry_hub.internal_api.core_state import rate_from_timestamps as _rate_from_timestamps
from reticulum_telemetry_hub.internal_api.v1.enums import ErrorCode
from reticulum_telemetry_hub.internal_api.v1.enums import Visibility
from reticulum_telemetry_hub.internal_api.v1.schemas import GetNodeStatusPayload
from reticulum_telemetry_hub.internal_api.v1.schemas import GetSubscribersPayload
from reticulum_telemetry_hub.internal_api.v1.schemas import QueryEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import QueryError
from reticulum_telemetry_hub.internal_api.v1.schemas import QueryResult
from reticulum_telemetry_hub.internal_api.v1.schemas import QueryResultPayload


class InternalApiQueryMixin:
    """Handle query payloads and build state snapshots."""

    def _handle_get_subscribers(self, query: QueryEnvelope) -> QueryResult:
        """Handle GetSubscribers queries."""

        payload = query.payload
        if not isinstance(payload, GetSubscribersPayload):
            return self._build_query_error(
                query,
                ErrorCode.INVALID_QUERY,
                "Invalid query payload",
            )
        topic_id = payload.topic_path
        if topic_id not in self._topics:
            return self._build_query_error(
                query,
                ErrorCode.TOPIC_NOT_FOUND,
                "Topic does not exist",
            )
        subscribers = self._get_subscribers_snapshot(topic_id)
        return self._build_query_result(
            query,
            {"topic_id": topic_id, "subscribers": subscribers},
            scope="hub",
        )

    def _handle_get_node_status(self, query: QueryEnvelope) -> QueryResult:
        """Handle GetNodeStatus queries."""

        payload = query.payload
        if not isinstance(payload, GetNodeStatusPayload):
            return self._build_query_error(
                query,
                ErrorCode.INVALID_QUERY,
                "Invalid query payload",
            )
        node_id = payload.node_id
        status = self._get_node_status_snapshot(node_id)
        return self._build_query_result(query, status, scope="node")

    def _build_query_result(
        self,
        query: QueryEnvelope,
        data: Dict[str, object],
        *,
        scope: str,
    ) -> QueryResult:
        """Build a successful query result with cache hints."""

        cache = {
            "ttl_seconds": CACHE_TTL_SECONDS,
            "scope": scope,
            "stale_while_revalidate": True,
        }
        payload = QueryResultPayload(data=data, _cache=cache)
        return QueryResult(
            query_id=query.query_id,
            ok=True,
            result=payload,
            error=None,
        )

    def _build_query_error(
        self, query: QueryEnvelope, code: ErrorCode, message: str
    ) -> QueryResult:
        """Build an error query result."""

        return QueryResult(
            query_id=query.query_id,
            ok=False,
            result=None,
            error=QueryError(code=code, message=message),
        )

    def _get_topics_snapshot(self) -> list[Dict[str, object]]:
        """Return topic summaries with live statistics."""

        now = _epoch_now()
        summaries: list[Dict[str, object]] = []
        for topic_path, topic in sorted(self._topics.items()):
            timestamps = self._topic_messages.get(topic_path, deque())
            message_rate = _rate_from_timestamps(timestamps, now)
            subscriber_count = sum(
                1 for subscriber, tpath in self._subscriptions if tpath == topic_path
            )
            visibility = "public"
            if topic.visibility == Visibility.RESTRICTED:
                visibility = "private"
            summaries.append(
                {
                    "topic_id": topic.topic_path,
                    "visibility": visibility,
                    "subscriber_count": subscriber_count,
                    "message_rate": message_rate,
                    "last_activity_ts": int(topic.last_activity_ts),
                    "created_ts": int(topic.created_ts),
                }
            )
        return summaries

    def _get_subscribers_snapshot(self, topic_id: str) -> list[Dict[str, object]]:
        """Return subscriber summaries for a topic."""

        summaries: list[Dict[str, object]] = []
        for subscriber_id, topic_path in sorted(self._subscriptions):
            if topic_path != topic_id:
                continue
            status = self._subscriber_status(subscriber_id)
            if status is None:
                continue
            stats = self._node_stats.get(subscriber_id)
            if stats is None:
                continue
            summaries.append(
                {
                    "node_id": subscriber_id,
                    "first_seen_ts": int(stats.first_seen_ts),
                    "last_seen_ts": int(stats.last_seen_ts),
                    "status": status,
                }
            )
        return summaries

    def get_subscriber_ids(self, topic_id: str) -> Set[str]:
        """Return subscriber IDs for a topic without status filtering."""

        return {
            subscriber_id
            for subscriber_id, topic_path in self._subscriptions
            if topic_path == topic_id
        }

    def _get_node_status_snapshot(self, node_id: str) -> Dict[str, object]:
        """Return a node status snapshot."""

        stats = self._node_stats.get(node_id)
        if stats is None:
            return {
                "node_id": node_id,
                "status": "unknown",
                "topics": [],
                "last_seen_ts": None,
                "metrics": {},
            }
        status = self._node_status(node_id)
        topics = sorted(
            topic_path
            for subscriber_id, topic_path in self._subscriptions
            if subscriber_id == node_id
        )
        metrics: Dict[str, object] = {}
        telemetry_rate = _rate_from_timestamps(stats.telemetry_timestamps, _epoch_now())
        if telemetry_rate > 0:
            metrics["telemetry_rate"] = telemetry_rate
        lxmf_rate = _rate_from_timestamps(stats.message_timestamps, _epoch_now())
        if lxmf_rate > 0:
            metrics["lxmf_rate"] = lxmf_rate
        if stats.battery_pct is not None:
            metrics["battery_pct"] = stats.battery_pct
        if stats.signal_quality is not None:
            metrics["signal_quality"] = stats.signal_quality

        return {
            "node_id": node_id,
            "status": status,
            "topics": topics,
            "last_seen_ts": int(stats.last_seen_ts),
            "metrics": metrics,
        }

    def _node_status(self, node_id: str) -> str:
        """Return the node status string."""

        if node_id in self._blackholed:
            return "blackholed"
        stats = self._node_stats.get(node_id)
        if stats is None:
            return "unknown"
        age = _epoch_now() - stats.last_seen_ts
        if age <= NODE_ONLINE_THRESHOLD_SECONDS:
            return "online"
        if age <= NODE_STALE_THRESHOLD_SECONDS:
            return "stale"
        return "offline"

    def _subscriber_status(self, node_id: str) -> Optional[str]:
        """Return subscriber status or None when inactive."""

        status = self._node_status(node_id)
        if status == "blackholed":
            return "blackholed"
        if status == "online":
            return "active"
        if status == "stale":
            return "stale"
        return None
