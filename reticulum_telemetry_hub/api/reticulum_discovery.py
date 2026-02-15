"""Helpers for exposing Reticulum discovery runtime state safely."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from datetime import timezone
import importlib
import platform
from typing import Any

try:  # pragma: no cover - optional runtime dependency
    import RNS
except Exception:  # pragma: no cover - optional runtime dependency
    RNS = None  # type: ignore[assignment]

try:  # pragma: no cover - optional runtime dependency
    from RNS import Discovery
except Exception:  # pragma: no cover - optional runtime dependency
    Discovery = None  # type: ignore[assignment]


SUPPORTED_INTERFACE_TYPE_IMPORTS: dict[str, tuple[str, str]] = {
    "AutoInterface": ("RNS.Interfaces.AutoInterface", "AutoInterface"),
    "BackboneInterface": ("RNS.Interfaces.BackboneInterface", "BackboneInterface"),
    "TCPServerInterface": ("RNS.Interfaces.TCPInterface", "TCPServerInterface"),
    "TCPClientInterface": ("RNS.Interfaces.TCPInterface", "TCPClientInterface"),
    "UDPInterface": ("RNS.Interfaces.UDPInterface", "UDPInterface"),
    "I2PInterface": ("RNS.Interfaces.I2PInterface", "I2PInterface"),
    "SerialInterface": ("RNS.Interfaces.SerialInterface", "SerialInterface"),
    "KISSInterface": ("RNS.Interfaces.KISSInterface", "KISSInterface"),
    "AX25KISSInterface": ("RNS.Interfaces.AX25KISSInterface", "AX25KISSInterface"),
    "PipeInterface": ("RNS.Interfaces.PipeInterface", "PipeInterface"),
    "RNodeInterface": ("RNS.Interfaces.RNodeInterface", "RNodeInterface"),
    "RNodeMultiInterface": ("RNS.Interfaces.RNodeMultiInterface", "RNodeMultiInterface"),
    # Retained in "all known types" for compatibility checks, but hidden for
    # creation in environments where it is unavailable.
    "RNodeIPInterface": ("RNS.Interfaces.RNodeIPInterface", "RNodeIPInterface"),
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _os_name() -> str:
    system_name = platform.system().strip().lower()
    if system_name.startswith("win"):
        return "windows"
    if system_name.startswith("linux"):
        return "linux"
    if system_name.startswith("darwin"):
        return "darwin"
    return "other"


def _safe_call(callable_obj, default: Any) -> Any:
    if not callable(callable_obj):
        return callable_obj
    try:
        return callable_obj()
    except Exception:
        return default


def _to_json_safe(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _as_sequence(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    if isinstance(value, dict):
        normalized: list[Any] = []
        for key, entry in value.items():
            if isinstance(entry, dict):
                copied = dict(entry)
                copied.setdefault("discovery_hash", _to_json_safe(key))
                normalized.append(copied)
            else:
                normalized.append(entry)
        return normalized
    return []


def _supports_interface_type(interface_type: str, os_name: str) -> bool:
    if RNS is None:
        return False
    if interface_type == "RNodeIPInterface":
        return False
    if interface_type == "BackboneInterface" and os_name != "linux":
        return False
    module_name, class_name = SUPPORTED_INTERFACE_TYPE_IMPORTS[interface_type]
    try:
        module = importlib.import_module(module_name)
        getattr(module, class_name)
        return True
    except Exception:
        return False


def _discoverable_interface_types() -> list[str]:
    if Discovery is None:
        return []
    try:
        available = getattr(Discovery.InterfaceAnnouncer, "DISCOVERABLE_INTERFACE_TYPES", [])
    except Exception:
        return []
    return [str(item) for item in available if isinstance(item, str)]


def _autoconnect_interface_types() -> list[str]:
    if Discovery is None:
        return []
    try:
        available = getattr(Discovery.InterfaceDiscovery, "AUTOCONNECT_TYPES", [])
    except Exception:
        return []
    return [str(item) for item in available if isinstance(item, str)]


def get_interface_capabilities() -> dict[str, Any]:
    """Return runtime capabilities for Reticulum interface configuration."""

    os_name = _os_name()
    all_types = sorted(SUPPORTED_INTERFACE_TYPE_IMPORTS.keys())
    supported_types = sorted(
        [
            interface_type
            for interface_type in all_types
            if _supports_interface_type(interface_type, os_name)
        ]
    )
    unsupported_types = sorted(
        [interface_type for interface_type in all_types if interface_type not in supported_types]
    )

    identity_hash_hex_length = 0
    runtime_active = False
    rns_version = "unavailable"
    if RNS is not None:
        rns_version = str(getattr(RNS, "__version__", "unknown"))
        hash_bits = int(getattr(getattr(RNS, "Reticulum", object), "TRUNCATED_HASHLENGTH", 0) or 0)
        if hash_bits > 0:
            identity_hash_hex_length = ((hash_bits + 7) // 8) * 2
        runtime_active = bool(
            _safe_call(getattr(getattr(RNS, "Reticulum", object), "get_instance", lambda: None), None)
        )

    discoverable_interface_types = sorted(
        [item for item in _discoverable_interface_types() if item in supported_types]
    )
    autoconnect_interface_types = sorted(
        [item for item in _autoconnect_interface_types() if item in supported_types]
    )

    return {
        "runtime_active": runtime_active,
        "os": os_name,
        "identity_hash_hex_length": identity_hash_hex_length,
        "supported_interface_types": supported_types,
        "unsupported_interface_types": unsupported_types,
        "discoverable_interface_types": discoverable_interface_types,
        "autoconnect_interface_types": autoconnect_interface_types,
        "rns_version": rns_version,
    }


def get_discovery_snapshot() -> dict[str, Any]:
    """Return a normalized snapshot of Reticulum discovery state."""

    payload: dict[str, Any] = {
        "runtime_active": False,
        "should_autoconnect": False,
        "max_autoconnected_interfaces": None,
        "required_discovery_value": None,
        "interface_discovery_sources": [],
        "discovered_interfaces": [],
        "refreshed_at": _utcnow_iso(),
    }
    if RNS is None:
        return payload

    reticulum_class = getattr(RNS, "Reticulum", None)
    if reticulum_class is None:
        return payload
    runtime_instance = _safe_call(getattr(reticulum_class, "get_instance", lambda: None), None)
    if runtime_instance is None:
        return payload

    payload["runtime_active"] = True
    payload["should_autoconnect"] = bool(
        _safe_call(getattr(reticulum_class, "should_autoconnect_discovered_interfaces"), False)
    )
    payload["max_autoconnected_interfaces"] = _safe_call(
        getattr(reticulum_class, "max_autoconnected_interfaces"), None
    )
    payload["required_discovery_value"] = _safe_call(
        getattr(reticulum_class, "required_discovery_value"), None
    )
    source_identities = _safe_call(getattr(reticulum_class, "interface_discovery_sources"), [])
    if isinstance(source_identities, Iterable) and not isinstance(source_identities, (str, bytes, bytearray)):
        payload["interface_discovery_sources"] = [
            str(_to_json_safe(value)) for value in source_identities if value is not None
        ]

    discovered_interfaces = _safe_call(getattr(reticulum_class, "discovered_interfaces"), [])
    discovered_sequence = _as_sequence(discovered_interfaces)

    required_keys = [
        "discovery_hash",
        "status",
        "status_code",
        "type",
        "name",
        "transport",
        "transport_id",
        "network_id",
        "hops",
        "value",
        "received",
        "last_heard",
        "heard_count",
    ]
    optional_keys = [
        "reachable_on",
        "port",
        "latitude",
        "longitude",
        "height",
        "frequency",
        "bandwidth",
        "sf",
        "cr",
        "modulation",
        "channel",
        "config_entry",
    ]

    normalized: list[dict[str, Any]] = []
    for entry in discovered_sequence:
        if not isinstance(entry, dict):
            continue
        normalized_entry: dict[str, Any] = {}
        for key in required_keys:
            normalized_entry[key] = _to_json_safe(entry.get(key))
        if normalized_entry["discovery_hash"] is None:
            # Keep a deterministic hash when runtimes expose keyed dictionaries.
            fallback_hash = entry.get("hash") or entry.get("id")
            if fallback_hash is not None:
                normalized_entry["discovery_hash"] = _to_json_safe(fallback_hash)
        for key in optional_keys:
            if key in entry:
                normalized_entry[key] = _to_json_safe(entry.get(key))
        normalized.append(normalized_entry)
    payload["discovered_interfaces"] = normalized
    return payload


__all__ = ["get_discovery_snapshot", "get_interface_capabilities"]
