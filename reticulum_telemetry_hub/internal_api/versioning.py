"""API version negotiation utilities for the internal contract."""

from __future__ import annotations

import re
from typing import Iterable
from typing import Optional

from reticulum_telemetry_hub.internal_api.v1.schemas import SUPPORTED_API_VERSION


_VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)")


class ApiVersionError(ValueError):
    """Raised when API version negotiation fails."""


def parse_api_version(value: str) -> tuple[int, int]:
    """Parse a semantic API version string (major.minor)."""

    match = _VERSION_PATTERN.fullmatch(value)
    if not match:
        raise ApiVersionError("Invalid API version format")
    return int(match.group(1)), int(match.group(2))


def is_version_compatible(
    candidate: str, *, supported: str = SUPPORTED_API_VERSION
) -> bool:
    """Return True when candidate is compatible with supported."""

    try:
        major, minor = parse_api_version(candidate)
        supported_major, supported_minor = parse_api_version(supported)
    except ApiVersionError:
        return False
    return major == supported_major and minor >= supported_minor


def negotiate_api_version(
    peer_versions: Iterable[str], *, supported: str = SUPPORTED_API_VERSION
) -> Optional[str]:
    """Return the negotiated API version or None if incompatible."""

    if any(is_version_compatible(version, supported=supported) for version in peer_versions):
        return supported
    return None


def select_api_version(
    peer_versions: Optional[Iterable[str]] = None,
    *,
    supported: str = SUPPORTED_API_VERSION,
) -> str:
    """Select a compatible API version or raise ApiVersionError."""

    if not peer_versions:
        return supported
    negotiated = negotiate_api_version(peer_versions, supported=supported)
    if negotiated is None:
        raise ApiVersionError("No compatible API version")
    return negotiated
