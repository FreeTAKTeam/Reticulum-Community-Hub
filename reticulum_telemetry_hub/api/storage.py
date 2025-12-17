from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import logging
from pathlib import Path
import time
from typing import List, Optional
import uuid

from sqlalchemy import JSON, Column, DateTime, Integer, String, create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

from .models import Client, Subscriber, Topic

Base = declarative_base()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TopicRecord(Base):
    __tablename__ = "topics"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    path = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class SubscriberRecord(Base):
    __tablename__ = "subscribers"

    id = Column(String, primary_key=True)
    destination = Column(String, nullable=False)
    topic_id = Column(String, nullable=True)
    reject_tests = Column(Integer, nullable=True)
    metadata_json = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class ClientRecord(Base):
    __tablename__ = "clients"

    identity = Column(String, primary_key=True)
    last_seen = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    metadata_json = Column("metadata", JSON, nullable=True)


class HubStorage:
    """SQLAlchemy-backed persistence layer for the RTH API."""

    _POOL_SIZE = 25
    _POOL_OVERFLOW = 50
    _CONNECT_TIMEOUT_SECONDS = 30
    _SESSION_RETRIES = 3
    _SESSION_BACKOFF = 0.1

    def __init__(self, db_path: Path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._engine = self._create_engine(db_path)
        self._enable_wal_mode()
        Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(bind=self._engine, expire_on_commit=False)

    # ------------------------------------------------------------------ #
    # Topic helpers
    # ------------------------------------------------------------------ #
    def create_topic(self, topic: Topic) -> Topic:
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

    # ------------------------------------------------------------------ #
    # Subscriber helpers
    # ------------------------------------------------------------------ #
    def create_subscriber(self, subscriber: Subscriber) -> Subscriber:
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
        with self._session_scope() as session:
            records = session.query(SubscriberRecord).all()
            return [self._subscriber_from_record(r) for r in records]

    def get_subscriber(self, subscriber_id: str) -> Optional[Subscriber]:
        with self._session_scope() as session:
            record = session.get(SubscriberRecord, subscriber_id)
            return self._subscriber_from_record(record) if record else None

    def delete_subscriber(self, subscriber_id: str) -> Optional[Subscriber]:
        with self._session_scope() as session:
            record = session.get(SubscriberRecord, subscriber_id)
            if not record:
                return None
            session.delete(record)
            session.commit()
            return self._subscriber_from_record(record)

    def update_subscriber(self, subscriber: Subscriber) -> Subscriber:
        return self.create_subscriber(subscriber)

    # ------------------------------------------------------------------ #
    # Client helpers
    # ------------------------------------------------------------------ #
    def upsert_client(self, identity: str) -> Client:
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
        with self._session_scope() as session:
            record = session.get(ClientRecord, identity)
            if not record:
                return False
            session.delete(record)
            session.commit()
            return True

    def list_clients(self) -> List[Client]:
        with self._session_scope() as session:
            records = session.query(ClientRecord).all()
            return [self._client_from_record(r) for r in records]

    # ------------------------------------------------------------------ #
    # engine/session helpers
    # ------------------------------------------------------------------ #
    def _create_engine(self, db_path: Path) -> Engine:
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
        try:
            with self._engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as conn:
                conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
        except OperationalError as exc:
            logging.warning("Failed to enable WAL mode: %s", exc)

    @contextmanager
    def _session_scope(self):
        """Yield a database session with automatic cleanup."""

        session = self._acquire_session_with_retry()
        try:
            yield session
        finally:
            session.close()

    def _acquire_session_with_retry(self):
        """Return a SQLite session, retrying on lock contention."""

        last_exc: OperationalError | None = None
        for attempt in range(1, self._SESSION_RETRIES + 1):
            session = None
            try:
                session = self._Session()
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
                    self._SESSION_RETRIES,
                    lock_detail,
                )
                time.sleep(self._SESSION_BACKOFF * attempt)
        logging.error(
            "Unable to obtain SQLite session after %d attempts", self._SESSION_RETRIES
        )
        if last_exc:
            raise last_exc
        raise RuntimeError("Failed to create SQLite session")

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _subscriber_from_record(record: SubscriberRecord) -> Subscriber:
        return Subscriber(
            subscriber_id=record.id,
            destination=record.destination,
            topic_id=record.topic_id,
            reject_tests=record.reject_tests,
            metadata=record.metadata_json or {},
        )

    @staticmethod
    def _client_from_record(record: ClientRecord) -> Client:
        client = Client(identity=record.identity, metadata=record.metadata_json or {})
        client.last_seen = record.last_seen
        return client
