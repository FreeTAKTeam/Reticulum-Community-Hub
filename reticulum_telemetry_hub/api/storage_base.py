"""Shared storage helpers for the Reticulum Community Hub API."""

from __future__ import annotations

from contextlib import contextmanager
import logging
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from .models import ChatAttachment
from .models import ChatMessage
from .models import Client
from .models import FileAttachment
from .models import Subscriber
from .storage_models import ChatMessageRecord
from .storage_models import ClientRecord
from .storage_models import FileRecord
from .storage_models import IdentityAnnounceRecord
from .storage_models import SubscriberRecord


class HubStorageBase:
    """Mixin with shared storage helper methods."""

    _engine: Any
    _session_factory: Any
    _session_retries: int
    _session_backoff: float

    def _ensure_file_topic_column(self) -> None:
        """Ensure the file_records table has the topic_id column."""

        try:
            with self._engine.connect() as conn:  # type: ignore[attr-defined]
                result = conn.execute(text("PRAGMA table_info(file_records);"))
                column_names = [row[1] for row in result.fetchall()]
                if "topic_id" not in column_names:
                    conn.execute(
                        text("ALTER TABLE file_records ADD COLUMN topic_id VARCHAR;")
                    )
        except OperationalError as exc:
            logging.warning("Failed to ensure file_records.topic_id column: %s", exc)

    @contextmanager
    def _session_scope(self):
        """Yield a database session with automatic cleanup."""

        session = self._acquire_session_with_retry()  # type: ignore[attr-defined]
        try:
            yield session
        finally:
            session.close()

    def _acquire_session_with_retry(self):
        """Return a SQLite session, retrying on lock contention."""
        last_exc: OperationalError | None = None
        for attempt in range(1, self._session_retries + 1):  # type: ignore[attr-defined]
            session = None
            try:
                session = self._session_factory()  # type: ignore[attr-defined]
                session.execute(text("SELECT 1"))
                return session
            except OperationalError as exc:
                last_exc = exc
                lock_detail = str(exc).strip() or "database is locked"
                if session is not None:
                    session.close()
                logging.warning(
                    "SQLite session acquisition failed (attempt %d/%d): %s",
                    attempt,
                    self._session_retries,  # type: ignore[attr-defined]
                    lock_detail,
                )
                time.sleep(self._session_backoff * attempt)  # type: ignore[attr-defined]
        logging.error(
            "Unable to obtain SQLite session after %d attempts",
            self._session_retries,  # type: ignore[attr-defined]
        )
        if last_exc:
            raise last_exc
        raise RuntimeError("Failed to create SQLite session")

    @staticmethod
    def _subscriber_from_record(record: SubscriberRecord) -> Subscriber:
        """Convert a SubscriberRecord into a domain model."""
        return Subscriber(
            subscriber_id=record.id,
            destination=record.destination,
            topic_id=record.topic_id,
            reject_tests=record.reject_tests,
            metadata=record.metadata_json or {},
        )

    @staticmethod
    def _client_from_record(
        record: ClientRecord,
        announce: IdentityAnnounceRecord | None = None,
    ) -> Client:
        """Convert a ClientRecord into a domain model."""
        metadata = dict(record.metadata_json or {})
        display_name = None
        if announce is not None and announce.display_name:
            display_name = announce.display_name
            metadata.setdefault("display_name", display_name)
        elif isinstance(metadata.get("display_name"), str):
            display_name = metadata.get("display_name")
        client = Client(identity=record.identity, metadata=metadata, display_name=display_name)
        client.last_seen = record.last_seen
        return client

    @staticmethod
    def _file_from_record(record: FileRecord) -> FileAttachment:
        """Convert a FileRecord into a domain model."""
        return FileAttachment(
            file_id=record.id,
            name=record.name,
            path=record.path,
            media_type=record.media_type,
            category=record.category,
            size=record.size,
            topic_id=record.topic_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _chat_from_record(record: ChatMessageRecord) -> ChatMessage:
        """Convert a ChatMessageRecord into a domain model."""
        attachments = [
            ChatAttachment.from_dict(item)
            for item in (record.attachments_json or [])
            if isinstance(item, dict)
        ]
        return ChatMessage(
            message_id=record.id,
            direction=record.direction,
            scope=record.scope,
            state=record.state,
            content=record.content,
            source=record.source,
            destination=record.destination,
            topic_id=record.topic_id,
            attachments=attachments,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _identity_announce_map(session) -> dict[str, IdentityAnnounceRecord]:
        """Return a lookup table for announce metadata."""

        records = session.query(IdentityAnnounceRecord).all()
        return {record.destination_hash: record for record in records}
