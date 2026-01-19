"""Tests for marker symbol helpers."""

from reticulum_telemetry_hub.api.marker_symbols import list_marker_symbols


def test_list_marker_symbols_includes_defaults() -> None:
    """Ensure the symbol list includes default icon entries."""

    symbols = list_marker_symbols()
    ids = {(entry["id"], entry["set"]) for entry in symbols}

    assert ("fire", "napsg") in ids
    assert ("marker", "maki") in ids
