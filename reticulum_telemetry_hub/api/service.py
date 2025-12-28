"""Reticulum Telemetry Hub API service operations."""

from __future__ import annotations

import uuid
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import List
from typing import Optional

from reticulum_telemetry_hub.config import HubConfigurationManager

from .models import Client
from .models import FileAttachment
from .models import ReticulumInfo
from .models import Subscriber
from .models import Topic
from .storage import HubStorage


class ReticulumTelemetryHubAPI:  # pylint: disable=too-many-public-methods
    """Persistence-backed implementation of the ReticulumTelemetryHub API."""

    def __init__(
        self,
        config_manager: Optional[HubConfigurationManager] = None,
        storage: Optional[HubStorage] = None,
    ) -> None:
        """Initialize the API service with configuration and storage providers.

        Args:
            config_manager (Optional[HubConfigurationManager]): Manager
                supplying hub configuration. When omitted, a default manager
                loads the hub configuration and database path.
            storage (Optional[HubStorage]): Persistence provider for clients,
                topics, and subscribers. Defaults to storage built with the
                configuration's database path.

        """
        self._config_manager = config_manager or HubConfigurationManager()
        hub_db_path = self._config_manager.config.hub_database_path
        self._storage = storage or HubStorage(hub_db_path)
        self._file_category = "file"
        self._image_category = "image"

    # ------------------------------------------------------------------ #
    # RTH operations
    # ------------------------------------------------------------------ #
    def join(self, identity: str) -> bool:
        """Register a client with the Reticulum Telemetry Hub.

        Args:
            identity (str): Unique Reticulum identity string.

        Returns:
            bool: ``True`` when the identity is recorded or updated.

        Raises:
            ValueError: If ``identity`` is empty.

        Examples:
            >>> api.join("ABCDE")
            True
        """
        if not identity:
            raise ValueError("identity is required")
        self._storage.upsert_client(identity)
        return True

    def leave(self, identity: str) -> bool:
        """Remove a client from the hub.

        Args:
            identity (str): Identity previously joined to the hub.

        Returns:
            bool: ``True`` if the client existed and was removed; ``False``
                otherwise.

        Raises:
            ValueError: If ``identity`` is empty.
        """
        if not identity:
            raise ValueError("identity is required")
        return self._storage.remove_client(identity)

    # ------------------------------------------------------------------ #
    # Client operations
    # ------------------------------------------------------------------ #
    def list_clients(self) -> List[Client]:
        """Return all clients that have joined the hub.

        Returns:
            List[Client]: All persisted client records in insertion order.
        """
        return self._storage.list_clients()

    def has_client(self, identity: str) -> bool:
        """Return ``True`` when the client is registered with the hub.

        Args:
            identity (str): Identity to look up.

        Returns:
            bool: ``True`` if the identity exists in the client registry.
        """
        if not identity:
            return False
        return self._storage.get_client(identity) is not None

    # ------------------------------------------------------------------ #
    # File operations
    # ------------------------------------------------------------------ #
    def store_file(
        self, file_path: str | Path, *, name: Optional[str] = None, media_type: str | None = None
    ) -> FileAttachment:
        """Persist metadata for a file stored on disk.

        Args:
            file_path (str | Path): Location of the file to record.
            name (Optional[str]): Human readable name for the file. Defaults
                to the filename.
            media_type (Optional[str]): MIME type if known.

        Returns:
            FileAttachment: Stored file metadata with an ID.

        Raises:
            ValueError: If the file path is invalid or cannot be read.
        """

        return self._store_attachment(
            file_path=file_path,
            name=name,
            media_type=media_type,
            category=self._file_category,
            base_path=self._config_manager.config.file_storage_path,
        )

    def store_image(
        self, image_path: str | Path, *, name: Optional[str] = None, media_type: str | None = None
    ) -> FileAttachment:
        """Persist metadata for an image stored on disk."""

        return self._store_attachment(
            file_path=image_path,
            name=name,
            media_type=media_type,
            category=self._image_category,
            base_path=self._config_manager.config.image_storage_path,
        )

    def list_files(self) -> List[FileAttachment]:
        """Return stored file records."""

        return self._storage.list_file_records(category=self._file_category)

    def list_images(self) -> List[FileAttachment]:
        """Return stored image records."""

        return self._storage.list_file_records(category=self._image_category)

    def retrieve_file(self, record_id: int) -> FileAttachment:
        """Fetch stored file metadata by ID."""

        return self._retrieve_attachment(record_id, expected_category=self._file_category)

    def retrieve_image(self, record_id: int) -> FileAttachment:
        """Fetch stored image metadata by ID."""

        return self._retrieve_attachment(record_id, expected_category=self._image_category)

    # ------------------------------------------------------------------ #
    # Topic operations
    # ------------------------------------------------------------------ #
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
        topic.topic_id = topic.topic_id or uuid.uuid4().hex
        return self._storage.create_topic(topic)

    def list_topics(self) -> List[Topic]:
        """List all topics known to the hub.

        Returns:
            List[Topic]: Current topic catalog from storage.
        """
        return self._storage.list_topics()

    def retrieve_topic(self, topic_id: str) -> Topic:
        """Fetch a topic by its identifier.

        Args:
            topic_id (str): Identifier of the topic to retrieve.

        Returns:
            Topic: The matching topic.

        Raises:
            KeyError: If the topic does not exist.
        """
        topic = self._storage.get_topic(topic_id)
        if not topic:
            raise KeyError(f"Topic '{topic_id}' not found")
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
        topic = self._storage.delete_topic(topic_id)
        if not topic:
            raise KeyError(f"Topic '{topic_id}' not found")
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
        topic = self.retrieve_topic(topic_id)
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
            raise KeyError(f"Topic '{topic_id}' not found")
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
        subscriber.topic_id = subscriber.topic_id or ""
        subscriber.subscriber_id = subscriber.subscriber_id or uuid.uuid4().hex
        return self._storage.create_subscriber(subscriber)

    def list_subscribers(self) -> List[Subscriber]:
        """List all subscribers.

        Returns:
            List[Subscriber]: Subscribers currently stored in the hub.
        """
        return self._storage.list_subscribers()

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
    def get_app_info(self) -> ReticulumInfo:
        """Return the current Reticulum configuration snapshot.

        Returns:
            ReticulumInfo: Configuration values sourced from the configuration
            manager, including the app name, version, and description.
        """
        info_dict = self._config_manager.reticulum_info_snapshot()
        return ReticulumInfo(**info_dict)

    def _store_attachment(  # pylint: disable=too-many-arguments
        self,
        *,
        file_path: str | Path,
        name: Optional[str],
        media_type: str | None,
        category: str,
        base_path: Path,
    ) -> FileAttachment:
        """Validate inputs and persist file metadata."""

        if category not in {self._file_category, self._image_category}:
            raise ValueError("unsupported category")
        if not file_path:
            raise ValueError("file_path is required")
        path_obj = Path(file_path)
        if not path_obj.is_file():
            raise ValueError(f"File '{file_path}' does not exist")
        resolved_name = name or path_obj.name
        if not resolved_name:
            raise ValueError("name is required")
        base_path.mkdir(parents=True, exist_ok=True)
        stat_result = path_obj.stat()
        timestamp = datetime.now(timezone.utc)
        attachment = FileAttachment(
            name=resolved_name,
            path=str(path_obj),
            category=category,
            size=stat_result.st_size,
            media_type=media_type,
            created_at=timestamp,
            updated_at=timestamp,
        )
        return self._storage.create_file_record(attachment)

    def _retrieve_attachment(self, record_id: int, *, expected_category: str) -> FileAttachment:
        """Return an attachment by ID, ensuring it matches the category."""

        record = self._storage.get_file_record(record_id)
        if not record or record.category != expected_category:
            raise KeyError(f"File '{record_id}' not found")
        return record
