"""SQLAlchemy models for the Reticulum Community Hub API storage."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone

from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Integer
from sqlalchemy import JSON
from sqlalchemy import String
from sqlalchemy.orm import declarative_base


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
    topic_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class ChatMessageRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for persisted chat messages."""

    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True)
    direction = Column(String, nullable=False)
    scope = Column(String, nullable=False)
    state = Column(String, nullable=False)
    content = Column(String, nullable=False)
    source = Column(String, nullable=True)
    destination = Column(String, nullable=True)
    topic_id = Column(String, nullable=True)
    attachments_json = Column("attachments", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class IdentityStateRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for identity moderation state."""

    __tablename__ = "identity_states"

    identity = Column(String, primary_key=True)
    is_banned = Column(Boolean, nullable=False, default=False)
    is_blackholed = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class IdentityAnnounceRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for Reticulum announce metadata."""

    __tablename__ = "identity_announces"

    destination_hash = Column(String, primary_key=True)
    display_name = Column(String, nullable=True)
    first_seen = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    last_seen = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    source_interface = Column(String, nullable=True)
