from __future__ import annotations

from pathlib import Path

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


def _spec(tmp_path: Path) -> dict:
    config_manager = HubConfigurationManager(storage_path=tmp_path)
    api = ReticulumTelemetryHubAPI(
        config_manager=config_manager,
        storage=HubStorage(tmp_path / "hub.sqlite"),
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


def test_openapi_includes_rem_eam_paths(tmp_path: Path) -> None:
    paths = _spec(tmp_path)["paths"]

    required = {
        "/api/EmergencyActionMessage": {"get", "post"},
        "/api/EmergencyActionMessage/{callsign}": {"get", "put", "delete"},
        "/api/EmergencyActionMessage/latest/{team_member_uid}": {"get"},
        "/api/EmergencyActionMessage/team/{team_uid}/summary": {"get"},
    }

    for route, methods in required.items():
        assert route in paths, route
        for method in methods:
            assert method in paths[route], f"{route} missing {method}"

    assert "/api/EmergencyActionMessage/latest/{subjectType}/{subjectId}" not in paths
    assert "/api/EmergencyActionMessage/team/{teamId}/summary" not in paths


def test_openapi_exposes_rem_query_and_path_params(tmp_path: Path) -> None:
    paths = _spec(tmp_path)["paths"]

    list_params = {item["name"] for item in paths["/api/EmergencyActionMessage"]["get"]["parameters"]}
    latest_params = {
        item["name"]
        for item in paths["/api/EmergencyActionMessage/latest/{team_member_uid}"]["get"]["parameters"]
    }
    summary_params = {
        item["name"]
        for item in paths["/api/EmergencyActionMessage/team/{team_uid}/summary"]["get"]["parameters"]
    }

    assert {"team_uid", "overall_status"}.issubset(list_params)
    assert "subjectType" not in list_params
    assert "subjectId" not in list_params
    assert "teamId" not in list_params
    assert latest_params >= {"team_member_uid"}
    assert summary_params >= {"team_uid"}


def test_openapi_exposes_generic_object_and_array_contracts(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    paths = spec["paths"]

    assert (
        paths["/api/EmergencyActionMessage"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["type"]
        == "array"
    )
    assert (
        paths["/api/EmergencyActionMessage"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["type"]
        == "object"
    )
    assert (
        paths["/api/EmergencyActionMessage/latest/{team_member_uid}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["type"]
        == "object"
    )
    assert (
        paths["/api/EmergencyActionMessage/team/{team_uid}/summary"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["type"]
        == "object"
    )
