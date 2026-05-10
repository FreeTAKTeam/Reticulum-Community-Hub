from __future__ import annotations

from pathlib import Path

import yaml


def _spec() -> dict:
    return yaml.safe_load(Path("API/ReticulumCommunityHub-OAS.yaml").read_text(encoding="utf-8"))


def test_openapi_websocket_stream_contracts_reference_ws_schemas() -> None:
    spec = _spec()
    paths = spec["paths"]
    schemas = spec["components"]["schemas"]

    assert {
        "WsAuthMessage",
        "WsSystemSubscribeMessage",
        "WsAuthOkMessage",
        "WsErrorMessage",
        "WsPingMessage",
        "WsPongMessage",
        "WsSystemStatusMessage",
        "WsSystemEventMessage",
        "WsTelemetrySubscribeMessage",
        "WsTelemetrySnapshotMessage",
        "WsTelemetryUpdateMessage",
        "WsMessageSubscribeMessage",
        "WsMessageSubscribedMessage",
        "WsMessageSendMessage",
        "WsMessageSentMessage",
        "WsMessageReceiveMessage",
    }.issubset(set(schemas))

    expected = {
        "/events/system": (
            "protected",
            "WsSystemStatusMessage",
            "WsSystemSubscribeMessage",
            True,
        ),
        "/telemetry/stream": (
            "public",
            "WsTelemetrySnapshotMessage",
            "WsTelemetrySubscribeMessage",
            False,
        ),
        "/messages/stream": (
            "protected",
            "WsMessageReceiveMessage",
            "WsMessageSendMessage",
            True,
        ),
    }

    for path, (scope, server_schema, client_schema, requires_auth) in expected.items():
        operation = paths[path]["get"]
        assert operation["x-scope"] == scope
        assert operation["x-websocket"] is True
        assert operation["x-ws-protocol"] == "rch-ws-v1"
        assert operation["responses"]["101"]["description"] == (
            "Switching Protocols (WebSocket upgrade)."
        )
        assert {"$ref": f"#/components/schemas/{server_schema}"} in operation[
            "x-ws-server-messages"
        ]
        assert {"$ref": f"#/components/schemas/{client_schema}"} in operation[
            "x-ws-client-messages"
        ]
        assert ("security" in operation) is requires_auth
