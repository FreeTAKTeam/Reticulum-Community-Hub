from __future__ import annotations

from pathlib import Path

import pytest

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.api.storage import HubStorage
from reticulum_telemetry_hub.config import HubConfigurationManager
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.mission_domain import EmergencyActionMessageService
from reticulum_telemetry_hub.mission_domain import MissionDomainService
from reticulum_telemetry_hub.northbound.app import create_app
from reticulum_telemetry_hub.northbound.auth import ApiAuth
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog
from tests.test_rth_api import RustTopicSubscriberApi


def _spec(tmp_path: Path, *, backend: str = "python") -> dict:
    config_manager = HubConfigurationManager(storage_path=tmp_path)
    api = (
        RustTopicSubscriberApi(tmp_path)
        if backend == "rust"
        else ReticulumTelemetryHubAPI(
            config_manager=config_manager,
            storage=HubStorage(tmp_path / "hub.sqlite"),
        )
    )
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
        routing_provider=lambda: ["dest-1"],
        message_dispatcher=lambda content, topic_id=None, destination=None, fields=None: None,
        mission_domain_service=MissionDomainService(config_manager.config.hub_database_path),
        emergency_action_message_service=EmergencyActionMessageService(
            config_manager.config.hub_database_path
        ),
    )
    return app.openapi()


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_openapi_exposes_core_payload_schema_names(
    tmp_path: Path, backend: str
) -> None:
    schemas = _spec(tmp_path, backend=backend)["components"]["schemas"]

    assert {
        "TopicPayload",
        "SubscriberPayload",
        "SubscribeTopicRequest",
        "AttachmentTopicPayload",
        "ConfigRollbackPayload",
        "MessagePayload",
        "HTTPValidationError",
        "ValidationError",
    }.issubset(set(schemas))
    assert schemas["SubscribeTopicRequest"]["required"] == ["TopicID"]


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_openapi_exposes_core_request_body_refs(
    tmp_path: Path, backend: str
) -> None:
    paths = _spec(tmp_path, backend=backend)["paths"]

    assert (
        paths["/Topic"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/TopicPayload"
    )
    assert (
        paths["/Topic"]["patch"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/TopicPayload"
    )
    assert (
        paths["/Topic/Subscribe"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/SubscribeTopicRequest"
    )
    assert (
        paths["/Subscriber"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/SubscriberPayload"
    )
    assert (
        paths["/Subscriber/Add"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/SubscriberPayload"
    )
    assert (
        paths["/File/{file_id}"]["patch"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/AttachmentTopicPayload"
    )
    assert (
        paths["/Image/{file_id}"]["patch"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/AttachmentTopicPayload"
    )
    assert (
        paths["/Config/Rollback"]["post"]["requestBody"]["content"]["application/json"]["schema"]["anyOf"][0]["$ref"]
        == "#/components/schemas/ConfigRollbackPayload"
    )
    assert (
        paths["/Message"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/MessagePayload"
    )


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_openapi_exposes_core_validation_and_path_parameter_shapes(
    tmp_path: Path, backend: str
) -> None:
    paths = _spec(tmp_path, backend=backend)["paths"]

    assert paths["/Topic"]["delete"]["parameters"][0]["name"] == "id"
    assert paths["/File/{file_id}"]["get"]["parameters"][0]["schema"]["type"] == "integer"
    assert (
        paths["/Topic"]["post"]["responses"]["422"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/HTTPValidationError"
    )
