"""Extended tests for northbound services."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from reticulum_telemetry_hub.api.models import Subscriber
from reticulum_telemetry_hub.api.models import Topic
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.api.storage import HubStorage
from reticulum_telemetry_hub.config.manager import HubConfigurationManager
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_enum import (
    SID_LOCATION,
    SID_TIME,
)
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.northbound.services import NorthboundServices
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog
from tests.factories import build_location_payload


def _build_services(
    tmp_path: Path,
    *,
    message_dispatcher=None,
    routing_provider=None,
) -> tuple[NorthboundServices, ReticulumTelemetryHubAPI, TelemetryController, EventLog]:
    config_manager = HubConfigurationManager(storage_path=tmp_path)
    storage = HubStorage(tmp_path / "hub.sqlite")
    api = ReticulumTelemetryHubAPI(config_manager=config_manager, storage=storage)
    event_log = EventLog()
    telemetry = TelemetryController(
        db_path=tmp_path / "telemetry.db",
        api=api,
        event_log=event_log,
    )
    services = NorthboundServices(
        api=api,
        telemetry=telemetry,
        event_log=event_log,
        started_at=datetime.now(timezone.utc),
        message_dispatcher=message_dispatcher,
        routing_provider=routing_provider,
    )
    return services, api, telemetry, event_log


def test_help_and_examples_fallback(tmp_path: Path) -> None:
    services, _, _, _ = _build_services(tmp_path)

    help_text = services.help_text()
    examples = services.examples_text()

    assert "Command" in help_text
    assert "Command" in examples


def test_status_snapshot_counts(tmp_path: Path) -> None:
    services, api, telemetry, _ = _build_services(tmp_path)
    topic = api.create_topic(Topic(topic_name="alerts", topic_path="alerts"))
    api.create_subscriber(Subscriber(destination="dest-1", topic_id=topic.topic_id))

    file_path = api._config_manager.config.file_storage_path / "note.txt"  # pylint: disable=protected-access
    file_path.write_text("payload", encoding="utf-8")
    api.store_file(file_path, media_type="text/plain")
    image_path = api._config_manager.config.image_storage_path / "photo.jpg"  # pylint: disable=protected-access
    image_path.write_bytes(b"img")
    api.store_image(image_path, media_type="image/jpeg")

    now = datetime.now(timezone.utc)
    telemetry.save_telemetry(
        {
            SID_TIME: int(now.timestamp()),
            SID_LOCATION: build_location_payload(int(now.timestamp())),
        },
        "dest-1",
        timestamp=now,
    )

    snapshot = services.status_snapshot()

    assert snapshot["topics"] == 1
    assert snapshot["subscribers"] == 1
    assert snapshot["files"] == 1
    assert snapshot["images"] == 1
    assert snapshot["telemetry"]["ingest_count"] == 1


def test_record_event_and_list_events(tmp_path: Path) -> None:
    services, _, _, _ = _build_services(tmp_path)

    services.record_event("test", "Recorded event")
    events = services.list_events()

    assert events
    assert events[0]["type"] == "test"


def test_dump_routing_uses_provider(tmp_path: Path) -> None:
    services, _, _, _ = _build_services(tmp_path, routing_provider=lambda: ["a", "b"])

    result = services.dump_routing()

    assert result["destinations"] == ["a", "b"]


def test_dump_routing_falls_back_to_clients(tmp_path: Path) -> None:
    services, api, _, _ = _build_services(tmp_path)
    api.join("dest-1")

    result = services.dump_routing()

    assert result["destinations"] == ["dest-1"]


def test_send_message_requires_dispatcher(tmp_path: Path) -> None:
    services, _, _, _ = _build_services(tmp_path)

    with pytest.raises(RuntimeError):
        services.send_message("payload")


def test_send_message_dispatches_payload(tmp_path: Path) -> None:
    captured = {}

    def _dispatcher(content, topic_id, destination, fields):
        captured["content"] = content
        captured["topic_id"] = topic_id
        captured["destination"] = destination
        captured["fields"] = fields

    services, _, _, _ = _build_services(tmp_path, message_dispatcher=_dispatcher)
    services.send_message("hello", topic_id="topic-1", destination="dest-1")

    assert captured == {
        "content": "hello",
        "topic_id": "topic-1",
        "destination": "dest-1",
        "fields": None,
    }


def test_telemetry_entries_proxy(tmp_path: Path) -> None:
    services, _, telemetry, _ = _build_services(tmp_path)
    now = datetime.now(timezone.utc)
    telemetry.save_telemetry(
        {
            SID_TIME: int(now.timestamp()),
            SID_LOCATION: build_location_payload(int(now.timestamp())),
        },
        "dest-1",
        timestamp=now,
    )

    entries = services.telemetry_entries(since=int(now.timestamp()) - 1, topic_id=None)

    assert entries


def test_app_info_round_trip(tmp_path: Path) -> None:
    services, _, _, _ = _build_services(tmp_path)

    info = services.app_info().to_dict()

    assert "app_name" in info
    assert "storage_path" in info
    assert "reticulum_destination" in info


def test_reticulum_interface_capabilities_proxy(tmp_path: Path, monkeypatch) -> None:
    """Return capabilities payload from the discovery helper."""

    services, _, _, _ = _build_services(tmp_path)
    monkeypatch.setattr(
        "reticulum_telemetry_hub.northbound.services.get_interface_capabilities",
        lambda: {"runtime_active": True, "supported_interface_types": ["TCPClientInterface"]},
    )

    payload = services.reticulum_interface_capabilities()

    assert payload["runtime_active"] is True
    assert payload["supported_interface_types"] == ["TCPClientInterface"]


def test_reticulum_discovery_snapshot_proxy(tmp_path: Path, monkeypatch) -> None:
    """Return discovery payload from the discovery helper."""

    services, _, _, _ = _build_services(tmp_path)
    monkeypatch.setattr(
        "reticulum_telemetry_hub.northbound.services.get_discovery_snapshot",
        lambda: {"runtime_active": False, "discovered_interfaces": []},
    )

    payload = services.reticulum_discovery_snapshot()

    assert payload["runtime_active"] is False
    assert payload["discovered_interfaces"] == []
