"""Tests for shared message delivery contract helpers."""

from __future__ import annotations

import pytest

from reticulum_telemetry_hub.message_delivery import DeliveryContractError
from reticulum_telemetry_hub.message_delivery import build_delivery_envelope
from reticulum_telemetry_hub.message_delivery import classify_delivery_mode
from reticulum_telemetry_hub.message_delivery import deserialize_topic_id
from reticulum_telemetry_hub.message_delivery import normalize_topic_id
from reticulum_telemetry_hub.message_delivery import serialize_topic_id
from reticulum_telemetry_hub.message_delivery import validate_delivery_envelope


def test_topic_id_round_trip_preserves_canonical_bytes() -> None:
    topic_id = normalize_topic_id("Ops.Alpha")

    assert topic_id == "Ops.Alpha"
    serialized = serialize_topic_id(topic_id)
    restored = deserialize_topic_id(serialized)

    assert serialized == restored.encode("utf-8")
    assert restored == topic_id


def test_build_delivery_envelope_rejects_unknown_content_type() -> None:
    with pytest.raises(DeliveryContractError, match="Unsupported Content-Type"):
        build_delivery_envelope(
            sender="deadbeef",
            content_type="application/xml",
        )


def test_validate_delivery_envelope_rejects_expired_message() -> None:
    envelope = build_delivery_envelope(
        sender="deadbeef",
        ttl_seconds=1,
        born_at_ms=1_000,
    )

    with pytest.raises(DeliveryContractError, match="exceeded TTL"):
        validate_delivery_envelope(envelope.to_dict(), now_ms=3_000)


def test_classify_delivery_mode_rejects_mixed_coordinates() -> None:
    with pytest.raises(DeliveryContractError, match="mutually exclusive"):
        classify_delivery_mode(topic_id="ops.alpha", destination="deadbeef")
