from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Topic:
    topic_name: str
    topic_path: str
    topic_description: str = ""
    topic_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "TopicID": self.topic_id,
            "TopicName": self.topic_name,
            "TopicPath": self.topic_path,
            "TopicDescription": self.topic_description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Topic":
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
    destination: str
    topic_id: Optional[str] = None
    reject_tests: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    subscriber_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "SubscriberID": self.subscriber_id,
            "Destination": self.destination,
            "TopicID": self.topic_id,
            "RejectTests": self.reject_tests,
            "Metadata": self.metadata or None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Subscriber":
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
    identity: str
    last_seen: datetime = field(default_factory=_now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        now = _now()
        if now <= self.last_seen:
            now = self.last_seen + timedelta(microseconds=1)
        self.last_seen = now

    def to_dict(self) -> dict:
        data = asdict(self)
        data["last_seen"] = self.last_seen.isoformat()
        return data


@dataclass
class ReticulumInfo:
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
        return asdict(self)
