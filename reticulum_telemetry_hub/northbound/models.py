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

    model_config = ConfigDict(populate_by_name=True)
    backup_path: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("backup_path", "backupPath"),
        serialization_alias="backup_path",
    )
