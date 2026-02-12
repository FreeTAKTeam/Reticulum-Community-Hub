"""Data models for the Reticulum Telemetry Hub API."""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional


def _now() -> datetime:
    """Return the current UTC timestamp with timezone information."""

    return datetime.now(timezone.utc)


def _json_safe_key(key: Any) -> str:
    """Return a JSON-safe dictionary key."""

    if isinstance(key, (bytes, bytearray, memoryview)):
        return bytes(key).hex()
    if key is None:
        return "null"
    return str(key)


def _json_safe(value: Any) -> Any:
    """Return a JSON-safe version of ``value``."""

    if isinstance(value, dict):
        return {_json_safe_key(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


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
            "Metadata": _json_safe(self.metadata or None),
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
    display_name: Optional[str] = None
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
        data["metadata"] = _json_safe(self.metadata or {})
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
    reticulum_destination: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize the info model to a dictionary."""

        data = asdict(self)
        data["name"] = self.app_name
        data["version"] = self.app_version
        data["description"] = self.app_description
        data["storage_paths"] = {
            "storage": self.storage_path,
            "database": self.database_path,
            "reticulum_config": self.reticulum_config_path,
            "files": self.file_storage_path,
            "images": self.image_storage_path,
        }
        return data


@dataclass
class FileAttachment:
    """Metadata for files or images stored by the hub."""

    name: str
    path: str
    category: str
    size: int
    media_type: Optional[str] = None
    topic_id: Optional[str] = None
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
            "TopicID": self.topic_id,
            "Size": self.size,
            "CreatedAt": self.created_at.isoformat(),
            "UpdatedAt": self.updated_at.isoformat(),
        }


@dataclass
class Marker:
    """Logical marker state stored by the hub."""

    local_id: str
    object_destination_hash: Optional[str]
    origin_rch: Optional[str]
    object_identity_storage_key: Optional[str]
    marker_type: str
    symbol: str
    name: str
    category: str
    lat: float
    lon: float
    notes: Optional[str] = None
    time: Optional[datetime] = field(default_factory=_now)
    stale_at: Optional[datetime] = field(default_factory=_now)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def to_dict(self) -> dict:
        """Serialize marker state for API responses."""

        time_value = self.time or self.updated_at or self.created_at
        stale_at_value = self.stale_at or time_value
        return {
            "object_destination_hash": self.object_destination_hash,
            "origin_rch": self.origin_rch,
            "type": self.marker_type,
            "name": self.name,
            "category": self.category,
            "symbol": self.symbol,
            "notes": self.notes,
            "position": {"lat": self.lat, "lon": self.lon},
            "time": time_value.isoformat() if time_value else None,
            "stale_at": stale_at_value.isoformat() if stale_at_value else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class ZonePoint:
    """A single zone polygon point."""

    lat: float
    lon: float

    def to_dict(self) -> dict:
        """Serialize the point for API responses."""

        return {"lat": self.lat, "lon": self.lon}


@dataclass
class Zone:
    """Logical zone state stored by the hub."""

    zone_id: str
    name: str
    points: List[ZonePoint] = field(default_factory=list)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def to_dict(self) -> dict:
        """Serialize zone state for API responses."""

        return {
            "zone_id": self.zone_id,
            "name": self.name,
            "points": [point.to_dict() for point in self.points],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class ChatAttachment:
    """Attachment metadata associated with a chat message."""

    file_id: int
    category: str
    name: str
    size: int
    media_type: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize the attachment reference for API responses."""

        return {
            "FileID": self.file_id,
            "Category": self.category,
            "Name": self.name,
            "Size": self.size,
            "MediaType": self.media_type,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatAttachment":
        """Create a ChatAttachment from a serialized dictionary."""

        return cls(
            file_id=int(data.get("FileID") or data.get("file_id") or 0),
            category=str(data.get("Category") or data.get("category") or ""),
            name=str(data.get("Name") or data.get("name") or ""),
            size=int(data.get("Size") or data.get("size") or 0),
            media_type=data.get("MediaType") or data.get("media_type"),
        )


@dataclass
class ChatMessage:
    """Chat message metadata persisted by the hub."""

    direction: str
    scope: str
    state: str
    content: str
    source: Optional[str] = None
    destination: Optional[str] = None
    topic_id: Optional[str] = None
    attachments: List[ChatAttachment] = field(default_factory=list)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    message_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize the chat message into API-friendly fields."""

        return {
            "MessageID": self.message_id,
            "Direction": self.direction,
            "Scope": self.scope,
            "State": self.state,
            "Content": self.content,
            "Source": self.source,
            "Destination": self.destination,
            "TopicID": self.topic_id,
            "Attachments": [attachment.to_dict() for attachment in self.attachments],
            "CreatedAt": self.created_at.isoformat(),
            "UpdatedAt": self.updated_at.isoformat(),
        }


@dataclass
class IdentityStatus:
    """Current identity status for admin tooling."""

    identity: str
    status: str
    last_seen: Optional[datetime] = None
    display_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_banned: bool = False
    is_blackholed: bool = False

    def to_dict(self) -> dict:
        """Serialize the identity status into JSON-friendly values."""

        return {
            "Identity": self.identity,
            "DisplayName": self.display_name,
            "Status": self.status,
            "LastSeen": self.last_seen.isoformat() if self.last_seen else None,
            "Metadata": _json_safe(self.metadata or {}),
            "IsBanned": self.is_banned,
            "IsBlackholed": self.is_blackholed,
        }
