"""Tests for northbound API authentication."""

from reticulum_telemetry_hub.northbound.auth import ApiAuth


def test_auth_accepts_valid_api_key() -> None:
    """Validate that matching keys are accepted."""

    auth = ApiAuth(api_key="secret")
    assert auth.validate_credentials(api_key="secret", token=None)
    assert auth.validate_credentials(api_key=None, token="secret")


def test_auth_disabled_allows_missing_keys(monkeypatch) -> None:
    """Ensure auth passes when no API key is configured."""

    monkeypatch.delenv("RTH_API_KEY", raising=False)
    auth = ApiAuth(api_key=None)
    assert auth.validate_credentials(api_key=None, token=None)


def test_auth_rejects_invalid_key() -> None:
    """Ensure auth rejects mismatched keys."""

    auth = ApiAuth(api_key="secret")
    assert not auth.validate_credentials(api_key="wrong", token=None)
