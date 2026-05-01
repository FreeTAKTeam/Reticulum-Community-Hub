"""SQLAlchemy models for the Reticulum Community Hub API storage."""
# ruff: noqa: E402

from __future__ import annotations

from datetime import datetime
from datetime import timezone

from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Float
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import JSON
from sqlalchemy import String
from sqlalchemy import UniqueConstraint
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
    __table_args__ = (
        Index("ix_subscribers_topic_id", "topic_id"),
        Index("ix_subscribers_destination", "destination"),
    )

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


class MarkerRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for operator markers."""

    __tablename__ = "markers"

    id = Column(String, primary_key=True)
    object_destination_hash = Column(String, nullable=True, unique=True)
    origin_rch = Column(String, nullable=True)
    object_identity_storage_key = Column(String, nullable=True)
    marker_type = Column(String, nullable=False)
    symbol = Column(String, nullable=False, default="")
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    notes = Column(String, nullable=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    time = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    stale_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class ZoneRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for operator zones."""

    __tablename__ = "zones"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    points_json = Column("points", JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class ChatMessageRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for persisted chat messages."""

    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_messages_topic_created_at", "topic_id", "created_at"),
        Index("ix_chat_messages_destination_created_at", "destination", "created_at"),
        Index("ix_chat_messages_source_created_at", "source", "created_at"),
    )

    id = Column(String, primary_key=True)
    direction = Column(String, nullable=False)
    scope = Column(String, nullable=False)
    state = Column(String, nullable=False)
    content = Column(String, nullable=False)
    source = Column(String, nullable=True)
    destination = Column(String, nullable=True)
    topic_id = Column(String, nullable=True)
    attachments_json = Column("attachments", JSON, nullable=True)
    delivery_metadata_json = Column("delivery_metadata", JSON, nullable=True)
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
    announced_identity_hash = Column(String, nullable=True)
    display_name = Column(String, nullable=True)
    announce_capabilities_json = Column("announce_capabilities", JSON, nullable=True)
    client_type = Column(String, nullable=True)
    first_seen = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    last_seen = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    last_capability_seen_at = Column(DateTime(timezone=True), nullable=True)
    source_interface = Column(String, nullable=True)


class IdentityRemModeRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for persisted REM client mode registrations."""

    __tablename__ = "identity_rem_modes"

    identity = Column(String, primary_key=True)
    mode = Column(String, nullable=False)
    requested_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class IdentityCapabilityGrantRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for per-identity capability grants."""

    __tablename__ = "identity_capability_grants"
    __table_args__ = (
        UniqueConstraint("identity", "capability", name="uq_identity_capability"),
    )

    grant_uid = Column(String, primary_key=True)
    identity = Column(String, nullable=False)
    capability = Column(String, nullable=False)
    granted = Column(Boolean, nullable=False, default=True)
    granted_by = Column(String, nullable=True)
    granted_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


from .r3akt_storage_models import EmergencyActionMessageRecord
from .r3akt_storage_models import R3aktAssetRecord
from .r3akt_storage_models import R3aktAssignmentAssetLinkRecord
from .r3akt_storage_models import R3aktChecklistCellRecord
from .r3akt_storage_models import R3aktChecklistColumnRecord
from .r3akt_storage_models import R3aktChecklistFeedPublicationRecord
from .r3akt_storage_models import R3aktChecklistRecord
from .r3akt_storage_models import R3aktChecklistTaskRecord
from .r3akt_storage_models import R3aktChecklistTemplateRecord
from .r3akt_storage_models import R3aktDomainEventRecord
from .r3akt_storage_models import R3aktDomainSnapshotRecord
from .r3akt_storage_models import R3aktLogEntryRecord
from .r3akt_storage_models import R3aktMissionChangeRecord
from .r3akt_storage_models import R3aktMissionMarkerLinkRecord
from .r3akt_storage_models import R3aktMissionRdeRecord
from .r3akt_storage_models import R3aktMissionRecord
from .r3akt_storage_models import R3aktMissionTaskAssignmentRecord
from .r3akt_storage_models import R3aktMissionTeamLinkRecord
from .r3akt_storage_models import R3aktMissionZoneLinkRecord
from .r3akt_storage_models import R3aktSkillRecord
from .r3akt_storage_models import R3aktTaskSkillRequirementRecord
from .r3akt_storage_models import R3aktTeamMemberClientLinkRecord
from .r3akt_storage_models import R3aktTeamMemberRecord
from .r3akt_storage_models import R3aktTeamMemberSkillRecord
from .r3akt_storage_models import R3aktTeamRecord


__all__ = [
    "Base",
    "ChatMessageRecord",
    "ClientRecord",
    "EmergencyActionMessageRecord",
    "FileRecord",
    "IdentityAnnounceRecord",
    "IdentityCapabilityGrantRecord",
    "IdentityRemModeRecord",
    "IdentityStateRecord",
    "MarkerRecord",
    "R3aktAssetRecord",
    "R3aktAssignmentAssetLinkRecord",
    "R3aktChecklistCellRecord",
    "R3aktChecklistColumnRecord",
    "R3aktChecklistFeedPublicationRecord",
    "R3aktChecklistRecord",
    "R3aktChecklistTaskRecord",
    "R3aktChecklistTemplateRecord",
    "R3aktDomainEventRecord",
    "R3aktDomainSnapshotRecord",
    "R3aktLogEntryRecord",
    "R3aktMissionChangeRecord",
    "R3aktMissionMarkerLinkRecord",
    "R3aktMissionRdeRecord",
    "R3aktMissionRecord",
    "R3aktMissionTaskAssignmentRecord",
    "R3aktMissionTeamLinkRecord",
    "R3aktMissionZoneLinkRecord",
    "R3aktSkillRecord",
    "R3aktTaskSkillRequirementRecord",
    "R3aktTeamMemberClientLinkRecord",
    "R3aktTeamMemberRecord",
    "R3aktTeamMemberSkillRecord",
    "R3aktTeamRecord",
    "SubscriberRecord",
    "TopicRecord",
    "ZoneRecord",
    "_utcnow",
]
