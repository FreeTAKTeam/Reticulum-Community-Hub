"""Mission-sync envelope schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from typing import Optional

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class MissionCommandSource(BaseModel):
    """Source metadata for mission command envelopes."""

    model_config = ConfigDict(extra="forbid")

    rns_identity: str


class MissionCommandEnvelope(BaseModel):
    """Mission command envelope carried in ``FIELD_COMMANDS``."""

    model_config = ConfigDict(extra="forbid")

    command_id: str
    source: MissionCommandSource
    timestamp: datetime
    command_type: str
    args: dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None
    topics: list[str] = Field(default_factory=list)


class MissionCommandAccepted(BaseModel):
    """Accepted command payload."""

    model_config = ConfigDict(extra="forbid")

    command_id: str
    status: str = "accepted"
    accepted_at: datetime
    correlation_id: Optional[str] = None
    by_identity: Optional[str] = None


class MissionCommandRejected(BaseModel):
    """Rejected command payload."""

    model_config = ConfigDict(extra="forbid")

    command_id: str
    status: str = "rejected"
    reason_code: str
    reason: Optional[str] = None
    correlation_id: Optional[str] = None
    required_capabilities: list[str] = Field(default_factory=list)


class MissionCommandResult(BaseModel):
    """Command result payload."""

    model_config = ConfigDict(extra="forbid")

    command_id: str
    status: str = "result"
    result: dict[str, Any]
    correlation_id: Optional[str] = None
