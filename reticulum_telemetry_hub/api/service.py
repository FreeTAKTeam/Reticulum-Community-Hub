"""Reticulum Telemetry Hub API service operations."""

from __future__ import annotations

import string
import uuid
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from typing import Callable
from typing import List
from typing import Optional

from reticulum_telemetry_hub.config import HubConfigurationManager
from reticulum_telemetry_hub.config.models import HubAppConfig

from .filesystem import FileSystemAdapter
from .filesystem import LocalFileSystemAdapter
from .models import ChatAttachment
from .models import ChatMessage
from .models import Client
from .models import FileAttachment
from .models import IdentityStatus
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
        on_config_reload: Optional[Callable[[HubAppConfig], None]] = None,
        filesystem: Optional[FileSystemAdapter] = None,
    ) -> None:
        """Initialize the API service with configuration and storage providers.

        Args:
            config_manager (Optional[HubConfigurationManager]): Manager
                supplying hub configuration. When omitted, a default manager
                loads the hub configuration and database path.
            storage (Optional[HubStorage]): Persistence provider for clients,
                topics, and subscribers. Defaults to storage built with the
                configuration's database path.
            filesystem (Optional[FileSystemAdapter]): Filesystem adapter used
                for file operations. Defaults to a local pathlib-backed
                implementation.

        """
        self._config_manager = config_manager or HubConfigurationManager()
        hub_db_path = self._config_manager.config.hub_database_path
        self._storage = storage or HubStorage(hub_db_path)
        self._filesystem = filesystem or LocalFileSystemAdapter()
        self._file_category = "file"
        self._image_category = "image"
        self._on_config_reload = on_config_reload
        self._reticulum_destination: str | None = None

    def set_reticulum_destination(self, destination: str | None) -> None:
        """Set the Reticulum destination hash for app info responses.

        Args:
            destination (str | None): Hex-encoded destination hash. Provide
                ``None`` or whitespace to clear the value.

        Raises:
            ValueError: If ``destination`` is not a valid hex string.
        """

        if destination is None:
            self._reticulum_destination = None
            return

        cleaned = destination.strip()
        if not cleaned:
            self._reticulum_destination = None
            return

        if not all(char in string.hexdigits for char in cleaned):
            raise ValueError("destination must be a hex string")
        if len(cleaned) % 2 != 0:
            raise ValueError("destination must contain an even number of hex characters")

        self._reticulum_destination = cleaned.lower()

    def _build_reticulum_info(self, info_dict: dict) -> ReticulumInfo:
        """Return a ReticulumInfo model enriched with runtime data.

        Args:
            info_dict (dict): Base info payload from configuration.

        Returns:
            ReticulumInfo: Info snapshot including runtime destination data.
        """

        payload = dict(info_dict)
        payload["hub_display_name"] = self._config_manager.resolve_hub_display_name(
            destination_hash=self._reticulum_destination
        )
        payload["reticulum_destination"] = self._reticulum_destination
        return ReticulumInfo(**payload)

    def _notify_config_reload(self, config: HubAppConfig) -> None:
        """Invoke the config reload callback when configured.

        Args:
            config (HubAppConfig): Updated configuration snapshot.
        """

        if self._on_config_reload is None:
            return
        self._on_config_reload(config)

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

    def record_identity_announce(
        self,
        identity: str,
        *,
        display_name: str | None = None,
        source_interface: str | None = None,
    ) -> None:
        """Persist announce metadata for a Reticulum identity.

        Args:
            identity (str): Destination hash in hex form.
            display_name (str | None): Optional display name from announce data.
            source_interface (str | None): Optional source interface label.
        """

        if not identity:
            raise ValueError("identity is required")
        identity = identity.lower()
        self._storage.upsert_identity_announce(
            identity,
            display_name=display_name,
            source_interface=source_interface,
        )

    def resolve_identity_display_name(self, identity: str) -> str | None:
        """Return the stored display name for an identity when available."""

        if not identity:
            return None
        record = self._storage.get_identity_announce(identity.lower())
        if record is None:
            return None
        return record.display_name

    def list_identity_capabilities(self, identity: str) -> List[str]:
        """Return active capabilities for an identity."""

        if not identity:
            return []
        return self._storage.list_identity_capabilities(identity)

    def list_capability_grants(self, identity: str | None = None) -> List[dict]:
        """Return persisted capability grant entries."""

        records = self._storage.list_identity_capability_grants(identity=identity)
        return [
            {
                "grant_uid": record.grant_uid,
                "identity": record.identity,
                "capability": record.capability,
                "granted": bool(record.granted),
                "granted_by": record.granted_by,
                "granted_at": record.granted_at.isoformat()
                if record.granted_at
                else None,
                "expires_at": record.expires_at.isoformat()
                if record.expires_at
                else None,
                "updated_at": record.updated_at.isoformat()
                if record.updated_at
                else None,
            }
            for record in records
        ]

    def grant_identity_capability(
        self,
        identity: str,
        capability: str,
        *,
        granted_by: str | None = None,
        expires_at: datetime | None = None,
    ) -> dict:
        """Grant a capability to an identity."""

        if not identity:
            raise ValueError("identity is required")
        if not capability:
            raise ValueError("capability is required")
        record = self._storage.upsert_identity_capability(
            identity,
            capability,
            granted=True,
            granted_by=granted_by,
            expires_at=expires_at,
        )
        return {
            "grant_uid": record.grant_uid,
            "identity": record.identity,
            "capability": record.capability,
            "granted": bool(record.granted),
        }

    def revoke_identity_capability(
        self,
        identity: str,
        capability: str,
        *,
        granted_by: str | None = None,
    ) -> dict:
        """Revoke a capability from an identity."""

        if not identity:
            raise ValueError("identity is required")
        if not capability:
            raise ValueError("capability is required")
        record = self._storage.upsert_identity_capability(
            identity,
            capability,
            granted=False,
            granted_by=granted_by,
            expires_at=None,
        )
        return {
            "grant_uid": record.grant_uid,
            "identity": record.identity,
            "capability": record.capability,
            "granted": bool(record.granted),
        }

    # ------------------------------------------------------------------ #
    # File operations
    # ------------------------------------------------------------------ #
    def store_file(
        self,
        file_path: str | Path,
        *,
        name: Optional[str] = None,
        media_type: str | None = None,
        topic_id: Optional[str] = None,
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
            topic_id=topic_id,
            category=self._file_category,
            base_path=self._config_manager.config.file_storage_path,
        )

    def store_image(
        self,
        image_path: str | Path,
        *,
        name: Optional[str] = None,
        media_type: str | None = None,
        topic_id: Optional[str] = None,
    ) -> FileAttachment:
        """Persist metadata for an image stored on disk."""

        return self._store_attachment(
            file_path=image_path,
            name=name,
            media_type=media_type,
            topic_id=topic_id,
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

    def delete_file(self, record_id: int) -> FileAttachment:
        """Delete a stored file from disk and metadata storage."""

        return self._delete_attachment(record_id, expected_category=self._file_category)

    def delete_image(self, record_id: int) -> FileAttachment:
        """Delete a stored image from disk and metadata storage."""

        return self._delete_attachment(record_id, expected_category=self._image_category)

    def store_uploaded_attachment(
        self,
        *,
        content: bytes,
        filename: str,
        media_type: Optional[str],
        category: str,
        topic_id: Optional[str] = None,
    ) -> FileAttachment:
        """Persist uploaded attachment bytes to disk and record metadata."""

        safe_name = Path(filename).name
        if not safe_name:
            raise ValueError("filename is required")
        if category == self._image_category:
            base_path = self._config_manager.config.image_storage_path
        elif category == self._file_category:
            base_path = self._config_manager.config.file_storage_path
        else:
            raise ValueError("unsupported category")
        self._filesystem.ensure_directory(base_path)
        suffix = Path(safe_name).suffix
        stored_name = f"{uuid.uuid4().hex}{suffix}"
        target_path = base_path / stored_name
        self._filesystem.write_bytes(target_path, content)
        return self._store_attachment(
            file_path=target_path,
            name=safe_name,
            media_type=media_type,
            topic_id=topic_id,
            category=category,
            base_path=base_path,
        )

    @staticmethod
    def chat_attachment_from_file(attachment: FileAttachment) -> ChatAttachment:
        """Convert a FileAttachment into a ChatAttachment reference."""

        return ChatAttachment(
            file_id=attachment.file_id or 0,
            category=attachment.category,
            name=attachment.name,
            size=attachment.size,
            media_type=attachment.media_type,
        )

    def record_chat_message(self, message: ChatMessage) -> ChatMessage:
        """Persist a chat message and return the stored record."""

        message.message_id = message.message_id or uuid.uuid4().hex
        return self._storage.create_chat_message(message)

    def list_chat_messages(
        self,
        *,
        limit: int = 200,
        direction: Optional[str] = None,
        topic_id: Optional[str] = None,
        destination: Optional[str] = None,
        source: Optional[str] = None,
    ) -> List[ChatMessage]:
        """Return persisted chat messages."""

        return self._storage.list_chat_messages(
            limit=limit,
            direction=direction,
            topic_id=topic_id,
            destination=destination,
            source=source,
        )

    def update_chat_message_state(self, message_id: str, state: str) -> ChatMessage | None:
        """Update a chat message delivery state."""

        return self._storage.update_chat_message_state(message_id, state)

    def chat_message_stats(self) -> dict[str, int]:
        """Return aggregated chat message counters."""

        return self._storage.chat_message_stats()

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

    def list_subscribers_for_topic(self, topic_id: str) -> List[Subscriber]:
        """Return subscribers for a specific topic.

        Args:
            topic_id (str): Topic identifier to filter by.

        Returns:
            List[Subscriber]: Subscribers attached to the topic.

        Raises:
            KeyError: If the topic does not exist.
        """
        self.retrieve_topic(topic_id)
        return [
            subscriber
            for subscriber in self._storage.list_subscribers()
            if subscriber.topic_id == topic_id
        ]

    def list_topics_for_destination(self, destination: str) -> List[Topic]:
        """Return topics a destination is subscribed to.

        Args:
            destination (str): Destination identity hash to query.

        Returns:
            List[Topic]: Topics matching the destination's subscriptions.
        """
        topic_ids = {
            subscriber.topic_id
            for subscriber in self._storage.list_subscribers()
            if subscriber.destination == destination and subscriber.topic_id
        }
        return [topic for topic in self.list_topics() if topic.topic_id in topic_ids]

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
        return self._build_reticulum_info(info_dict)

    def get_config_text(self) -> str:
        """Return the raw hub configuration file content."""

        return self._config_manager.get_config_text()

    def get_reticulum_config_text(self) -> str:
        """Return the raw Reticulum configuration file content."""

        return self._config_manager.get_reticulum_config_text()

    def validate_config_text(self, config_text: str) -> dict:
        """Validate the provided configuration payload."""

        return self._config_manager.validate_config_text(config_text)

    def validate_reticulum_config_text(self, config_text: str) -> dict:
        """Validate the provided Reticulum configuration payload."""

        return self._config_manager.validate_reticulum_config_text(config_text)

    def apply_config_text(self, config_text: str) -> dict:
        """Persist a new configuration payload and reload."""

        result = self._config_manager.apply_config_text(config_text)
        config = self._config_manager.reload()
        self._notify_config_reload(config)
        return result

    def apply_reticulum_config_text(self, config_text: str) -> dict:
        """Persist a new Reticulum configuration payload and reload."""

        result = self._config_manager.apply_reticulum_config_text(config_text)
        config = self._config_manager.reload()
        self._notify_config_reload(config)
        return result

    def rollback_config_text(self, backup_path: str | None = None) -> dict:
        """Rollback configuration from the latest backup."""

        result = self._config_manager.rollback_config_text(backup_path=backup_path)
        config = self._config_manager.reload()
        self._notify_config_reload(config)
        return result

    def rollback_reticulum_config_text(self, backup_path: str | None = None) -> dict:
        """Rollback Reticulum configuration from the latest backup."""

        result = self._config_manager.rollback_reticulum_config_text(
            backup_path=backup_path
        )
        config = self._config_manager.reload()
        self._notify_config_reload(config)
        return result

    def reload_config(self) -> ReticulumInfo:
        """Reload the configuration from disk."""

        config = self._config_manager.reload()
        self._notify_config_reload(config)
        return self._build_reticulum_info(config.to_reticulum_info_dict())

    def list_identity_statuses(self) -> List[IdentityStatus]:
        """Return identity statuses merged with client data."""

        clients: dict[str, Client] = {}
        for client in self._storage.list_clients():
            if not client.identity:
                continue
            identity_key = client.identity.strip().lower()
            if not identity_key:
                continue
            existing = clients.get(identity_key)
            if existing is None or client.last_seen > existing.last_seen:
                clients[identity_key] = client

        states: dict[str, dict[str, object]] = {}
        for state in self._storage.list_identity_states():
            identity_value = getattr(state, "identity", None)
            if not identity_value:
                continue
            identity_key = identity_value.strip().lower()
            if not identity_key:
                continue
            entry = states.get(identity_key)
            if entry is None:
                states[identity_key] = {
                    "identity": identity_value,
                    "is_banned": bool(state.is_banned),
                    "is_blackholed": bool(state.is_blackholed),
                    "updated_at": state.updated_at,
                }
                continue
            entry["is_banned"] = bool(entry["is_banned"]) or bool(state.is_banned)
            entry["is_blackholed"] = bool(entry["is_blackholed"]) or bool(
                state.is_blackholed
            )
            updated_at = state.updated_at
            existing_updated_at = entry.get("updated_at")
            if updated_at is None:
                continue
            if existing_updated_at is None or updated_at >= existing_updated_at:
                entry["identity"] = identity_value
                entry["updated_at"] = updated_at

        announces = {
            record.destination_hash.lower(): record
            for record in self._storage.list_identity_announces()
        }
        announce_sources = {
            key: (record.source_interface or "").strip().lower() or None
            for key, record in announces.items()
        }
        identities = sorted(
            set(clients.keys()) | set(states.keys()) | set(announces.keys())
        )
        statuses: List[IdentityStatus] = []
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=60)
        for identity_key in identities:
            client = clients.get(identity_key)
            state_entry = states.get(identity_key)
            announce = announces.get(identity_key)
            display_name = announce.display_name if announce else None
            metadata = dict(client.metadata if client else {})
            if display_name and "display_name" not in metadata:
                metadata["display_name"] = display_name
            is_banned = bool(state_entry.get("is_banned")) if state_entry else False
            is_blackholed = (
                bool(state_entry.get("is_blackholed")) if state_entry else False
            )
            announce_last_seen = None
            if announce and announce.last_seen:
                announce_last_seen = announce.last_seen
                if announce_last_seen.tzinfo is None:
                    announce_last_seen = announce_last_seen.replace(tzinfo=timezone.utc)
            last_seen = announce_last_seen or (client.last_seen if client else None)
            status = "inactive"
            if announce_last_seen and announce_last_seen >= cutoff:
                status = "active"
            if is_blackholed:
                status = "blackholed"
            elif is_banned:
                status = "banned"
            identity_value = identity_key
            if client and client.identity:
                identity_value = client.identity
            elif state_entry and state_entry.get("identity"):
                identity_value = str(state_entry.get("identity"))
            elif announce and announce.destination_hash:
                identity_value = announce.destination_hash
            statuses.append(
                IdentityStatus(
                    identity=identity_value,
                    status=status,
                    last_seen=last_seen,
                    display_name=display_name,
                    metadata=metadata,
                    is_banned=is_banned,
                    is_blackholed=is_blackholed,
                )
            )
        return self._dedupe_identity_statuses(
            statuses,
            announce_sources=announce_sources,
            client_keys=set(clients.keys()),
            state_keys=set(states.keys()),
        )

    def _dedupe_identity_statuses(
        self,
        statuses: List[IdentityStatus],
        *,
        announce_sources: dict[str, str | None],
        client_keys: set[str],
        state_keys: set[str],
    ) -> List[IdentityStatus]:
        """Collapse duplicate identity statuses with matching display metadata.

        Args:
            statuses (List[IdentityStatus]): Raw identity status entries.
            announce_sources (dict[str, str | None]): Announce source tags keyed by
                identity hash.
            client_keys (set[str]): Identities currently joined to the hub.
            state_keys (set[str]): Identities with moderation state records.

        Returns:
            List[IdentityStatus]: Deduplicated status list for UI consumption.
        """

        results: List[IdentityStatus] = []
        index_by_key: dict[tuple[object, ...], int] = {}
        for status in statuses:
            display_name = (status.display_name or "").strip()
            if not display_name:
                results.append(status)
                continue
            key = (
                display_name.lower(),
                status.status,
                self._identity_status_bucket(status.last_seen),
                bool(status.is_banned),
                bool(status.is_blackholed),
            )
            existing_index = index_by_key.get(key)
            if existing_index is None:
                index_by_key[key] = len(results)
                results.append(status)
                continue
            existing = results[existing_index]
            if self._identity_status_preferred(
                status,
                existing,
                announce_sources=announce_sources,
                client_keys=client_keys,
                state_keys=state_keys,
            ):
                results[existing_index] = status
        return results

    @staticmethod
    def _identity_status_bucket(last_seen: datetime | None) -> int | None:
        """Return a bucketed timestamp for deduping announce entries.

        Args:
            last_seen (datetime | None): Timestamp to bucket.

        Returns:
            int | None: A 5-second bucket epoch timestamp or ``None`` when missing.
        """

        if not last_seen:
            return None
        timestamp = int(last_seen.timestamp())
        return timestamp - (timestamp % 5)

    @staticmethod
    def _identity_status_rank(
        identity_key: str,
        *,
        announce_sources: dict[str, str | None],
        client_keys: set[str],
        state_keys: set[str],
    ) -> int:
        """Return a preference rank for selecting a canonical identity entry.

        Args:
            identity_key (str): Normalized identity hash.
            announce_sources (dict[str, str | None]): Announce source tags keyed by
                identity hash.
            client_keys (set[str]): Joined identities.
            state_keys (set[str]): Moderated identities.

        Returns:
            int: Preference rank where higher values are preferred.
        """

        if identity_key in client_keys or identity_key in state_keys:
            return 3
        source = announce_sources.get(identity_key)
        if source == "identity":
            return 2
        if source == "destination":
            return 1
        return 0

    @classmethod
    def _identity_status_preferred(
        cls,
        candidate: IdentityStatus,
        current: IdentityStatus,
        *,
        announce_sources: dict[str, str | None],
        client_keys: set[str],
        state_keys: set[str],
    ) -> bool:
        """Return True when the candidate status should replace the current one.

        Args:
            candidate (IdentityStatus): Proposed replacement entry.
            current (IdentityStatus): Existing entry in the deduped list.
            announce_sources (dict[str, str | None]): Announce source tags keyed by
                identity hash.
            client_keys (set[str]): Joined identities.
            state_keys (set[str]): Moderated identities.

        Returns:
            bool: ``True`` if the candidate should replace the current entry.
        """

        candidate_key = (candidate.identity or "").strip().lower()
        current_key = (current.identity or "").strip().lower()
        candidate_rank = cls._identity_status_rank(
            candidate_key,
            announce_sources=announce_sources,
            client_keys=client_keys,
            state_keys=state_keys,
        )
        current_rank = cls._identity_status_rank(
            current_key,
            announce_sources=announce_sources,
            client_keys=client_keys,
            state_keys=state_keys,
        )
        if candidate_rank != current_rank:
            return candidate_rank > current_rank
        if candidate_key and current_key and candidate_key != current_key:
            return candidate_key < current_key
        return False

    def ban_identity(self, identity: str) -> IdentityStatus:
        """Mark an identity as banned."""

        if not identity:
            raise ValueError("identity is required")
        state = self._storage.upsert_identity_state(identity, is_banned=True)
        client = self._storage.get_client(identity)
        announce = self._storage.get_identity_announce(identity.lower())
        display_name = announce.display_name if announce else None
        metadata = dict(client.metadata if client else {})
        if display_name and "display_name" not in metadata:
            metadata["display_name"] = display_name
        last_seen = announce.last_seen if announce else None
        if last_seen and last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        return IdentityStatus(
            identity=identity,
            status="banned",
            last_seen=last_seen or (client.last_seen if client else None),
            display_name=display_name,
            metadata=metadata,
            is_banned=state.is_banned,
            is_blackholed=state.is_blackholed,
        )

    def unban_identity(self, identity: str) -> IdentityStatus:
        """Clear ban/blackhole flags for an identity."""

        if not identity:
            raise ValueError("identity is required")
        state = self._storage.upsert_identity_state(
            identity, is_banned=False, is_blackholed=False
        )
        client = self._storage.get_client(identity)
        announce = self._storage.get_identity_announce(identity.lower())
        display_name = announce.display_name if announce else None
        metadata = dict(client.metadata if client else {})
        if display_name and "display_name" not in metadata:
            metadata["display_name"] = display_name
        last_seen = announce.last_seen if announce else None
        if last_seen and last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        status = "inactive"
        if last_seen and last_seen >= datetime.now(timezone.utc) - timedelta(minutes=60):
            status = "active"
        return IdentityStatus(
            identity=identity,
            status=status,
            last_seen=last_seen or (client.last_seen if client else None),
            display_name=display_name,
            metadata=metadata,
            is_banned=state.is_banned,
            is_blackholed=state.is_blackholed,
        )

    def blackhole_identity(self, identity: str) -> IdentityStatus:
        """Mark an identity as blackholed."""

        if not identity:
            raise ValueError("identity is required")
        state = self._storage.upsert_identity_state(identity, is_blackholed=True)
        client = self._storage.get_client(identity)
        announce = self._storage.get_identity_announce(identity.lower())
        display_name = announce.display_name if announce else None
        metadata = dict(client.metadata if client else {})
        if display_name and "display_name" not in metadata:
            metadata["display_name"] = display_name
        last_seen = announce.last_seen if announce else None
        if last_seen and last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        return IdentityStatus(
            identity=identity,
            status="blackholed",
            last_seen=last_seen or (client.last_seen if client else None),
            display_name=display_name,
            metadata=metadata,
            is_banned=state.is_banned,
            is_blackholed=state.is_blackholed,
        )

    def _store_attachment(  # pylint: disable=too-many-arguments
        self,
        *,
        file_path: str | Path,
        name: Optional[str],
        media_type: str | None,
        topic_id: Optional[str],
        category: str,
        base_path: Path,
    ) -> FileAttachment:
        """Validate inputs and persist file metadata."""

        if category not in {self._file_category, self._image_category}:
            raise ValueError("unsupported category")
        if not file_path:
            raise ValueError("file_path is required")
        path_obj = Path(file_path)
        if not self._filesystem.is_file(path_obj):
            raise ValueError(f"File '{file_path}' does not exist")
        resolved_name = name or path_obj.name
        if not resolved_name:
            raise ValueError("name is required")
        self._filesystem.ensure_directory(base_path)
        resolved_base_path = self._filesystem.resolve(base_path)
        resolved_path = self._filesystem.resolve(path_obj)
        try:
            resolved_path.relative_to(resolved_base_path)
        except ValueError as exc:
            raise ValueError(
                f"File '{file_path}' must be stored within '{resolved_base_path}'"
            ) from exc
        timestamp = datetime.now(timezone.utc)
        attachment = FileAttachment(
            name=resolved_name,
            path=str(resolved_path),
            category=category,
            size=self._filesystem.stat_size(resolved_path),
            media_type=media_type,
            topic_id=topic_id,
            created_at=timestamp,
            updated_at=timestamp,
        )
        return self._storage.create_file_record(attachment)

    def _delete_attachment(
        self,
        record_id: int,
        *,
        expected_category: str,
    ) -> FileAttachment:
        """Delete an attachment record and its on-disk file.

        The persisted attachment record already contains the canonical on-disk
        path. Deletion should therefore use the stored path directly instead of
        re-validating it against the *current* configuration, which can change
        after the record was created or differ from older attachment layouts.
        When the stored path itself cannot be inspected cleanly (for example
        due to legacy malformed values on a different platform), the metadata
        record is still removed so the operator is not blocked by a stale entry.
        """

        record = self._retrieve_attachment(record_id, expected_category=expected_category)
        path_value = record.path
        if isinstance(path_value, str) and path_value:
            stored_path = Path(path_value)
            try:
                if self._filesystem.is_file(stored_path):
                    self._filesystem.delete_file(stored_path)
            except ValueError:
                pass
        deleted = self._storage.delete_file_record(record_id)
        if deleted is None:
            raise KeyError(f"File '{record_id}' not found")
        return deleted

    def _retrieve_attachment(self, record_id: int, *, expected_category: str) -> FileAttachment:
        """Return an attachment by ID, ensuring it matches the category."""

        record = self._storage.get_file_record(record_id)
        if not record or record.category != expected_category:
            raise KeyError(f"File '{record_id}' not found")
        return record
