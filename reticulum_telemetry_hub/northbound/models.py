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
from pydantic import model_validator

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

    backup_path: Optional[str] = Field(default=None, alias="backup_path")

    class Config:
        """Pydantic configuration."""

        allow_population_by_field_name = True
        allow_population_by_alias = True


class MessagePayload(BaseModel):
    """Payload for sending chat messages into the hub."""

    content: str = Field(alias="Content")
    topic_id: Optional[str] = Field(default=None, alias="TopicID")
    destination: Optional[str] = Field(default=None, alias="Destination")

    class Config:
        """Pydantic configuration."""

        allow_population_by_field_name = True
        allow_population_by_alias = True


class ChatSendPayload(BaseModel):
    """Payload for sending chat messages with optional attachments."""

    model_config = ConfigDict(populate_by_name=True)

    content: Optional[str] = Field(default=None, alias="Content")
    scope: str = Field(alias="Scope")
    topic_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("TopicID", "topic_id", "topicId"),
        serialization_alias="TopicID",
    )
    destination: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("Destination", "destination"),
        serialization_alias="Destination",
    )
    file_ids: list[int] = Field(
        default_factory=list,
        validation_alias=AliasChoices("FileIDs", "file_ids", "fileIds"),
        serialization_alias="FileIDs",
    )
    image_ids: list[int] = Field(
        default_factory=list,
        validation_alias=AliasChoices("ImageIDs", "image_ids", "imageIds"),
        serialization_alias="ImageIDs",
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
