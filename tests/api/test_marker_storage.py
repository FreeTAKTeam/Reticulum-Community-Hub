from datetime import datetime
from datetime import timezone

from reticulum_telemetry_hub.api.marker_storage import MarkerStorage
from reticulum_telemetry_hub.api.models import Marker


def test_marker_storage_crud(tmp_path):
    storage = MarkerStorage(tmp_path / "hub.sqlite")
    now = datetime.now(timezone.utc)
    marker = Marker(
        marker_id="marker-1",
        marker_type="napsg",
        name="fire+demo",
        category="fire",
        notes=None,
        lat=1.0,
        lon=2.0,
        created_at=now,
        updated_at=now,
    )

    created = storage.create_marker(marker)

    assert created.marker_id == "marker-1"
    assert created.marker_type == "napsg"

    fetched = storage.get_marker("marker-1")
    assert fetched is not None
    assert fetched.name == "fire+demo"

    listed = storage.list_markers()
    assert len(listed) == 1

    updated = storage.update_marker_position("marker-1", lat=5.5, lon=-4.2, updated_at=now)
    assert updated is not None
    assert updated.lat == 5.5
    assert updated.lon == -4.2


def test_marker_storage_missing_returns_none(tmp_path):
    storage = MarkerStorage(tmp_path / "hub.sqlite")

    assert storage.get_marker("missing") is None
    assert storage.update_marker_position("missing", lat=0.0, lon=0.0) is None
