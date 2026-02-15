"""Tests for northbound auth helpers."""

import os

from reticulum_telemetry_hub.northbound.auth import ApiAuth
from reticulum_telemetry_hub.northbound.auth import _parse_bearer_token


def test_parse_bearer_token_accepts_valid_header() -> None:
    """Ensure bearer tokens are parsed from headers."""

    token = _parse_bearer_token("Bearer token123")

    assert token == "token123"


def test_parse_bearer_token_rejects_invalid_header() -> None:
    """Ensure bearer tokens reject malformed headers."""

    assert _parse_bearer_token("token123") is None
    assert _parse_bearer_token("Basic token123") is None


def test_auth_is_enabled_reads_env(monkeypatch) -> None:
    """Ensure auth checks the environment when enabled."""

    monkeypatch.setenv("RTH_API_KEY", "secret")
    monkeypatch.delenv("RCH_API_KEY", raising=False)
    auth = ApiAuth(api_key=None)

    assert auth.is_enabled()


def test_auth_override_wins(monkeypatch) -> None:
    """Ensure explicit API keys override env values."""

    monkeypatch.setenv("RTH_API_KEY", "env")
    monkeypatch.delenv("RCH_API_KEY", raising=False)
    auth = ApiAuth(api_key="override")

    assert auth.validate_credentials(api_key="override", token=None)
    assert not auth.validate_credentials(api_key="env", token=None)

    monkeypatch.delenv("RTH_API_KEY", raising=False)
    assert os.environ.get("RTH_API_KEY") is None


def test_auth_legacy_env_alias_supported(monkeypatch) -> None:
    """Accept legacy RCH_API_KEY when canonical key is not set."""

    monkeypatch.delenv("RTH_API_KEY", raising=False)
    monkeypatch.setenv("RCH_API_KEY", "legacy-secret")
    auth = ApiAuth(api_key=None)

    assert auth.is_enabled()
    assert auth.validate_credentials(api_key="legacy-secret", token=None)


def test_auth_prefers_canonical_key_over_legacy_alias(monkeypatch) -> None:
    """Use RTH_API_KEY when both canonical and alias keys are present."""

    monkeypatch.setenv("RTH_API_KEY", "canonical")
    monkeypatch.setenv("RCH_API_KEY", "legacy")
    auth = ApiAuth(api_key=None)

    assert auth.validate_credentials(api_key="canonical", token=None)
    assert not auth.validate_credentials(api_key="legacy", token=None)
