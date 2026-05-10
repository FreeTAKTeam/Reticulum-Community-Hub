from __future__ import annotations

from pathlib import Path

import yaml


def _spec() -> dict:
    return yaml.safe_load(Path("API/ReticulumCommunityHub-OAS.yaml").read_text(encoding="utf-8"))


def _parameter_names(spec: dict, operation: dict) -> set[str]:
    names = set()
    for parameter in operation.get("parameters", []):
        if "$ref" in parameter:
            name = parameter["$ref"].rsplit("/", 1)[-1]
            parameter = spec["components"]["parameters"][name]
        names.add(parameter["name"])
    return names


def test_openapi_runtime_status_and_discovery_contracts_reference_schemas() -> None:
    spec = _spec()
    paths = spec["paths"]
    schemas = spec["components"]["schemas"]

    assert {
        "Status",
        "Event",
        "TelemetryResponse",
        "RoutingSummary",
        "FlushTelemetryResult",
        "ReticulumInfo",
        "ReticulumDiscoveryState",
        "ReticulumInterfaceCapabilities",
        "AuthValidationResponse",
    }.issubset(set(schemas))

    expected_get_refs = {
        "/Status": "Status",
        "/Telemetry": "TelemetryResponse",
        "/Command/DumpRouting": "RoutingSummary",
        "/Reticulum/Discovery": "ReticulumDiscoveryState",
        "/Reticulum/Interfaces/Capabilities": "ReticulumInterfaceCapabilities",
        "/api/v1/auth/validate": "AuthValidationResponse",
        "/api/v1/app/info": "ReticulumInfo",
    }
    for path, schema in expected_get_refs.items():
        assert (
            paths[path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
            == f"#/components/schemas/{schema}"
        )

    assert (
        paths["/Events"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["items"]["$ref"]
        == "#/components/schemas/Event"
    )
    telemetry_params = _parameter_names(spec, paths["/Telemetry"]["get"])
    assert {"since", "topic_id"}.issubset(telemetry_params)
    assert (
        paths["/Command/FlushTelemetry"]["post"]["responses"]["200"]["content"]["application/json"]["schema"][
            "$ref"
        ]
        == "#/components/schemas/FlushTelemetryResult"
    )
    assert (
        paths["/Command/ReloadConfig"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/ReticulumInfo"
    )


def test_openapi_config_and_text_doc_contracts_reference_schemas() -> None:
    spec = _spec()
    paths = spec["paths"]
    schemas = spec["components"]["schemas"]

    assert {
        "ConfigApplyResult",
        "ConfigValidation",
        "ConfigRollbackResult",
    }.issubset(set(schemas))

    for path in ("/Help", "/Examples", "/Config", "/Reticulum/Config"):
        assert (
            paths[path]["get"]["responses"]["200"]["content"]["text/plain"]["schema"]["type"]
            == "string"
        )

    for path in ("/Config", "/Reticulum/Config"):
        assert (
            paths[path]["put"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
            == "#/components/schemas/ConfigApplyResult"
        )

    for path in ("/Config/Validate", "/Reticulum/Config/Validate"):
        assert (
            paths[path]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
            == "#/components/schemas/ConfigValidation"
        )

    for path in ("/Config/Rollback", "/Reticulum/Config/Rollback"):
        assert (
            paths[path]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
            == "#/components/schemas/ConfigRollbackResult"
        )


def test_openapi_identity_moderation_contracts_reference_status_schema() -> None:
    spec = _spec()
    paths = spec["paths"]
    schemas = spec["components"]["schemas"]

    assert "IdentityStatus" in schemas
    assert (
        paths["/Identities"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["items"]["$ref"]
        == "#/components/schemas/IdentityStatus"
    )

    for path in ("/Client/{id}/Ban", "/Client/{id}/Unban", "/Client/{id}/Blackhole"):
        operation = paths[path]["post"]
        assert (
            operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
            == "#/components/schemas/IdentityStatus"
        )
        assert "id" in _parameter_names(spec, operation)
