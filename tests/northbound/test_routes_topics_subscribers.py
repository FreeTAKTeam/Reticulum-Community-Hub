"""Tests for topic and subscriber routes."""
# pylint: disable=import-error

from __future__ import annotations

from datetime import datetime
from datetime import timezone
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from reticulum_telemetry_hub.api.models import Topic
from reticulum_telemetry_hub.api.models import Subscriber
from reticulum_telemetry_hub.api.pagination import PageRequest
from reticulum_telemetry_hub.api.pagination import PaginatedResult
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.api.storage import HubStorage
from reticulum_telemetry_hub.config import HubConfigurationManager
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.northbound.app import create_app
from reticulum_telemetry_hub.northbound.auth import ApiAuth
from reticulum_telemetry_hub.mission_sync.rust_bridge import RustMissionSyncBridge
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandEnvelope
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog


FIELD_RESULTS = 10
FIELD_GROUP = 11
FIELD_EVENT = 13


class RustTopicApi:
    """Topic/subscriber API subset backed by the Rust RCH bridge."""

    def __init__(self, config_manager: HubConfigurationManager, db_path: Path) -> None:
        self._config_manager = config_manager
        self._bridge = _bridge(db_path)

    def apply_config_text(self, config_text: str) -> dict:
        result = self._config_manager.apply_config_text(config_text)
        self._config_manager.reload()
        return result

    def create_topic(self, topic: Topic) -> Topic:
        result = self._result(
            "topic.create",
            {
                "topic_id": topic.topic_id,
                "topic_name": topic.topic_name,
                "topic_path": topic.topic_path,
                "topic_description": topic.topic_description,
            },
            command_id="cmd-northbound-topic-create",
        )
        return Topic.from_dict(result)

    def retrieve_topic(self, topic_id: str) -> Topic:
        for topic in self.list_topics():
            if topic.topic_id == topic_id:
                return topic
        raise KeyError(topic_id)

    def list_topics(self) -> list[Topic]:
        return [Topic.from_dict(topic) for topic in self._snapshot_rows("topics")]

    def list_topics_paginated(self, page_request: PageRequest) -> PaginatedResult[Topic]:
        topics = self.list_topics()
        return _page(topics, page_request)

    def patch_topic(self, topic_id: str, **updates: object) -> Topic:
        args = {
            "topic_id": topic_id,
            "topic_name": updates.get("TopicName") or updates.get("topic_name"),
            "topic_path": updates.get("TopicPath") or updates.get("topic_path"),
            "topic_description": updates.get("TopicDescription")
            or updates.get("topic_description"),
        }
        result = self._result("topic.patch", args, command_id="cmd-northbound-topic-patch")
        return Topic.from_dict(result)

    def delete_topic(self, topic_id: str) -> Topic:
        topic = self.retrieve_topic(topic_id)
        self._result(
            "topic.delete",
            {"topic_id": topic_id},
            command_id="cmd-northbound-topic-delete",
        )
        return topic

    def subscribe_topic(
        self,
        topic_id: str | None,
        destination: str,
        *,
        reject_tests: object | None = None,
        metadata: dict | None = None,
    ) -> Subscriber:
        result = self._result(
            "topic.subscribe",
            {
                "topic_id": topic_id,
                "destination": destination,
                "reject_tests": reject_tests,
                "metadata": metadata or {},
            },
            command_id="cmd-northbound-topic-subscribe",
        )
        return Subscriber.from_dict(result)

    def list_subscribers(self) -> list[Subscriber]:
        return [
            Subscriber(
                destination=str(subscriber.get("node_id") or ""),
                topic_id=str(subscriber.get("topic_id") or ""),
                metadata=dict(subscriber.get("metadata") or {}),
                subscriber_id=str(subscriber.get("node_id") or ""),
            )
            for subscriber in self._snapshot_rows("subscribers")
        ]

    def retrieve_subscriber(self, subscriber_id: str) -> Subscriber:
        for subscriber in self.list_subscribers():
            if subscriber.subscriber_id == subscriber_id:
                return subscriber
        raise KeyError(subscriber_id)

    def delete_subscriber(self, subscriber_id: str) -> Subscriber:
        result = self._result(
            "topic.subscriber.delete",
            {"subscriber_id": subscriber_id},
            command_id="cmd-northbound-subscriber-delete",
        )
        return Subscriber.from_dict(result)

    def patch_subscriber(self, subscriber_id: str, **updates: object) -> Subscriber:
        result = self._result(
            "topic.subscriber.patch",
            {
                "subscriber_id": subscriber_id,
                "destination": updates.get("Destination") or updates.get("destination"),
                "topic_id": updates.get("TopicID") or updates.get("topic_id"),
                "metadata": updates.get("Metadata") or updates.get("metadata") or {},
            },
            command_id="cmd-northbound-subscriber-patch",
        )
        return Subscriber.from_dict(result)

    def add_subscriber(self, subscriber: Subscriber) -> Subscriber:
        return self.create_subscriber(subscriber)

    def create_subscriber(self, subscriber: Subscriber) -> Subscriber:
        return self.subscribe_topic(
            subscriber.topic_id,
            subscriber.destination,
            metadata=subscriber.metadata,
        )

    def list_subscribers_paginated(
        self,
        page_request: PageRequest,
    ) -> PaginatedResult[Subscriber]:
        subscribers = self.list_subscribers()
        return _page(subscribers, page_request)

    def _snapshot_rows(self, key: str) -> list[dict[str, object]]:
        rows = self._bridge.state_snapshot().get(key)
        assert isinstance(rows, list)
        return [dict(row) for row in rows if isinstance(row, dict)]

    def _result(
        self,
        command_type: str,
        args: dict[str, object],
        *,
        command_id: str,
    ) -> dict[str, object]:
        responses = self._bridge.handle_command(
            MissionCommandEnvelope.model_validate(
                {
                    "command_id": command_id,
                    "source": {"rns_identity": "peer-a"},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "command_type": command_type,
                    "args": args,
                }
            ),
            source_identity="peer-a",
        )
        if not responses:
            raise RuntimeError(f"Rust bridge returned no response for {command_type}")
        payload = responses[-1].fields[FIELD_RESULTS]
        if not isinstance(payload, dict):
            raise RuntimeError(f"Rust bridge returned malformed payload for {command_type}")
        if payload.get("status") == "rejected" and payload.get("reason_code") == "not_found":
            raise KeyError(command_type)
        if payload.get("status") == "rejected" and payload.get("reason_code") == "invalid_payload":
            raise ValueError(payload.get("reason") or payload.get("detail") or command_type)
        if payload.get("status") != "result":
            raise RuntimeError(f"Rust bridge rejected {command_type}: {payload}")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"Rust bridge returned non-object result for {command_type}")
        return result


def _runtime_root() -> Path:
    candidates = [
        Path(__file__).resolve().parents[4] / "New project" / "R3AKT-Runtime",
        Path(r"C:\Users\broth\Documents\New project\R3AKT-Runtime"),
    ]
    for candidate in candidates:
        if (candidate / "Cargo.toml").exists():
            return candidate
    pytest.fail("R3AKT-Runtime workspace not found for Rust northbound parity tests")


def _bridge(db_path: Path) -> RustMissionSyncBridge:
    runtime_root = _runtime_root()

    def runner(args, **kwargs):  # type: ignore[no-untyped-def]
        request_db_path = args[args.index("--db") + 1]
        return subprocess.run(
            ["cargo", "run", "-q", "-p", "r3akt-rch-bridge", "--", "--db", request_db_path],
            cwd=runtime_root,
            input=kwargs["input"],
            text=True,
            capture_output=True,
            check=False,
        )

    return RustMissionSyncBridge(
        binary_path="cargo-run-r3akt-rch-bridge",
        db_path=str(db_path),
        field_results=FIELD_RESULTS,
        field_event=FIELD_EVENT,
        field_group=FIELD_GROUP,
        runner=runner,
    )


def _page(items: list, page_request: PageRequest) -> PaginatedResult:
    return PaginatedResult.from_request(
        items=items[page_request.offset : page_request.offset + page_request.per_page],
        request=page_request,
        total=len(items),
    )


def _build_client(
    tmp_path: Path,
    *,
    client_address: tuple[str, int] = ("testclient", 50000),
    backend: str = "python",
) -> tuple[TestClient, ReticulumTelemetryHubAPI | RustTopicApi]:
    config_manager = HubConfigurationManager(storage_path=tmp_path)
    if backend == "rust":
        api = RustTopicApi(config_manager, tmp_path / "r3akt-topic-routes.sqlite")
    else:
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


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_topic_crud_and_subscribe_flow(tmp_path: Path, backend: str) -> None:
    client, _ = _build_client(tmp_path, backend=backend)
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

    remote_client, _ = _build_client(
        tmp_path,
        client_address=("198.51.100.10", 50000),
        backend=backend,
    )
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


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_topic_list_pagination_uses_configured_default_and_max(
    tmp_path: Path,
    backend: str,
) -> None:
    (tmp_path / "config.ini").write_text(
        "[api]\n"
        "pagination_default_page_size = 2\n"
        "pagination_max_page_size = 3\n",
        encoding="utf-8",
    )
    client, api = _build_client(tmp_path, backend=backend)
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


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_topic_list_pagination_uses_reloaded_config_default(
    tmp_path: Path,
    backend: str,
) -> None:
    (tmp_path / "config.ini").write_text(
        "[api]\n"
        "pagination_default_page_size = 2\n"
        "pagination_max_page_size = 5\n",
        encoding="utf-8",
    )
    client, api = _build_client(tmp_path, backend=backend)
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


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_subscriber_crud_flow(tmp_path: Path, backend: str) -> None:
    client, api = _build_client(tmp_path, backend=backend)
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


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_subscriber_list_pagination_returns_requested_page(
    tmp_path: Path,
    backend: str,
) -> None:
    client, api = _build_client(tmp_path, backend=backend)
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
