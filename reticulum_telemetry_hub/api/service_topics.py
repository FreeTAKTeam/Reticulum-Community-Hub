"""Topic and subscriber service methods."""

from __future__ import annotations

import uuid
from typing import List
from typing import Optional

from reticulum_telemetry_hub.message_delivery import normalize_topic_id
from .models import Subscriber
from .models import Topic
from .pagination import PageRequest
from .pagination import PaginatedResult


class ApiTopicSubscriberMixin:
    """Topic and subscriber service methods."""

    def create_topic(self, topic: Topic) -> Topic:
        """Create a topic in the hub database.

        Args:
            topic (Topic): Topic definition to store. ``topic_id`` is
                auto-generated when not provided.

        Returns:
            Topic: Persisted topic record with a guaranteed ``topic_id``.

        Raises:
            ValueError: If ``topic.topic_name`` or ``topic.topic_path`` is
                missing.

        Notes:
            A hex UUID is generated for ``topic_id`` when it is absent to
            ensure unique topic identifiers across requests.
        """
        if not topic.topic_name or not topic.topic_path:
            raise ValueError("TopicName and TopicPath are required")
        topic.topic_id = normalize_topic_id(topic.topic_id) or uuid.uuid4().hex
        created = self._storage.create_topic(topic)
        self._notify_topic_registry_change()
        return created

    def list_topics(self) -> List[Topic]:
        """List all topics known to the hub.

        Returns:
            List[Topic]: Current topic catalog from storage.
        """
        return self._storage.list_topics()

    def list_topics_paginated(self, page_request: PageRequest) -> PaginatedResult[Topic]:
        """Return a page of topics known to the hub."""

        return self._storage.paginate_topics(page_request)

    def count_topics(self) -> int:
        """Return the number of topics known to the hub."""

        return self._storage.count_topics()

    def retrieve_topic(self, topic_id: str) -> Topic:
        """Fetch a topic by its identifier.

        Args:
            topic_id (str): Identifier of the topic to retrieve.

        Returns:
            Topic: The matching topic.

        Raises:
            KeyError: If the topic does not exist.
        """
        normalized_topic_id = normalize_topic_id(topic_id) or topic_id
        topic = self._storage.get_topic(normalized_topic_id)
        if not topic:
            raise KeyError(f"Topic '{normalized_topic_id}' not found")
        return topic

    def delete_topic(self, topic_id: str) -> Topic:
        """Delete a topic by its identifier.

        Args:
            topic_id (str): Identifier of the topic to delete.

        Returns:
            Topic: The removed topic record.

        Raises:
            KeyError: If the topic does not exist.
        """
        normalized_topic_id = normalize_topic_id(topic_id) or topic_id
        topic = self._storage.delete_topic(normalized_topic_id)
        if not topic:
            raise KeyError(f"Topic '{normalized_topic_id}' not found")
        self._storage.clear_file_record_topic(normalized_topic_id)
        self._notify_topic_registry_change()
        return topic

    def patch_topic(self, topic_id: str, **updates) -> Topic:
        """Update selected fields of a topic.

        Args:
            topic_id (str): Identifier of the topic to update.
            **updates: Optional fields to modify, accepting either snake_case
                or title-cased keys (``topic_name``/``TopicName``,
                ``topic_path``/``TopicPath``, ``topic_description``/
                ``TopicDescription``).

        Returns:
            Topic: Updated topic. If no update fields are provided, the
                existing topic is returned unchanged.

        Raises:
            KeyError: If the topic does not exist.

        Notes:
            ``topic_description`` defaults to an empty string when explicitly
            set to ``None`` or an empty value.
        """
        normalized_topic_id = normalize_topic_id(topic_id) or topic_id
        topic = self.retrieve_topic(normalized_topic_id)
        update_fields = {}
        if "topic_name" in updates or "TopicName" in updates:
            topic.topic_name = updates.get("topic_name") or updates.get("TopicName")
            update_fields["topic_name"] = topic.topic_name
        if "topic_path" in updates or "TopicPath" in updates:
            topic.topic_path = updates.get("topic_path") or updates.get("TopicPath")
            update_fields["topic_path"] = topic.topic_path
        if "topic_description" in updates or "TopicDescription" in updates:
            description = updates.get(
                "topic_description", updates.get("TopicDescription")
            )
            topic.topic_description = description or ""
            update_fields["topic_description"] = topic.topic_description
        if not update_fields:
            return topic
        updated_topic = self._storage.update_topic(topic.topic_id, **update_fields)
        if not updated_topic:
            raise KeyError(f"Topic '{normalized_topic_id}' not found")
        self._notify_topic_registry_change()
        return updated_topic

    def subscribe_topic(
        self,
        topic_id: str,
        destination: str,
        reject_tests: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> Subscriber:
        """Subscribe a destination to a topic.

        Args:
            topic_id (str): Identifier of the topic to subscribe to.
            destination (str): Destination identity or address.
            reject_tests (Optional[int]): Value indicating whether to reject
                test messages; stored as provided.
            metadata (Optional[dict]): Subscriber metadata. Defaults to an
                empty dict when not provided.

        Returns:
            Subscriber: Persisted subscriber with a generated ``subscriber_id``
                and the topic's resolved ``topic_id``.

        Raises:
            KeyError: If the referenced topic does not exist.
            ValueError: If ``destination`` is empty.

        Examples:
            >>> api.subscribe_topic(topic_id, "dest")
            Subscriber(..., subscriber_id="<uuid>", metadata={})
        """
        normalized_topic_id = normalize_topic_id(topic_id) or topic_id
        topic = self.retrieve_topic(normalized_topic_id)
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
        """Create a subscriber record.

        Args:
            subscriber (Subscriber): Subscriber definition.
                ``subscriber_id`` is auto-generated when missing. ``topic_id``
                defaults to an empty string when not provided.

        Returns:
            Subscriber: Persisted subscriber with ensured identifiers.

        Raises:
            ValueError: If ``subscriber.destination`` is empty.

        Notes:
            ``subscriber.metadata`` is stored as-is; callers should supply an
            empty dict when no metadata is required to avoid ``None`` values.
        """
        if not subscriber.destination:
            raise ValueError("Subscriber destination is required")
        subscriber.topic_id = normalize_topic_id(subscriber.topic_id) or ""
        subscriber.subscriber_id = subscriber.subscriber_id or uuid.uuid4().hex
        created = self._storage.create_subscriber(subscriber)
        self._notify_topic_registry_change()
        return created

    def list_subscribers(self) -> List[Subscriber]:
        """List all subscribers.

        Returns:
            List[Subscriber]: Subscribers currently stored in the hub.
        """
        return self._storage.list_subscribers()

    def list_subscribers_paginated(
        self,
        page_request: PageRequest,
    ) -> PaginatedResult[Subscriber]:
        """Return a page of subscribers."""

        return self._storage.paginate_subscribers(page_request)

    def count_subscribers(self) -> int:
        """Return the number of subscribers."""

        return self._storage.count_subscribers()

    def list_subscribers_for_topic(self, topic_id: str) -> List[Subscriber]:
        """Return subscribers for a specific topic.

        Args:
            topic_id (str): Topic identifier to filter by.

        Returns:
            List[Subscriber]: Subscribers attached to the topic.

        Raises:
            KeyError: If the topic does not exist.
        """
        normalized_topic_id = normalize_topic_id(topic_id) or topic_id
        self.retrieve_topic(normalized_topic_id)
        return self._storage.list_subscribers_for_topic(normalized_topic_id)

    def list_topics_for_destination(self, destination: str) -> List[Topic]:
        """Return topics a destination is subscribed to.

        Args:
            destination (str): Destination identity hash to query.

        Returns:
            List[Topic]: Topics matching the destination's subscriptions.
        """
        if not destination:
            return []
        return self._storage.list_topics_for_destination(destination)

    def retrieve_subscriber(self, subscriber_id: str) -> Subscriber:
        """Fetch a subscriber by identifier.

        Args:
            subscriber_id (str): Identifier of the subscriber to retrieve.

        Returns:
            Subscriber: The matching subscriber.

        Raises:
            KeyError: If the subscriber does not exist.
        """
        subscriber = self._storage.get_subscriber(subscriber_id)
        if not subscriber:
            raise KeyError(f"Subscriber '{subscriber_id}' not found")
        return subscriber

    def delete_subscriber(self, subscriber_id: str) -> Subscriber:
        """Delete a subscriber by identifier.

        Args:
            subscriber_id (str): Identifier of the subscriber to delete.

        Returns:
            Subscriber: The removed subscriber record.

        Raises:
            KeyError: If the subscriber does not exist.
        """
        subscriber = self._storage.delete_subscriber(subscriber_id)
        if not subscriber:
            raise KeyError(f"Subscriber '{subscriber_id}' not found")
        self._notify_topic_registry_change()
        return subscriber

    def patch_subscriber(self, subscriber_id: str, **updates) -> Subscriber:
        """Update selected subscriber fields.

        Args:
            subscriber_id (str): Identifier of the subscriber to update.
            **updates: Optional fields to modify, accepting either snake_case
                or title-cased keys (``destination``/``Destination``,
                ``topic_id``/``TopicID``, ``reject_tests``/``RejectTests``,
                ``metadata``/``Metadata``).

        Returns:
            Subscriber: Updated subscriber record.

        Raises:
            KeyError: If the subscriber does not exist.

        Notes:
            The metadata dictionary is replaced only when provided; otherwise,
            existing metadata remains unchanged. Topic existence is not
            validated during updates.
        """
        subscriber = self.retrieve_subscriber(subscriber_id)
        if "destination" in updates or "Destination" in updates:
            subscriber.destination = updates.get("destination") or updates.get(
                "Destination"
            )
        if "topic_id" in updates or "TopicID" in updates:
            subscriber.topic_id = normalize_topic_id(
                updates.get("topic_id") or updates.get("TopicID")
            )
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
        updated = self._storage.update_subscriber(subscriber)
        self._notify_topic_registry_change()
        return updated

    def add_subscriber(self, subscriber: Subscriber) -> Subscriber:
        """Alias for :meth:`create_subscriber`.

        Args:
            subscriber (Subscriber): Subscriber definition to persist.

        Returns:
            Subscriber: Persisted subscriber record.
        """
        return self.create_subscriber(subscriber)

    # ------------------------------------------------------------------ #
    # Reticulum info
    # ------------------------------------------------------------------ #
