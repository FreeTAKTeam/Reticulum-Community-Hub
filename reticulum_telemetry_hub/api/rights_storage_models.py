"""Subject-aware rights storage models."""

from __future__ import annotations

from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import String
from sqlalchemy import UniqueConstraint

from .storage_models import Base
from .storage_models import _utcnow


class SubjectOperationGrantRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for subject-scoped operation rights."""

    __tablename__ = "subject_operation_grants"
    __table_args__ = (
        UniqueConstraint(
            "subject_type",
            "subject_id",
            "operation",
            "scope_type",
            "scope_id",
            name="uq_subject_operation_scope",
        ),
    )

    grant_uid = Column(String, primary_key=True)
    subject_type = Column(String, nullable=False)
    subject_id = Column(String, nullable=False)
    operation = Column(String, nullable=False)
    scope_type = Column(String, nullable=False, default="global")
    scope_id = Column(String, nullable=False, default="")
    granted = Column(Boolean, nullable=False, default=True)
    granted_by = Column(String, nullable=True)
    granted_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class MissionAccessAssignmentRecord(Base):  # pylint: disable=too-few-public-methods
    """SQLAlchemy record for mission access role assignments."""

    __tablename__ = "mission_access_assignments"
    __table_args__ = (
        UniqueConstraint(
            "mission_uid",
            "subject_type",
            "subject_id",
            name="uq_mission_access_assignment",
        ),
    )

    assignment_uid = Column(String, primary_key=True)
    mission_uid = Column(String, nullable=False)
    subject_type = Column(String, nullable=False)
    subject_id = Column(String, nullable=False)
    role = Column(String, nullable=False)
    assigned_by = Column(String, nullable=True)
    assigned_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
