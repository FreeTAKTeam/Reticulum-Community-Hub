"""Client and file attachment storage methods."""

from __future__ import annotations

from typing import List
import uuid

from sqlalchemy import func
from sqlalchemy.sql.functions import count as sa_count

from reticulum_telemetry_hub.message_delivery import normalize_topic_id
from .models import Client
from .models import FileAttachment
from .pagination import PageRequest
from .pagination import PaginatedResult
from .storage_models import ClientRecord
from .storage_models import FileRecord
from .storage_models import _utcnow


class ClientFileStorageMixin:
    """Client and file attachment storage methods."""

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
        topic_filter = func.trim(FileRecord.topic_id) == normalized_topic_id
        try:
            topic_uuid = uuid.UUID(normalized_topic_id)
        except (ValueError, AttributeError, TypeError):
            pass
        else:
            topic_match_values = {normalized_topic_id.lower()}
            topic_match_values.add(topic_uuid.hex.lower())
            topic_match_values.add(str(topic_uuid).lower())
            topic_filter = func.lower(func.trim(FileRecord.topic_id)).in_(topic_match_values)
        with self._session_scope() as session:
            records = (
                session.query(FileRecord)
                .filter(topic_filter)
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

