"""Pydantic models for the northbound API."""
# pylint: disable=import-error

from __future__ import annotations

from typing import Any
from typing import Dict
from typing import Optional

from pydantic import AliasChoices
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator

from reticulum_telemetry_hub.api.marker_symbols import is_supported_marker_symbol
from reticulum_telemetry_hub.api.marker_symbols import normalize_marker_symbol
from reticulum_telemetry_hub.api.marker_symbols import SUPPORTED_MARKER_SYMBOLS


def _normalize_aliases(values: object, alias_map: dict[str, tuple[str, ...]]) -> object:
    """Normalize payload keys using alias hints.

    Args:
        values (object): Raw payload input.
        alias_map (dict[str, tuple[str, ...]]): Map of canonical keys to alias keys.

    Returns:
        object: Normalized payload values.
    """

    if not isinstance(values, dict):
        return values

    normalized = dict(values)
    for field_name, aliases in alias_map.items():
        if field_name in normalized:
            continue
        for alias in aliases:
            if alias in normalized:
                normalized[field_name] = normalized[alias]
                break
    return normalized


class TopicPayload(BaseModel):
    """Topic payload for create/update requests."""

    model_config = ConfigDict(populate_by_name=True)

    topic_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("TopicID", "topic_id", "topicId", "id"),
        serialization_alias="TopicID",
    )
    topic_name: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("TopicName", "topic_name", "topicName", "name"),
        serialization_alias="TopicName",
    )
    topic_path: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("TopicPath", "topic_path", "topicPath", "path"),
        serialization_alias="TopicPath",
    )
    topic_description: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("TopicDescription", "topic_description", "topicDescription", "description"),
        serialization_alias="TopicDescription",
    )


class SubscriberPayload(BaseModel):
    """Subscriber payload for create/update requests."""

    model_config = ConfigDict(populate_by_name=True)

    subscriber_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("SubscriberID", "subscriber_id", "subscriberId", "id"),
        serialization_alias="SubscriberID",
    )
    destination: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("Destination", "destination"),
        serialization_alias="Destination",
    )
    topic_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("TopicID", "topic_id", "topicId"),
        serialization_alias="TopicID",
    )
    reject_tests: Optional[int] = Field(
        default=None,
        validation_alias=AliasChoices("RejectTests", "reject_tests", "rejectTests"),
        serialization_alias="RejectTests",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        validation_alias=AliasChoices("Metadata", "metadata"),
        serialization_alias="Metadata",
    )


class SubscribeTopicRequest(BaseModel):
    """Payload for topic subscription requests."""

    model_config = ConfigDict(populate_by_name=True)

    topic_id: str = Field(
        validation_alias=AliasChoices("TopicID", "topic_id", "topicId", "id"),
        serialization_alias="TopicID",
    )
    destination: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("Destination", "destination"),
        serialization_alias="Destination",
    )
    reject_tests: Optional[int] = Field(
        default=None,
        validation_alias=AliasChoices("RejectTests", "reject_tests", "rejectTests"),
        serialization_alias="RejectTests",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        validation_alias=AliasChoices("Metadata", "metadata"),
        serialization_alias="Metadata",
    )


class ConfigRollbackPayload(BaseModel):
    """Payload for configuration rollbacks."""

    backup_path: Optional[str] = None


class MessagePayload(BaseModel):
    """Payload for sending chat messages into the hub."""

    model_config = ConfigDict(populate_by_name=True)

    content: str
    topic_id: Optional[str] = None
    destination: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_payload(cls, values: object) -> object:
        """Normalize payload aliases to field names.

        Args:
            values (object): Raw payload input.

        Returns:
            object: Normalized payload values.
        """

        return _normalize_aliases(
            values,
            {
                "content": ("Content",),
                "topic_id": ("TopicID", "topicId"),
                "destination": ("Destination",),
            },
        )


class ChatSendPayload(BaseModel):
    """Payload for sending chat messages with optional attachments."""

    model_config = ConfigDict(populate_by_name=True)

    content: Optional[str] = None
    scope: str
    topic_id: Optional[str] = None
    destination: Optional[str] = None
    file_ids: list[int] = Field(default_factory=list)
    image_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_payload(cls, values: object) -> object:
        """Normalize payload aliases to field names.

        Args:
            values (object): Raw payload input.

        Returns:
            object: Normalized payload values.
        """

        return _normalize_aliases(
            values,
            {
                "content": ("Content",),
                "scope": ("Scope",),
                "topic_id": ("TopicID", "topicId"),
                "destination": ("Destination",),
                "file_ids": ("FileIDs", "fileIds"),
                "image_ids": ("ImageIDs", "imageIds"),
            },
        )

    @model_validator(mode="after")
    def _validate_payload(self) -> "ChatSendPayload":
        """Validate scope-specific requirements."""

        scope = self.scope.lower().strip()
        if scope not in {"dm", "topic", "broadcast"}:
            raise ValueError("Scope must be dm, topic, or broadcast")
        if scope == "dm" and not self.destination:
            raise ValueError("Destination is required for DM scope")
        if scope == "topic" and not self.topic_id:
            raise ValueError("TopicID is required for topic scope")
        if not (self.content and self.content.strip()) and not (self.file_ids or self.image_ids):
            raise ValueError("Content or attachments are required")
        return self


class MarkerCreatePayload(BaseModel):
    """Payload for creating operator markers."""

    marker_type: str = Field(json_schema_extra={"enum": SUPPORTED_MARKER_SYMBOLS})
    symbol: str = Field(json_schema_extra={"enum": SUPPORTED_MARKER_SYMBOLS})
    name: Optional[str] = None
    category: Optional[str] = None
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    notes: Optional[str] = None
    ttl_seconds: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="before")
    @classmethod
    def _normalize_payload(cls, values: object) -> object:
        """Normalize payload aliases to field names."""

        return _normalize_aliases(
            values,
            {"marker_type": ("type", "marker_type", "markerType")},
        )

    @field_validator("marker_type", mode="before")
    @classmethod
    def _normalize_marker_type(cls, value: object) -> object:
        """Normalize marker type aliases before validation."""

        if isinstance(value, str):
            return normalize_marker_symbol(value)
        return value

    @field_validator("symbol", mode="before")
    @classmethod
    def _normalize_symbol(cls, value: object) -> object:
        """Normalize marker symbol aliases before validation."""

        if isinstance(value, str):
            return normalize_marker_symbol(value)
        return value

    @field_validator("marker_type")
    @classmethod
    def _validate_marker_type(cls, value: str) -> str:
        """Validate marker type against supported symbols."""

        if not is_supported_marker_symbol(value):
            raise ValueError("Unsupported marker type")
        return value

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, value: str) -> str:
        """Validate marker symbol against supported symbols."""

        if not is_supported_marker_symbol(value):
            raise ValueError("Unsupported marker symbol")
        return value

    @field_validator("category")
    @classmethod
    def _normalize_category(cls, value: Optional[str]) -> Optional[str]:
        """Normalize marker category whitespace."""

        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class MarkerPositionPayload(BaseModel):
    """Payload for marker position updates."""

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class MarkerUpdatePayload(BaseModel):
    """Payload for marker metadata updates."""

    name: str = Field(min_length=1, max_length=96)


class ZonePointPayload(BaseModel):
    """Payload for a zone polygon point."""

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class ZoneCreatePayload(BaseModel):
    """Payload for creating an operational zone."""

    name: str = Field(min_length=1, max_length=96)
    points: list[ZonePointPayload] = Field(min_length=3, max_length=200)

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        """Trim and validate zone names."""

        resolved = value.strip()
        if not resolved:
            raise ValueError("Zone name is required")
        return resolved


class ZoneUpdatePayload(BaseModel):
    """Payload for updating an operational zone."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=96)
    points: Optional[list[ZonePointPayload]] = Field(default=None, min_length=3, max_length=200)

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: Optional[str]) -> Optional[str]:
        """Trim and validate optional zone names."""

        if value is None:
            return None
        resolved = value.strip()
        if not resolved:
            raise ValueError("Zone name is required")
        return resolved

    @model_validator(mode="after")
    def _validate_has_updates(self) -> "ZoneUpdatePayload":
        """Ensure at least one field is supplied for patch."""

        if self.name is None and self.points is None:
            raise ValueError("At least one zone field must be provided")
        return self
