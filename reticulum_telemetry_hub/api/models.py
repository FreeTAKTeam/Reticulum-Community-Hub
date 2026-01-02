"""Data models for the Reticulum Telemetry Hub API."""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any
from typing import Dict
from typing import Optional


def _now() -> datetime:
    """Return the current UTC timestamp with timezone information."""

    return datetime.now(timezone.utc)


@dataclass
class Topic:
    """Topic subscription metadata for the Reticulum Telemetry Hub."""

    topic_name: str
    topic_path: str
    topic_description: str = ""
    topic_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize the topic into the external API schema."""

        return {
            "TopicID": self.topic_id,
            "TopicName": self.topic_name,
            "TopicPath": self.topic_path,
            "TopicDescription": self.topic_description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Topic":
        """Create a Topic from a dictionary with flexible casing.

        Args:
            data (Dict[str, Any]): Source mapping using either title-case or
                snake_case keys.

        Returns:
            Topic: Parsed topic instance with defaults for missing values.
        """

        return cls(
            topic_name=data.get("TopicName") or data.get("topic_name") or "",
            topic_path=data.get("TopicPath") or data.get("topic_path") or "",
            topic_description=data.get("TopicDescription")
            or data.get("topic_description")
            or "",
            topic_id=data.get("TopicID") or data.get("topic_id"),
        )


@dataclass
class Subscriber:
    """Subscription details linking destinations to topics."""

    destination: str
    topic_id: Optional[str] = None
    reject_tests: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    subscriber_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize the subscriber into the external API schema."""

        return {
            "SubscriberID": self.subscriber_id,
            "Destination": self.destination,
            "TopicID": self.topic_id,
            "RejectTests": self.reject_tests,
            "Metadata": self.metadata or None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Subscriber":
        """Create a Subscriber from a dictionary with flexible casing.

        Args:
            data (Dict[str, Any]): Source mapping using either title-case or
                snake_case keys.

        Returns:
            Subscriber: Parsed subscriber instance.
        """

        reject_tests = None
        if "RejectTests" in data:
            reject_tests = data.get("RejectTests")
        elif "reject_tests" in data:
            reject_tests = data.get("reject_tests")

        return cls(
            destination=data.get("Destination") or data.get("destination") or "",
            topic_id=data.get("TopicID") or data.get("topic_id"),
            reject_tests=reject_tests,
            metadata=data.get("Metadata") or data.get("metadata") or {},
            subscriber_id=data.get("SubscriberID") or data.get("subscriber_id"),
        )


@dataclass
class Client:
    """Connected client state and metadata."""

    identity: str
    last_seen: datetime = field(default_factory=_now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        """Update ``last_seen`` to the latest timestamp in UTC."""

        now = _now()
        if now <= self.last_seen:
            now = self.last_seen + timedelta(microseconds=1)
        self.last_seen = now

    def to_dict(self) -> dict:
        """Serialize the client into primitive types for JSON responses."""

        data = asdict(self)
        data["last_seen"] = self.last_seen.isoformat()
        return data


@dataclass
# pylint: disable=too-many-instance-attributes
class ReticulumInfo:
    """Application and environment metadata exposed by the API."""

    is_transport_enabled: bool
    is_connected_to_shared_instance: bool
    reticulum_config_path: str
    database_path: str
    storage_path: str
    file_storage_path: str
    image_storage_path: str
    app_name: str
    rns_version: str
    lxmf_version: str
    app_version: str
    app_description: str

    def to_dict(self) -> dict:
        """Serialize the info model to a dictionary."""

        return asdict(self)


@dataclass
class FileAttachment:
    """Metadata for files or images stored by the hub."""

    name: str
    path: str
    category: str
    size: int
    media_type: Optional[str] = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    file_id: Optional[int] = None

    def to_dict(self) -> dict:
        """Return a serialization friendly representation."""

        return {
            "FileID": self.file_id,
            "Name": self.name,
            "Path": self.path,
            "Category": self.category,
            "MediaType": self.media_type,
            "Size": self.size,
            "CreatedAt": self.created_at.isoformat(),
            "UpdatedAt": self.updated_at.isoformat(),
        }
