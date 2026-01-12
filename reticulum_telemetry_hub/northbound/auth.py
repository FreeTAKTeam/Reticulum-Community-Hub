"""Authentication helpers for the northbound API."""

from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv as load_env
from fastapi import Header
from fastapi import HTTPException
from fastapi import status


class ApiAuth:
    """Validate API key or bearer token credentials."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        """Initialize the auth validator.

        Args:
            api_key (Optional[str]): API key override. When omitted, the
                validator reads ``RTH_API_KEY`` from the environment.
        """

        load_env()
        self._api_key = api_key

    def is_enabled(self) -> bool:
        """Return ``True`` when an API key is configured.

        Returns:
            bool: ``True`` when protected endpoints require credentials.
        """

        return bool(self._api_key or self._env_api_key())

    def validate_credentials(
        self, api_key: Optional[str], token: Optional[str]
    ) -> bool:
        """Validate provided credentials.

        Args:
            api_key (Optional[str]): API key header value.
            token (Optional[str]): Bearer token value.

        Returns:
            bool: ``True`` when credentials are valid or auth is disabled.
        """

        expected = self._api_key or self._env_api_key()
        if not expected:
            return True
        return api_key == expected or token == expected

    @staticmethod
    def _env_api_key() -> Optional[str]:
        """Return the configured API key from the environment.

        Returns:
            Optional[str]: API key string if defined.
        """

        return os.environ.get("RTH_API_KEY")


def _parse_bearer_token(authorization: Optional[str]) -> Optional[str]:
    """Extract a bearer token from an authorization header.

    Args:
        authorization (Optional[str]): Authorization header value.

    Returns:
        Optional[str]: Parsed bearer token, if present.
    """

    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) != 2:
        return None
    if parts[0].lower() != "bearer":
        return None
    return parts[1]


def build_protected_dependency(auth: ApiAuth):
    """Return a dependency that enforces protected access.

    Args:
        auth (ApiAuth): Auth validator instance.

    Returns:
        Callable: Dependency function for FastAPI routes.
    """

    async def _require_protected(
        x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
        authorization: Optional[str] = Header(default=None, alias="Authorization"),
    ) -> None:
        """Validate protected endpoint credentials.

        Args:
            x_api_key (Optional[str]): API key header value.
            authorization (Optional[str]): Authorization header value.

        Returns:
            None: This dependency raises on invalid credentials.
        """

        token = _parse_bearer_token(authorization)
        if auth.validate_credentials(x_api_key, token):
            return
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    return _require_protected
