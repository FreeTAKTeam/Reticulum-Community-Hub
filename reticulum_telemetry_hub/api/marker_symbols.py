"""Marker symbol definitions and helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


_DEFAULT_NAPSG_SYMBOLS = {
    "fire",
    "hazmat",
    "medical",
    "police",
    "search",
    "shelter",
}

_DEFAULT_MAKI_SYMBOLS = {
    "marker",
    "town-hall",
    "dog-park",
    "hospital",
    "bus",
    "airfield",
}


def _icon_root() -> Path:
    """Return the repository icon root path when present."""

    return Path(__file__).resolve().parents[2] / "ui" / "public" / "icons"


def _load_symbol_set(symbol_set: str, defaults: Iterable[str]) -> set[str]:
    """Load marker symbols from the UI icon directory when available.

    Args:
        symbol_set (str): Icon subdirectory name (napsg or maki).
        defaults (Iterable[str]): Fallback symbol identifiers.

    Returns:
        set[str]: Resolved symbol identifiers.
    """

    root = _icon_root() / symbol_set
    if not root.is_dir():
        return {item for item in defaults}
    symbols = {
        path.stem
        for path in root.glob("*.svg")
        if path.is_file() and path.stem
    }
    return symbols or {item for item in defaults}


NAPSG_SYMBOLS = _load_symbol_set("napsg", _DEFAULT_NAPSG_SYMBOLS)
MAKI_SYMBOLS = _load_symbol_set("maki", _DEFAULT_MAKI_SYMBOLS)
SUPPORTED_MARKER_SYMBOLS = sorted(NAPSG_SYMBOLS | MAKI_SYMBOLS)


def list_marker_symbols() -> list[dict[str, str]]:
    """Return marker symbol definitions grouped by icon set.

    Returns:
        list[dict[str, str]]: Marker symbol metadata entries.
    """

    return [
        {"id": symbol, "set": "napsg"} for symbol in sorted(NAPSG_SYMBOLS)
    ] + [{"id": symbol, "set": "maki"} for symbol in sorted(MAKI_SYMBOLS)]


def resolve_marker_symbol_set(symbol: str) -> str:
    """Return the symbol set name for a marker symbol.

    Args:
        symbol (str): Symbol identifier provided by the client.

    Returns:
        str: Symbol set identifier ("napsg" or "maki").

    Raises:
        ValueError: When the symbol is unsupported.
    """

    normalized = (symbol or "").strip().lower()
    if normalized in NAPSG_SYMBOLS:
        return "napsg"
    if normalized in MAKI_SYMBOLS:
        return "maki"
    raise ValueError(f"Unsupported marker symbol '{symbol}'")


def is_supported_marker_symbol(symbol: str) -> bool:
    """Return True when a marker symbol is supported.

    Args:
        symbol (str): Symbol identifier to check.

    Returns:
        bool: True when supported, False otherwise.
    """

    normalized = (symbol or "").strip().lower()
    return normalized in NAPSG_SYMBOLS or normalized in MAKI_SYMBOLS
