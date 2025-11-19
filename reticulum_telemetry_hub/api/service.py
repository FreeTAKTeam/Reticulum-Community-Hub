from __future__ import annotations

import uuid
from typing import List, Optional

from reticulum_telemetry_hub.config import HubConfigurationManager

from .models import Client, ReticulumInfo, Subscriber, Topic
from .storage import HubStorage


class ReticulumTelemetryHubAPI:
    """Persistence-backed implementation of the ReticulumTelemetryHub API."""

    def __init__(
        self,
        config_manager: Optional[HubConfigurationManager] = None,
        storage: Optional[HubStorage] = None,
    ) -> None:
        self._config_manager = config_manager or HubConfigurationManager()
        hub_db_path = self._config_manager.config.hub_database_path
        self._storage = storage or HubStorage(hub_db_path)

    # ------------------------------------------------------------------ #
    # RTH operations
    # ------------------------------------------------------------------ #
    def join(self, identity: str) -> bool:
        if not identity:
            raise ValueError("identity is required")
        self._storage.upsert_client(identity)
        return True

    def leave(self, identity: str) -> bool:
        if not identity:
            raise ValueError("identity is required")
        return self._storage.remove_client(identity)

    # ------------------------------------------------------------------ #
    # Client operations
    # ------------------------------------------------------------------ #
    def list_clients(self) -> List[Client]:
        return self._storage.list_clients()

    # ------------------------------------------------------------------ #
    # Topic operations
    # ------------------------------------------------------------------ #
    def create_topic(self, topic: Topic) -> Topic:
        if not topic.topic_name or not topic.topic_path:
            raise ValueError("TopicName and TopicPath are required")
        topic.topic_id = topic.topic_id or uuid.uuid4().hex
        return self._storage.create_topic(topic)

    def list_topics(self) -> List[Topic]:
        return self._storage.list_topics()

    def retrieve_topic(self, topic_id: str) -> Topic:
        topic = self._storage.get_topic(topic_id)
        if not topic:
            raise KeyError(f"Topic '{topic_id}' not found")
        return topic

    def delete_topic(self, topic_id: str) -> Topic:
        topic = self._storage.delete_topic(topic_id)
        if not topic:
            raise KeyError(f"Topic '{topic_id}' not found")
        return topic

    def patch_topic(self, topic_id: str, **updates) -> Topic:
        topic = self.retrieve_topic(topic_id)
        update_fields = {}
        if "topic_name" in updates or "TopicName" in updates:
            topic.topic_name = updates.get("topic_name") or updates.get("TopicName")
            update_fields["topic_name"] = topic.topic_name
        if "topic_path" in updates or "TopicPath" in updates:
            topic.topic_path = updates.get("topic_path") or updates.get("TopicPath")
            update_fields["topic_path"] = topic.topic_path
        if "topic_description" in updates or "TopicDescription" in updates:
            if "topic_description" in updates:
                description = updates["topic_description"]
            else:
                description = updates["TopicDescription"]
            topic.topic_description = description or ""
            update_fields["topic_description"] = topic.topic_description
        if not update_fields:
            return topic
        updated_topic = self._storage.update_topic(topic.topic_id, **update_fields)
        if not updated_topic:
            raise KeyError(f"Topic '{topic_id}' not found")
        return updated_topic

    def subscribe_topic(
        self,
        topic_id: str,
        destination: str,
        reject_tests: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> Subscriber:
        topic = self.retrieve_topic(topic_id)
        subscriber = Subscriber(
            destination=destination,
            topic_id=topic.topic_id,
            reject_tests=reject_tests,
            metadata=metadata or {},
        )
        return self.create_subscriber(subscriber)

    # ------------------------------------------------------------------ #
    # Subscriber operations
    # ------------------------------------------------------------------ #
    def create_subscriber(self, subscriber: Subscriber) -> Subscriber:
        if not subscriber.destination:
            raise ValueError("Subscriber destination is required")
        subscriber.topic_id = subscriber.topic_id or ""
        subscriber.subscriber_id = subscriber.subscriber_id or uuid.uuid4().hex
        return self._storage.create_subscriber(subscriber)

    def list_subscribers(self) -> List[Subscriber]:
        return self._storage.list_subscribers()

    def retrieve_subscriber(self, subscriber_id: str) -> Subscriber:
        subscriber = self._storage.get_subscriber(subscriber_id)
        if not subscriber:
            raise KeyError(f"Subscriber '{subscriber_id}' not found")
        return subscriber

    def delete_subscriber(self, subscriber_id: str) -> Subscriber:
        subscriber = self._storage.delete_subscriber(subscriber_id)
        if not subscriber:
            raise KeyError(f"Subscriber '{subscriber_id}' not found")
        return subscriber

    def patch_subscriber(self, subscriber_id: str, **updates) -> Subscriber:
        subscriber = self.retrieve_subscriber(subscriber_id)
        if "destination" in updates or "Destination" in updates:
            subscriber.destination = updates.get("destination") or updates.get(
                "Destination"
            )
        if "topic_id" in updates or "TopicID" in updates:
            subscriber.topic_id = updates.get("topic_id") or updates.get("TopicID")
        if "reject_tests" in updates:
            subscriber.reject_tests = updates["reject_tests"]
        elif "RejectTests" in updates:
            subscriber.reject_tests = updates["RejectTests"]
        metadata_key = None
        if "metadata" in updates:
            metadata_key = "metadata"
        elif "Metadata" in updates:
            metadata_key = "Metadata"

        if metadata_key is not None:
            subscriber.metadata = updates[metadata_key]
        return self._storage.update_subscriber(subscriber)

    def add_subscriber(self, subscriber: Subscriber) -> Subscriber:
        return self.create_subscriber(subscriber)

    # ------------------------------------------------------------------ #
    # Reticulum info
    # ------------------------------------------------------------------ #
    def get_app_info(self) -> ReticulumInfo:
        info_dict = self._config_manager.reticulum_info_snapshot()
        return ReticulumInfo(**info_dict)
