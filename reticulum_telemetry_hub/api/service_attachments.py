"""Attachment and chat service methods."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import List
from typing import Optional

from reticulum_telemetry_hub.message_delivery import normalize_topic_id
from .models import ChatAttachment
from .models import ChatMessage
from .models import FileAttachment
from .pagination import PageRequest
from .pagination import PaginatedResult


class ApiAttachmentChatMixin:
    """Attachment and chat service methods."""

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

    def list_files_paginated(
        self,
        page_request: PageRequest,
    ) -> PaginatedResult[FileAttachment]:
        """Return a page of stored file records."""

        return self._storage.paginate_file_records(
            page_request,
            category=self._file_category,
        )

    def count_files(self) -> int:
        """Return the number of stored file records."""

        return self._storage.count_file_records(category=self._file_category)

    def list_images(self) -> List[FileAttachment]:
        """Return stored image records."""

        return self._storage.list_file_records(category=self._image_category)

    def list_images_paginated(
        self,
        page_request: PageRequest,
    ) -> PaginatedResult[FileAttachment]:
        """Return a page of stored image records."""

        return self._storage.paginate_file_records(
            page_request,
            category=self._image_category,
        )

    def count_images(self) -> int:
        """Return the number of stored image records."""

        return self._storage.count_file_records(category=self._image_category)

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

    def assign_file_to_topic(
        self,
        record_id: int,
        topic_id: Optional[str],
    ) -> FileAttachment:
        """Associate or detach a stored file from a topic."""

        return self._update_attachment_topic(
            record_id,
            expected_category=self._file_category,
            topic_id=topic_id,
        )

    def assign_image_to_topic(
        self,
        record_id: int,
        topic_id: Optional[str],
    ) -> FileAttachment:
        """Associate or detach a stored image from a topic."""

        return self._update_attachment_topic(
            record_id,
            expected_category=self._image_category,
            topic_id=topic_id,
        )

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

        message.topic_id = normalize_topic_id(message.topic_id)
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
            topic_id=normalize_topic_id(topic_id),
            destination=destination,
            source=source,
        )

    def update_chat_message_state(
        self,
        message_id: str,
        state: str,
        *,
        delivery_metadata: dict | None = None,
    ) -> ChatMessage | None:
        """Update a chat message delivery state."""

        return self._storage.update_chat_message_state(
            message_id,
            state,
            delivery_metadata=delivery_metadata,
        )

    def chat_message_stats(self) -> dict[str, int]:
        """Return aggregated chat message counters."""

        return self._storage.chat_message_stats()

    # ------------------------------------------------------------------ #
    # Topic operations
    # ------------------------------------------------------------------ #
