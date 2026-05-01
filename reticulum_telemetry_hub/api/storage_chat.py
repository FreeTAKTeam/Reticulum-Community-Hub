"""Chat message storage methods."""

from __future__ import annotations

from typing import List
import uuid

from sqlalchemy.sql.functions import count as sa_count

from .models import ChatMessage
from .storage_models import ChatMessageRecord
from .storage_models import _utcnow


class ChatStorageMixin:
    """Chat message storage methods."""

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

