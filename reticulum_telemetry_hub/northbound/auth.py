"""Authentication helpers for the northbound API."""
# pylint: disable=import-error

from __future__ import annotations

import ipaddress
import os
from typing import Optional

from dotenv import load_dotenv as load_env
from fastapi import Header
from fastapi import HTTPException
from fastapi import Request
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
        self,
        api_key: Optional[str],
        token: Optional[str],
        *,
        client_host: Optional[str] = None,
    ) -> bool:
        """Validate provided credentials.

        Args:
            api_key (Optional[str]): API key header value.
            token (Optional[str]): Bearer token value.
            client_host (Optional[str]): Optional client host used for
                remote-aware authentication decisions.

        Returns:
            bool: ``True`` when credentials are valid.
        """

        if client_host is not None and self.is_local_client(client_host):
            return True

        expected = self._api_key or self._env_api_key()
        if expected:
            return api_key == expected or token == expected
        if client_host is None:
            return True
        return self.is_local_client(client_host)

    @staticmethod
    def is_local_client(client_host: Optional[str]) -> bool:
        """Return ``True`` when the client host is loopback/local.

        Args:
            client_host (Optional[str]): Client host string.

        Returns:
            bool: ``True`` when the host is local.
        """

        if not client_host:
            return False
        normalized = str(client_host).strip().lower()
        if not normalized:
            return False
        if normalized in {"localhost", "testclient"}:
            return True

        candidate = normalized.split("%", maxsplit=1)[0]
        try:
            ip_addr = ipaddress.ip_address(candidate)
        except ValueError:
            return False

        if ip_addr.is_loopback:
            return True
        mapped = getattr(ip_addr, "ipv4_mapped", None)
        return bool(mapped and mapped.is_loopback)

    def failure_detail(self, client_host: Optional[str]) -> str:
        """Return an auth failure reason suitable for HTTP/WS errors.

        Args:
            client_host (Optional[str]): Client host string.

        Returns:
            str: Failure detail message.
        """

        expected = self._api_key or self._env_api_key()
        if expected:
            return "Unauthorized"
        if not self.is_local_client(client_host):
            return "Remote access requires authentication; set RTH_API_KEY."
        return "Unauthorized"

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
        request: Request,
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
        client_host = request.client.host if request.client else None
        if auth.validate_credentials(x_api_key, token, client_host=client_host):
            return
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=auth.failure_detail(client_host),
        )

    return _require_protected
