from __future__ import annotations

from pathlib import Path

import yaml


def _spec() -> dict:
    return yaml.safe_load(Path("API/ReticulumCommunityHub-OAS.yaml").read_text(encoding="utf-8"))


def test_openapi_marker_contracts_reference_marker_schemas() -> None:
    spec = _spec()
    paths = spec["paths"]
    schemas = spec["components"]["schemas"]

    assert {
        "Marker",
        "MarkerCreateRequest",
        "MarkerPositionUpdate",
        "MarkerSymbol",
    }.issubset(set(schemas))

    assert (
        paths["/api/markers"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["items"]["$ref"]
        == "#/components/schemas/Marker"
    )
    assert (
        paths["/api/markers"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/MarkerCreateRequest"
    )
    assert (
        paths["/api/markers/symbols"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["items"][
            "$ref"
        ]
        == "#/components/schemas/MarkerSymbol"
    )

    position = paths["/api/markers/{object_destination_hash}/position"]["patch"]
    assert (
        position["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/MarkerPositionUpdate"
    )
    assert "object_destination_hash" in {
        parameter["name"] for parameter in position["parameters"]
    }


def test_openapi_zone_contracts_reference_zone_schemas() -> None:
    spec = _spec()
    paths = spec["paths"]
    schemas = spec["components"]["schemas"]

    assert {
        "Zone",
        "ZonePoint",
        "ZoneCreateRequest",
        "ZoneUpdateRequest",
    }.issubset(set(schemas))

    assert (
        paths["/api/zones"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["items"]["$ref"]
        == "#/components/schemas/Zone"
    )
    assert (
        paths["/api/zones"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/ZoneCreateRequest"
    )

    zone_detail = paths["/api/zones/{zone_id}"]
    assert (
        zone_detail["patch"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/ZoneUpdateRequest"
    )
    for method in ("patch", "delete"):
        assert "zone_id" in {
            parameter["name"] for parameter in zone_detail[method]["parameters"]
        }
