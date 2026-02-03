"""Tests for LXMF appearance helpers."""

import LXMF
from reticulum_telemetry_hub.reticulum_server.appearance import DEFAULT_BG_HEX
from reticulum_telemetry_hub.reticulum_server.appearance import DEFAULT_FG_HEX
from reticulum_telemetry_hub.reticulum_server.appearance import DEFAULT_ICON_NAME
from reticulum_telemetry_hub.reticulum_server.appearance import apply_icon_appearance
from reticulum_telemetry_hub.reticulum_server.appearance import build_icon_appearance_payload
from reticulum_telemetry_hub.reticulum_server.appearance import build_icon_appearance_value
from reticulum_telemetry_hub.reticulum_server.appearance import (
    build_telemetry_icon_appearance_payload,
)
from reticulum_telemetry_hub.reticulum_server.appearance import (
    build_telemetry_icon_appearance_value,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_enum import (
    SID_CUSTOM,
)


def test_build_icon_appearance_payload_defaults() -> None:
    """Use defaults when no overrides are provided."""

    payload = build_icon_appearance_payload()

    icon, bg_bytes, fg_bytes = payload[LXMF.FIELD_ICON_APPEARANCE]
    assert icon == DEFAULT_ICON_NAME
    assert bg_bytes == bytes.fromhex(DEFAULT_BG_HEX)
    assert fg_bytes == bytes.fromhex(DEFAULT_FG_HEX)


def test_build_icon_appearance_payload_env_overrides(monkeypatch) -> None:
    """Allow environment overrides for icon and colors."""

    monkeypatch.setenv("RCH_ICON_APPEARANCE", "hiking")
    monkeypatch.setenv("RCH_ICON_FG", "FF00FF")
    monkeypatch.setenv("RCH_ICON_BG", "#00FF00")

    payload = build_icon_appearance_payload()
    icon, bg_bytes, fg_bytes = payload[LXMF.FIELD_ICON_APPEARANCE]

    assert icon == "hiking"
    assert bg_bytes == b"\x00\xff\x00"
    assert fg_bytes == b"\xff\x00\xff"


def test_build_icon_appearance_value_matches_payload() -> None:
    """Return the appearance list used by the payload helper."""

    payload = build_icon_appearance_payload()
    value = build_icon_appearance_value()

    assert value == payload[LXMF.FIELD_ICON_APPEARANCE]


def test_apply_icon_appearance_preserves_existing() -> None:
    """Keep explicit appearance fields intact."""

    existing = {
        LXMF.FIELD_ICON_APPEARANCE: ["custom", b"\x01\x02\x03", b"\x04\x05\x06"]
    }
    merged = apply_icon_appearance(existing)

    assert merged[LXMF.FIELD_ICON_APPEARANCE] == existing[LXMF.FIELD_ICON_APPEARANCE]
    assert merged is not existing


def test_apply_icon_appearance_adds_to_fields() -> None:
    """Add appearance when missing."""

    original = {LXMF.FIELD_THREAD: "topic"}
    merged = apply_icon_appearance(original)

    assert LXMF.FIELD_THREAD in merged
    assert LXMF.FIELD_ICON_APPEARANCE in merged
    assert original == {LXMF.FIELD_THREAD: "topic"}


def test_build_telemetry_icon_appearance_payload_uses_symbol_metadata() -> None:
    """Derive icon names and colors from marker metadata."""

    payload = {
        SID_CUSTOM: [["marker", [{"symbol": "friendly"}, None]]],
    }
    appearance = build_telemetry_icon_appearance_payload(payload)
    icon, bg_bytes, fg_bytes = appearance[LXMF.FIELD_ICON_APPEARANCE]

    assert icon == "rectangle"
    assert bg_bytes == bytes.fromhex("6BCBEC")
    assert fg_bytes == bytes.fromhex(DEFAULT_FG_HEX)


def test_build_telemetry_icon_appearance_value_matches_payload() -> None:
    """Return the telemetry-derived appearance list."""

    payload = {
        SID_CUSTOM: [["marker", [{"symbol": "friendly"}, None]]],
    }
    value = build_telemetry_icon_appearance_value(payload)
    appearance = build_telemetry_icon_appearance_payload(payload)

    assert value == appearance[LXMF.FIELD_ICON_APPEARANCE]


def test_build_telemetry_icon_appearance_payload_falls_back_without_custom() -> None:
    """Fallback to defaults when no custom metadata exists."""

    appearance = build_telemetry_icon_appearance_payload({})
    icon, bg_bytes, fg_bytes = appearance[LXMF.FIELD_ICON_APPEARANCE]

    assert icon == DEFAULT_ICON_NAME
    assert bg_bytes == bytes.fromhex(DEFAULT_BG_HEX)
    assert fg_bytes == bytes.fromhex(DEFAULT_FG_HEX)


def test_build_telemetry_icon_appearance_payload_handles_invalid_custom() -> None:
    """Ignore malformed custom payloads."""

    payload = {SID_CUSTOM: "invalid"}
    appearance = build_telemetry_icon_appearance_payload(payload)
    icon, bg_bytes, fg_bytes = appearance[LXMF.FIELD_ICON_APPEARANCE]

    assert icon == DEFAULT_ICON_NAME
    assert bg_bytes == bytes.fromhex(DEFAULT_BG_HEX)
    assert fg_bytes == bytes.fromhex(DEFAULT_FG_HEX)
