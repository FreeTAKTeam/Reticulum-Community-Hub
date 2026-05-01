"""Routing destination normalization for the gateway API."""

from __future__ import annotations

from typing import Any

import RNS


def routing_destinations_from_hub(hub: Any) -> list[dict[str, str]]:
    """Return connected routing entries with destination, identity, and label."""

    provider = getattr(hub, "routing_destinations", None)
    if callable(provider):
        try:
            normalized: list[dict[str, str]] = []
            for value in provider():
                entry = _normalize_routing_entry(value)
                if entry is None:
                    continue
                normalized.append(entry)
            deduped: list[dict[str, str]] = []
            seen: set[str] = set()
            for entry in normalized:
                destination = entry["destination"]
                if destination in seen:
                    continue
                seen.add(destination)
                deduped.append(entry)
            return deduped
        except Exception as exc:  # pragma: no cover - defensive logging
            RNS.log(
                f"Failed to fetch hub routing destinations: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )

    connections = getattr(hub, "connections", None)
    if connections is None:
        return []
    if hasattr(connections, "values"):
        entries = list(connections.values())
    else:
        entries = list(connections)

    routes: list[dict[str, str]] = []
    for connection in entries:
        destination = _normalize_hash_hex(getattr(connection, "hash", None))
        identity = getattr(connection, "identity", None)
        identity_hash = _normalize_hash_hex(getattr(identity, "hash", None))
        if destination is None:
            destination = identity_hash
        if destination is None:
            continue
        if identity_hash is None:
            identity_hash = destination
        route: dict[str, str] = {
            "destination": destination,
            "identity": identity_hash,
        }
        display_name = _resolve_routing_display_name(
            hub, destination=destination, identity=identity_hash
        )
        if display_name:
            route["display_name"] = display_name
        routes.append(route)

    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for route in routes:
        destination = route["destination"]
        if destination in seen:
            continue
        seen.add(destination)
        deduped.append(route)
    return deduped


def _normalize_hash_hex(value: object) -> str | None:
    """Return a lowercase hex hash string when available."""

    if isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
        return data.hex().lower() if data else None
    if isinstance(value, str):
        cleaned = value.strip().lower()
        return cleaned or None
    hash_value = getattr(value, "hash", None)
    if isinstance(hash_value, (bytes, bytearray, memoryview)):
        data = bytes(hash_value)
        return data.hex().lower() if data else None
    if isinstance(hash_value, str):
        cleaned = hash_value.strip().lower()
        return cleaned or None
    return None


def _resolve_routing_display_name(
    hub: Any, *, destination: str, identity: str
) -> str | None:
    """Resolve a human-readable label for a routing entry."""

    identities = getattr(hub, "identities", None)
    if isinstance(identities, dict):
        for key in (destination, identity):
            value = identities.get(key) or identities.get(key.lower())
            if isinstance(value, str):
                label = value.strip()
                if label:
                    return label

    api = getattr(hub, "api", None)
    resolver = getattr(api, "resolve_identity_display_name", None)
    if callable(resolver):
        for key in (identity, destination):
            try:
                value = resolver(key)
            except Exception:  # pragma: no cover - defensive
                value = None
            if isinstance(value, str):
                label = value.strip()
                if label:
                    return label
    return None


def _normalize_routing_entry(value: object) -> dict[str, str] | None:
    """Normalize provider values into routing-entry dictionaries."""

    if isinstance(value, str):
        destination = _normalize_hash_hex(value)
        if destination is None:
            return None
        return {"destination": destination, "identity": destination}
    if not isinstance(value, dict):
        return None
    destination = _normalize_hash_hex(
        value.get("destination")
        or value.get("Destination")
        or value.get("destination_hash")
        or value.get("destinationHash")
        or value.get("lxmf_destination")
        or value.get("lxmfDestination")
    )
    identity = _normalize_hash_hex(
        value.get("identity")
        or value.get("Identity")
        or value.get("identity_hash")
        or value.get("identityHash")
        or value.get("source_identity")
        or value.get("sourceIdentity")
    )
    if destination is None:
        destination = identity
    if destination is None:
        return None
    if identity is None:
        identity = destination
    normalized: dict[str, str] = {"destination": destination, "identity": identity}
    display_name = value.get("display_name") or value.get("displayName")
    if isinstance(display_name, str):
        label = display_name.strip()
        if label:
            normalized["display_name"] = label
    return normalized
