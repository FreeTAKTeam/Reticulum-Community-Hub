"""Event log helpers for Reticulum Telemetry Hub runtime."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional


def _utcnow() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc)


class EventLog:
    """In-memory event buffer for dashboard activity."""

    def __init__(self, max_entries: int = 200) -> None:
        """Initialize the event log with a fixed-size buffer.

        Args:
            max_entries (int): Maximum number of events to retain.
        """

        self._events: Deque[Dict[str, object]] = deque(maxlen=max_entries)

    def add_event(
        self,
        event_type: str,
        message: str,
        *,
        metadata: Optional[Dict[str, object]] = None,
    ) -> Dict[str, object]:
        """Append an event entry and return the stored representation.

        Args:
            event_type (str): Short category label for the event.
            message (str): Human readable description of the event.
            metadata (Optional[Dict[str, object]]): Optional structured details.

        Returns:
            Dict[str, object]: The recorded event entry.
        """

        entry = {
            "timestamp": _utcnow().isoformat(),
            "type": event_type,
            "message": message,
            "metadata": metadata or {},
        }
        self._events.append(entry)
        return entry

    def list_events(self, limit: int | None = None) -> List[Dict[str, object]]:
        """Return the most recent events, newest first.

        Args:
            limit (int | None): Maximum number of events to return.

        Returns:
            List[Dict[str, object]]: Event entries in reverse chronological order.
        """

        entries = list(self._events)
        if limit is None:
            return list(reversed(entries))
        return list(reversed(entries[-limit:]))
