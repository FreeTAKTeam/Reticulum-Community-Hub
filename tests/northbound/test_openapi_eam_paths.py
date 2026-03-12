from __future__ import annotations

from pathlib import Path

import yaml


def _spec() -> dict:
    return yaml.safe_load(
        Path("API/ReticulumCommunityHub-OAS.yaml").read_text(encoding="utf-8")
    )


def test_openapi_includes_eam_paths() -> None:
    paths = _spec()["paths"]

    required = {
        "/api/EmergencyActionMessage": {"get", "post"},
        "/api/EmergencyActionMessage/{callsign}": {"get", "put", "delete"},
        "/api/EmergencyActionMessage/latest/{subjectType}/{subjectId}": {"get"},
        "/api/EmergencyActionMessage/team/{teamId}/summary": {"get"},
    }

    for route, methods in required.items():
        assert route in paths, route
        for method in methods:
            assert method in paths[route], f"{route} missing {method}"


def test_openapi_exposes_eam_schemas_and_refs() -> None:
    spec = _spec()
    schemas = spec["components"]["schemas"]
    paths = spec["paths"]

    assert {"EAMStatus", "SubjectType", "EmergencyActionMessage", "EmergencyActionMessageUpsertRequest", "TeamStatusSummary"}.issubset(
        set(schemas)
    )
    assert schemas["EAMStatus"]["enum"] == ["Green", "Yellow", "Red", "Unknown"]
    assert schemas["SubjectType"]["enum"] == ["member"]
    assert (
        paths["/api/EmergencyActionMessage"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/EmergencyActionMessageUpsertRequest"
    )
    assert (
        paths["/api/EmergencyActionMessage/team/{teamId}/summary"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/TeamStatusSummary"
    )
    assert "securityCapability" in schemas["EmergencyActionMessage"]["properties"]
    assert schemas["EmergencyActionMessage"]["properties"]["securityCapability"]["deprecated"] is True
