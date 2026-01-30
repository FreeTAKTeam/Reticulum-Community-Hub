"""Tests for northbound payload models."""

import pytest
from pydantic import ValidationError

from reticulum_telemetry_hub.northbound.models import ChatSendPayload
from reticulum_telemetry_hub.northbound.models import MarkerCreatePayload
from reticulum_telemetry_hub.northbound.models import MarkerPositionPayload
from reticulum_telemetry_hub.northbound.models import MessagePayload


def test_message_payload_accepts_pascal_case_keys() -> None:
    """Ensure message payload accepts PascalCase keys."""

    payload = MessagePayload.model_validate(
        {
            "Content": "hello",
            "TopicID": "weather",
            "Destination": "abcd1234",
        }
    )

    assert payload.content == "hello"
    assert payload.topic_id == "weather"
    assert payload.destination == "abcd1234"


def test_chat_send_payload_accepts_pascal_case_aliases() -> None:
    """Ensure chat payload accepts PascalCase aliases."""

    payload = ChatSendPayload.model_validate(
        {
            "Content": "hello",
            "Scope": "topic",
            "TopicID": "updates",
            "FileIDs": [1, 2],
            "ImageIDs": [3],
        }
    )

    assert payload.content == "hello"
    assert payload.scope == "topic"
    assert payload.topic_id == "updates"
    assert payload.file_ids == [1, 2]
    assert payload.image_ids == [3]


def test_chat_send_payload_prefers_field_names_over_aliases() -> None:
    """Ensure canonical keys win when aliases are also supplied."""

    payload = ChatSendPayload.model_validate(
        {
            "content": "keep",
            "Content": "drop",
            "scope": "topic",
            "Scope": "dm",
            "TopicID": "news",
        }
    )

    assert payload.content == "keep"
    assert payload.scope == "topic"
    assert payload.topic_id == "news"


def test_chat_send_payload_rejects_invalid_scope() -> None:
    """Ensure invalid scopes raise validation errors."""

    with pytest.raises(ValidationError):
        ChatSendPayload.model_validate({"Content": "hello", "Scope": "invalid"})


def test_marker_payload_accepts_supported_symbols() -> None:
    """Ensure marker payload accepts supported marker symbols."""

    payload = MarkerCreatePayload.model_validate(
        {
            "name": "Alpha",
            "type": "fire",
            "symbol": "fire",
            "category": "napsg",
            "lat": 1.0,
            "lon": 2.0,
        }
    )

    assert payload.marker_type == "fire"
    assert payload.symbol == "fire"
    assert payload.category == "napsg"


def test_marker_payload_rejects_unknown_type() -> None:
    """Ensure marker payload rejects unsupported types."""

    with pytest.raises(ValidationError):
        MarkerCreatePayload.model_validate(
            {
                "name": "Alpha",
                "type": "mystery-type",
                "symbol": "fire",
                "lat": 1.0,
                "lon": 2.0,
            }
        )


def test_marker_payload_rejects_unknown_symbol() -> None:
    """Ensure marker payload rejects unsupported symbols."""

    with pytest.raises(ValidationError):
        MarkerCreatePayload.model_validate(
            {
                "name": "Alpha",
                "type": "fire",
                "symbol": "mystery-symbol",
                "lat": 1.0,
                "lon": 2.0,
            }
        )


def test_marker_position_payload_bounds() -> None:
    """Ensure marker position payload enforces coordinate bounds."""

    with pytest.raises(ValidationError):
        MarkerPositionPayload.model_validate({"lat": -95.0, "lon": 0.0})
