"""Database storage helpers for the Reticulum Telemetry Hub API."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from datetime import timezone
import logging
from pathlib import Path
import time
from typing import List
from typing import Optional
import uuid

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Integer
from sqlalchemy import JSON
from sqlalchemy import String
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from .models import Client
from .models import FileAttachment
from .models import Subscriber
from .models import Topic

Base = declarative_base()


def _utcnow() -> datetime:
    """Return the current UTC datetime with timezone information."""
    return datetime.now(timezone.utc)


class TopicRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for topics."""
    __tablename__ = "topics"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    path = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class SubscriberRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for subscribers."""
    __tablename__ = "subscribers"

    id = Column(String, primary_key=True)
    destination = Column(String, nullable=False)
    topic_id = Column(String, nullable=True)
    reject_tests = Column(Integer, nullable=True)
    metadata_json = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class ClientRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for clients."""
    __tablename__ = "clients"

    identity = Column(String, primary_key=True)
    last_seen = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    metadata_json = Column("metadata", JSON, nullable=True)


class FileRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for stored files."""
    __tablename__ = "file_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    path = Column(String, nullable=False)
    media_type = Column(String, nullable=True)
    category = Column(String, nullable=False)
    size = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class HubStorage:
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
            records = session.query(TopicRecord).all()
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
            return [self._client_from_record(r) for r in records]

    def get_client(self, identity: str) -> Client | None:
        """Return a client by identity when it exists.

        Args:
            identity (str): Unique identity hash for the client.

        Returns:
            Client | None: Stored client or ``None`` when unknown.
        """
        with self._session_scope() as session:
            record = session.get(ClientRecord, identity)
            return self._client_from_record(record) if record else None

    def create_file_record(self, attachment: FileAttachment) -> FileAttachment:
        """Persist metadata about a stored file or image."""
        with self._session_scope() as session:
            record = FileRecord(
                name=attachment.name,
                path=attachment.path,
                media_type=attachment.media_type,
                category=attachment.category,
                size=attachment.size,
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

    @contextmanager
    def _session_scope(self):
        """Yield a database session with automatic cleanup.

        Yields:
            Session: SQLAlchemy session bound to the configured engine.
        """
        session = self._acquire_session_with_retry()
        try:
            yield session
        finally:
            session.close()

    def _acquire_session_with_retry(self):
        """Return a SQLite session, retrying on lock contention."""
        last_exc: OperationalError | None = None
        for attempt in range(1, self._session_retries + 1):
            session = None
            try:
                session = self._session_factory()
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
                    self._session_retries,
                    lock_detail,
                )
                time.sleep(self._session_backoff * attempt)
        logging.error(
            "Unable to obtain SQLite session after %d attempts", self._session_retries
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
    def _client_from_record(record: ClientRecord) -> Client:
        """Convert a ClientRecord into a domain model."""
        client = Client(identity=record.identity, metadata=record.metadata_json or {})
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
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
