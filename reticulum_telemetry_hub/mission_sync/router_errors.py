"""Mission-sync router exception types."""

from __future__ import annotations

from typing import Optional


class MissionCommandError(Exception):
    """Error raised for mission command execution failures."""

    def __init__(
        self,
        reason_code: str,
        reason: str,
        *,
        required_capabilities: Optional[list[str]] = None,
    ) -> None:
        super().__init__(reason)
        self.reason_code = reason_code
        self.reason = reason
        self.required_capabilities = list(required_capabilities or [])
