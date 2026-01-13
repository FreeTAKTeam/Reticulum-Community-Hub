"""Event log helpers for Reticulum Telemetry Hub runtime."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import threading
import time
import uuid
from typing import Callable
from typing import Deque
from typing import Dict
from typing import List
from typing import Optional


DEFAULT_EVENT_LOG_FILENAME = "events.jsonl"
DEFAULT_TAIL_INTERVAL_SECONDS = 0.5


def resolve_event_log_path(storage_path: Path | str) -> Path:
    """Return the default event log file path for a storage directory."""

    return Path(storage_path) / DEFAULT_EVENT_LOG_FILENAME


def _utcnow() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc)


class EventLog:
    """Event buffer with optional shared-file persistence."""

    def __init__(
        self,
        max_entries: int = 200,
        *,
        event_path: Path | str | None = None,
        tail: bool = False,
        tail_interval: float = DEFAULT_TAIL_INTERVAL_SECONDS,
    ) -> None:
        """Initialize the event log with a fixed-size buffer.

        Args:
            max_entries (int): Maximum number of events to retain.
            event_path (Path | str | None): Optional path for shared event storage.
            tail (bool): When True, tail the shared log file for new entries.
            tail_interval (float): Seconds between tail polling attempts.
        """

        self._events: Deque[Dict[str, object]] = deque(maxlen=max_entries)
        self._listeners: List[Callable[[Dict[str, object]], None]] = []
        self._lock = threading.Lock()
        self._origin_id = uuid.uuid4().hex
        self._event_path = Path(event_path) if event_path else None
        self._tail_interval = max(tail_interval, 0.05)
        self._seen_limit = max(max_entries * 4, 200)
        self._seen_queue: Deque[str] = deque()
        self._seen_lookup: set[str] = set()
        self._tail_stop = threading.Event()
        self._tail_thread: threading.Thread | None = None
        self._tail_offset = 0

        if self._event_path:
            self._event_path.parent.mkdir(parents=True, exist_ok=True)
            self._event_path.touch(exist_ok=True)
            self._tail_offset = self._load_existing_events()
            if tail:
                self._start_tailer()

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

        with self._lock:
            self._listeners.append(listener)

        def _remove_listener() -> None:
            """Remove the registered listener.

            Returns:
                None: Removes the listener if registered.
            """

            with self._lock:
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
            "id": uuid.uuid4().hex,
            "timestamp": _utcnow().isoformat(),
            "type": event_type,
            "message": message,
            "metadata": metadata or {},
            "origin": self._origin_id,
        }
        self._ingest_entry(entry, notify=True, allow_origin=True)
        self._write_entry(entry)
        return entry

    def list_events(self, limit: int | None = None) -> List[Dict[str, object]]:
        """Return the most recent events, newest first.

        Args:
            limit (int | None): Maximum number of events to return.

        Returns:
            List[Dict[str, object]]: Event entries in reverse chronological order.
        """

        with self._lock:
            entries = [self._normalize_entry(entry) for entry in self._events]
        if limit is None:
            return list(reversed(entries))
        return list(reversed(entries[-limit:]))

    def close(self) -> None:
        """Stop the tailer thread when enabled."""

        self._tail_stop.set()
        if self._tail_thread is not None:
            self._tail_thread.join(timeout=1.0)
            self._tail_thread = None

    def _write_entry(self, entry: Dict[str, object]) -> None:
        """Append an entry to the shared event log file when configured."""

        if not self._event_path:
            return
        try:
            payload = json.dumps(entry, ensure_ascii=True, default=str)
            with self._event_path.open("a", encoding="utf-8") as handle:
                handle.write(payload + "\n")
        except (OSError, TypeError, ValueError):
            # Reason: event logging should never break event recording.
            return

    def _load_existing_events(self) -> int:
        """Load existing events from the shared log file."""

        if not self._event_path or not self._event_path.exists():
            return 0
        offset = 0
        try:
            with self._event_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    self._ingest_line(line, notify=False, allow_origin=True)
                offset = handle.tell()
        except OSError:
            return 0
        return offset

    def _start_tailer(self) -> None:
        """Start a background thread that tails the shared log file."""

        if self._tail_thread is not None or not self._event_path:
            return
        self._tail_thread = threading.Thread(target=self._tail_loop, daemon=True)
        self._tail_thread.start()

    def _tail_loop(self) -> None:
        """Continuously tail the shared log file for new entries."""

        if not self._event_path:
            return
        try:
            with self._event_path.open("r", encoding="utf-8") as handle:
                handle.seek(self._tail_offset)
                while not self._tail_stop.is_set():
                    line = handle.readline()
                    if not line:
                        time.sleep(self._tail_interval)
                        continue
                    self._ingest_line(line, notify=True, allow_origin=False)
        except OSError:
            return

    def _ingest_line(
        self, line: str, *, notify: bool, allow_origin: bool
    ) -> None:
        """Parse and record a raw JSON line."""

        payload = line.strip()
        if not payload:
            return
        try:
            entry = json.loads(payload)
        except json.JSONDecodeError:
            return
        if not isinstance(entry, dict):
            return
        entry_id = entry.get("id")
        if not isinstance(entry_id, str):
            entry_id = self._hash_payload(payload)
            entry["id"] = entry_id
        self._ingest_entry(entry, notify=notify, allow_origin=allow_origin)

    def _hash_payload(self, payload: str) -> str:
        """Return a stable hash for a raw payload string."""

        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    def _ingest_entry(
        self,
        entry: Dict[str, object],
        *,
        notify: bool,
        allow_origin: bool,
    ) -> None:
        """Append a parsed entry to the buffer and notify listeners."""

        normalized = self._normalize_entry(entry)
        entry_id = normalized.get("id")
        if not isinstance(entry_id, str):
            entry_id = uuid.uuid4().hex
            normalized["id"] = entry_id
        if not allow_origin and normalized.get("origin") == self._origin_id:
            return
        if self._is_duplicate(entry_id):
            return
        self._remember_id(entry_id)
        with self._lock:
            self._events.append(normalized)
            listeners = list(self._listeners)
        if notify:
            for listener in listeners:
                try:
                    listener(normalized)
                except Exception:  # pragma: no cover - defensive logging
                    # Reason: event listeners should never break event recording.
                    continue

    def _is_duplicate(self, entry_id: str) -> bool:
        """Return True when the entry ID has already been processed."""

        return entry_id in self._seen_lookup

    def _remember_id(self, entry_id: str) -> None:
        """Track the entry ID to avoid duplicate processing."""

        if entry_id in self._seen_lookup:
            return
        if len(self._seen_queue) >= self._seen_limit:
            oldest = self._seen_queue.popleft()
            self._seen_lookup.discard(oldest)
        self._seen_queue.append(entry_id)
        self._seen_lookup.add(entry_id)

    def _normalize_entry(self, entry: Dict[str, object]) -> Dict[str, object]:
        """Return a JSON-safe event entry."""

        normalized: Dict[str, object] = {}
        for key, value in entry.items():
            if key == "metadata":
                continue
            safe_key = self._json_safe_key(key)
            if key == "id":
                normalized["id"] = self._coerce_id(value)
            elif key == "type":
                normalized["type"] = "" if value is None else str(value)
            elif key == "message":
                normalized["message"] = "" if value is None else str(value)
            elif key == "timestamp":
                normalized["timestamp"] = self._json_safe_value(value)
            elif key == "origin":
                normalized["origin"] = self._json_safe_value(value)
            else:
                normalized[safe_key] = self._json_safe_value(value)

        if "id" not in normalized:
            normalized["id"] = uuid.uuid4().hex
        if "type" not in normalized:
            normalized["type"] = ""
        if "message" not in normalized:
            normalized["message"] = ""
        if "timestamp" not in normalized:
            normalized["timestamp"] = _utcnow().isoformat()
        if "origin" not in normalized:
            normalized["origin"] = None

        metadata = entry.get("metadata")
        if metadata is None:
            normalized["metadata"] = {}
        elif isinstance(metadata, dict):
            normalized["metadata"] = self._json_safe_value(metadata)
        else:
            normalized["metadata"] = {"value": self._json_safe_value(metadata)}
        return normalized

    def _coerce_id(self, value: object) -> str:
        """Return a safe string ID."""

        if isinstance(value, (bytes, bytearray, memoryview)):
            return bytes(value).hex()
        if value is None:
            return uuid.uuid4().hex
        return str(value)

    def _json_safe_key(self, key: object) -> str:
        """Return a JSON-safe dictionary key."""

        if isinstance(key, (bytes, bytearray, memoryview)):
            return bytes(key).hex()
        if key is None:
            return "null"
        return str(key)

    def _json_safe_value(self, value: object) -> object:
        """Return a JSON-safe value."""

        if isinstance(value, dict):
            return {self._json_safe_key(k): self._json_safe_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._json_safe_value(item) for item in value]
        if isinstance(value, (bytes, bytearray, memoryview)):
            return bytes(value).hex()
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)
