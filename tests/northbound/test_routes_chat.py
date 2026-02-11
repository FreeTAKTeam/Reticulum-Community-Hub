"""Tests for chat routes in the northbound API."""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from reticulum_telemetry_hub.api.models import ChatMessage
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.api.storage import HubStorage
from reticulum_telemetry_hub.config.manager import HubConfigurationManager
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.northbound.app import create_app
from reticulum_telemetry_hub.northbound.gateway import build_gateway_app
from reticulum_telemetry_hub.northbound.routes_chat import MAX_ATTACHMENT_BYTES
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog


class _StubHub:
    """Minimal hub stub for gateway chat tests."""

    def __init__(
        self,
        *,
        api: ReticulumTelemetryHubAPI,
        telemetry: TelemetryController,
        event_log: EventLog,
    ) -> None:
        self.api = api
        self.tel_controller = telemetry
        self.event_log = event_log
        self.command_manager = None
        self.marker_service = None
        self.dispatch_calls: list[dict] = []
        self.marker_dispatch_calls: list[dict] = []

    def dispatch_northbound_message(
        self,
        message: str,
        topic_id: str | None = None,
        destination: str | None = None,
        fields: dict | None = None,
    ) -> ChatMessage:
        """Record dispatches and return a stubbed chat message."""

        self.dispatch_calls.append(
            {
                "message": message,
                "topic_id": topic_id,
                "destination": destination,
                "fields": fields,
            }
        )
        scope = "broadcast"
        if isinstance(fields, dict) and isinstance(fields.get("scope"), str):
            scope = fields["scope"]
        return ChatMessage(
            direction="outbound",
            scope=scope,
            state="sent",
            content=message,
            destination=destination,
            topic_id=topic_id,
            message_id="msg-1",
        )

    def dispatch_marker_event(self, marker, event_type: str) -> bool:
        """Record marker dispatches for gateway compatibility."""

        self.marker_dispatch_calls.append({"event_type": event_type, "marker": marker})
        return True

    def register_message_listener(self, listener):
        """Provide a no-op unsubscribe callback."""

        return lambda: None


def _build_api(tmp_path: Path) -> ReticulumTelemetryHubAPI:
    """Create an API instance backed by a temp database."""

    config_manager = HubConfigurationManager(storage_path=tmp_path)
    storage = HubStorage(tmp_path / "hub.sqlite")
    return ReticulumTelemetryHubAPI(config_manager=config_manager, storage=storage)


def _build_gateway_client(tmp_path: Path) -> tuple[TestClient, _StubHub]:
    """Create a TestClient wired to a stubbed gateway hub."""

    api = _build_api(tmp_path)
    telemetry = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)
    hub = _StubHub(api=api, telemetry=telemetry, event_log=EventLog())
    app = build_gateway_app(hub)
    return TestClient(app), hub


def test_chat_message_send_success(tmp_path: Path) -> None:
    """Ensure chat messages dispatch through the gateway."""

    client, hub = _build_gateway_client(tmp_path)

    response = client.post(
        "/Chat/Message",
        json={"content": "hello", "scope": "broadcast"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["Content"] == "hello"
    assert hub.dispatch_calls
    dispatch = hub.dispatch_calls[0]
    assert dispatch["message"] == "hello"
    assert dispatch["topic_id"] is None
    assert dispatch["destination"] is None
    assert dispatch["fields"]["scope"] == "broadcast"
    assert dispatch["fields"]["attachments"] == []


def test_chat_message_accepts_scope_variants(tmp_path: Path) -> None:
    """Ensure scope validation accepts trimmed variants."""

    client, hub = _build_gateway_client(tmp_path)

    response = client.post(
        "/Chat/Message",
        json={"content": "hi", "scope": " BROADCAST "},
    )

    assert response.status_code == 200
    assert hub.dispatch_calls[-1]["fields"]["scope"] == " BROADCAST "


def test_chat_message_requires_dispatcher(tmp_path: Path) -> None:
    """Ensure missing dispatchers return a 503."""

    api = _build_api(tmp_path)
    telemetry = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)
    app = create_app(api=api, telemetry_controller=telemetry, event_log=EventLog())
    client = TestClient(app)

    response = client.post(
        "/Chat/Message",
        json={"content": "hello", "scope": "broadcast"},
    )

    assert response.status_code == 503


def test_chat_messages_list_applies_filters(tmp_path: Path) -> None:
    """Ensure list endpoint forwards query filters to storage."""

    client, hub = _build_gateway_client(tmp_path)

    hub.api.record_chat_message(
        ChatMessage(
            direction="inbound",
            scope="topic",
            state="delivered",
            content="hello-topic",
            source="src-a",
            destination="dst-a",
            topic_id="topic-a",
        )
    )
    hub.api.record_chat_message(
        ChatMessage(
            direction="outbound",
            scope="broadcast",
            state="sent",
            content="hello-other",
            destination="dst-b",
            topic_id="topic-b",
        )
    )

    response = client.get(
        "/Chat/Messages",
        params={
            "limit": 1,
            "direction": "inbound",
            "topic_id": "topic-a",
            "destination": "dst-a",
            "source": "src-a",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["Content"] == "hello-topic"
    assert payload[0]["Direction"] == "inbound"
    assert payload[0]["TopicID"] == "topic-a"


def test_chat_message_returns_404_for_missing_attachment(tmp_path: Path) -> None:
    """Ensure send endpoint maps missing attachments to HTTP 404."""

    client, _hub = _build_gateway_client(tmp_path)

    response = client.post(
        "/Chat/Message",
        json={"content": "hello", "scope": "broadcast", "file_ids": [99999]},
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_upload_attachment_validates_category(tmp_path: Path) -> None:
    """Ensure invalid attachment categories are rejected."""

    client, _hub = _build_gateway_client(tmp_path)

    response = client.post(
        "/Chat/Attachment",
        data={"category": "binary"},
        files={"file": ("sample.bin", b"abc", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Attachment category must be file or image"


def test_upload_attachment_rejects_empty_payload(tmp_path: Path) -> None:
    """Ensure empty uploads are rejected."""

    client, _hub = _build_gateway_client(tmp_path)

    response = client.post(
        "/Chat/Attachment",
        data={"category": "file"},
        files={"file": ("empty.txt", b"", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Attachment content is empty"


def test_upload_attachment_rejects_oversized_payload(tmp_path: Path) -> None:
    """Ensure uploads above the configured size limit are rejected."""

    client, _hub = _build_gateway_client(tmp_path)
    too_large = b"x" * (MAX_ATTACHMENT_BYTES + 1)

    response = client.post(
        "/Chat/Attachment",
        data={"category": "file"},
        files={"file": ("large.bin", too_large, "application/octet-stream")},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Attachment exceeds size limit"


def test_upload_attachment_rejects_non_image_content_type(tmp_path: Path) -> None:
    """Ensure image uploads require an image media type."""

    client, _hub = _build_gateway_client(tmp_path)

    response = client.post(
        "/Chat/Attachment",
        data={"category": "image"},
        files={"file": ("not-image.txt", b"abc", "text/plain")},
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"] == "Image attachments must use an image content type"
    )


def test_upload_attachment_rejects_hash_mismatch(tmp_path: Path) -> None:
    """Ensure provided SHA-256 checksums must match content."""

    client, _hub = _build_gateway_client(tmp_path)

    response = client.post(
        "/Chat/Attachment",
        data={"category": "file", "sha256": "0" * 64},
        files={"file": ("data.txt", b"abc", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Attachment hash mismatch"


def test_upload_attachment_success_with_hash_and_topic(tmp_path: Path) -> None:
    """Ensure valid uploads persist and return attachment metadata."""

    client, _hub = _build_gateway_client(tmp_path)
    content = b"payload-123"
    digest = hashlib.sha256(content).hexdigest()

    response = client.post(
        "/Chat/Attachment",
        data={"category": "file", "sha256": digest, "topic_id": "topic-a"},
        files={"file": ("payload.bin", content, "application/octet-stream")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["Category"] == "file"
    assert payload["TopicID"] == "topic-a"
    assert payload["Size"] == len(content)
    assert isinstance(payload["FileID"], int)
