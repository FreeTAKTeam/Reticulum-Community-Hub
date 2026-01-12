"""Tests for telemetry entry listing."""

from datetime import datetime
from datetime import timezone
from pathlib import Path

import pytest

from reticulum_telemetry_hub.api.models import Subscriber
from reticulum_telemetry_hub.api.models import Topic
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.api.storage import HubStorage
from reticulum_telemetry_hub.config import HubConfigurationManager
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_enum import (
    SID_TIME,
)
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)


def _build_api(tmp_path: Path) -> ReticulumTelemetryHubAPI:
    """Create an API instance backed by a temp database.

    Args:
        tmp_path (Path): Temporary directory for storage.

    Returns:
        ReticulumTelemetryHubAPI: Configured API service.
    """

    config_manager = HubConfigurationManager(storage_path=tmp_path)
    storage = HubStorage(tmp_path / "hub.sqlite")
    return ReticulumTelemetryHubAPI(config_manager=config_manager, storage=storage)


def test_list_telemetry_entries_returns_latest(tmp_path) -> None:
    """Ensure telemetry entries are returned for recent data."""

    api = _build_api(tmp_path)
    controller = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)
    now = datetime.now(timezone.utc)
    payload = {SID_TIME: int(now.timestamp())}
    controller.save_telemetry(payload, "peer-1", timestamp=now)

    entries = controller.list_telemetry_entries(since=int(now.timestamp()) - 10)

    assert len(entries) == 1
    assert entries[0]["peer_destination"] == "peer-1"


def test_list_telemetry_entries_filters_by_topic(tmp_path) -> None:
    """Ensure telemetry entries respect topic filtering."""

    api = _build_api(tmp_path)
    controller = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)
    topic = api.create_topic(Topic(topic_name="Topic", topic_path="/topic"))
    api.create_subscriber(Subscriber(destination="peer-1", topic_id=topic.topic_id))

    now = datetime.now(timezone.utc)
    payload = {SID_TIME: int(now.timestamp())}
    controller.save_telemetry(payload, "peer-1", timestamp=now)
    controller.save_telemetry(payload, "peer-2", timestamp=now)

    entries = controller.list_telemetry_entries(
        since=int(now.timestamp()) - 10,
        topic_id=topic.topic_id,
    )

    assert len(entries) == 1
    assert entries[0]["peer_destination"] == "peer-1"


def test_list_telemetry_entries_unknown_topic(tmp_path) -> None:
    """Ensure missing topics raise errors."""

    api = _build_api(tmp_path)
    controller = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)

    with pytest.raises(KeyError):
        controller.list_telemetry_entries(since=0, topic_id="missing")
