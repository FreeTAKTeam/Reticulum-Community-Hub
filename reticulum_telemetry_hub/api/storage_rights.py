"""Subject rights and R3AKT lookup storage methods."""

from __future__ import annotations

from typing import List
import uuid

from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .rights_storage_models import MissionAccessAssignmentRecord
from .rights_storage_models import SubjectOperationGrantRecord
from .storage_models import IdentityStateRecord
from .storage_models import R3aktMissionRecord
from .storage_models import R3aktTeamMemberClientLinkRecord
from .storage_models import R3aktTeamMemberRecord
from .storage_models import _utcnow


class RightsStorageMixin:
    """Subject rights and R3AKT lookup storage methods."""

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

