"""Outbound delivery policy helpers for direct-vs-propagated routing."""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone
import threading
from typing import Any

from reticulum_telemetry_hub.message_delivery import normalize_hash

RECENT_ANNOUNCE_WINDOW = timedelta(hours=1)
RECENT_RUNTIME_PRESENCE_WINDOW = timedelta(hours=1)


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


def _ensure_aware(value: datetime | None) -> datetime | None:
    """Return ``value`` as a timezone-aware UTC timestamp when present."""

    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class OutboundDeliveryPolicy:
    """Track fresh presence evidence and direct-delivery cooldowns."""

    def __init__(self, hub: Any) -> None:
        self._hub = hub
        self._presence_observed_at: dict[str, datetime] = {}
        self._direct_failure_cooldowns: dict[str, datetime] = {}
        self._lock = threading.Lock()

    def mark_presence(self, identity: str | None, *, observed_at: datetime | None = None) -> None:
        """Record fresh presence evidence for ``identity`` and clear stale cooldowns."""

        normalized_identity = normalize_hash(identity)
        if not normalized_identity:
            return
        observed = _ensure_aware(observed_at) or _utcnow()
        with self._lock:
            current = self._presence_observed_at.get(normalized_identity)
            if current is None or observed > current:
                self._presence_observed_at[normalized_identity] = observed
            cooldown_started_at = self._direct_failure_cooldowns.get(normalized_identity)
            if cooldown_started_at is not None and observed > cooldown_started_at:
                self._direct_failure_cooldowns.pop(normalized_identity, None)

    def mark_direct_failure(self, identity: str | None, *, failed_at: datetime | None = None) -> None:
        """Start or refresh a direct-delivery cooldown for ``identity``."""

        normalized_identity = normalize_hash(identity)
        if not normalized_identity:
            return
        failed = _ensure_aware(failed_at) or _utcnow()
        with self._lock:
            current = self._direct_failure_cooldowns.get(normalized_identity)
            if current is None or failed > current:
                self._direct_failure_cooldowns[normalized_identity] = failed

    def delivery_decision(self, route_type: str, identity: str | None) -> tuple[str, str]:
        """Return the delivery mode and policy reason for one outbound payload."""

        normalized_identity = normalize_hash(identity)
        if route_type == "broadcast":
            return "propagated", "broadcast_route"
        if route_type == "fanout":
            return "propagated", "fanout_route"
        if not normalized_identity:
            return "propagated", "missing_identity"

        latest_presence = self._latest_presence_evidence(normalized_identity)
        if latest_presence is None:
            return "propagated", "no_fresh_presence"

        with self._lock:
            cooldown_started_at = self._direct_failure_cooldowns.get(normalized_identity)
        if cooldown_started_at is not None and latest_presence <= cooldown_started_at:
            return "propagated", "direct_cooldown"

        if cooldown_started_at is not None:
            with self._lock:
                current = self._direct_failure_cooldowns.get(normalized_identity)
                if current is not None and current <= latest_presence:
                    self._direct_failure_cooldowns.pop(normalized_identity, None)
        return "direct", "fresh_presence"

    def _latest_presence_evidence(self, identity: str) -> datetime | None:
        """Return the freshest direct-delivery evidence currently available."""

        now = _utcnow()
        runtime_presence = self._runtime_presence(identity, now)

        api = getattr(self._hub, "api", None)
        announce_presence = None
        if api is not None and hasattr(api, "resolve_identity_announce_last_seen"):
            try:
                announce_presence = api.resolve_identity_announce_last_seen(identity)
            except Exception:
                announce_presence = None
        announce_presence = _ensure_aware(announce_presence)
        if announce_presence is not None and announce_presence < now - RECENT_ANNOUNCE_WINDOW:
            announce_presence = None

        if runtime_presence is None:
            return announce_presence
        if announce_presence is None:
            return runtime_presence
        return max(runtime_presence, announce_presence)

    def _runtime_presence(self, identity: str, now: datetime) -> datetime | None:
        """Return recent runtime presence evidence and evict stale observations."""

        with self._lock:
            runtime_presence = self._presence_observed_at.get(identity)
            if runtime_presence is None:
                return None
            if runtime_presence < now - RECENT_RUNTIME_PRESENCE_WINDOW:
                self._presence_observed_at.pop(identity, None)
                return None
            return runtime_presence
