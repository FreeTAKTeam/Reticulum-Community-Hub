"""REST API tests for the northbound FastAPI app."""
# pylint: disable=import-error

from datetime import datetime
from datetime import timezone
from pathlib import Path

from fastapi.testclient import TestClient

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
from reticulum_telemetry_hub.northbound.app import create_app
from reticulum_telemetry_hub.northbound.auth import ApiAuth
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog


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


def test_status_endpoint_returns_counts(tmp_path) -> None:
    """Verify the status endpoint returns telemetry stats and counts."""

    api = _build_api(tmp_path)
    topic = api.create_topic(Topic(topic_name="Topic", topic_path="/topic"))
    api.create_subscriber(Subscriber(destination="peer-1", topic_id=topic.topic_id))

    telemetry_controller = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)
    now = datetime.now(timezone.utc)
    telemetry_controller.save_telemetry({SID_TIME: int(now.timestamp())}, "peer-1", timestamp=now)

    app = create_app(
        api=api,
        telemetry_controller=telemetry_controller,
        event_log=EventLog(),
        auth=ApiAuth(api_key="secret"),
    )

    client = TestClient(app)
    response = client.get("/Status", headers={"X-API-Key": "secret"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["topics"] == 1
    assert payload["subscribers"] == 1
    assert payload["telemetry"]["ingest_count"] == 1


def test_subscribe_requires_destination(tmp_path) -> None:
    """Ensure public topic subscribe requires a destination in this context."""

    api = _build_api(tmp_path)
    topic = api.create_topic(Topic(topic_name="Topic", topic_path="/topic"))
    app = create_app(api=api, telemetry_controller=TelemetryController(db_path=tmp_path / "telemetry.db", api=api))
    client = TestClient(app)

    response = client.post("/Topic/Subscribe", json={"TopicID": topic.topic_id})

    assert response.status_code == 400


def test_protected_endpoint_requires_api_key(tmp_path) -> None:
    """Ensure protected endpoints enforce API keys when configured."""

    api = _build_api(tmp_path)
    app = create_app(
        api=api,
        telemetry_controller=TelemetryController(db_path=tmp_path / "telemetry.db", api=api),
        auth=ApiAuth(api_key="secret"),
    )
    client = TestClient(app)

    response = client.get("/Status")

    assert response.status_code == 401


def test_message_endpoint_sends_payload(tmp_path) -> None:
    """Ensure message endpoint forwards payload to the message sender."""

    api = _build_api(tmp_path)
    telemetry_controller = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)
    event_log = EventLog()
    captured = {}

    def _message_sender(message: str, topic_id: str | None, exclude: set[str] | None) -> None:
        """Capture outbound messages for assertions.

        Args:
            message (str): Outbound content.
            topic_id (str | None): Optional topic id.
            exclude (set[str] | None): Excluded destinations.
        """

        captured["message"] = message
        captured["topic_id"] = topic_id
        captured["exclude"] = exclude

    app = create_app(
        api=api,
        telemetry_controller=telemetry_controller,
        event_log=event_log,
        message_sender=_message_sender,
        auth=ApiAuth(api_key="secret"),
    )
    client = TestClient(app)

    response = client.post(
        "/Message",
        headers={"X-API-Key": "secret"},
        json={"Message": "Hello", "TopicID": "topic-1", "Exclude": ["ABC"]},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    assert captured == {"message": "Hello", "topic_id": "topic-1", "exclude": {"abc"}}
    events = event_log.list_events()
    assert events[0]["type"] == "northbound_message_sent"


def test_message_endpoint_requires_sender(tmp_path) -> None:
    """Ensure message endpoint returns an error when no sender is configured."""

    api = _build_api(tmp_path)
    telemetry_controller = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)
    app = create_app(
        api=api,
        telemetry_controller=telemetry_controller,
        auth=ApiAuth(api_key="secret"),
    )
    client = TestClient(app)

    response = client.post(
        "/Message",
        headers={"X-API-Key": "secret"},
        json={"Message": "Hello"},
    )

    assert response.status_code == 501
