from __future__ import annotations

from pathlib import Path

import yaml


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: UniqueKeyLoader, node: yaml.Node, deep: bool = False) -> dict:
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise AssertionError(f"Duplicate OpenAPI YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _spec() -> dict:
    return yaml.safe_load(Path("API/ReticulumCommunityHub-OAS.yaml").read_text(encoding="utf-8"))


def test_openapi_yaml_uses_unique_mapping_keys() -> None:
    yaml.load(
        Path("API/ReticulumCommunityHub-OAS.yaml").read_text(encoding="utf-8"),
        Loader=UniqueKeyLoader,
    )


def _parameter_names(spec: dict, operation: dict) -> set[str]:
    names = set()
    for parameter in operation.get("parameters", []):
        if "$ref" in parameter:
            name = parameter["$ref"].rsplit("/", 1)[-1]
            parameter = spec["components"]["parameters"][name]
        names.add(parameter["name"])
    return names


def test_openapi_topic_and_subscriber_detail_contracts_reference_schemas() -> None:
    spec = _spec()
    paths = spec["paths"]
    schemas = spec["components"]["schemas"]

    assert {"Topic", "Subscriber"}.issubset(set(schemas))
    assert schemas["Topic"]["required"] == ["TopicName", "TopicPath"]
    for nested_schema in (
        "FileAttachment",
        "MarkerSymbol",
        "Marker",
        "Zone",
        "Client",
    ):
        assert nested_schema not in schemas["Topic"]

    assert (
        paths["/Topic/{id}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/Topic"
    )
    assert "id" in _parameter_names(spec, paths["/Topic/{id}"]["get"])
    assert (
        paths["/Topic/Associate"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/Topic"
    )
    assert (
        paths["/Topic/Subscribe"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/Subscriber"
    )
    assert (
        paths["/Subscriber/{id}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/Subscriber"
    )
    assert "id" in _parameter_names(spec, paths["/Subscriber/{id}"]["get"])
    assert (
        paths["/Subscriber/Add"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/Subscriber"
    )


def test_openapi_file_and_image_detail_contracts_reference_attachment_schema() -> None:
    spec = _spec()
    paths = spec["paths"]
    schemas = spec["components"]["schemas"]

    assert "FileAttachment" in schemas
    for route in ("/File/{id}", "/Image/{id}"):
        for method in ("get", "delete"):
            operation = paths[route][method]
            assert (
                operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
                == "#/components/schemas/FileAttachment"
            )
            assert "id" in _parameter_names(spec, operation)

    for route in ("/File/{id}/raw", "/Image/{id}/raw"):
        operation = paths[route]["get"]
        assert (
            operation["responses"]["200"]["content"]["application/octet-stream"]["schema"]["type"]
            == "string"
        )
        assert "id" in _parameter_names(spec, operation)


def test_openapi_message_contract_references_send_result_schema() -> None:
    spec = _spec()
    operation = spec["paths"]["/Message"]["post"]

    assert (
        operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/MessageRequest"
    )
    assert (
        operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/MessageSendResult"
    )
