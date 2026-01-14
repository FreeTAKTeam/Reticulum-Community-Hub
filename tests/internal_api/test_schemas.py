"""Tests for internal API schemas."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
import random
from uuid import uuid4

import pytest
from pydantic import ValidationError

from reticulum_telemetry_hub.internal_api.v1.enums import CommandType
from reticulum_telemetry_hub.internal_api.v1.enums import EventType
from reticulum_telemetry_hub.internal_api.v1.enums import QueryType
from reticulum_telemetry_hub.internal_api.v1.schemas import CommandEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import EventEnvelope
from reticulum_telemetry_hub.internal_api.v1.schemas import PublishMessagePayload
from reticulum_telemetry_hub.internal_api.v1.schemas import QueryEnvelope


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_command_envelope_round_trip() -> None:
    payload = {
        "api_version": "1.0",
        "command_id": str(uuid4()),
        "command_type": "RegisterNode",
        "issued_at": _iso_now(),
        "issuer": {"type": "reticulum", "id": "node-1"},
        "payload": {
            "node_id": "node-1",
            "node_type": "reticulum",
            "metadata": {
                "name": "Node One",
                "capabilities": ["telemetry"],
                "location": {"lat": 1.0, "lon": 2.0},
            },
        },
    }

    model = CommandEnvelope.model_validate(payload)
    dumped = model.model_dump()

    assert dumped["command_type"] == CommandType.REGISTER_NODE
    assert dumped["payload"]["node_id"] == "node-1"


def test_event_envelope_round_trip() -> None:
    payload = {
        "api_version": "1.0",
        "event_id": str(uuid4()),
        "event_type": "NodeRegistered",
        "occurred_at": _iso_now(),
        "origin": "hub-core",
        "payload": {"node_id": "node-1", "node_type": "reticulum"},
    }

    model = EventEnvelope.model_validate(payload)
    dumped = model.model_dump()

    assert dumped["event_type"] == EventType.NODE_REGISTERED
    assert dumped["payload"]["node_id"] == "node-1"


def test_query_envelope_round_trip() -> None:
    payload = {
        "api_version": "1.0",
        "query_id": str(uuid4()),
        "query_type": "GetTopics",
        "issued_at": _iso_now(),
        "payload": {"prefix": "ops"},
    }

    model = QueryEnvelope.model_validate(payload)
    dumped = model.model_dump()

    assert dumped["query_type"] == QueryType.GET_TOPICS
    assert dumped["payload"]["prefix"] == "ops"


def test_unknown_fields_rejected() -> None:
    payload = {
        "api_version": "1.0",
        "command_id": str(uuid4()),
        "command_type": "RegisterNode",
        "issued_at": _iso_now(),
        "issuer": {"type": "reticulum", "id": "node-1"},
        "payload": {"node_id": "node-1", "node_type": "reticulum"},
        "extra_field": "nope",
    }

    with pytest.raises(ValidationError) as exc:
        CommandEnvelope.model_validate(payload)

    assert exc.value.errors()[0]["type"] == "extra_forbidden"


def test_missing_required_field_rejected() -> None:
    payload = {
        "api_version": "1.0",
        "command_type": "RegisterNode",
        "issued_at": _iso_now(),
        "issuer": {"type": "reticulum", "id": "node-1"},
        "payload": {"node_id": "node-1", "node_type": "reticulum"},
    }

    with pytest.raises(ValidationError):
        CommandEnvelope.model_validate(payload)


def test_version_major_mismatch_rejected() -> None:
    payload = {
        "api_version": "2.0",
        "query_id": str(uuid4()),
        "query_type": "GetTopics",
        "issued_at": _iso_now(),
        "payload": {"prefix": "ops"},
    }

    with pytest.raises(ValidationError) as exc:
        QueryEnvelope.model_validate(payload)

    assert exc.value.errors()[0]["type"] == "API_VERSION_UNSUPPORTED"


def test_version_minor_higher_accepted() -> None:
    payload = {
        "api_version": "1.2",
        "query_id": str(uuid4()),
        "query_type": "GetTopics",
        "issued_at": _iso_now(),
        "payload": {"prefix": "ops"},
    }

    model = QueryEnvelope.model_validate(payload)

    assert model.api_version == "1.2"


def test_version_format_rejected() -> None:
    payload = {
        "api_version": "1.0.0",
        "query_id": str(uuid4()),
        "query_type": "GetTopics",
        "issued_at": _iso_now(),
        "payload": {"prefix": "ops"},
    }

    with pytest.raises(ValidationError) as exc:
        QueryEnvelope.model_validate(payload)

    assert exc.value.errors()[0]["type"] == "API_VERSION_UNSUPPORTED"


def test_publish_message_content_mismatch_rejected() -> None:
    payload = {
        "topic_path": "ops",
        "message_type": "text",
        "content": {
            "message_type": "event",
            "event_name": "alert",
            "attributes": {"level": "high"},
        },
        "qos": "best_effort",
    }

    with pytest.raises(ValidationError) as exc:
        PublishMessagePayload.model_validate(payload)

    assert exc.value.errors()[0]["type"] == "MESSAGE_TYPE_MISMATCH"


def test_command_payload_mismatch_rejected() -> None:
    payload = {
        "api_version": "1.0",
        "command_id": str(uuid4()),
        "command_type": "CreateTopic",
        "issued_at": _iso_now(),
        "issuer": {"type": "api", "id": "gateway"},
        "payload": {
            "node_id": "node-1",
            "node_type": "reticulum",
        },
    }

    with pytest.raises(ValidationError) as exc:
        CommandEnvelope.model_validate(payload)

    assert exc.value.errors()[0]["type"] == "COMMAND_PAYLOAD_MISMATCH"


def test_query_payload_mismatch_rejected() -> None:
    payload = {
        "api_version": "1.0",
        "query_id": str(uuid4()),
        "query_type": "GetSubscribers",
        "issued_at": _iso_now(),
        "payload": {"prefix": "ops"},
    }

    with pytest.raises(ValidationError) as exc:
        QueryEnvelope.model_validate(payload)

    assert exc.value.errors()[0]["type"] == "QUERY_PAYLOAD_MISMATCH"


def test_register_node_metadata_rejects_unknown_fields() -> None:
    payload = {
        "api_version": "1.0",
        "command_id": str(uuid4()),
        "command_type": "RegisterNode",
        "issued_at": _iso_now(),
        "issuer": {"type": "reticulum", "id": "node-1"},
        "payload": {
            "node_id": "node-1",
            "node_type": "reticulum",
            "metadata": {"unknown": "nope"},
        },
    }

    with pytest.raises(ValidationError) as exc:
        CommandEnvelope.model_validate(payload)

    assert exc.value.errors()[0]["type"] == "extra_forbidden"


def test_command_fuzz_rejects_malformed_payloads() -> None:
    random.seed(0)
    base = {
        "api_version": "1.0",
        "command_id": str(uuid4()),
        "command_type": "RegisterNode",
        "issued_at": _iso_now(),
        "issuer": {"type": "reticulum", "id": "node-1"},
        "payload": {"node_id": "node-1", "node_type": "reticulum"},
    }
    mutations = [
        {"command_id": 123},
        {"issued_at": 123},
        {"issuer": "bad"},
        {"payload": "bad"},
        {"api_version": "nope"},
        {"command_type": "Unknown"},
        {"payload": {"node_id": "node-1"}},
    ]

    for mutation in mutations:
        malformed = dict(base)
        malformed.update(mutation)
        with pytest.raises(ValidationError):
            CommandEnvelope.model_validate(malformed)
