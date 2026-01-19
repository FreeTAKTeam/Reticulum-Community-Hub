import pytest

from reticulum_telemetry_hub.api.marker_service import MarkerService
from reticulum_telemetry_hub.api.marker_storage import MarkerStorage


def _marker_key() -> str:
    return "11" * 32


def test_marker_service_creates_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("RTH_MARKER_IDENTITY_KEY", _marker_key())
    storage = MarkerStorage(tmp_path / "hub.sqlite")
    service = MarkerService(storage)

    marker = service.create_marker(
        name=None,
        marker_type="fire",
        symbol="fire",
        category="napsg",
        lat=1.0,
        lon=2.0,
        origin_rch="origin",
    )

    assert marker.marker_type == "fire"
    assert marker.symbol == "fire"
    assert marker.name.startswith("fire+")
    assert marker.category == "napsg"
    assert marker.object_destination_hash
    assert marker.object_identity_storage_key
    assert marker.time < marker.stale_at


def test_marker_service_rejects_unknown_type(tmp_path, monkeypatch):
    monkeypatch.setenv("RTH_MARKER_IDENTITY_KEY", _marker_key())
    storage = MarkerStorage(tmp_path / "hub.sqlite")
    service = MarkerService(storage)

    with pytest.raises(ValueError, match="Unsupported marker type"):
        service.create_marker(
            name="test",
            marker_type="unknown",
            symbol="fire",
            category="napsg",
            lat=0.0,
            lon=0.0,
            origin_rch="origin",
        )


def test_marker_service_rejects_unknown_symbol(tmp_path, monkeypatch):
    monkeypatch.setenv("RTH_MARKER_IDENTITY_KEY", _marker_key())
    storage = MarkerStorage(tmp_path / "hub.sqlite")
    service = MarkerService(storage)

    with pytest.raises(ValueError, match="Unsupported marker symbol"):
        service.create_marker(
            name="test",
            marker_type="fire",
            symbol="unknown",
            category="napsg",
            lat=0.0,
            lon=0.0,
            origin_rch="origin",
        )


def test_marker_service_idempotent_update(tmp_path, monkeypatch):
    monkeypatch.setenv("RTH_MARKER_IDENTITY_KEY", _marker_key())
    storage = MarkerStorage(tmp_path / "hub.sqlite")
    service = MarkerService(storage)
    marker = service.create_marker(
        name="alpha",
        marker_type="fire",
        symbol="fire",
        category="napsg",
        lat=1.0,
        lon=2.0,
        origin_rch="origin",
    )

    result = service.update_marker_position(
        marker.object_destination_hash or "",
        lat=1.0,
        lon=2.0,
    )

    assert result.changed is False
    assert result.marker.object_destination_hash == marker.object_destination_hash


def test_marker_service_updates_position(tmp_path, monkeypatch):
    monkeypatch.setenv("RTH_MARKER_IDENTITY_KEY", _marker_key())
    storage = MarkerStorage(tmp_path / "hub.sqlite")
    service = MarkerService(storage)
    marker = service.create_marker(
        name="alpha",
        marker_type="fire",
        symbol="fire",
        category="napsg",
        lat=1.0,
        lon=2.0,
        origin_rch="origin",
    )

    result = service.update_marker_position(
        marker.object_destination_hash or "",
        lat=3.0,
        lon=4.0,
    )

    assert result.changed is True
    assert result.marker.lat == 3.0
    assert result.marker.lon == 4.0


def test_marker_service_handles_naive_timestamps(tmp_path, monkeypatch):
    monkeypatch.setenv("RTH_MARKER_IDENTITY_KEY", _marker_key())
    storage = MarkerStorage(tmp_path / "hub.sqlite")
    service = MarkerService(storage)
    marker = service.create_marker(
        name="alpha",
        marker_type="fire",
        symbol="fire",
        category="napsg",
        lat=1.0,
        lon=2.0,
        origin_rch="origin",
    )
    naive_time = marker.time.replace(tzinfo=None)
    naive_stale = marker.stale_at.replace(tzinfo=None)
    storage.update_marker_position(
        marker.object_destination_hash or "",
        lat=marker.lat,
        lon=marker.lon,
        time=naive_time,
        stale_at=naive_stale,
    )

    result = service.update_marker_position(
        marker.object_destination_hash or "",
        lat=marker.lat,
        lon=marker.lon,
    )

    assert result.marker.object_destination_hash == marker.object_destination_hash
