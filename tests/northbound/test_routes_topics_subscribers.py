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


def _build_client(
    tmp_path: Path,
    *,
    client_address: tuple[str, int] = ("testclient", 50000),
) -> tuple[TestClient, ReticulumTelemetryHubAPI]:
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
    return TestClient(app, client=client_address), api


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

    list_response = client.get("/Topic", headers=headers)
    assert list_response.status_code == 200
    assert list_response.json()

    get_response = client.get(f"/Topic/{topic_id}", headers=headers)
    assert get_response.status_code == 200

    patch_response = client.patch(
        "/Topic",
        json={"TopicID": topic_id, "TopicDescription": "Updated"},
        headers=headers,
    )
    assert patch_response.status_code == 200

    remote_client, _ = _build_client(tmp_path, client_address=("198.51.100.10", 50000))
    assoc_missing = remote_client.post("/Topic/Associate", json={})
    assert assoc_missing.status_code == 401

    assoc_response = client.post(
        "/Topic/Associate",
        json={"TopicID": topic_id},
        headers=headers,
    )
    assert assoc_response.status_code == 200
    assert assoc_response.json()["TopicID"] == topic_id

    subscribe_missing = client.post(
        "/Topic/Subscribe",
        json={"TopicID": topic_id},
        headers=headers,
    )
    assert subscribe_missing.status_code == 400

    subscribe_response = client.post(
        "/Topic/Subscribe",
        json={"TopicID": topic_id, "Destination": "dest-1"},
        headers=headers,
    )
    assert subscribe_response.status_code == 200

    delete_response = client.delete(
        "/Topic",
        params={"id": topic_id},
        headers=headers,
    )
    assert delete_response.status_code == 200

    missing_response = client.get("/Topic/missing", headers=headers)
    assert missing_response.status_code == 404


def test_topic_list_pagination_uses_configured_default_and_max(tmp_path: Path) -> None:
    (tmp_path / "config.ini").write_text(
        "[api]\n"
        "pagination_default_page_size = 2\n"
        "pagination_max_page_size = 3\n",
        encoding="utf-8",
    )
    client, api = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}
    for index in range(5):
        api.create_topic(Topic(topic_name=f"topic-{index}", topic_path=f"topic-{index}"))

    response = client.get("/Topic", params={"page": 1}, headers=headers)
    too_large_response = client.get(
        "/Topic",
        params={"page": 1, "per_page": 4},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 2
    assert payload["per_page"] == 2
    assert payload["total"] == 5
    assert payload["total_pages"] == 3
    assert too_large_response.status_code == 422


def test_topic_list_pagination_uses_reloaded_config_default(tmp_path: Path) -> None:
    (tmp_path / "config.ini").write_text(
        "[api]\n"
        "pagination_default_page_size = 2\n"
        "pagination_max_page_size = 5\n",
        encoding="utf-8",
    )
    client, api = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}
    for index in range(5):
        api.create_topic(Topic(topic_name=f"topic-{index}", topic_path=f"topic-{index}"))

    apply_response = client.put(
        "/Config",
        content="[api]\npagination_default_page_size = 3\npagination_max_page_size = 5\n",
        headers={**headers, "Content-Type": "text/plain"},
    )
    response = client.get("/Topic", params={"page": 1}, headers=headers)

    assert apply_response.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 3
    assert payload["per_page"] == 3
    assert payload["total"] == 5


def test_topic_routes_require_auth_for_remote_clients(tmp_path: Path) -> None:
    client, api = _build_client(tmp_path)
    topic = api.create_topic(Topic(topic_name="alerts", topic_path="alerts"))
    remote_client, _ = _build_client(tmp_path, client_address=("198.51.100.10", 50000))

    assert remote_client.get("/Topic").status_code == 401
    assert remote_client.get(f"/Topic/{topic.topic_id}").status_code == 401
    assert remote_client.post(
        "/Topic/Subscribe",
        json={"TopicID": topic.topic_id, "Destination": "dest-1"},
    ).status_code == 401


def test_topic_patch_requires_id(tmp_path: Path) -> None:
    client, _ = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    response = client.patch("/Topic", json={"TopicName": "x"}, headers=headers)

    assert response.status_code == 400


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


def test_subscriber_list_pagination_returns_requested_page(tmp_path: Path) -> None:
    client, api = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}
    topic = api.create_topic(Topic(topic_name="alerts", topic_path="alerts"))
    for index in range(3):
        api.subscribe_topic(topic.topic_id, destination=f"dest-{index}")

    response = client.get(
        "/Subscriber",
        params={"page": 2, "per_page": 2},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 1
    assert payload["page"] == 2
    assert payload["per_page"] == 2
    assert payload["total"] == 3
    assert payload["has_next"] is False
    assert payload["has_previous"] is True
