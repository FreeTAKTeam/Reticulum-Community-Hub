"""Database storage helpers for the Reticulum Telemetry Hub API."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List
from typing import Optional
import uuid

from sqlalchemy import create_engine
from sqlalchemy import func
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from .models import ChatMessage
from .models import Client
from .models import FileAttachment
from .models import Subscriber
from .models import Topic
from .storage_base import HubStorageBase
from .storage_models import Base
from .storage_models import ChatMessageRecord
from .storage_models import ClientRecord
from .storage_models import FileRecord
from .storage_models import IdentityAnnounceRecord
from .storage_models import IdentityStateRecord
from .storage_models import SubscriberRecord
from .storage_models import TopicRecord
from .storage_models import _utcnow


class HubStorage(HubStorageBase):
    """SQLAlchemy-backed persistence layer for the RTH API."""
    _POOL_SIZE = 25
    _POOL_OVERFLOW = 50
    _CONNECT_TIMEOUT_SECONDS = 30
    _session_retries = 3
    _session_backoff = 0.1

    def __init__(self, db_path: Path):
        """Create a storage instance backed by SQLite.

        Args:
            db_path (Path): Path to the SQLite database file.
        """
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._engine = self._create_engine(db_path)
        self._enable_wal_mode()
        Base.metadata.create_all(self._engine)
        self._ensure_file_topic_column()
        self._session_factory = sessionmaker(  # pylint: disable=invalid-name
            bind=self._engine, expire_on_commit=False
        )

    @property
    def _Session(self):  # pylint: disable=invalid-name
        """Return a session factory for backward compatibility in tests."""
        return self._session_factory

    def create_topic(self, topic: Topic) -> Topic:
        """Insert or update a topic record.

        Args:
            topic (Topic): Topic to persist.

        Returns:
            Topic: Stored topic with an ID assigned.
        """
        with self._session_scope() as session:
            record = TopicRecord(
                id=topic.topic_id or uuid.uuid4().hex,
                name=topic.topic_name,
                path=topic.topic_path,
                description=topic.topic_description,
            )
            session.merge(record)
            session.commit()
            return Topic(
                topic_id=record.id,
                topic_name=record.name,
                topic_path=record.path,
                topic_description=record.description or "",
            )

    def list_topics(self) -> List[Topic]:
        """Return all topics ordered by insertion."""
        with self._session_scope() as session:
            records = (
                session.query(TopicRecord)
                .order_by(TopicRecord.created_at, TopicRecord.id)
                .all()
            )
            return [
                Topic(
                    topic_id=r.id,
                    topic_name=r.name,
                    topic_path=r.path,
                    topic_description=r.description or "",
                )
                for r in records
            ]

    def get_topic(self, topic_id: str) -> Optional[Topic]:
        """Fetch a topic by identifier.

        Args:
            topic_id (str): Unique topic identifier.

        Returns:
            Optional[Topic]: Matching topic or ``None`` if missing.
        """
        with self._session_scope() as session:
            record = session.get(TopicRecord, topic_id)
            if not record:
                return None
            return Topic(
                topic_id=record.id,
                topic_name=record.name,
                topic_path=record.path,
                topic_description=record.description or "",
            )

    def delete_topic(self, topic_id: str) -> Optional[Topic]:
        """Delete a topic record.

        Args:
            topic_id (str): Identifier of the topic to remove.

        Returns:
            Optional[Topic]: Removed topic or ``None`` when absent.
        """
        with self._session_scope() as session:
            record = session.get(TopicRecord, topic_id)
            if not record:
                return None
            session.delete(record)
            session.commit()
            return Topic(
                topic_id=record.id,
                topic_name=record.name,
                topic_path=record.path,
                topic_description=record.description or "",
            )

    def update_topic(
        self,
        topic_id: str,
        *,
        topic_name: Optional[str] = None,
        topic_path: Optional[str] = None,
        topic_description: Optional[str] = None,
    ) -> Optional[Topic]:
        """Update a topic with provided fields.

        Args:
            topic_id (str): Identifier of the topic to update.
            topic_name (Optional[str]): New name when provided.
            topic_path (Optional[str]): New path when provided.
            topic_description (Optional[str]): New description when provided.

        Returns:
            Optional[Topic]: Updated topic or ``None`` when not found.
        """
        with self._session_scope() as session:
            record = session.get(TopicRecord, topic_id)
            if not record:
                return None
            if topic_name is not None:
                record.name = topic_name
            if topic_path is not None:
                record.path = topic_path
            if topic_description is not None:
                record.description = topic_description
            session.commit()
            return Topic(
                topic_id=record.id,
                topic_name=record.name,
                topic_path=record.path,
                topic_description=record.description or "",
            )

    def create_subscriber(self, subscriber: Subscriber) -> Subscriber:
        """Insert or update a subscriber record.

        Args:
            subscriber (Subscriber): Subscriber data to persist.

        Returns:
            Subscriber: Stored subscriber with ID assigned.
        """
        with self._session_scope() as session:
            record = SubscriberRecord(
                id=subscriber.subscriber_id or uuid.uuid4().hex,
                destination=subscriber.destination,
                topic_id=subscriber.topic_id,
                reject_tests=subscriber.reject_tests,
                metadata_json=subscriber.metadata or {},
            )
            session.merge(record)
            session.commit()
            return self._subscriber_from_record(record)

    def list_subscribers(self) -> List[Subscriber]:
        """Return all subscribers."""
        with self._session_scope() as session:
            records = session.query(SubscriberRecord).all()
            return [self._subscriber_from_record(r) for r in records]

    def get_subscriber(self, subscriber_id: str) -> Optional[Subscriber]:
        """Fetch a subscriber by ID.

        Args:
            subscriber_id (str): Unique subscriber identifier.

        Returns:
            Optional[Subscriber]: Matching subscriber or ``None``.
        """
        with self._session_scope() as session:
            record = session.get(SubscriberRecord, subscriber_id)
            return self._subscriber_from_record(record) if record else None

    def delete_subscriber(self, subscriber_id: str) -> Optional[Subscriber]:
        """Delete a subscriber.

        Args:
            subscriber_id (str): Identifier of the subscriber to remove.

        Returns:
            Optional[Subscriber]: Removed subscriber or ``None`` if missing.
        """
        with self._session_scope() as session:
            record = session.get(SubscriberRecord, subscriber_id)
            if not record:
                return None
            session.delete(record)
            session.commit()
            return self._subscriber_from_record(record)

    def update_subscriber(self, subscriber: Subscriber) -> Subscriber:
        """Update a subscriber by merging fields."""
        return self.create_subscriber(subscriber)

    def upsert_client(self, identity: str) -> Client:
        """Insert or update a client record.

        Args:
            identity (str): Client identity hash.

        Returns:
            Client: Stored or updated client instance.
        """
        with self._session_scope() as session:
            record = session.get(ClientRecord, identity)
            if record:
                record.last_seen = _utcnow()
            else:
                record = ClientRecord(identity=identity, last_seen=_utcnow())
                session.add(record)
            session.commit()
            return self._client_from_record(record)

    def remove_client(self, identity: str) -> bool:
        """Remove a client from storage.

        Args:
            identity (str): Identity hash to delete.

        Returns:
            bool: ``True`` when deletion occurred, ``False`` otherwise.
        """
        with self._session_scope() as session:
            record = session.get(ClientRecord, identity)
            if not record:
                return False
            session.delete(record)
            session.commit()
            return True

    def list_clients(self) -> List[Client]:
        """Return all known clients."""
        with self._session_scope() as session:
            records = session.query(ClientRecord).all()
            announce_map = self._identity_announce_map(session)
            return [
                self._client_from_record(
                    record, announce_map.get(record.identity.lower())
                )
                for record in records
            ]

    def get_client(self, identity: str) -> Client | None:
        """Return a client by identity when it exists.

        Args:
            identity (str): Unique identity hash for the client.

        Returns:
            Client | None: Stored client or ``None`` when unknown.
        """
        with self._session_scope() as session:
            record = session.get(ClientRecord, identity)
            if not record:
                return None
            announce = session.get(IdentityAnnounceRecord, identity.lower())
            return self._client_from_record(record, announce)

    def create_file_record(self, attachment: FileAttachment) -> FileAttachment:
        """Persist metadata about a stored file or image."""
        with self._session_scope() as session:
            record = FileRecord(
                name=attachment.name,
                path=attachment.path,
                media_type=attachment.media_type,
                category=attachment.category,
                size=attachment.size,
                topic_id=attachment.topic_id,
                created_at=attachment.created_at,
                updated_at=attachment.updated_at,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._file_from_record(record)

    def list_file_records(self, category: str | None = None) -> List[FileAttachment]:
        """Return all stored file records, optionally filtered by category."""
        with self._session_scope() as session:
            query = session.query(FileRecord)
            if category:
                query = query.filter(FileRecord.category == category)
            records = query.all()
            return [self._file_from_record(record) for record in records]

    def get_file_record(self, record_id: int) -> FileAttachment | None:
        """Return a stored file by its database identifier."""
        with self._session_scope() as session:
            record = session.get(FileRecord, record_id)
            return self._file_from_record(record) if record else None

    def delete_file_record(self, record_id: int) -> FileAttachment | None:
        """Delete a stored file by its database identifier."""

        with self._session_scope() as session:
            record = session.get(FileRecord, record_id)
            if not record:
                return None
            attachment = self._file_from_record(record)
            session.delete(record)
            session.commit()
            return attachment

    def upsert_identity_state(
        self,
        identity: str,
        *,
        is_banned: bool | None = None,
        is_blackholed: bool | None = None,
    ) -> IdentityStateRecord:
        """Insert or update the moderation state for an identity."""

        with self._session_scope() as session:
            record = session.get(IdentityStateRecord, identity)
            if record is None:
                record = IdentityStateRecord(identity=identity)
                session.add(record)
            if is_banned is not None:
                record.is_banned = bool(is_banned)
            if is_blackholed is not None:
                record.is_blackholed = bool(is_blackholed)
            record.updated_at = _utcnow()
            session.commit()
            return record

    def upsert_identity_announce(
        self,
        identity: str,
        *,
        display_name: str | None = None,
        source_interface: str | None = None,
    ) -> IdentityAnnounceRecord:
        """Insert or update Reticulum announce metadata."""

        identity = identity.lower()
        now = _utcnow()
        with self._session_scope() as session:
            record = session.get(IdentityAnnounceRecord, identity)
            if record is None:
                record = IdentityAnnounceRecord(
                    destination_hash=identity,
                    display_name=display_name,
                    first_seen=now,
                    last_seen=now,
                    source_interface=source_interface,
                )
                session.add(record)
            else:
                record.last_seen = now
                if display_name and (
                    record.display_name is None or record.display_name != display_name
                ):
                    record.display_name = display_name
                if source_interface and (
                    record.source_interface is None
                    or record.source_interface != source_interface
                ):
                    record.source_interface = source_interface
            session.commit()
            return record

    def get_identity_announce(self, identity: str) -> IdentityAnnounceRecord | None:
        """Return announce metadata for an identity when present."""

        with self._session_scope() as session:
            return session.get(IdentityAnnounceRecord, identity.lower())

    def list_identity_announces(self) -> List[IdentityAnnounceRecord]:
        """Return all announce metadata records."""

        with self._session_scope() as session:
            return session.query(IdentityAnnounceRecord).all()

    def get_identity_state(self, identity: str) -> IdentityStateRecord | None:
        """Return the moderation state for an identity when present."""

        with self._session_scope() as session:
            return session.get(IdentityStateRecord, identity)

    def list_identity_states(self) -> List[IdentityStateRecord]:
        """Return all identity moderation state records."""

        with self._session_scope() as session:
            return session.query(IdentityStateRecord).all()

    def create_chat_message(self, message: ChatMessage) -> ChatMessage:
        """Insert or update a chat message record."""

        with self._session_scope() as session:
            record = ChatMessageRecord(
                id=message.message_id or uuid.uuid4().hex,
                direction=message.direction,
                scope=message.scope,
                state=message.state,
                content=message.content,
                source=message.source,
                destination=message.destination,
                topic_id=message.topic_id,
                attachments_json=[attachment.to_dict() for attachment in message.attachments],
                created_at=message.created_at,
                updated_at=message.updated_at,
            )
            session.merge(record)
            session.commit()
            return self._chat_from_record(record)

    def list_chat_messages(
        self,
        *,
        limit: int = 200,
        direction: str | None = None,
        topic_id: str | None = None,
        destination: str | None = None,
        source: str | None = None,
    ) -> List[ChatMessage]:
        """Return chat messages with optional filters."""

        with self._session_scope() as session:
            query = session.query(ChatMessageRecord)
            if direction:
                query = query.filter(ChatMessageRecord.direction == direction)
            if topic_id:
                query = query.filter(ChatMessageRecord.topic_id == topic_id)
            if destination:
                query = query.filter(ChatMessageRecord.destination == destination)
            if source:
                query = query.filter(ChatMessageRecord.source == source)
            records = (
                query.order_by(ChatMessageRecord.created_at.desc())
                .limit(max(limit, 1))
                .all()
            )
            return [self._chat_from_record(record) for record in records]

    def update_chat_message_state(self, message_id: str, state: str) -> ChatMessage | None:
        """Update a chat message delivery state."""

        with self._session_scope() as session:
            record = session.get(ChatMessageRecord, message_id)
            if not record:
                return None
            record.state = state
            record.updated_at = _utcnow()
            session.commit()
            return self._chat_from_record(record)

    def chat_message_stats(self) -> dict[str, int]:
        """Return basic chat message counters."""

        with self._session_scope() as session:
            rows = (
                session.query(ChatMessageRecord.state, func.count(ChatMessageRecord.id))
                .group_by(ChatMessageRecord.state)
                .all()
            )
            return {state: count for state, count in rows}

    def _create_engine(self, db_path: Path) -> Engine:
        """Build a SQLite engine configured for concurrency.

        Args:
            db_path (Path): Database path for the engine.

        Returns:
            Engine: Configured SQLAlchemy engine.
        """
        return create_engine(
            f"sqlite:///{db_path}",
            connect_args={
                "check_same_thread": False,
                "timeout": self._CONNECT_TIMEOUT_SECONDS,
            },
            poolclass=QueuePool,
            pool_size=self._POOL_SIZE,
            max_overflow=self._POOL_OVERFLOW,
            pool_pre_ping=True,
        )

    def _enable_wal_mode(self) -> None:
        """Enable write-ahead logging on the SQLite connection."""
        try:
            with self._engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as conn:
                conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
        except OperationalError as exc:
            logging.warning("Failed to enable WAL mode: %s", exc)
