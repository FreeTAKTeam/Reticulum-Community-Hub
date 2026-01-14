"""Tests for shared event log behavior."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from reticulum_telemetry_hub.reticulum_server.event_log import EventLog


def _write_entry(path: Path, entry: dict) -> None:
    """Append a JSON entry to the shared log."""

    payload = json.dumps(entry, ensure_ascii=True, default=str)
    path.write_text(payload + "\n", encoding="utf-8")


def test_event_log_serializes_metadata_bytes(tmp_path: Path) -> None:
    """Ensure metadata bytes are converted to hex strings."""

    event_path = tmp_path / "events.jsonl"
    event_log = EventLog(event_path=event_path)

    event_log.add_event(
        "message_received",
        "Message received",
        metadata={"raw": b"\x01\xff"},
    )

    entries = event_log.list_events()

    assert entries[0]["metadata"] == {"raw": "01ff"}


def test_event_log_tails_new_entries(tmp_path: Path) -> None:
    """Ensure tailer picks up new entries written by other processes."""

    event_path = tmp_path / "events.jsonl"
    initial = {
        "id": "init-1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "seeded",
        "message": "Seeded event",
        "metadata": {},
        "origin": "external",
    }
    _write_entry(event_path, initial)

    event_log = EventLog(event_path=event_path, tail=True, tail_interval=0.05)
    received: list[dict] = []

    def _listener(entry: dict) -> None:
        received.append(entry)

    event_log.add_listener(_listener)

    follow_up = {
        "id": "follow-1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "follow_up",
        "message": "Follow up",
        "metadata": {"value": 1},
        "origin": "external",
    }
    with event_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(follow_up, ensure_ascii=True) + "\n")

    deadline = time.time() + 2.0
    while time.time() < deadline:
        if received:
            break
        time.sleep(0.05)

    event_log.close()

    assert received
    assert received[0]["id"] == "follow-1"


def test_event_log_deduplicates_by_id(tmp_path: Path) -> None:
    """Ensure duplicate IDs are ignored when tailing."""

    event_path = tmp_path / "events.jsonl"
    entry = {
        "id": "dup-1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "duplicate",
        "message": "Dup",
        "metadata": {},
        "origin": "external",
    }

    with event_path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
        handle.write(json.dumps(entry, ensure_ascii=True) + "\n")

    event_log = EventLog(event_path=event_path, tail=True, tail_interval=0.05)
    deadline = time.time() + 1.0
    while time.time() < deadline:
        if event_log.list_events():
            break
        time.sleep(0.05)

    event_log.close()

    entries = event_log.list_events()
    assert len(entries) == 1
