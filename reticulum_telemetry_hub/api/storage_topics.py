"""Topic and subscriber storage methods."""

from __future__ import annotations

from typing import List
from typing import Optional
import uuid

from sqlalchemy.sql.functions import count as sa_count

from reticulum_telemetry_hub.message_delivery import normalize_topic_id
from .models import Subscriber
from .models import Topic
from .pagination import PageRequest
from .pagination import PaginatedResult
from .storage_models import SubscriberRecord
from .storage_models import TopicRecord


class TopicSubscriberStorageMixin:
    """Topic and subscriber storage methods."""

    def create_topic(self, topic: Topic) -> Topic:
        """Insert or update a topic record.

        Args:
            topic (Topic): Topic to persist.

        Returns:
            Topic: Stored topic with an ID assigned.
        """
        with self._session_scope() as session:
            normalized_topic_id = normalize_topic_id(topic.topic_id) or uuid.uuid4().hex
            record = TopicRecord(
                id=normalized_topic_id,
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

    def count_topics(self) -> int:
        """Return the total number of topics."""

        with self._session_scope() as session:
            total = session.query(sa_count(TopicRecord.id)).scalar()
            return int(total or 0)

    def paginate_topics(self, page_request: PageRequest) -> PaginatedResult[Topic]:
        """Return a page of topics ordered by insertion."""

        with self._session_scope() as session:
            total = session.query(sa_count(TopicRecord.id)).scalar() or 0
            records = (
                session.query(TopicRecord)
                .order_by(TopicRecord.created_at, TopicRecord.id)
                .offset(page_request.offset)
                .limit(page_request.per_page)
                .all()
            )
            items = [
                Topic(
                    topic_id=record.id,
                    topic_name=record.name,
                    topic_path=record.path,
                    topic_description=record.description or "",
                )
                for record in records
            ]
            return PaginatedResult.from_request(
                items=items,
                request=page_request,
                total=total,
            )

    def get_topic(self, topic_id: str) -> Optional[Topic]:
        """Fetch a topic by identifier.

        Args:
            topic_id (str): Unique topic identifier.

        Returns:
            Optional[Topic]: Matching topic or ``None`` if missing.
        """
        normalized_topic_id = normalize_topic_id(topic_id)
        with self._session_scope() as session:
            record = session.get(TopicRecord, normalized_topic_id)
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
        normalized_topic_id = normalize_topic_id(topic_id)
        with self._session_scope() as session:
            record = session.get(TopicRecord, normalized_topic_id)
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
        normalized_topic_id = normalize_topic_id(topic_id)
        with self._session_scope() as session:
            record = session.get(TopicRecord, normalized_topic_id)
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
                topic_id=normalize_topic_id(subscriber.topic_id),
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

    def count_subscribers(self) -> int:
        """Return the total number of subscribers."""

        with self._session_scope() as session:
            total = session.query(sa_count(SubscriberRecord.id)).scalar()
            return int(total or 0)

    def paginate_subscribers(self, page_request: PageRequest) -> PaginatedResult[Subscriber]:
        """Return a page of subscribers ordered by insertion."""

        with self._session_scope() as session:
            total = session.query(sa_count(SubscriberRecord.id)).scalar() or 0
            records = (
                session.query(SubscriberRecord)
                .order_by(SubscriberRecord.created_at, SubscriberRecord.id)
                .offset(page_request.offset)
                .limit(page_request.per_page)
                .all()
            )
            return PaginatedResult.from_request(
                items=[self._subscriber_from_record(record) for record in records],
                request=page_request,
                total=total,
            )

    def list_subscribers_for_topic(self, topic_id: str) -> List[Subscriber]:
        """Return subscribers stored for a topic identifier."""

        normalized_topic_id = normalize_topic_id(topic_id)
        with self._session_scope() as session:
            records = (
                session.query(SubscriberRecord)
                .filter(SubscriberRecord.topic_id == normalized_topic_id)
                .all()
            )
            return [self._subscriber_from_record(record) for record in records]

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

    def list_topics_for_destination(self, destination: str) -> List[Topic]:
        """Return topics associated with a subscriber destination."""

        with self._session_scope() as session:
            records = (
                session.query(TopicRecord)
                .join(SubscriberRecord, SubscriberRecord.topic_id == TopicRecord.id)
                .filter(SubscriberRecord.destination == destination)
                .order_by(TopicRecord.created_at, TopicRecord.id)
                .distinct()
                .all()
            )
            return [
                Topic(
                    topic_id=record.id,
                    topic_name=record.name,
                    topic_path=record.path,
                    topic_description=record.description or "",
                )
                for record in records
            ]

