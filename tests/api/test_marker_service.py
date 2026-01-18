from reticulum_telemetry_hub.api.marker_service import MarkerService
from reticulum_telemetry_hub.api.marker_storage import MarkerStorage


def test_marker_service_creates_defaults(tmp_path):
    storage = MarkerStorage(tmp_path / "hub.sqlite")
    service = MarkerService(storage)

    marker = service.create_marker(name=None, category="fire", lat=1.0, lon=2.0)

    assert marker.marker_type == "napsg"
    assert marker.name.startswith("fire+")
    assert marker.category == "fire"


def test_marker_service_rejects_unknown_category(tmp_path):
    storage = MarkerStorage(tmp_path / "hub.sqlite")
    service = MarkerService(storage)

    try:
        service.create_marker(name="test", category="unknown", lat=0.0, lon=0.0)
    except ValueError as exc:
        assert "Unsupported marker category" in str(exc)
    else:
        assert False, "Expected ValueError"


def test_marker_service_idempotent_update(tmp_path):
    storage = MarkerStorage(tmp_path / "hub.sqlite")
    service = MarkerService(storage)
    marker = service.create_marker(name="alpha", category="fire", lat=1.0, lon=2.0)

    result = service.update_marker_position(marker.marker_id, lat=1.0, lon=2.0)

    assert result.changed is False
    assert result.marker.marker_id == marker.marker_id


def test_marker_service_updates_position(tmp_path):
    storage = MarkerStorage(tmp_path / "hub.sqlite")
    service = MarkerService(storage)
    marker = service.create_marker(name="alpha", category="fire", lat=1.0, lon=2.0)

    result = service.update_marker_position(marker.marker_id, lat=3.0, lon=4.0)

    assert result.changed is True
    assert result.marker.lat == 3.0
    assert result.marker.lon == 4.0
