"""Tests for marker symbol helpers."""

from reticulum_telemetry_hub.api.marker_symbols import list_marker_symbols


def test_list_marker_symbols_includes_defaults() -> None:
    """Ensure the symbol list includes default icon entries."""

    symbols = list_marker_symbols()
    ids = {(entry["id"], entry["set"]) for entry in symbols}

    assert ("marker", "mdi") in ids
    assert ("vehicle", "mdi") in ids
