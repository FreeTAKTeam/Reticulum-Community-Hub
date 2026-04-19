"""Shared storage helpers for the Reticulum Community Hub API."""

from __future__ import annotations

from contextlib import contextmanager
import logging
import time
from typing import Any

from sqlalchemy import case
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

    def _ensure_chat_delivery_metadata_column(self) -> None:
        """Ensure the chat_messages table has the delivery_metadata column."""

        try:
            with self._engine.connect() as conn:  # type: ignore[attr-defined]
                result = conn.execute(text("PRAGMA table_info(chat_messages);"))
                column_names = [row[1] for row in result.fetchall()]
                if "delivery_metadata" not in column_names:
                    conn.execute(
                        text(
                            "ALTER TABLE chat_messages "
                            "ADD COLUMN delivery_metadata JSON;"
                        )
                    )
        except OperationalError as exc:
            logging.warning(
                "Failed to ensure chat_messages.delivery_metadata column: %s",
                exc,
            )

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
        announce_capabilities: list[str] = []
        client_type = "generic_lxmf"
        if announce is not None and announce.display_name:
            display_name = announce.display_name
            metadata.setdefault("display_name", display_name)
        elif isinstance(metadata.get("display_name"), str):
            display_name = metadata.get("display_name")
        if announce is not None:
            raw_caps = announce.announce_capabilities_json or []
            if isinstance(raw_caps, list):
                announce_capabilities = [
                    str(item).strip().lower() for item in raw_caps if str(item).strip()
                ]
            raw_client_type = str(announce.client_type or "").strip().lower()
            if raw_client_type:
                client_type = raw_client_type
        client = Client(
            identity=record.identity,
            metadata=metadata,
            display_name=display_name,
            client_type=client_type,
            announce_capabilities=announce_capabilities,
            is_rem_capable=client_type == "rem",
        )
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
            delivery_metadata=record.delivery_metadata_json or {},
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _identity_announce_preferred(
        candidate: IdentityAnnounceRecord,
        current: IdentityAnnounceRecord,
    ) -> bool:
        """Return True when ``candidate`` should be the canonical base record."""

        candidate_source = str(candidate.source_interface or "").strip().lower()
        current_source = str(current.source_interface or "").strip().lower()
        if candidate_source != current_source:
            return candidate_source == "identity"
        return bool(candidate.display_name) and not bool(current.display_name)

    @staticmethod
    def _merge_identity_announce_records(
        current: IdentityAnnounceRecord | None,
        candidate: IdentityAnnounceRecord,
    ) -> IdentityAnnounceRecord:
        """Return a canonical announce record merged across announce sources."""

        if current is None:
            merged = IdentityAnnounceRecord(destination_hash=candidate.destination_hash)
            merged.announced_identity_hash = candidate.announced_identity_hash
            merged.display_name = candidate.display_name
            merged.announce_capabilities_json = candidate.announce_capabilities_json
            merged.client_type = candidate.client_type
            merged.first_seen = candidate.first_seen
            merged.last_seen = candidate.last_seen
            merged.last_capability_seen_at = candidate.last_capability_seen_at
            merged.source_interface = candidate.source_interface
            return merged

        preferred = candidate if HubStorageBase._identity_announce_preferred(candidate, current) else current
        other = current if preferred is candidate else candidate
        merged = IdentityAnnounceRecord(destination_hash=preferred.destination_hash)
        merged.announced_identity_hash = preferred.announced_identity_hash or other.announced_identity_hash
        merged.display_name = preferred.display_name or other.display_name
        merged.announce_capabilities_json = (
            preferred.announce_capabilities_json
            if preferred.announce_capabilities_json
            else other.announce_capabilities_json
        )
        merged.client_type = preferred.client_type or other.client_type
        merged.first_seen = min(
            [value for value in (current.first_seen, candidate.first_seen) if value is not None],
            default=None,
        )
        merged.last_seen = max(
            [value for value in (current.last_seen, candidate.last_seen) if value is not None],
            default=None,
        )
        merged.last_capability_seen_at = max(
            [
                value
                for value in (
                    current.last_capability_seen_at,
                    candidate.last_capability_seen_at,
                )
                if value is not None
            ],
            default=None,
        )
        merged.source_interface = preferred.source_interface or other.source_interface
        return merged

    @staticmethod
    def _identity_announce_map(session) -> dict[str, IdentityAnnounceRecord]:
        """Return a lookup table for announce metadata."""

        records = session.query(IdentityAnnounceRecord).all()
        announce_map: dict[str, IdentityAnnounceRecord] = {}
        for record in records:
            identity_key = str(
                record.announced_identity_hash or record.destination_hash or ""
            ).strip().lower()
            if not identity_key:
                continue
            announce_map[identity_key] = HubStorageBase._merge_identity_announce_records(
                announce_map.get(identity_key),
                record,
            )
        return announce_map

    @staticmethod
    def _identity_announce_for_identity(
        session,
        identity: str,
    ) -> IdentityAnnounceRecord | None:
        """Return announce metadata for ``identity`` using indexed point lookups."""

        normalized_identity = str(identity or "").strip().lower()
        if not normalized_identity:
            return None
        direct = session.get(IdentityAnnounceRecord, normalized_identity)
        if direct is not None:
            return direct
        return (
            session.query(IdentityAnnounceRecord)
            .filter(IdentityAnnounceRecord.announced_identity_hash == normalized_identity)
            .order_by(
                case(
                    (IdentityAnnounceRecord.source_interface == "identity", 0),
                    (IdentityAnnounceRecord.display_name.is_not(None), 1),
                    else_=2,
                ),
                IdentityAnnounceRecord.last_seen.desc(),
            )
            .first()
        )
