"""Tests for chat routes in the northbound API."""

from __future__ import annotations

from pathlib import Path

import pytest
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
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog
from tests.test_rth_api import RustTopicSubscriberApi


class _StubHub:
    """Minimal hub stub for gateway chat tests."""

    def __init__(
        self,
        *,
        api: ReticulumTelemetryHubAPI | RustTopicSubscriberApi,
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
            state="queued",
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


def _build_api(
    tmp_path: Path, *, backend: str = "python"
) -> ReticulumTelemetryHubAPI | RustTopicSubscriberApi:
    """Create an API instance backed by a temp database."""

    if backend == "rust":
        return RustTopicSubscriberApi(tmp_path)
    config_manager = HubConfigurationManager(storage_path=tmp_path)
    storage = HubStorage(tmp_path / "hub.sqlite")
    return ReticulumTelemetryHubAPI(config_manager=config_manager, storage=storage)


def _build_gateway_client(
    tmp_path: Path, *, backend: str = "python"
) -> tuple[TestClient, _StubHub]:
    """Create a TestClient wired to a stubbed gateway hub."""

    api = _build_api(tmp_path, backend=backend)
    telemetry = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)
    hub = _StubHub(api=api, telemetry=telemetry, event_log=EventLog())
    app = build_gateway_app(hub)
    return TestClient(app), hub


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_chat_message_send_success(tmp_path: Path, backend: str) -> None:
    """Ensure chat messages dispatch through the gateway."""

    client, hub = _build_gateway_client(tmp_path, backend=backend)

    response = client.post(
        "/Chat/Message",
        json={"content": "hello", "scope": "broadcast"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["Content"] == "hello"
    assert payload["State"] == "queued"
    assert hub.dispatch_calls
    dispatch = hub.dispatch_calls[0]
    assert dispatch["message"] == "hello"
    assert dispatch["topic_id"] is None
    assert dispatch["destination"] is None
    assert dispatch["fields"]["scope"] == "broadcast"
    assert dispatch["fields"]["attachments"] == []


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_chat_message_accepts_scope_variants(tmp_path: Path, backend: str) -> None:
    """Ensure scope validation accepts trimmed variants."""

    client, hub = _build_gateway_client(tmp_path, backend=backend)

    response = client.post(
        "/Chat/Message",
        json={"content": "hi", "scope": " BROADCAST "},
    )

    assert response.status_code == 200
    assert hub.dispatch_calls[-1]["fields"]["scope"] == " BROADCAST "


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_chat_message_requires_dispatcher(tmp_path: Path, backend: str) -> None:
    """Ensure missing dispatchers return a 503."""

    api = _build_api(tmp_path, backend=backend)
    telemetry = TelemetryController(db_path=tmp_path / "telemetry.db", api=api)
    app = create_app(api=api, telemetry_controller=telemetry, event_log=EventLog())
    client = TestClient(app)

    response = client.post(
        "/Chat/Message",
        json={"content": "hello", "scope": "broadcast"},
    )

    assert response.status_code == 503


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_chat_attachment_honors_configured_size_limit(
    tmp_path: Path, backend: str
) -> None:
    """Ensure attachment uploads respect the configured byte limit."""

    config_path = tmp_path / "config.ini"
    config_path.write_text("[hub]\nchat_attachment_max_bytes = 4\n")
    client, _hub = _build_gateway_client(tmp_path, backend=backend)

    within_limit = client.post(
        "/Chat/Attachment",
        data={"category": "file"},
        files={"file": ("ok.txt", b"1234", "text/plain")},
    )

    assert within_limit.status_code == 200

    over_limit = client.post(
        "/Chat/Attachment",
        data={"category": "file"},
        files={"file": ("too-big.txt", b"12345", "text/plain")},
    )

    assert over_limit.status_code == 413
    assert over_limit.json()["detail"] == "Attachment exceeds size limit"
