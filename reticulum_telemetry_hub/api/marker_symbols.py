"""Marker symbol definitions and helpers."""

from __future__ import annotations


NAPSG_SYMBOLS = {
    "fire",
    "hazmat",
    "medical",
    "police",
    "search",
    "shelter",
}

MAKI_SYMBOLS = {
    "marker",
    "town-hall",
    "dog-park",
    "hospital",
    "bus",
    "airfield",
}

SUPPORTED_MARKER_SYMBOLS = sorted(NAPSG_SYMBOLS | MAKI_SYMBOLS)


def resolve_marker_symbol_set(category: str) -> str:
    """Return the symbol set name for a marker category.

    Args:
        category (str): Symbol identifier provided by the client.

    Returns:
        str: Symbol set identifier ("napsg" or "maki").

    Raises:
        ValueError: When the category is unsupported.
    """

    normalized = (category or "").strip().lower()
    if normalized in NAPSG_SYMBOLS:
        return "napsg"
    if normalized in MAKI_SYMBOLS:
        return "maki"
    raise ValueError(f"Unsupported marker category '{category}'")


def is_supported_marker_symbol(category: str) -> bool:
    """Return True when a marker category is supported.

    Args:
        category (str): Symbol identifier to check.

    Returns:
        bool: True when supported, False otherwise.
    """

    normalized = (category or "").strip().lower()
    return normalized in NAPSG_SYMBOLS or normalized in MAKI_SYMBOLS
