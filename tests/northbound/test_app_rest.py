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
    SID_LOCATION,
    SID_TIME,
)
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.northbound.app import create_app
from reticulum_telemetry_hub.northbound.auth import ApiAuth
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog
from tests.factories import build_location_payload


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
    telemetry_controller.save_telemetry(
        {
            SID_TIME: int(now.timestamp()),
            SID_LOCATION: build_location_payload(int(now.timestamp())),
        },
        "peer-1",
        timestamp=now,
    )

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
    client = TestClient(app, client=("198.51.100.10", 50000))

    response = client.get("/Status")

    assert response.status_code == 401


def test_auth_validate_localhost_without_key_allowed(tmp_path) -> None:
    """Allow localhost access to auth validation without configured API keys."""

    api = _build_api(tmp_path)
    app = create_app(
        api=api,
        telemetry_controller=TelemetryController(db_path=tmp_path / "telemetry.db", api=api),
        auth=ApiAuth(api_key=None),
    )
    client = TestClient(app, client=("127.0.0.1", 50000))

    response = client.get("/api/v1/auth/validate")

    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    assert response.json()["auth_mode"] == "local_only"


def test_auth_validate_remote_without_key_rejected(tmp_path) -> None:
    """Reject remote auth validation requests without an API key."""

    api = _build_api(tmp_path)
    app = create_app(
        api=api,
        telemetry_controller=TelemetryController(db_path=tmp_path / "telemetry.db", api=api),
        auth=ApiAuth(api_key=None),
    )
    client = TestClient(app, client=("198.51.100.10", 50000))

    response = client.get("/api/v1/auth/validate")

    assert response.status_code == 401


def test_auth_validate_remote_with_bearer_token_allowed(tmp_path) -> None:
    """Allow remote auth validation requests with a valid bearer token."""

    api = _build_api(tmp_path)
    app = create_app(
        api=api,
        telemetry_controller=TelemetryController(db_path=tmp_path / "telemetry.db", api=api),
        auth=ApiAuth(api_key="secret"),
    )
    client = TestClient(app, client=("198.51.100.10", 50000))

    response = client.get(
        "/api/v1/auth/validate",
        headers={"Authorization": "Bearer secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["authenticated"] is True
    assert payload["auth_mode"] == "api_key"
    assert payload["app"]["name"] == "ReticulumCommunityHub"


def test_app_info_prefers_hub_display_name(tmp_path) -> None:
    """Expose the configured hub display name as the primary app-info name."""

    (tmp_path / "config.ini").write_text(
        "[hub]\ndisplay_name = RCH - Altre Alternative\n",
        encoding="utf-8",
    )
    api = _build_api(tmp_path)
    app = create_app(
        api=api,
        telemetry_controller=TelemetryController(db_path=tmp_path / "telemetry.db", api=api),
        event_log=EventLog(),
        auth=ApiAuth(api_key="secret"),
    )
    client = TestClient(app)

    response = client.get("/api/v1/app/info")

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "RCH - Altre Alternative"
    assert payload["display_name"] == "RCH - Altre Alternative"
    assert payload["app_name"] == "ReticulumTelemetryHub"
