"""Subject-aware rights orchestration for mission access."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy import or_

from reticulum_telemetry_hub.mission_domain.enums import MissionRole

from .rights_resolvers import RightsMissionResolverMixin
from .rights_policy import client_links_by_member
from .rights_policy import MISSION_ROLE_BUNDLES
from .rights_policy import SUPPORTED_OPERATIONS
from .rights_policy import mission_team_uids
from .rights_policy import normalize_mission_role
from .rights_policy import normalize_subject_id
from .rights_policy import normalize_subject_type
from .rights_policy import serialize_mission_access_assignment
from .rights_policy import serialize_operation_right
from .rights_policy import team_map
from .rights_storage_models import MissionAccessAssignmentRecord
from .rights_storage_models import SubjectOperationGrantRecord
from .storage import HubStorage
from .storage_models import R3aktTeamMemberClientLinkRecord
from .storage_models import R3aktTeamMemberRecord


class SubjectAwareRightsService(RightsMissionResolverMixin):
    """Resolve explicit and mission-derived rights for identities."""

    _serialize_operation_right = staticmethod(serialize_operation_right)
    _serialize_mission_access_assignment = staticmethod(
        serialize_mission_access_assignment
    )
    _normalize_subject_type = staticmethod(normalize_subject_type)
    _normalize_subject_id = staticmethod(normalize_subject_id)
    _normalize_mission_role = staticmethod(normalize_mission_role)
    _team_map = staticmethod(team_map)
    _mission_team_uids = staticmethod(mission_team_uids)
    _client_links_by_member = staticmethod(client_links_by_member)

    def __init__(self, storage: HubStorage) -> None:
        """Initialize the rights service."""

        self._storage = storage

    def operation_definitions(self) -> dict[str, Any]:
        """Return supported operations and standard mission bundles."""

        return {
            "subject_types": ["identity", "team_member"],
            "scope_types": ["global", "mission"],
            "operations": list(SUPPORTED_OPERATIONS),
            "mission_role_bundles": {
                role: sorted(operations)
                for role, operations in sorted(MISSION_ROLE_BUNDLES.items())
            },
        }

    def grant_operation_right(
        self,
        subject_type: str,
        subject_id: str,
        operation: str,
        *,
        scope_type: str | None = None,
        scope_id: str | None = None,
        granted_by: str | None = None,
        expires_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Persist an explicit operation grant."""

        record = self._storage.upsert_operation_right(
            subject_type,
            subject_id,
            operation,
            scope_type=scope_type,
            scope_id=scope_id,
            granted=True,
            granted_by=granted_by,
            expires_at=expires_at,
        )
        return self._serialize_operation_right(record)

    def revoke_operation_right(
        self,
        subject_type: str,
        subject_id: str,
        operation: str,
        *,
        scope_type: str | None = None,
        scope_id: str | None = None,
        granted_by: str | None = None,
    ) -> dict[str, Any]:
        """Persist an explicit operation revoke."""

        record = self._storage.upsert_operation_right(
            subject_type,
            subject_id,
            operation,
            scope_type=scope_type,
            scope_id=scope_id,
            granted=False,
            granted_by=granted_by,
            expires_at=None,
        )
        return self._serialize_operation_right(record)

    def list_operation_rights(
        self,
        *,
        subject_type: str | None = None,
        subject_id: str | None = None,
        operation: str | None = None,
        scope_type: str | None = None,
        scope_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return persisted explicit operation rights."""

        records = self._storage.list_operation_rights(
            subject_type=subject_type,
            subject_id=subject_id,
            operation=operation,
            scope_type=scope_type,
            scope_id=scope_id,
        )
        return [self._serialize_operation_right(record) for record in records]

    def assign_mission_access_role(
        self,
        mission_uid: str,
        subject_type: str,
        subject_id: str,
        *,
        role: str | None = None,
        assigned_by: str | None = None,
    ) -> dict[str, Any]:
        """Assign a standard mission access role to a subject."""

        normalized_mission_uid = str(mission_uid or "").strip()
        mission = self._storage.get_mission_record(normalized_mission_uid)
        if mission is None:
            raise KeyError(f"Mission '{normalized_mission_uid}' not found")

        normalized_subject_type = self._normalize_subject_type(subject_type)
        normalized_subject_id = self._normalize_subject_id(
            normalized_subject_type,
            subject_id,
        )
        if normalized_subject_type == "team_member":
            if self._storage.get_team_member_record(normalized_subject_id) is None:
                raise KeyError(f"Team member '{normalized_subject_id}' not found")

        resolved_role = self.resolve_default_mission_role(
            normalized_mission_uid,
            owner=False,
        )
        if role is not None and str(role).strip():
            resolved_role = self._normalize_mission_role(role)

        record = self._storage.upsert_mission_access_assignment(
            normalized_mission_uid,
            normalized_subject_type,
            normalized_subject_id,
            resolved_role,
            assigned_by=assigned_by,
        )
        return self._serialize_mission_access_assignment(record)

    def revoke_mission_access_role(
        self,
        mission_uid: str,
        subject_type: str,
        subject_id: str,
    ) -> dict[str, Any]:
        """Remove a mission access role assignment."""

        normalized_mission_uid = str(mission_uid or "").strip()
        deleted = self._storage.delete_mission_access_assignment(
            normalized_mission_uid,
            subject_type,
            subject_id,
        )
        return {
            "mission_uid": normalized_mission_uid,
            "subject_type": self._normalize_subject_type(subject_type),
            "subject_id": self._normalize_subject_id(subject_type, subject_id),
            "deleted": deleted,
        }

    def list_mission_access_assignments(
        self,
        *,
        mission_uid: str | None = None,
        subject_type: str | None = None,
        subject_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return mission access role assignments."""

        records = self._storage.list_mission_access_assignments(
            mission_uid=mission_uid,
            subject_type=subject_type,
            subject_id=subject_id,
        )
        return [self._serialize_mission_access_assignment(record) for record in records]

    def list_team_member_subjects(
        self,
        *,
        mission_uid: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return team members as rights subjects."""

        normalized_mission_uid = str(mission_uid or "").strip() or None
        with self._storage._session_scope() as session:  # pylint: disable=protected-access
            query = session.query(R3aktTeamMemberRecord)
            team_map = self._team_map(session)
            client_links = self._client_links_by_member(session)
            if normalized_mission_uid:
                team_uids = self._mission_team_uids(session, normalized_mission_uid)
                if not team_uids:
                    return []
                query = query.filter(R3aktTeamMemberRecord.team_uid.in_(team_uids))
            records = query.order_by(R3aktTeamMemberRecord.display_name.asc()).all()
            subjects: list[dict[str, Any]] = []
            for record in records:
                mission_uids = self._team_mission_uids(session, str(record.team_uid or ""))
                if normalized_mission_uid and normalized_mission_uid not in mission_uids:
                    continue
                team = team_map.get(str(record.team_uid or ""))
                subjects.append(
                    {
                        "subject_type": "team_member",
                        "subject_id": record.uid,
                        "team_member_uid": record.uid,
                        "rns_identity": record.rns_identity,
                        "display_name": record.display_name,
                        "team_uid": record.team_uid,
                        "team_name": team.team_name if team is not None else None,
                        "client_identities": sorted(client_links.get(record.uid, set())),
                        "mission_uids": mission_uids,
                    }
                )
            return subjects

    def resolve_effective_operations(
        self,
        identity: str,
        mission_uid: str | None = None,
    ) -> list[str]:
        """Resolve effective operations for an identity."""

        normalized_identity = str(identity or "").strip().lower()
        if not normalized_identity:
            return []
        normalized_mission_uid = str(mission_uid or "").strip() or None
        now = datetime.now(timezone.utc)

        with self._storage._session_scope() as session:  # pylint: disable=protected-access
            subject_refs = self._subject_refs_for_identity(session, normalized_identity)
            explicit_records = self._matching_operation_grants(
                session,
                subject_refs=subject_refs,
                mission_uid=normalized_mission_uid,
                now=now,
            )
            role_records = self._matching_mission_access_assignments(
                session,
                subject_refs=subject_refs,
                mission_uid=normalized_mission_uid,
            )

        granted_operations = {
            record.operation for record in explicit_records if bool(record.granted)
        }
        denied_operations = {
            record.operation for record in explicit_records if not bool(record.granted)
        }
        bundle_operations: set[str] = set()
        for record in role_records:
            bundle_operations.update(MISSION_ROLE_BUNDLES.get(record.role, set()))
        effective_operations = (granted_operations | bundle_operations) - denied_operations
        return sorted(effective_operations)

    def authorize(
        self,
        identity: str,
        operation: str,
        mission_uid: str | None = None,
    ) -> bool:
        """Return whether the identity is authorized for the operation."""

        normalized_operation = str(operation or "").strip()
        if not normalized_operation:
            return False
        return normalized_operation in self.resolve_effective_operations(
            identity,
            mission_uid=mission_uid,
        )

    def resolve_default_mission_role(
        self,
        mission_uid: str,
        *,
        owner: bool = False,
    ) -> str:
        """Return the mission-default access role."""

        mission = self._storage.get_mission_record(mission_uid)
        if mission is None:
            raise KeyError(f"Mission '{mission_uid}' not found")
        configured_role = mission.owner_role if owner else mission.default_role
        fallback_role = (
            MissionRole.MISSION_OWNER.value
            if owner
            else MissionRole.MISSION_SUBSCRIBER.value
        )
        if configured_role is None or not str(configured_role).strip():
            return fallback_role
        return self._normalize_mission_role(configured_role)

    def _subject_refs_for_identity(
        self,
        session,
        identity: str,
    ) -> set[tuple[str, str]]:
        subject_refs: set[tuple[str, str]] = {("identity", identity)}
        member_rows = (
            session.query(R3aktTeamMemberRecord.uid)
            .filter(func.lower(R3aktTeamMemberRecord.rns_identity) == identity)
            .all()
        )
        link_rows = (
            session.query(R3aktTeamMemberClientLinkRecord.team_member_uid)
            .filter(R3aktTeamMemberClientLinkRecord.client_identity == identity)
            .all()
        )
        for row in [*member_rows, *link_rows]:
            team_member_uid = str(row[0]).strip()
            if team_member_uid:
                subject_refs.add(("team_member", team_member_uid))
        return subject_refs

    @staticmethod
    def _matching_operation_grants(
        session,
        *,
        subject_refs: set[tuple[str, str]],
        mission_uid: str | None,
        now: datetime,
    ) -> list[SubjectOperationGrantRecord]:
        if not subject_refs:
            return []
        query = session.query(SubjectOperationGrantRecord).filter(
            or_(
                *[
                    (
                        SubjectOperationGrantRecord.subject_type == subject_type
                    )
                    & (SubjectOperationGrantRecord.subject_id == subject_id)
                    for subject_type, subject_id in subject_refs
                ]
            ),
            or_(
                SubjectOperationGrantRecord.expires_at.is_(None),
                SubjectOperationGrantRecord.expires_at > now,
            ),
        )
        if mission_uid:
            query = query.filter(
                or_(
                    (
                        SubjectOperationGrantRecord.scope_type == "global"
                    )
                    & (SubjectOperationGrantRecord.scope_id == ""),
                    (
                        SubjectOperationGrantRecord.scope_type == "mission"
                    )
                    & (SubjectOperationGrantRecord.scope_id == mission_uid),
                )
            )
        else:
            query = query.filter(
                SubjectOperationGrantRecord.scope_type == "global",
                SubjectOperationGrantRecord.scope_id == "",
            )
        return query.all()

    @staticmethod
    def _matching_mission_access_assignments(
        session,
        *,
        subject_refs: set[tuple[str, str]],
        mission_uid: str | None,
    ) -> list[MissionAccessAssignmentRecord]:
        if not subject_refs or not mission_uid:
            return []
        return (
            session.query(MissionAccessAssignmentRecord)
            .filter(
                MissionAccessAssignmentRecord.mission_uid == mission_uid,
                or_(
                    *[
                        (
                            MissionAccessAssignmentRecord.subject_type == subject_type
                        )
                        & (MissionAccessAssignmentRecord.subject_id == subject_id)
                        for subject_type, subject_id in subject_refs
                    ]
                ),
            )
            .all()
        )
