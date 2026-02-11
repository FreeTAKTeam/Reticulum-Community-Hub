"""Tests for topic and subscriber routes."""
# pylint: disable=import-error

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from reticulum_telemetry_hub.api.models import Topic
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.api.storage import HubStorage
from reticulum_telemetry_hub.config import HubConfigurationManager
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.northbound.app import create_app
from reticulum_telemetry_hub.northbound.auth import ApiAuth
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog


def _build_client(tmp_path: Path) -> tuple[TestClient, ReticulumTelemetryHubAPI]:
    config_manager = HubConfigurationManager(storage_path=tmp_path)
    storage = HubStorage(tmp_path / "hub.sqlite")
    api = ReticulumTelemetryHubAPI(config_manager=config_manager, storage=storage)
    event_log = EventLog()
    telemetry = TelemetryController(
        db_path=tmp_path / "telemetry.db",
        api=api,
        event_log=event_log,
    )
    app = create_app(
        api=api,
        telemetry_controller=telemetry,
        event_log=event_log,
        auth=ApiAuth(api_key="secret"),
    )
    return TestClient(app), api


def test_topic_crud_and_subscribe_flow(tmp_path: Path) -> None:
    client, _ = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    create_response = client.post(
        "/Topic",
        json={"TopicName": "alerts", "TopicPath": "alerts"},
        headers=headers,
    )
    assert create_response.status_code == 200
    topic_id = create_response.json()["TopicID"]

    list_response = client.get("/Topic")
    assert list_response.status_code == 200
    assert list_response.json()

    get_response = client.get(f"/Topic/{topic_id}")
    assert get_response.status_code == 200

    patch_response = client.patch(
        "/Topic",
        json={"TopicID": topic_id, "TopicDescription": "Updated"},
        headers=headers,
    )
    assert patch_response.status_code == 200

    assoc_missing = client.post("/Topic/Associate", json={})
    assert assoc_missing.status_code == 401

    assoc_response = client.post(
        "/Topic/Associate",
        json={"TopicID": topic_id},
        headers=headers,
    )
    assert assoc_response.status_code == 200
    assert assoc_response.json()["TopicID"] == topic_id

    subscribe_missing = client.post("/Topic/Subscribe", json={"TopicID": topic_id})
    assert subscribe_missing.status_code == 400

    subscribe_response = client.post(
        "/Topic/Subscribe",
        json={"TopicID": topic_id, "Destination": "dest-1"},
    )
    assert subscribe_response.status_code == 200

    delete_response = client.delete(
        "/Topic",
        params={"id": topic_id},
        headers=headers,
    )
    assert delete_response.status_code == 200

    missing_response = client.get("/Topic/missing")
    assert missing_response.status_code == 404


def test_topic_patch_requires_id(tmp_path: Path) -> None:
    client, _ = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    response = client.patch("/Topic", json={"TopicName": "x"}, headers=headers)

    assert response.status_code == 400


def test_topic_routes_error_paths(tmp_path: Path) -> None:
    """Cover topic route 400/404 branches."""

    client, _api = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    create_invalid = client.post(
        "/Topic",
        json={"TopicName": "", "TopicPath": ""},
        headers=headers,
    )
    assert create_invalid.status_code == 400

    delete_missing = client.delete("/Topic", params={"id": "missing"}, headers=headers)
    assert delete_missing.status_code == 404

    patch_missing = client.patch(
        "/Topic",
        json={"TopicID": "missing", "TopicDescription": "x"},
        headers=headers,
    )
    assert patch_missing.status_code == 404

    subscribe_missing_topic = client.post(
        "/Topic/Subscribe",
        json={"TopicID": "missing", "Destination": "dest-404"},
    )
    assert subscribe_missing_topic.status_code == 404

    associate_missing_with_auth = client.post(
        "/Topic/Associate",
        json={},
        headers=headers,
    )
    assert associate_missing_with_auth.status_code == 400


def test_subscriber_crud_flow(tmp_path: Path) -> None:
    client, api = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}
    topic = api.create_topic(Topic(topic_name="alerts", topic_path="alerts"))

    create_response = client.post(
        "/Subscriber",
        json={"Destination": "dest-1", "TopicID": topic.topic_id},
        headers=headers,
    )
    assert create_response.status_code == 200
    subscriber_id = create_response.json()["SubscriberID"]

    add_response = client.post(
        "/Subscriber/Add",
        json={"Destination": "dest-2", "TopicID": topic.topic_id},
        headers=headers,
    )
    assert add_response.status_code == 200

    list_response = client.get("/Subscriber", headers=headers)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 2

    get_response = client.get(f"/Subscriber/{subscriber_id}", headers=headers)
    assert get_response.status_code == 200

    patch_missing = client.patch(
        "/Subscriber",
        json={"Destination": "dest-3"},
        headers=headers,
    )
    assert patch_missing.status_code == 400

    patch_missing_id = client.patch(
        "/Subscriber",
        json={"SubscriberID": "missing", "Destination": "dest-3"},
        headers=headers,
    )
    assert patch_missing_id.status_code == 404

    delete_response = client.delete(
        "/Subscriber",
        params={"id": subscriber_id},
        headers=headers,
    )
    assert delete_response.status_code == 200

    delete_missing = client.delete(
        "/Subscriber",
        params={"id": "missing"},
        headers=headers,
    )
    assert delete_missing.status_code == 404


def test_subscriber_routes_error_paths(tmp_path: Path) -> None:
    """Cover subscriber route validation and not-found branches."""

    client, api = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}
    topic = api.create_topic(Topic(topic_name="alerts", topic_path="alerts"))

    missing_retrieve = client.get("/Subscriber/missing", headers=headers)
    assert missing_retrieve.status_code == 404

    add_invalid = client.post(
        "/Subscriber/Add",
        json={"Destination": "", "TopicID": topic.topic_id},
        headers=headers,
    )
    assert add_invalid.status_code == 400

    create_invalid = client.post(
        "/Subscriber",
        json={"Destination": "", "TopicID": topic.topic_id},
        headers=headers,
    )
    assert create_invalid.status_code == 400
