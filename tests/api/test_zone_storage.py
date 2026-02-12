from datetime import datetime
from datetime import timezone

from reticulum_telemetry_hub.api.models import Zone
from reticulum_telemetry_hub.api.models import ZonePoint
from reticulum_telemetry_hub.api.zone_storage import ZoneStorage


def _zone_points() -> list[ZonePoint]:
    return [
        ZonePoint(lat=37.0, lon=-122.0),
        ZonePoint(lat=37.1, lon=-122.0),
        ZonePoint(lat=37.1, lon=-121.9),
    ]


def test_zone_storage_crud(tmp_path):
    storage = ZoneStorage(tmp_path / "hub.sqlite")
    now = datetime.now(timezone.utc)
    zone = Zone(
        zone_id="zone-1",
        name="Alpha Zone",
        points=_zone_points(),
        created_at=now,
        updated_at=now,
    )

    created = storage.create_zone(zone)
    assert created.zone_id == "zone-1"
    assert created.name == "Alpha Zone"
    assert len(created.points) == 3

    fetched = storage.get_zone("zone-1")
    assert fetched is not None
    assert fetched.name == "Alpha Zone"

    listed = storage.list_zones()
    assert len(listed) == 1

    updated = storage.update_zone(
        "zone-1",
        name="Bravo Zone",
        points=[
            ZonePoint(lat=37.0, lon=-122.0),
            ZonePoint(lat=37.2, lon=-122.0),
            ZonePoint(lat=37.2, lon=-121.8),
        ],
        updated_at=now,
    )
    assert updated is not None
    assert updated.name == "Bravo Zone"
    assert updated.points[1].lat == 37.2

    deleted = storage.delete_zone("zone-1")
    assert deleted is not None
    assert deleted.zone_id == "zone-1"
    assert storage.get_zone("zone-1") is None


def test_zone_storage_missing_returns_none(tmp_path):
    storage = ZoneStorage(tmp_path / "hub.sqlite")

    assert storage.get_zone("missing") is None
    assert storage.update_zone("missing", name="Nope") is None
    assert storage.delete_zone("missing") is None
