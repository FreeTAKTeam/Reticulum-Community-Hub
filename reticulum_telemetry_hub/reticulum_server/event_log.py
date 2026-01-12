"""Event log helpers for Reticulum Telemetry Hub runtime."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Callable
from typing import Deque
from typing import Dict
from typing import List
from typing import Optional


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
        self._listeners: List[Callable[[Dict[str, object]], None]] = []

    def add_listener(
        self, listener: Callable[[Dict[str, object]], None]
    ) -> Callable[[], None]:
        """Register an event listener.

        Args:
            listener (Callable[[Dict[str, object]], None]): Callback invoked
                with newly recorded events.

        Returns:
            Callable[[], None]: Callback that unregisters the listener.
        """

        self._listeners.append(listener)

        def _remove_listener() -> None:
            """Remove the registered listener.

            Returns:
                None: Removes the listener if registered.
            """

            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove_listener

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
        for listener in list(self._listeners):
            try:
                listener(entry)
            except Exception:  # pragma: no cover - defensive logging
                # Reason: event listeners should never break event recording.
                continue
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
