"""Tests for marker symbol helpers."""

from reticulum_telemetry_hub.api.marker_symbols import list_marker_symbols
from reticulum_telemetry_hub.api.marker_symbols import resolve_marker_mdi_name


def test_list_marker_symbols_includes_defaults() -> None:
    """Ensure the symbol list includes default icon entries."""

    symbols = list_marker_symbols()
    ids = {(entry["id"], entry["set"]) for entry in symbols}

    assert ("marker", "mdi") in ids
    assert ("vehicle", "mdi") in ids


def test_resolve_marker_mdi_name_uses_registry() -> None:
    """Return the MDI icon name for known symbols."""

    assert resolve_marker_mdi_name("person") == "account"


def test_resolve_marker_mdi_name_returns_none_for_unknown() -> None:
    """Return None for unsupported symbols."""

    assert resolve_marker_mdi_name("missing-symbol") is None
