from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
import uuid

from sqlalchemy import JSON, Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

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

    def __init__(self, db_path: Path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(bind=self._engine, expire_on_commit=False)

    # ------------------------------------------------------------------ #
    # Topic helpers
    # ------------------------------------------------------------------ #
    def create_topic(self, topic: Topic) -> Topic:
        with self._Session() as session:
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
        with self._Session() as session:
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
        with self._Session() as session:
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
        with self._Session() as session:
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

    # ------------------------------------------------------------------ #
    # Subscriber helpers
    # ------------------------------------------------------------------ #
    def create_subscriber(self, subscriber: Subscriber) -> Subscriber:
        with self._Session() as session:
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
        with self._Session() as session:
            records = session.query(SubscriberRecord).all()
            return [self._subscriber_from_record(r) for r in records]

    def get_subscriber(self, subscriber_id: str) -> Optional[Subscriber]:
        with self._Session() as session:
            record = session.get(SubscriberRecord, subscriber_id)
            return self._subscriber_from_record(record) if record else None

    def delete_subscriber(self, subscriber_id: str) -> Optional[Subscriber]:
        with self._Session() as session:
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
        with self._Session() as session:
            record = session.get(ClientRecord, identity)
            if record:
                record.last_seen = _utcnow()
            else:
                record = ClientRecord(identity=identity, last_seen=_utcnow())
                session.add(record)
            session.commit()
            return self._client_from_record(record)

    def remove_client(self, identity: str) -> bool:
        with self._Session() as session:
            record = session.get(ClientRecord, identity)
            if not record:
                return False
            session.delete(record)
            session.commit()
            return True

    def list_clients(self) -> List[Client]:
        with self._Session() as session:
            records = session.query(ClientRecord).all()
            return [self._client_from_record(r) for r in records]

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
