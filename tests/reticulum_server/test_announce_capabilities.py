"""Tests for announce capability payloads."""

import msgpack
import pytest
from pydantic import ValidationError

from reticulum_telemetry_hub.reticulum_server.__main__ import ReticulumTelemetryHub
from reticulum_telemetry_hub.reticulum_server.announce_capabilities import (
    CAPABILITY_PRIORITY,
    append_capabilities_to_announce_app_data,
    build_capability_payload,
    decode_inbound_capability_payload,
    encode_capability_payload,
    normalize_capability_list,
    select_capability_encoder,
)


def test_capability_encoding_is_deterministic():
    encoder = select_capability_encoder()
    payload = build_capability_payload(
        rch_version="1.2.3",
        caps=["telemetry_relay", "topic_broker"],
        roles=None,
        include_timestamp=False,
    )

    first = encode_capability_payload(payload, encoder=encoder, max_bytes=512)
    second = encode_capability_payload(payload, encoder=encoder, max_bytes=512)

    assert first.encoded == second.encoded

    decoded = encoder.decode(first.encoded)
    assert decoded["app"] == "rch"
    assert decoded["schema"] == 1
    assert decoded["caps"] == normalize_capability_list(
        ["telemetry_relay", "topic_broker"], priority=CAPABILITY_PRIORITY
    )


def test_capability_payload_rejects_invalid_caps():
    with pytest.raises(ValidationError):
        build_capability_payload(
            rch_version=None,
            caps=["not-snake"],
            roles=None,
            include_timestamp=False,
        )


def test_capability_truncation_drops_optional_fields_first():
    encoder = select_capability_encoder()
    payload = build_capability_payload(
        rch_version="1.2.3",
        caps=CAPABILITY_PRIORITY,
        roles=["admin"],
        include_timestamp=True,
        timestamp=1700000000,
    )
    payload_dict = payload.model_dump(exclude_none=True, by_alias=True)
    without_ts = dict(payload_dict)
    without_ts.pop("ts", None)
    max_bytes = len(encoder.encode(without_ts))

    result = encode_capability_payload(payload, encoder=encoder, max_bytes=max_bytes)

    assert result.truncated is True
    assert "ts" not in result.payload
    assert "roles" in result.payload
    assert "rch_version" in result.payload


def test_capability_truncation_trims_caps():
    encoder = select_capability_encoder()
    payload = build_capability_payload(
        rch_version="1.2.3",
        caps=CAPABILITY_PRIORITY,
        roles=["admin"],
        include_timestamp=True,
        timestamp=1700000000,
    )
    payload_dict = payload.model_dump(exclude_none=True, by_alias=True)
    for field in ("ts", "roles", "rch_version"):
        payload_dict.pop(field, None)
    one_cap = dict(payload_dict)
    one_cap["caps"] = payload_dict["caps"][:1]
    max_bytes = len(encoder.encode(one_cap))

    result = encode_capability_payload(payload, encoder=encoder, max_bytes=max_bytes)

    assert result.payload["caps"] == payload_dict["caps"][:1]
    assert "ts" not in result.payload
    assert result.truncated is True


def test_append_capabilities_to_announce_app_data():
    encoder = select_capability_encoder()
    payload = build_capability_payload(
        rch_version="1.2.3",
        caps=["telemetry_relay"],
        roles=None,
        include_timestamp=False,
    )
    result = encode_capability_payload(payload, encoder=encoder, max_bytes=512)
    base = msgpack.packb([b"Name", 3], use_bin_type=True)

    combined = append_capabilities_to_announce_app_data(base, result.encoded)
    decoded = msgpack.unpackb(combined, raw=False)

    assert decoded[0] == b"Name"
    assert decoded[1] == 3
    assert decoded[2] == result.encoded


def test_append_capabilities_handles_legacy_app_data():
    encoder = select_capability_encoder()
    payload = build_capability_payload(
        rch_version="1.2.3",
        caps=["telemetry_relay"],
        roles=None,
        include_timestamp=False,
    )
    result = encode_capability_payload(payload, encoder=encoder, max_bytes=512)

    combined = append_capabilities_to_announce_app_data(b"LegacyName", result.encoded)
    decoded = msgpack.unpackb(combined, raw=False)

    assert decoded[0] == b"LegacyName"
    assert decoded[1] is None
    assert decoded[2] == result.encoded


def test_decode_inbound_capability_payload_normalizes_caps() -> None:
    payload = msgpack.packb(
        {"app": "rch", "schema": 1, "caps": ["R3AKT", "Telemetry_Relay"]},
        use_bin_type=True,
    )

    decoded = decode_inbound_capability_payload(payload)

    assert isinstance(decoded, dict)
    assert decoded["caps"] == ["r3akt", "telemetry_relay"]


def test_send_announce_includes_capabilities(tmp_path):
    hub = ReticulumTelemetryHub("Announcer", str(tmp_path), tmp_path / "identity")
    captured: list[bytes | None] = []
    encoder = select_capability_encoder()

    def _announce(*, app_data=None, **_kwargs):
        captured.append(app_data)
        return True

    hub.my_lxmf_dest.announce = _announce

    try:
        assert hub.send_announce() is True
        assert captured
        app_data = captured[-1]
        assert isinstance(app_data, (bytes, bytearray))
        decoded = msgpack.unpackb(app_data, raw=False)
        assert len(decoded) >= 3
        capability_payload = decoded[2]
        decoded_caps = encoder.decode(capability_payload)
        assert decoded_caps["app"] == "rch"
        assert decoded_caps["schema"] == 1
    finally:
        hub.shutdown()


def test_send_announce_emits_propagation_aspect_when_enabled(tmp_path):
    hub = ReticulumTelemetryHub("Announcer", str(tmp_path), tmp_path / "identity")
    propagation_calls: list[bool] = []

    def _announce(*_args, **_kwargs):
        return True

    def _announce_propagation_node(*_args, **_kwargs):
        propagation_calls.append(True)

    hub.my_lxmf_dest.announce = _announce
    hub.lxm_router.propagation_node = True
    hub.lxm_router.announce_propagation_node = _announce_propagation_node

    try:
        assert hub.send_announce() is True
        assert len(propagation_calls) == 1
    finally:
        hub.shutdown()


def test_reannounce_on_capability_change(tmp_path):
    hub = ReticulumTelemetryHub("Announcer", str(tmp_path), tmp_path / "identity")
    captured: list[bytes | None] = []
    encoder = select_capability_encoder()

    def _announce(*, app_data=None, **_kwargs):
        captured.append(app_data)
        return True

    hub.my_lxmf_dest.announce = _announce

    try:
        hub.send_announce()
        assert len(captured) == 1

        hub.tak_connector = None
        hub._refresh_announce_capabilities(trigger_announce=True)

        assert len(captured) == 2
        decoded = msgpack.unpackb(captured[-1], raw=False)
        capability_payload = decoded[2]
        decoded_caps = encoder.decode(capability_payload)
        assert "tak_bridge" not in decoded_caps["caps"]
    finally:
        hub.shutdown()
