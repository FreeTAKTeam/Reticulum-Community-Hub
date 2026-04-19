"""Tests for pagination coverage in the static OpenAPI contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


SPEC_PATH = Path("API") / "ReticulumCommunityHub-OAS.yaml"


def _load_spec() -> dict[str, Any]:
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


def test_static_openapi_documents_paginated_list_endpoints() -> None:
    """Verify list endpoints expose pagination params and envelope schemas."""

    spec = _load_spec()
    expected_schemas = {
        "/Client": "PaginatedClientList",
        "/Topic": "PaginatedTopicList",
        "/Subscriber": "PaginatedSubscriberList",
        "/File": "PaginatedFileAttachmentList",
        "/Image": "PaginatedFileAttachmentList",
    }

    for path, schema_name in expected_schemas.items():
        operation = spec["paths"][path]["get"]
        parameters = operation.get("parameters", [])
        assert {"$ref": "#/components/parameters/page"} in parameters
        assert {"$ref": "#/components/parameters/perPage"} in parameters

        if "$ref" in operation["responses"]["200"]:
            response_name = operation["responses"]["200"]["$ref"].split("/")[-1]
            response = spec["components"]["responses"][response_name]
        else:
            response = operation["responses"]["200"]
        one_of = response["content"]["application/json"]["schema"]["oneOf"]
        assert {"$ref": f"#/components/schemas/{schema_name}"} in one_of

