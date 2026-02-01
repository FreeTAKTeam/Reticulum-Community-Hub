"""Marker symbol definitions and helpers."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import re
from typing import Mapping
from typing import Optional

try:  # pragma: no cover - optional dependency
    import yaml
except ImportError:  # pragma: no cover - optional dependency
    yaml = None


@dataclass(frozen=True)
class SymbolDefinition:
    """Symbol registry entry."""

    symbol_id: str
    mdi: Optional[str] = None
    description: Optional[str] = None
    tak: Optional[str] = None
    category: Optional[str] = None


DEFAULT_SYMBOL_REGISTRY: dict[str, dict[str, str]] = {
    "marker": {
        "mdi": "map-marker",
        "description": "Marker",
        "category": "general",
    },
    "friendly": {
        "mdi": "rectangle",
        "description": "Friendly",
        "category": "nato",
    },
    "hostile": {
        "mdi": "rhombus",
        "description": "Hostile",
        "category": "nato",
    },
    "neutral": {
        "mdi": "square",
        "description": "Neutral",
        "category": "nato",
    },
    "unknown": {
        "mdi": "clover",
        "description": "Unknown",
        "category": "nato",
    },
    "vehicle": {
        "mdi": "car",
        "description": "Vehicle",
        "category": "mobility",
    },
    "drone": {
        "mdi": "drone",
        "description": "Drone",
        "category": "mobility",
    },
    "animal": {
        "mdi": "paw",
        "description": "Animal",
        "category": "wildlife",
    },
    "sensor": {
        "mdi": "radar",
        "description": "Sensor",
        "category": "equipment",
    },
    "radio": {
        "mdi": "radio",
        "description": "Radio",
        "category": "equipment",
    },
    "antenna": {
        "mdi": "antenna",
        "description": "Antenna",
        "category": "equipment",
    },
    "camera": {
        "mdi": "camera",
        "description": "Camera",
        "category": "equipment",
    },
    "fire": {
        "mdi": "fire",
        "description": "Fire",
        "category": "incident",
    },
    "flood": {
        "mdi": "home-flood",
        "description": "Flood",
        "category": "incident",
    },
    "person": {
        "mdi": "account",
        "description": "Person",
        "category": "people",
    },
    "group": {
        "mdi": "account-group",
        "description": "Group / Community",
        "category": "people",
    },
    "infrastructure": {
        "mdi": "office-building",
        "description": "Infrastructure",
        "category": "infrastructure",
    },
    "medic": {
        "mdi": "hospital",
        "description": "Medic",
        "category": "medical",
    },
    "alert": {
        "mdi": "alert",
        "description": "Alert",
        "category": "incident",
    },
    "task": {
        "mdi": "clipboard-check",
        "description": "Task",
        "category": "task",
    },
}

SUPPORTED_MARKER_SYMBOLS = sorted(DEFAULT_SYMBOL_REGISTRY.keys())

_MARKER_SYMBOL_ALIASES: dict[str, str] = {
    "marker": "marker",
    "pin": "marker",
    "location": "marker",
    "vehicle": "vehicle",
    "car": "vehicle",
    "truck": "vehicle",
    "auto": "vehicle",
    "automobile": "vehicle",
    "drone": "drone",
    "uav": "drone",
    "uas": "drone",
    "animal": "animal",
    "wildlife": "animal",
    "pet": "animal",
    "sensor": "sensor",
    "radar": "sensor",
    "telemetry": "sensor",
    "vehicle-sensor": "sensor",
    "radio": "radio",
    "antenna": "antenna",
    "camera": "camera",
    "cctv": "camera",
    "fire": "fire",
    "flame": "fire",
    "wildfire": "fire",
    "flood": "flood",
    "water": "flood",
    "person": "person",
    "human": "person",
    "operator": "person",
    "group": "group",
    "community": "group",
    "group-community": "group",
    "team": "group",
    "infrastructure": "infrastructure",
    "building": "infrastructure",
    "facility": "infrastructure",
    "medic": "medic",
    "medical": "medic",
    "hospital": "medic",
    "alert": "alert",
    "alarm": "alert",
    "warning": "alert",
    "task": "task",
    "mission": "task",
    "assignment": "task",
}

_registry_cache: list[SymbolDefinition] | None = None
_registry_mtime: float | None = None


def _symbol_registry_path() -> Path:
    """Return the configured symbol registry path."""

    env_path = os.getenv("RTH_SYMBOL_REGISTRY_PATH")
    if env_path:
        return Path(env_path)
    return Path(__file__).resolve().parents[2] / "rch-symbols.yaml"


def _normalize_segment(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return normalized.strip("-")


def normalize_marker_symbol(symbol: str) -> str:
    """Normalize marker symbols to canonical keys.

    Args:
        symbol (str): Symbol identifier provided by the client.

    Returns:
        str: Canonical symbol identifier.
    """

    raw = (symbol or "").strip().lower()
    if not raw:
        return ""
    parts = [part for part in raw.split(".") if part.strip()]
    if not parts:
        return ""
    normalized_parts = [_normalize_segment(part) for part in parts]
    normalized = ".".join(part for part in normalized_parts if part)
    if not normalized:
        return ""
    return _MARKER_SYMBOL_ALIASES.get(normalized, normalized)


def _normalize_mdi_name(value: Optional[str], fallback: str) -> Optional[str]:
    if value is None:
        return fallback or None
    if not isinstance(value, str):
        return fallback or None
    normalized = re.sub(r"[^a-z0-9-]+", "-", value.strip().lower())
    return normalized.strip("-") or fallback or None


def _load_registry_payload(path: Path) -> Mapping[str, object]:
    if not path.is_file():
        return {}
    if yaml is None:  # pragma: no cover - optional dependency
        logging.warning(
            "Symbol registry %s is present, but PyYAML is unavailable. Using defaults.",
            path,
        )
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # pragma: no cover - defensive
        logging.warning("Failed to load symbol registry %s: %s", path, exc)
        return {}
    if not isinstance(raw, dict):
        logging.warning("Symbol registry %s must be a mapping. Using defaults.", path)
        return {}
    return raw


def _build_registry_entries(raw: Mapping[str, object]) -> list[SymbolDefinition]:
    entries_by_id: dict[str, SymbolDefinition] = {}

    def _apply_registry(source: Mapping[str, object]) -> None:
        for key, value in source.items():
            if not isinstance(key, str):
                continue
            symbol_id = normalize_marker_symbol(key)
            if not symbol_id:
                continue
            payload = value if isinstance(value, dict) else {}
            description = payload.get("description")
            tak = payload.get("tak")
            category = payload.get("category")
            mdi_name = _normalize_mdi_name(payload.get("mdi"), symbol_id)
            entries_by_id[symbol_id] = SymbolDefinition(
                symbol_id=symbol_id,
                mdi=mdi_name,
                description=description if isinstance(description, str) else None,
                tak=tak if isinstance(tak, str) else None,
                category=category if isinstance(category, str) else None,
            )

    _apply_registry(DEFAULT_SYMBOL_REGISTRY)
    _apply_registry(raw)

    if entries_by_id:
        return list(entries_by_id.values())
    return []


def _load_symbol_registry() -> list[SymbolDefinition]:
    global _registry_cache
    global _registry_mtime

    path = _symbol_registry_path()
    mtime = path.stat().st_mtime if path.exists() else None
    if _registry_cache is not None and _registry_mtime == mtime:
        return _registry_cache
    raw = _load_registry_payload(path)
    entries = _build_registry_entries(raw)
    _registry_cache = entries
    _registry_mtime = mtime
    return entries


def list_marker_symbols() -> list[dict[str, Optional[str]]]:
    """Return marker symbol definitions from the registry.

    Returns:
        list[dict[str, Optional[str]]]: Marker symbol metadata entries.
    """

    symbols = []
    for entry in _load_symbol_registry():
        symbols.append(
            {
                "id": entry.symbol_id,
                "set": "mdi",
                "mdi": entry.mdi,
                "description": entry.description,
                "tak": entry.tak,
                "category": entry.category,
            }
        )
    return symbols


def resolve_marker_mdi_name(symbol: str) -> Optional[str]:
    """Return the MDI icon name for a marker symbol.

    Args:
        symbol (str): Marker symbol identifier.

    Returns:
        Optional[str]: MDI icon name when available.
    """

    normalized = normalize_marker_symbol(symbol)
    if not normalized:
        return None
    for entry in _load_symbol_registry():
        if entry.symbol_id == normalized:
            return entry.mdi or normalized
    return None


def resolve_marker_symbol_set(symbol: str) -> str:
    """Return the symbol set name for a marker symbol.

    Args:
        symbol (str): Symbol identifier provided by the client.

    Returns:
        str: Symbol set identifier ("mdi").

    Raises:
        ValueError: When the symbol is unsupported.
    """

    normalized = normalize_marker_symbol(symbol)
    if normalized and is_supported_marker_symbol(normalized):
        return "mdi"
    raise ValueError(f"Unsupported marker symbol '{symbol}'")


def is_supported_marker_symbol(symbol: str) -> bool:
    """Return True when a marker symbol is supported.

    Args:
        symbol (str): Symbol identifier to check.

    Returns:
        bool: True when supported, False otherwise.
    """

    normalized = normalize_marker_symbol(symbol)
    if not normalized:
        return False
    registry_ids = {entry.symbol_id for entry in _load_symbol_registry()}
    return normalized in registry_ids
