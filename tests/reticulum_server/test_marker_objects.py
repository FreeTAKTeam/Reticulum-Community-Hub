"""Tests for marker object manager error handling."""

from datetime import datetime
from datetime import timezone

from reticulum_telemetry_hub.api.models import Marker
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_enum import (
    SID_CUSTOM,
    SID_LOCATION,
    SID_TIME,
)
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog
from reticulum_telemetry_hub.reticulum_server.marker_objects import _is_marker_expired
from reticulum_telemetry_hub.reticulum_server.marker_objects import MarkerObjectManager


def _build_marker(**overrides: object) -> Marker:
    """Return a baseline marker with overridable fields."""

    defaults = {
        "local_id": "local-1",
        "object_destination_hash": None,
        "origin_rch": None,
        "object_identity_storage_key": None,
        "marker_type": "fire",
        "symbol": "fire",
        "name": "Test Marker",
        "category": "napsg",
        "lat": 1.0,
        "lon": 2.0,
        "notes": None,
    }
    defaults.update(overrides)
    return Marker(**defaults)


def test_announce_marker_skips_missing_identity() -> None:
    """Ensure marker announces skip when identity metadata is missing."""

    event_log = EventLog()
    manager = MarkerObjectManager(
        origin_rch_provider=lambda: "",
        event_log=event_log,
    )

    manager.announce_marker(_build_marker())

    events = event_log.list_events()
    assert any(event["type"] == "marker_announce_skipped" for event in events)


def test_dispatch_marker_skips_missing_identity() -> None:
    """Ensure marker telemetry skips when identity metadata is missing."""

    event_log = EventLog()
    manager = MarkerObjectManager(
        origin_rch_provider=lambda: "",
        event_log=event_log,
    )
    marker = _build_marker()

    result = manager.dispatch_marker_telemetry(marker, "marker.updated")

    assert result is False
    events = event_log.list_events()
    assert any(event["type"] == "marker_telemetry_failed" for event in events)


def test_marker_expiration_handles_naive_timestamp() -> None:
    """Ensure marker expiration compares naive timestamps safely."""

    marker = _build_marker(stale_at=datetime(2020, 1, 1))

    assert _is_marker_expired(marker, now=datetime(2020, 1, 2, tzinfo=timezone.utc))


def test_dispatch_marker_records_telemetry_payload() -> None:
    """Ensure marker telemetry is persisted in Sideband-compatible format."""

    recorded: list[tuple[dict[int, object], str]] = []

    def _record(payload: dict[int, object], peer_dest: str) -> None:
        recorded.append((payload, peer_dest))

    manager = MarkerObjectManager(
        origin_rch_provider=lambda: "origin",
        event_log=EventLog(),
        telemetry_recorder=_record,
    )
    marker = _build_marker(
        object_destination_hash="deadbeef",
        object_identity_storage_key="storage-key",
        origin_rch="origin",
    )

    result = manager.dispatch_marker_telemetry(marker, "marker.updated")

    assert result is True
    assert recorded
    payload, peer_dest = recorded[0]
    assert peer_dest == "deadbeef"
    assert SID_TIME in payload
    assert SID_LOCATION in payload
    assert SID_CUSTOM in payload
