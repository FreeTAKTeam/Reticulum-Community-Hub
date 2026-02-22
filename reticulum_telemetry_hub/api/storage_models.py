"""SQLAlchemy models for the Reticulum Community Hub API storage."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone

from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Float
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


class R3aktMissionRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for R3AKT missions."""

    __tablename__ = "r3akt_missions"

    uid = Column(String, primary_key=True)
    mission_name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    topic_id = Column(String, nullable=True)
    path = Column(String, nullable=True)
    classification = Column(String, nullable=True)
    tool = Column(String, nullable=True)
    keywords_json = Column("keywords", JSON, nullable=True)
    parent_uid = Column(String, nullable=True)
    feeds_json = Column("feeds", JSON, nullable=True)
    password_hash = Column(String, nullable=True)
    default_role = Column(String, nullable=True)
    mission_priority = Column(Integer, nullable=True)
    mission_status = Column(String, nullable=True)
    owner_role = Column(String, nullable=True)
    token = Column(String, nullable=True)
    invite_only = Column(Boolean, nullable=False, default=False)
    expiration = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class R3aktMissionChangeRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for R3AKT mission change entries."""

    __tablename__ = "r3akt_mission_changes"

    uid = Column(String, primary_key=True)
    mission_uid = Column(String, nullable=False)
    name = Column(String, nullable=True)
    team_member_rns_identity = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    notes = Column(String, nullable=True)
    change_type = Column(String, nullable=True)
    is_federated_change = Column(Boolean, nullable=False, default=False)
    hashes_json = Column("hashes", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class R3aktLogEntryRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for mission log entries."""

    __tablename__ = "r3akt_log_entries"

    entry_uid = Column(String, primary_key=True)
    mission_uid = Column(String, nullable=False)
    content = Column(String, nullable=False)
    server_time = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    client_time = Column(DateTime(timezone=True), nullable=True)
    content_hashes_json = Column("content_hashes", JSON, nullable=True)
    keywords_json = Column("keywords", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class R3aktTeamRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for R3AKT teams."""

    __tablename__ = "r3akt_teams"

    uid = Column(String, primary_key=True)
    mission_uid = Column(String, nullable=True)
    color = Column(String, nullable=True)
    team_name = Column(String, nullable=False)
    team_description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class R3aktTeamMemberRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for R3AKT team members."""

    __tablename__ = "r3akt_team_members"

    uid = Column(String, primary_key=True)
    team_uid = Column(String, nullable=True)
    rns_identity = Column(String, nullable=False)
    icon = Column(String, nullable=True)
    display_name = Column(String, nullable=False)
    role = Column(String, nullable=True)
    callsign = Column(String, nullable=True)
    freq = Column(Float, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    modulation = Column(String, nullable=True)
    availability = Column(String, nullable=True)
    certifications_json = Column("certifications", JSON, nullable=True)
    last_active = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class R3aktAssetRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for R3AKT assets."""

    __tablename__ = "r3akt_assets"

    asset_uid = Column(String, primary_key=True)
    team_member_uid = Column(String, nullable=True)
    name = Column(String, nullable=False)
    asset_type = Column(String, nullable=False)
    serial_number = Column(String, nullable=True)
    status = Column(String, nullable=False)
    location = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class R3aktSkillRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for R3AKT skills."""

    __tablename__ = "r3akt_skills"

    skill_uid = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=True)
    description = Column(String, nullable=True)
    proficiency_scale = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class R3aktTeamMemberSkillRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for team-member skill mappings."""

    __tablename__ = "r3akt_team_member_skills"
    __table_args__ = (
        UniqueConstraint(
            "team_member_rns_identity",
            "skill_uid",
            name="uq_team_member_skill",
        ),
    )

    uid = Column(String, primary_key=True)
    team_member_rns_identity = Column(String, nullable=False)
    skill_uid = Column(String, nullable=False)
    level = Column(Integer, nullable=False, default=0)
    validated_by = Column(String, nullable=True)
    validated_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class R3aktTaskSkillRequirementRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for task skill requirements."""

    __tablename__ = "r3akt_task_skill_requirements"
    __table_args__ = (
        UniqueConstraint("task_uid", "skill_uid", name="uq_task_skill_requirement"),
    )

    uid = Column(String, primary_key=True)
    task_uid = Column(String, nullable=False)
    skill_uid = Column(String, nullable=False)
    minimum_level = Column(Integer, nullable=False, default=0)
    is_mandatory = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class R3aktChecklistTemplateRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for checklist templates."""

    __tablename__ = "r3akt_checklist_templates"

    uid = Column(String, primary_key=True)
    template_name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    created_by_team_member_rns_identity = Column(String, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    source_template_uid = Column(String, nullable=True)
    server_only = Column(Boolean, nullable=False, default=True)


class R3aktChecklistRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for checklist instances."""

    __tablename__ = "r3akt_checklists"

    uid = Column(String, primary_key=True)
    mission_uid = Column(String, nullable=True)
    template_uid = Column(String, nullable=True)
    template_version = Column(Integer, nullable=True)
    template_name = Column(String, nullable=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=False, default="")
    start_time = Column(DateTime(timezone=True), nullable=False)
    mode = Column(String, nullable=False)
    sync_state = Column(String, nullable=False)
    origin_type = Column(String, nullable=False)
    checklist_status = Column(String, nullable=False, default="PENDING")
    progress_percent = Column(Float, nullable=False, default=0.0)
    pending_count = Column(Integer, nullable=False, default=0)
    late_count = Column(Integer, nullable=False, default=0)
    complete_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    created_by_team_member_rns_identity = Column(String, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    uploaded_at = Column(DateTime(timezone=True), nullable=True)


class R3aktChecklistColumnRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for checklist columns."""

    __tablename__ = "r3akt_checklist_columns"

    column_uid = Column(String, primary_key=True)
    checklist_uid = Column(String, nullable=True)
    template_uid = Column(String, nullable=True)
    column_name = Column(String, nullable=False)
    display_order = Column(Integer, nullable=False)
    column_type = Column(String, nullable=False)
    column_editable = Column(Boolean, nullable=False, default=True)
    background_color = Column(String, nullable=True)
    text_color = Column(String, nullable=True)
    is_removable = Column(Boolean, nullable=False, default=True)
    system_key = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class R3aktChecklistTaskRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for checklist tasks."""

    __tablename__ = "r3akt_checklist_tasks"

    task_uid = Column(String, primary_key=True)
    checklist_uid = Column(String, nullable=False)
    number = Column(Integer, nullable=False)
    user_status = Column(String, nullable=False, default="PENDING")
    task_status = Column(String, nullable=False, default="PENDING")
    is_late = Column(Boolean, nullable=False, default=False)
    custom_status = Column(Integer, nullable=True)
    due_relative_minutes = Column(Integer, nullable=True)
    due_dtg = Column(DateTime(timezone=True), nullable=True)
    notes = Column(String, nullable=True)
    row_background_color = Column(String, nullable=True)
    line_break_enabled = Column(Boolean, nullable=False, default=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by_team_member_rns_identity = Column(String, nullable=True)
    legacy_value = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class R3aktChecklistCellRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for checklist cell values."""

    __tablename__ = "r3akt_checklist_cells"
    __table_args__ = (
        UniqueConstraint("task_uid", "column_uid", name="uq_task_column_cell"),
    )

    cell_uid = Column(String, primary_key=True)
    task_uid = Column(String, nullable=False)
    column_uid = Column(String, nullable=False)
    value = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_by_team_member_rns_identity = Column(String, nullable=True)


class R3aktChecklistFeedPublicationRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for checklist feed publications."""

    __tablename__ = "r3akt_checklist_feed_publications"

    publication_uid = Column(String, primary_key=True)
    checklist_uid = Column(String, nullable=False)
    mission_feed_uid = Column(String, nullable=False)
    published_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    published_by_team_member_rns_identity = Column(String, nullable=False)


class R3aktMissionTaskAssignmentRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for mission task assignments."""

    __tablename__ = "r3akt_mission_task_assignments"

    assignment_uid = Column(String, primary_key=True)
    mission_uid = Column(String, nullable=False)
    task_uid = Column(String, nullable=False)
    team_member_rns_identity = Column(String, nullable=False)
    assigned_by = Column(String, nullable=True)
    assigned_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    due_dtg = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="PENDING")
    notes = Column(String, nullable=True)
    assets_json = Column("assets", JSON, nullable=True)


class R3aktAssignmentAssetLinkRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for assignment-to-asset links."""

    __tablename__ = "r3akt_assignment_assets"
    __table_args__ = (
        UniqueConstraint("assignment_uid", "asset_uid", name="uq_assignment_asset_link"),
    )

    link_uid = Column(String, primary_key=True)
    assignment_uid = Column(String, nullable=False)
    asset_uid = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class R3aktMissionZoneLinkRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for mission-to-zone links."""

    __tablename__ = "r3akt_mission_zone_links"
    __table_args__ = (
        UniqueConstraint("mission_uid", "zone_id", name="uq_mission_zone_link"),
    )

    link_uid = Column(String, primary_key=True)
    mission_uid = Column(String, nullable=False)
    zone_id = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class R3aktMissionTeamLinkRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for mission-to-team links."""

    __tablename__ = "r3akt_mission_team_links"
    __table_args__ = (
        UniqueConstraint("mission_uid", "team_uid", name="uq_mission_team_link"),
    )

    link_uid = Column(String, primary_key=True)
    mission_uid = Column(String, nullable=False)
    team_uid = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class R3aktTeamMemberClientLinkRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record linking team members to client identities."""

    __tablename__ = "r3akt_team_member_client_links"
    __table_args__ = (
        UniqueConstraint(
            "team_member_uid",
            "client_identity",
            name="uq_team_member_client_link",
        ),
    )

    link_uid = Column(String, primary_key=True)
    team_member_uid = Column(String, nullable=False)
    client_identity = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class R3aktMissionRdeRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for mission role descriptor entry."""

    __tablename__ = "r3akt_mission_rde"

    mission_uid = Column(String, primary_key=True)
    role = Column(String, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class R3aktDomainEventRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for immutable R3AKT domain events."""

    __tablename__ = "r3akt_domain_events"

    event_uid = Column(String, primary_key=True)
    domain = Column(String, nullable=False)
    aggregate_type = Column(String, nullable=False)
    aggregate_uid = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    payload_json = Column("payload", JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class R3aktDomainSnapshotRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for immutable R3AKT aggregate snapshots."""

    __tablename__ = "r3akt_domain_snapshots"

    snapshot_uid = Column(String, primary_key=True)
    domain = Column(String, nullable=False)
    aggregate_type = Column(String, nullable=False)
    aggregate_uid = Column(String, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    state_json = Column("state", JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
