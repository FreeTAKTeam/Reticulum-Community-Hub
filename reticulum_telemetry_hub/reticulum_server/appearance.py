"""Helpers for LXMF icon appearance fields."""

from __future__ import annotations

import os
import re
from typing import Optional

import LXMF
from reticulum_telemetry_hub.api.marker_symbols import normalize_marker_symbol
from reticulum_telemetry_hub.api.marker_symbols import resolve_marker_mdi_name
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_enum import (
    SID_CUSTOM,
)


DEFAULT_ICON_NAME = "person"
DEFAULT_FG_HEX = "FFFFFF"
DEFAULT_BG_HEX = "000000"
ENV_ICON_NAME = "RCH_ICON_APPEARANCE"
ENV_FG_HEX = "RCH_ICON_FG"
ENV_BG_HEX = "RCH_ICON_BG"
EXPLICIT_SYMBOL_COLORS = {
    "friendly": "6BCBEC",
    "hostile": "DE6767",
    "neutral": "9BBB59",
    "unknown": "F1E097",
}
MDI_COLOR_PALETTE = (
    "38BDF8",
    "A78BFA",
    "F59E0B",
    "F87171",
    "22D3EE",
    "94A3B8",
)


def _strip_mdi_prefix(value: str) -> str:
    """Return ``value`` without a leading ``mdi-`` prefix."""

    trimmed = value.strip()
    if trimmed.lower().startswith("mdi-"):
        return trimmed[4:]
    return trimmed


def _normalize_icon_name(value: Optional[str]) -> Optional[str]:
    """Normalize icon names to lowercase MDI-compatible identifiers.

    Args:
        value (Optional[str]): Raw icon name input.

    Returns:
        Optional[str]: Normalized icon identifier or ``None`` when invalid.
    """

    if not value:
        return None
    trimmed = _strip_mdi_prefix(value)
    normalized = re.sub(r"[^a-z0-9-]+", "-", trimmed.strip().lower())
    return normalized.strip("-") or None


def _normalize_hex(value: Optional[str]) -> Optional[str]:
    """Normalize a hex color string to 6 uppercase characters.

    Args:
        value (Optional[str]): Raw hex color string.

    Returns:
        Optional[str]: Normalized 6-character hex string or None if invalid.
    """

    if not value:
        return None
    trimmed = value.strip()
    if trimmed.startswith("#"):
        trimmed = trimmed[1:]
    if re.fullmatch(r"[0-9a-fA-F]{6}", trimmed) is None:
        return None
    return trimmed.upper()


def _hex_to_bytes(value: str) -> bytes:
    """Convert a six-character hex string to 3-byte RGB data.

    Args:
        value (str): Hex string in RRGGBB format.

    Returns:
        bytes: RGB bytes.
    """

    return bytes.fromhex(value)


def _resolve_icon_name(value: Optional[str]) -> str:
    """Resolve the icon name for LXMF appearance.

    Args:
        value (Optional[str]): Requested icon name override.

    Returns:
        str: Resolved icon name.
    """

    candidate = (value or os.getenv(ENV_ICON_NAME) or DEFAULT_ICON_NAME).strip()
    return candidate or DEFAULT_ICON_NAME


def _resolve_color(value: Optional[str], env_key: str, fallback: str) -> str:
    """Resolve a color hex string from input or environment.

    Args:
        value (Optional[str]): Requested color override.
        env_key (str): Environment variable name to check.
        fallback (str): Fallback color when overrides are invalid.

    Returns:
        str: Normalized color hex string.
    """

    candidate = value or os.getenv(env_key)
    normalized = _normalize_hex(candidate)
    return normalized or fallback


def _hash_symbol(value: str) -> int:
    """Return a stable hash for ``value``.

    Args:
        value (str): Input string to hash.

    Returns:
        int: Deterministic non-negative hash.
    """

    accumulator = 0
    for char in value:
        accumulator = (accumulator * 31 + ord(char)) & 0xFFFFFFFF
    return abs(accumulator)


def _resolve_symbol_color_hex(symbol: str) -> str:
    """Return a hex color for a symbol identifier.

    Args:
        symbol (str): Marker or icon identifier.

    Returns:
        str: Hex color (RRGGBB) for the symbol.
    """

    normalized = normalize_marker_symbol(symbol)
    if not normalized:
        normalized = _normalize_icon_name(symbol) or ""
    if normalized in EXPLICIT_SYMBOL_COLORS:
        return EXPLICIT_SYMBOL_COLORS[normalized]
    if not normalized:
        return DEFAULT_BG_HEX
    index = _hash_symbol(normalized) % len(MDI_COLOR_PALETTE)
    return MDI_COLOR_PALETTE[index]


def _extract_custom_icon_and_symbol(
    custom_payload: object,
) -> tuple[Optional[str], Optional[str]]:
    """Return icon and symbol hints from a custom sensor payload.

    Args:
        custom_payload (object): Raw SID_CUSTOM payload.

    Returns:
        tuple[Optional[str], Optional[str]]: ``(icon, symbol)`` hints when found.
    """

    if not custom_payload:
        return None, None

    entries: list[tuple[object, object]] = []
    if isinstance(custom_payload, dict):
        entries = list(custom_payload.items())
    elif isinstance(custom_payload, (list, tuple)):
        for record in custom_payload:
            if isinstance(record, (list, tuple)) and len(record) >= 2:
                entries.append((record[0], record[1]))
    else:
        return None, None

    icon_candidate = None
    symbol_candidate = None
    for _, values in entries:
        if not isinstance(values, (list, tuple)):
            continue
        if len(values) > 1 and isinstance(values[1], str):
            icon_candidate = values[1].strip() or None
        metadata = values[0] if values else None
        if isinstance(metadata, dict):
            for key in (
                "icon",
                "symbol",
                "marker_type",
                "category",
                "type",
                "kind",
                "role",
                "class",
            ):
                candidate = metadata.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    cleaned = candidate.strip()
                    if key == "icon" and icon_candidate is None:
                        icon_candidate = cleaned
                    if symbol_candidate is None:
                        symbol_candidate = cleaned
                    break
        if icon_candidate or symbol_candidate:
            break
    return icon_candidate, symbol_candidate


def build_icon_appearance_payload(
    icon_name: Optional[str] = None,
    fg_hex: Optional[str] = None,
    bg_hex: Optional[str] = None,
) -> dict[int, list[object]]:
    """Return a LXMF icon appearance field payload.

    Args:
        icon_name (Optional[str]): MDI icon name to display.
        fg_hex (Optional[str]): Foreground RGB hex string (RRGGBB).
        bg_hex (Optional[str]): Background RGB hex string (RRGGBB).

    Returns:
        dict[int, list[object]]: LXMF fields payload with icon appearance.
    """

    icon = _resolve_icon_name(icon_name)
    fg_value = _resolve_color(fg_hex, ENV_FG_HEX, DEFAULT_FG_HEX)
    bg_value = _resolve_color(bg_hex, ENV_BG_HEX, DEFAULT_BG_HEX)
    return {
        LXMF.FIELD_ICON_APPEARANCE: [
            icon,
            _hex_to_bytes(fg_value),
            _hex_to_bytes(bg_value),
        ]
    }


def build_icon_appearance_value(
    icon_name: Optional[str] = None,
    fg_hex: Optional[str] = None,
    bg_hex: Optional[str] = None,
) -> list[object]:
    """Return the LXMF icon appearance value list.

    Args:
        icon_name (Optional[str]): MDI icon name to display.
        fg_hex (Optional[str]): Foreground RGB hex string (RRGGBB).
        bg_hex (Optional[str]): Background RGB hex string (RRGGBB).

    Returns:
        list[object]: Appearance list ``[icon_name, fg_rgb_bytes, bg_rgb_bytes]``.
    """

    payload = build_icon_appearance_payload(
        icon_name=icon_name,
        fg_hex=fg_hex,
        bg_hex=bg_hex,
    )
    return payload[LXMF.FIELD_ICON_APPEARANCE]


def build_telemetry_icon_appearance_payload(
    telemetry_payload: Optional[dict[int, object]],
) -> dict[int, list[object]]:
    """Return an icon appearance payload derived from telemetry metadata.

    Args:
        telemetry_payload (Optional[dict[int, object]]): Raw telemetry sensor map.

    Returns:
        dict[int, list[object]]: LXMF icon appearance payload.
    """

    if not isinstance(telemetry_payload, dict):
        return build_icon_appearance_payload()

    custom_payload = telemetry_payload.get(SID_CUSTOM)
    icon_candidate, symbol_candidate = _extract_custom_icon_and_symbol(custom_payload)

    icon_name = _normalize_icon_name(icon_candidate)
    symbol_key = icon_name or None
    if icon_name is None and symbol_candidate:
        normalized_symbol = normalize_marker_symbol(symbol_candidate)
        if normalized_symbol:
            symbol_key = normalized_symbol
            mdi_name = resolve_marker_mdi_name(normalized_symbol) or normalized_symbol
            icon_name = _normalize_icon_name(mdi_name)
        else:
            icon_name = _normalize_icon_name(symbol_candidate)
            symbol_key = icon_name or symbol_candidate

    fg_hex = None
    bg_hex = None
    if symbol_key:
        bg_hex = _resolve_symbol_color_hex(symbol_key)
        fg_hex = DEFAULT_FG_HEX

    return build_icon_appearance_payload(
        icon_name=icon_name,
        fg_hex=fg_hex,
        bg_hex=bg_hex,
    )


def build_telemetry_icon_appearance_value(
    telemetry_payload: Optional[dict[int, object]],
) -> list[object]:
    """Return the icon appearance list derived from telemetry metadata.

    Args:
        telemetry_payload (Optional[dict[int, object]]): Raw telemetry sensor map.

    Returns:
        list[object]: Appearance list ``[icon_name, fg_rgb_bytes, bg_rgb_bytes]``.
    """

    payload = build_telemetry_icon_appearance_payload(telemetry_payload)
    return payload[LXMF.FIELD_ICON_APPEARANCE]


def apply_icon_appearance(fields: Optional[dict]) -> dict:
    """Return fields augmented with icon appearance when missing.

    Args:
        fields (Optional[dict]): Existing LXMF fields payload.

    Returns:
        dict: Fields payload including icon appearance.
    """

    resolved = dict(fields or {})
    if LXMF.FIELD_ICON_APPEARANCE not in resolved:
        resolved.update(build_icon_appearance_payload())
    return resolved
