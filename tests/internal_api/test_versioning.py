"""Tests for internal API version negotiation helpers."""

from __future__ import annotations

import pytest

from reticulum_telemetry_hub.internal_api.versioning import ApiVersionError
from reticulum_telemetry_hub.internal_api.versioning import is_version_compatible
from reticulum_telemetry_hub.internal_api.versioning import negotiate_api_version
from reticulum_telemetry_hub.internal_api.versioning import parse_api_version
from reticulum_telemetry_hub.internal_api.versioning import select_api_version


def test_parse_api_version_valid() -> None:
    assert parse_api_version("1.0") == (1, 0)


def test_parse_api_version_invalid() -> None:
    with pytest.raises(ApiVersionError):
        parse_api_version("1.0.0")


def test_version_compatibility_rules() -> None:
    assert is_version_compatible("1.2", supported="1.0") is True
    assert is_version_compatible("1.0", supported="1.0") is True
    assert is_version_compatible("1.0", supported="1.1") is False
    assert is_version_compatible("2.0", supported="1.0") is False


def test_negotiate_api_version_returns_supported() -> None:
    negotiated = negotiate_api_version(["2.0", "1.3"], supported="1.0")
    assert negotiated == "1.0"


def test_negotiate_api_version_incompatible() -> None:
    negotiated = negotiate_api_version(["2.0", "0.9"], supported="1.0")
    assert negotiated is None


def test_select_api_version_raises_on_incompatible() -> None:
    with pytest.raises(ApiVersionError):
        select_api_version(["2.0"], supported="1.0")
