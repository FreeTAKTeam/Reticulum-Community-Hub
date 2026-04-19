"""Database storage helpers for the Reticulum Telemetry Hub API."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List
from typing import Optional
import uuid

from sqlalchemy import create_engine
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from sqlalchemy.sql import text
from sqlalchemy.sql.functions import count as sa_count

from .models import ChatMessage
from .models import Client
from .models import FileAttachment
from .models import Subscriber
from .models import Topic
from .pagination import PageRequest
from .pagination import PaginatedResult
from reticulum_telemetry_hub.message_delivery import normalize_topic_id
from .rights_storage_models import MissionAccessAssignmentRecord
from .rights_storage_models import SubjectOperationGrantRecord
from .storage_base import HubStorageBase
from .storage_models import Base
from .storage_models import ChatMessageRecord
from .storage_models import ClientRecord
from .storage_models import FileRecord
from .storage_models import IdentityAnnounceRecord
from .storage_models import IdentityCapabilityGrantRecord
from .storage_models import IdentityRemModeRecord
from .storage_models import IdentityStateRecord
from .storage_models import R3aktMissionRecord
from .storage_models import R3aktTeamMemberClientLinkRecord
from .storage_models import R3aktTeamMemberRecord
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
        self._ensure_chat_delivery_metadata_column()
        self._ensure_identity_announce_columns()
        self._ensure_indexes()
        self._backfill_identity_capability_grants()
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

    def count_clients(self) -> int:
        """Return the total number of clients."""

        with self._session_scope() as session:
            total = session.query(sa_count(ClientRecord.identity)).scalar()
            return int(total or 0)

    def paginate_clients(self, page_request: PageRequest) -> PaginatedResult[Client]:
        """Return a page of known clients ordered by recent activity."""

        with self._session_scope() as session:
            total = session.query(sa_count(ClientRecord.identity)).scalar() or 0
            records = (
                session.query(ClientRecord)
                .order_by(ClientRecord.last_seen.desc(), ClientRecord.identity)
                .offset(page_request.offset)
                .limit(page_request.per_page)
                .all()
            )
            announce_map = self._identity_announce_map(
                session,
                identities=[record.identity for record in records],
            )
            items = [
                self._client_from_record(
                    record,
                    announce_map.get(record.identity.lower()),
                )
                for record in records
            ]
            return PaginatedResult.from_request(
                items=items,
                request=page_request,
                total=total,
            )

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
            announce = self._identity_announce_for_identity(session, identity)
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

    def count_file_records(self, category: str | None = None) -> int:
        """Return the number of stored file records for an optional category."""

        with self._session_scope() as session:
            query = session.query(sa_count(FileRecord.id))
            if category:
                query = query.filter(FileRecord.category == category)
            total = query.scalar()
            return int(total or 0)

    def paginate_file_records(
        self,
        page_request: PageRequest,
        category: str | None = None,
    ) -> PaginatedResult[FileAttachment]:
        """Return a page of stored file records, optionally filtered by category."""

        with self._session_scope() as session:
            count_query = session.query(sa_count(FileRecord.id))
            query = session.query(FileRecord)
            if category:
                count_query = count_query.filter(FileRecord.category == category)
                query = query.filter(FileRecord.category == category)
            total = count_query.scalar() or 0
            records = (
                query.order_by(FileRecord.created_at.desc(), FileRecord.id)
                .offset(page_request.offset)
                .limit(page_request.per_page)
                .all()
            )
            return PaginatedResult.from_request(
                items=[self._file_from_record(record) for record in records],
                request=page_request,
                total=total,
            )

    def get_file_record(self, record_id: int) -> FileAttachment | None:
        """Return a stored file by its database identifier."""
        with self._session_scope() as session:
            record = session.get(FileRecord, record_id)
            return self._file_from_record(record) if record else None

    def update_file_record_topic(
        self,
        record_id: int,
        *,
        topic_id: str | None,
    ) -> FileAttachment | None:
        """Update the topic association for a stored file or image."""

        with self._session_scope() as session:
            record = session.get(FileRecord, record_id)
            if not record:
                return None
            record.topic_id = normalize_topic_id(topic_id)
            record.updated_at = _utcnow()
            session.commit()
            return self._file_from_record(record)

    def clear_file_record_topic(self, topic_id: str) -> int:
        """Remove a topic association from all linked file/image records."""

        normalized_topic_id = normalize_topic_id(topic_id)
        if not normalized_topic_id:
            return 0
        topic_match_values = {normalized_topic_id.lower()}
        try:
            topic_uuid = uuid.UUID(normalized_topic_id)
        except (ValueError, AttributeError, TypeError):
            pass
        else:
            topic_match_values.add(topic_uuid.hex.lower())
            topic_match_values.add(str(topic_uuid).lower())
        with self._session_scope() as session:
            records = (
                session.query(FileRecord)
                .filter(func.lower(func.trim(FileRecord.topic_id)).in_(topic_match_values))
                .all()
            )
            for record in records:
                record.topic_id = None
                record.updated_at = _utcnow()
            session.commit()
            return len(records)

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
        announced_identity_hash: str | None = None,
        display_name: str | None = None,
        source_interface: str | None = None,
        announce_capabilities: list[str] | None = None,
        client_type: str | None = None,
    ) -> IdentityAnnounceRecord:
        """Insert or update Reticulum announce metadata."""

        identity = identity.lower()
        normalized_announced_identity = (
            announced_identity_hash.strip().lower()
            if isinstance(announced_identity_hash, str) and announced_identity_hash.strip()
            else None
        )
        now = _utcnow()
        with self._session_scope() as session:
            insert_values = {
                "destination_hash": identity,
                "announced_identity_hash": normalized_announced_identity,
                "display_name": display_name,
                "announce_capabilities": list(announce_capabilities or []) or None,
                "client_type": client_type,
                "first_seen": now,
                "last_seen": now,
                "last_capability_seen_at": now if announce_capabilities is not None else None,
                "source_interface": source_interface,
            }
            update_values = {"last_seen": now}
            if normalized_announced_identity:
                update_values["announced_identity_hash"] = normalized_announced_identity
            if display_name:
                update_values["display_name"] = display_name
            if source_interface:
                update_values["source_interface"] = source_interface
            if announce_capabilities is not None:
                update_values["announce_capabilities"] = list(announce_capabilities)
                update_values["last_capability_seen_at"] = now
            if client_type:
                update_values["client_type"] = client_type
            stmt = sqlite_insert(IdentityAnnounceRecord.__table__).values(**insert_values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[IdentityAnnounceRecord.destination_hash],
                set_=update_values,
            )
            session.execute(stmt)
            session.commit()
            record = session.get(IdentityAnnounceRecord, identity)
            if record is None:  # pragma: no cover - defensive
                raise RuntimeError("Failed to upsert identity announce record")
            return record

    def get_identity_announce(self, identity: str) -> IdentityAnnounceRecord | None:
        """Return announce metadata for an identity when present."""

        with self._session_scope() as session:
            return self._identity_announce_for_identity(session, identity)

    def resolve_identity_display_names_bulk(
        self,
        identities: list[str],
    ) -> dict[str, str | None]:
        """Resolve display names for many identities with one database roundtrip."""

        normalized_identities = [
            str(identity).strip().lower()
            for identity in identities
            if str(identity).strip()
        ]
        if not normalized_identities:
            return {}
        requested = set(normalized_identities)
        canonical_announces: dict[str, IdentityAnnounceRecord] = {}
        keys_by_canonical: dict[str, set[str]] = {}
        with self._session_scope() as session:
            records = (
                session.query(IdentityAnnounceRecord)
                .filter(
                    or_(
                        IdentityAnnounceRecord.destination_hash.in_(requested),
                        IdentityAnnounceRecord.announced_identity_hash.in_(requested),
                    )
                )
                .all()
            )
            for record in records:
                destination_hash = str(record.destination_hash or "").strip().lower()
                announced_identity_hash = str(record.announced_identity_hash or "").strip().lower()
                canonical_key = announced_identity_hash or destination_hash
                if not canonical_key:
                    continue
                canonical_announces[canonical_key] = self._merge_identity_announce_records(
                    canonical_announces.get(canonical_key),
                    record,
                )
                keys = keys_by_canonical.setdefault(canonical_key, set())
                if destination_hash in requested:
                    keys.add(destination_hash)
                if announced_identity_hash in requested:
                    keys.add(announced_identity_hash)
        resolved_display_names: dict[str, str | None] = {}
        for canonical_key, keys in keys_by_canonical.items():
            display_name = canonical_announces.get(canonical_key).display_name
            for key in keys:
                resolved_display_names[key] = display_name

        return {identity: resolved_display_names.get(identity) for identity in normalized_identities}

    def list_identity_announces(self) -> List[IdentityAnnounceRecord]:
        """Return all announce metadata records."""

        with self._session_scope() as session:
            return session.query(IdentityAnnounceRecord).all()

    def list_canonical_identity_announces(self) -> List[IdentityAnnounceRecord]:
        """Return announce metadata merged by canonical announced identity."""

        with self._session_scope() as session:
            return list(self._identity_announce_map(session).values())

    def upsert_identity_rem_mode(
        self,
        identity: str,
        *,
        mode: str,
    ) -> IdentityRemModeRecord:
        """Insert or update a persisted REM mode registration."""

        normalized_identity = identity.strip().lower()
        normalized_mode = mode.strip().lower()
        now = _utcnow()
        with self._session_scope() as session:
            insert_values = {
                "identity": normalized_identity,
                "mode": normalized_mode,
                "requested_at": now,
                "updated_at": now,
            }
            stmt = sqlite_insert(IdentityRemModeRecord).values(**insert_values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[IdentityRemModeRecord.identity],
                set_={
                    "mode": normalized_mode,
                    "updated_at": now,
                },
            )
            session.execute(stmt)
            session.commit()
            record = session.get(IdentityRemModeRecord, normalized_identity)
            if record is None:  # pragma: no cover - defensive
                raise RuntimeError("Failed to persist identity REM mode")
            return record

    def get_identity_rem_mode(self, identity: str) -> IdentityRemModeRecord | None:
        """Return the persisted REM mode registration for an identity."""

        with self._session_scope() as session:
            return session.get(IdentityRemModeRecord, identity.strip().lower())

    def list_identity_rem_modes(self) -> List[IdentityRemModeRecord]:
        """Return all persisted REM mode registrations."""

        with self._session_scope() as session:
            return (
                session.query(IdentityRemModeRecord)
                .order_by(IdentityRemModeRecord.identity.asc())
                .all()
            )

    def upsert_identity_capability(
        self,
        identity: str,
        capability: str,
        *,
        granted: bool = True,
        granted_by: str | None = None,
        expires_at=None,
    ) -> IdentityCapabilityGrantRecord:
        """Insert or update a capability grant for an identity."""

        identity = identity.strip().lower()
        capability = capability.strip()
        now = _utcnow()
        with self._session_scope() as session:
            insert_values = {
                "grant_uid": uuid.uuid4().hex,
                "identity": identity,
                "capability": capability,
                "granted": bool(granted),
                "granted_by": granted_by,
                "granted_at": now,
                "expires_at": expires_at,
                "updated_at": now,
            }
            update_values = {
                "granted": bool(granted),
                "granted_by": granted_by,
                "updated_at": now,
                "expires_at": expires_at,
            }
            if granted:
                update_values["granted_at"] = now
            stmt = sqlite_insert(IdentityCapabilityGrantRecord).values(**insert_values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[
                    IdentityCapabilityGrantRecord.identity,
                    IdentityCapabilityGrantRecord.capability,
                ],
                set_=update_values,
            )
            session.execute(stmt)
            session.commit()
            record = (
                session.query(IdentityCapabilityGrantRecord)
                .filter(
                    IdentityCapabilityGrantRecord.identity == identity,
                    IdentityCapabilityGrantRecord.capability == capability,
                )
                .first()
            )
            if record is None:  # pragma: no cover - defensive
                raise RuntimeError("Failed to persist identity capability grant")
            return record

    def list_identity_capabilities(self, identity: str) -> List[str]:
        """Return active capabilities granted to an identity."""

        identity = identity.strip().lower()
        now = _utcnow()
        with self._session_scope() as session:
            rows = (
                session.query(IdentityCapabilityGrantRecord.capability)
                .filter(
                    IdentityCapabilityGrantRecord.identity == identity,
                    IdentityCapabilityGrantRecord.granted.is_(True),
                    or_(
                        IdentityCapabilityGrantRecord.expires_at.is_(None),
                        IdentityCapabilityGrantRecord.expires_at > now,
                    ),
                )
                .all()
            )
            return sorted({row[0] for row in rows})

    def list_identity_capability_grants(
        self, identity: str | None = None
    ) -> List[IdentityCapabilityGrantRecord]:
        """Return persisted capability grants."""

        with self._session_scope() as session:
            query = session.query(IdentityCapabilityGrantRecord)
            if identity:
                query = query.filter(
                    IdentityCapabilityGrantRecord.identity == identity.strip().lower()
                )
            return (
                query.order_by(
                    IdentityCapabilityGrantRecord.identity,
                    IdentityCapabilityGrantRecord.capability,
                )
                .all()
            )

    def upsert_operation_right(
        self,
        subject_type: str,
        subject_id: str,
        operation: str,
        *,
        scope_type: str | None = None,
        scope_id: str | None = None,
        granted: bool = True,
        granted_by: str | None = None,
        expires_at=None,
        granted_at=None,
        updated_at=None,
    ) -> SubjectOperationGrantRecord:
        """Insert or update a subject-scoped operation right."""

        normalized_subject_type = self._normalize_subject_type(subject_type)
        normalized_subject_id = self._normalize_subject_id(
            normalized_subject_type,
            subject_id,
        )
        normalized_operation = self._normalize_operation(operation)
        normalized_scope_type, normalized_scope_id = self._normalize_scope(
            scope_type,
            scope_id,
        )
        now = updated_at or _utcnow()
        grant_timestamp = granted_at or now

        with self._session_scope() as session:
            insert_values = {
                "grant_uid": uuid.uuid4().hex,
                "subject_type": normalized_subject_type,
                "subject_id": normalized_subject_id,
                "operation": normalized_operation,
                "scope_type": normalized_scope_type,
                "scope_id": normalized_scope_id,
                "granted": bool(granted),
                "granted_by": granted_by,
                "granted_at": grant_timestamp,
                "expires_at": expires_at,
                "updated_at": now,
            }
            update_values = {
                "granted": bool(granted),
                "granted_by": granted_by,
                "expires_at": expires_at,
                "updated_at": now,
            }
            if granted_at is not None or granted:
                update_values["granted_at"] = grant_timestamp
            stmt = sqlite_insert(SubjectOperationGrantRecord).values(**insert_values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[
                    SubjectOperationGrantRecord.subject_type,
                    SubjectOperationGrantRecord.subject_id,
                    SubjectOperationGrantRecord.operation,
                    SubjectOperationGrantRecord.scope_type,
                    SubjectOperationGrantRecord.scope_id,
                ],
                set_=update_values,
            )
            session.execute(stmt)
            session.commit()
            record = (
                session.query(SubjectOperationGrantRecord)
                .filter(
                    SubjectOperationGrantRecord.subject_type == normalized_subject_type,
                    SubjectOperationGrantRecord.subject_id == normalized_subject_id,
                    SubjectOperationGrantRecord.operation == normalized_operation,
                    SubjectOperationGrantRecord.scope_type == normalized_scope_type,
                    SubjectOperationGrantRecord.scope_id == normalized_scope_id,
                )
                .first()
            )
            if record is None:  # pragma: no cover - defensive
                raise RuntimeError("Failed to persist subject operation grant")
            return record

    def list_operation_rights(
        self,
        *,
        subject_type: str | None = None,
        subject_id: str | None = None,
        operation: str | None = None,
        scope_type: str | None = None,
        scope_id: str | None = None,
    ) -> List[SubjectOperationGrantRecord]:
        """Return persisted subject-scoped operation rights."""

        with self._session_scope() as session:
            query = session.query(SubjectOperationGrantRecord)
            if subject_type:
                normalized_subject_type = self._normalize_subject_type(subject_type)
                query = query.filter(
                    SubjectOperationGrantRecord.subject_type == normalized_subject_type
                )
                if subject_id is not None:
                    query = query.filter(
                        SubjectOperationGrantRecord.subject_id
                        == self._normalize_subject_id(
                            normalized_subject_type,
                            subject_id,
                        )
                    )
            elif subject_id is not None:
                raise ValueError("subject_type is required when subject_id is provided")
            if operation:
                query = query.filter(
                    SubjectOperationGrantRecord.operation
                    == self._normalize_operation(operation)
                )
            if scope_type is not None or scope_id is not None:
                normalized_scope_type, normalized_scope_id = self._normalize_scope(
                    scope_type,
                    scope_id,
                )
                query = query.filter(
                    SubjectOperationGrantRecord.scope_type == normalized_scope_type,
                    SubjectOperationGrantRecord.scope_id == normalized_scope_id,
                )
            return (
                query.order_by(
                    SubjectOperationGrantRecord.subject_type,
                    SubjectOperationGrantRecord.subject_id,
                    SubjectOperationGrantRecord.operation,
                    SubjectOperationGrantRecord.scope_type,
                    SubjectOperationGrantRecord.scope_id,
                )
                .all()
            )

    def upsert_mission_access_assignment(
        self,
        mission_uid: str,
        subject_type: str,
        subject_id: str,
        role: str,
        *,
        assigned_by: str | None = None,
        assigned_at=None,
        updated_at=None,
    ) -> MissionAccessAssignmentRecord:
        """Insert or update a mission access role assignment."""

        normalized_mission_uid = str(mission_uid or "").strip()
        if not normalized_mission_uid:
            raise ValueError("mission_uid is required")
        normalized_subject_type = self._normalize_subject_type(subject_type)
        normalized_subject_id = self._normalize_subject_id(
            normalized_subject_type,
            subject_id,
        )
        normalized_role = str(role or "").strip().upper()
        if not normalized_role:
            raise ValueError("role is required")
        now = updated_at or _utcnow()
        assignment_timestamp = assigned_at or now

        with self._session_scope() as session:
            insert_values = {
                "assignment_uid": uuid.uuid4().hex,
                "mission_uid": normalized_mission_uid,
                "subject_type": normalized_subject_type,
                "subject_id": normalized_subject_id,
                "role": normalized_role,
                "assigned_by": assigned_by,
                "assigned_at": assignment_timestamp,
                "updated_at": now,
            }
            stmt = sqlite_insert(MissionAccessAssignmentRecord).values(**insert_values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[
                    MissionAccessAssignmentRecord.mission_uid,
                    MissionAccessAssignmentRecord.subject_type,
                    MissionAccessAssignmentRecord.subject_id,
                ],
                set_={
                    "role": normalized_role,
                    "assigned_by": assigned_by,
                    "assigned_at": assignment_timestamp,
                    "updated_at": now,
                },
            )
            session.execute(stmt)
            session.commit()
            record = (
                session.query(MissionAccessAssignmentRecord)
                .filter(
                    MissionAccessAssignmentRecord.mission_uid == normalized_mission_uid,
                    MissionAccessAssignmentRecord.subject_type == normalized_subject_type,
                    MissionAccessAssignmentRecord.subject_id == normalized_subject_id,
                )
                .first()
            )
            if record is None:  # pragma: no cover - defensive
                raise RuntimeError("Failed to persist mission access assignment")
            return record

    def delete_mission_access_assignment(
        self,
        mission_uid: str,
        subject_type: str,
        subject_id: str,
    ) -> bool:
        """Delete a mission access role assignment."""

        normalized_mission_uid = str(mission_uid or "").strip()
        if not normalized_mission_uid:
            raise ValueError("mission_uid is required")
        normalized_subject_type = self._normalize_subject_type(subject_type)
        normalized_subject_id = self._normalize_subject_id(
            normalized_subject_type,
            subject_id,
        )
        with self._session_scope() as session:
            deleted = (
                session.query(MissionAccessAssignmentRecord)
                .filter(
                    MissionAccessAssignmentRecord.mission_uid == normalized_mission_uid,
                    MissionAccessAssignmentRecord.subject_type == normalized_subject_type,
                    MissionAccessAssignmentRecord.subject_id == normalized_subject_id,
                )
                .delete(synchronize_session=False)
            )
            session.commit()
            return bool(deleted)

    def list_mission_access_assignments(
        self,
        *,
        mission_uid: str | None = None,
        subject_type: str | None = None,
        subject_id: str | None = None,
    ) -> List[MissionAccessAssignmentRecord]:
        """Return mission access role assignments."""

        with self._session_scope() as session:
            query = session.query(MissionAccessAssignmentRecord)
            if mission_uid:
                query = query.filter(
                    MissionAccessAssignmentRecord.mission_uid == str(mission_uid).strip()
                )
            if subject_type:
                normalized_subject_type = self._normalize_subject_type(subject_type)
                query = query.filter(
                    MissionAccessAssignmentRecord.subject_type == normalized_subject_type
                )
                if subject_id is not None:
                    query = query.filter(
                        MissionAccessAssignmentRecord.subject_id
                        == self._normalize_subject_id(
                            normalized_subject_type,
                            subject_id,
                        )
                    )
            elif subject_id is not None:
                raise ValueError("subject_type is required when subject_id is provided")
            return (
                query.order_by(
                    MissionAccessAssignmentRecord.mission_uid,
                    MissionAccessAssignmentRecord.subject_type,
                    MissionAccessAssignmentRecord.subject_id,
                )
                .all()
            )

    def get_mission_record(self, mission_uid: str) -> R3aktMissionRecord | None:
        """Return a mission record when present."""

        with self._session_scope() as session:
            return session.get(R3aktMissionRecord, str(mission_uid or "").strip())

    def get_team_member_record(self, team_member_uid: str) -> R3aktTeamMemberRecord | None:
        """Return a team member record when present."""

        with self._session_scope() as session:
            return session.get(R3aktTeamMemberRecord, str(team_member_uid or "").strip())

    def get_team_member_by_identity(self, identity: str) -> List[R3aktTeamMemberRecord]:
        """Return team members matching the given RNS identity."""

        normalized_identity = str(identity or "").strip().lower()
        if not normalized_identity:
            return []
        with self._session_scope() as session:
            return (
                session.query(R3aktTeamMemberRecord)
                .filter(
                    func.lower(R3aktTeamMemberRecord.rns_identity) == normalized_identity
                )
                .order_by(R3aktTeamMemberRecord.display_name.asc())
                .all()
            )

    def list_team_member_client_links(
        self,
        *,
        team_member_uid: str | None = None,
        client_identity: str | None = None,
    ) -> List[R3aktTeamMemberClientLinkRecord]:
        """Return team-member/client identity link records."""

        with self._session_scope() as session:
            query = session.query(R3aktTeamMemberClientLinkRecord)
            if team_member_uid:
                query = query.filter(
                    R3aktTeamMemberClientLinkRecord.team_member_uid
                    == str(team_member_uid).strip()
                )
            if client_identity:
                query = query.filter(
                    R3aktTeamMemberClientLinkRecord.client_identity
                    == str(client_identity).strip().lower()
                )
            return (
                query.order_by(
                    R3aktTeamMemberClientLinkRecord.team_member_uid,
                    R3aktTeamMemberClientLinkRecord.client_identity,
                )
                .all()
            )

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
                delivery_metadata_json=message.delivery_metadata or {},
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

    def update_chat_message_state(
        self,
        message_id: str,
        state: str,
        *,
        delivery_metadata: dict | None = None,
    ) -> ChatMessage | None:
        """Update a chat message delivery state."""

        with self._session_scope() as session:
            record = session.get(ChatMessageRecord, message_id)
            if not record:
                return None
            record.state = state
            if delivery_metadata:
                merged_metadata = dict(record.delivery_metadata_json or {})
                merged_metadata.update(delivery_metadata)
                record.delivery_metadata_json = merged_metadata
            record.updated_at = _utcnow()
            session.commit()
            return self._chat_from_record(record)

    def chat_message_stats(self) -> dict[str, int]:
        """Return basic chat message counters."""

        with self._session_scope() as session:
            rows = (
                session.query(
                    ChatMessageRecord.state, sa_count(ChatMessageRecord.id)
                )
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

    def _ensure_indexes(self) -> None:
        """Create hot-path SQLite indexes for existing databases."""

        statements = (
            "CREATE INDEX IF NOT EXISTS ix_subscribers_topic_id ON subscribers(topic_id);",
            "CREATE INDEX IF NOT EXISTS ix_subscribers_destination ON subscribers(destination);",
            (
                "CREATE INDEX IF NOT EXISTS ix_chat_messages_topic_created_at "
                "ON chat_messages(topic_id, created_at DESC);"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_chat_messages_destination_created_at "
                "ON chat_messages(destination, created_at DESC);"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_chat_messages_source_created_at "
                "ON chat_messages(source, created_at DESC);"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_identity_announces_announced_identity_hash "
                "ON identity_announces(announced_identity_hash);"
            ),
        )
        try:
            with self._engine.begin() as conn:
                for statement in statements:
                    conn.exec_driver_sql(statement)
        except OperationalError as exc:
            logging.warning("Failed to create SQLite indexes: %s", exc)

    def _ensure_identity_announce_columns(self) -> None:
        """Ensure REM announce metadata columns exist on legacy databases."""

        statements = []
        try:
            with self._engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as conn:
                result = conn.execute(text("PRAGMA table_info(identity_announces);"))
                column_names = {str(row[1]) for row in result.fetchall()}
                if "announce_capabilities" not in column_names:
                    statements.append(
                        "ALTER TABLE identity_announces ADD COLUMN announce_capabilities JSON;"
                    )
                if "announced_identity_hash" not in column_names:
                    statements.append(
                        "ALTER TABLE identity_announces ADD COLUMN announced_identity_hash VARCHAR;"
                    )
                if "client_type" not in column_names:
                    statements.append(
                        "ALTER TABLE identity_announces ADD COLUMN client_type VARCHAR;"
                    )
                if "last_capability_seen_at" not in column_names:
                    statements.append(
                        "ALTER TABLE identity_announces ADD COLUMN last_capability_seen_at DATETIME;"
                    )
                for statement in statements:
                    conn.execute(text(statement))
                conn.execute(
                    text(
                        "UPDATE identity_announces "
                        "SET announced_identity_hash = destination_hash "
                        "WHERE (source_interface IS NULL OR source_interface = 'identity') "
                        "AND announced_identity_hash IS NULL"
                    )
                )
        except OperationalError as exc:
            logging.warning("Failed to ensure identity_announces REM columns: %s", exc)

    def _backfill_identity_capability_grants(self) -> None:
        """Copy legacy identity capability grants into subject-aware rights."""

        with self._engine.begin() as conn:
            legacy_rows = conn.execute(
                IdentityCapabilityGrantRecord.__table__.select()
            ).mappings()
            for row in legacy_rows:
                identity = str(row["identity"] or "").strip().lower()
                capability = str(row["capability"] or "").strip()
                if not identity or not capability:
                    continue
                insert_values = {
                    "grant_uid": uuid.uuid4().hex,
                    "subject_type": "identity",
                    "subject_id": identity,
                    "operation": capability,
                    "scope_type": "global",
                    "scope_id": "",
                    "granted": bool(row["granted"]),
                    "granted_by": row["granted_by"],
                    "granted_at": row["granted_at"] or _utcnow(),
                    "expires_at": row["expires_at"],
                    "updated_at": row["updated_at"] or _utcnow(),
                }
                stmt = sqlite_insert(SubjectOperationGrantRecord).values(**insert_values)
                stmt = stmt.on_conflict_do_update(
                    index_elements=[
                        SubjectOperationGrantRecord.subject_type,
                        SubjectOperationGrantRecord.subject_id,
                        SubjectOperationGrantRecord.operation,
                        SubjectOperationGrantRecord.scope_type,
                        SubjectOperationGrantRecord.scope_id,
                    ],
                    set_={
                        "granted": insert_values["granted"],
                        "granted_by": insert_values["granted_by"],
                        "granted_at": insert_values["granted_at"],
                        "expires_at": insert_values["expires_at"],
                        "updated_at": insert_values["updated_at"],
                    },
                )
                conn.execute(stmt)

    @staticmethod
    def _normalize_subject_type(subject_type: str) -> str:
        normalized_subject_type = str(subject_type or "").strip().lower()
        if normalized_subject_type not in {"identity", "team_member"}:
            raise ValueError("subject_type must be one of: identity, team_member")
        return normalized_subject_type

    @staticmethod
    def _normalize_subject_id(subject_type: str, subject_id: str) -> str:
        normalized_subject_id = str(subject_id or "").strip()
        if not normalized_subject_id:
            raise ValueError("subject_id is required")
        if subject_type == "identity":
            return normalized_subject_id.lower()
        return normalized_subject_id

    @staticmethod
    def _normalize_operation(operation: str) -> str:
        normalized_operation = str(operation or "").strip()
        if not normalized_operation:
            raise ValueError("operation is required")
        return normalized_operation

    @staticmethod
    def _normalize_scope(
        scope_type: str | None,
        scope_id: str | None,
    ) -> tuple[str, str]:
        normalized_scope_type = str(scope_type or "global").strip().lower() or "global"
        if normalized_scope_type == "global":
            return "global", ""
        if normalized_scope_type != "mission":
            raise ValueError("scope_type must be one of: global, mission")
        normalized_scope_id = str(scope_id or "").strip()
        if not normalized_scope_id:
            raise ValueError("scope_id is required for mission scope")
        return normalized_scope_type, normalized_scope_id
