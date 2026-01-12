"""Pydantic models for the northbound API."""

from __future__ import annotations

from typing import Any
from typing import Dict
from typing import Optional

from pydantic import BaseModel
from pydantic import Field


class TopicPayload(BaseModel):
    """Topic payload for create/update requests."""

    topic_id: Optional[str] = Field(default=None, alias="TopicID")
    topic_name: Optional[str] = Field(default=None, alias="TopicName")
    topic_path: Optional[str] = Field(default=None, alias="TopicPath")
    topic_description: Optional[str] = Field(default=None, alias="TopicDescription")

    class Config:
        """Pydantic configuration."""

        allow_population_by_field_name = True
        allow_population_by_alias = True


class SubscriberPayload(BaseModel):
    """Subscriber payload for create/update requests."""

    subscriber_id: Optional[str] = Field(default=None, alias="SubscriberID")
    destination: Optional[str] = Field(default=None, alias="Destination")
    topic_id: Optional[str] = Field(default=None, alias="TopicID")
    reject_tests: Optional[int] = Field(default=None, alias="RejectTests")
    metadata: Optional[Dict[str, Any]] = Field(default=None, alias="Metadata")

    class Config:
        """Pydantic configuration."""

        allow_population_by_field_name = True
        allow_population_by_alias = True


class SubscribeTopicRequest(BaseModel):
    """Payload for topic subscription requests."""

    topic_id: str = Field(alias="TopicID")
    destination: Optional[str] = Field(default=None, alias="Destination")
    reject_tests: Optional[int] = Field(default=None, alias="RejectTests")
    metadata: Optional[Dict[str, Any]] = Field(default=None, alias="Metadata")

    class Config:
        """Pydantic configuration."""

        allow_population_by_field_name = True
        allow_population_by_alias = True


class ConfigRollbackPayload(BaseModel):
    """Payload for configuration rollbacks."""

    backup_path: Optional[str] = Field(default=None, alias="backup_path")

    class Config:
        """Pydantic configuration."""

        allow_population_by_field_name = True
        allow_population_by_alias = True
