"""Subject-aware rights orchestration for mission access."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy import or_

from reticulum_telemetry_hub.mission_domain.enums import MissionRole

from .rights_storage_models import MissionAccessAssignmentRecord
from .rights_storage_models import SubjectOperationGrantRecord
from .storage import HubStorage
from .storage_models import R3aktAssetRecord
from .storage_models import R3aktChecklistRecord
from .storage_models import R3aktMissionRecord
from .storage_models import R3aktMissionTaskAssignmentRecord
from .storage_models import R3aktMissionTeamLinkRecord
from .storage_models import R3aktTeamMemberClientLinkRecord
from .storage_models import R3aktTeamMemberRecord
from .storage_models import R3aktTeamRecord


MISSION_READONLY_OPERATIONS = {
    "mission.join",
    "mission.leave",
    "mission.audit.read",
    "topic.read",
    "mission.content.read",
    "mission.zone.read",
    "mission.registry.mission.read",
    "mission.registry.log.read",
    "mission.registry.status.read",
    "mission.registry.team.read",
    "mission.registry.asset.read",
    "mission.registry.skill.read",
    "mission.registry.assignment.read",
    "checklist.read",
    "checklist.join",
}

MISSION_WRITE_OPERATIONS = MISSION_READONLY_OPERATIONS | {
    "mission.message.send",
    "topic.subscribe",
    "mission.content.write",
    "mission.zone.write",
    "mission.registry.log.write",
    "mission.registry.status.write",
    "mission.registry.assignment.write",
    "checklist.write",
    "checklist.upload",
    "checklist.feed.publish",
}

MISSION_OWNER_OPERATIONS = MISSION_WRITE_OPERATIONS | {
    "topic.create",
    "topic.write",
    "topic.delete",
    "mission.zone.delete",
    "mission.registry.mission.write",
    "mission.registry.team.write",
    "mission.registry.asset.write",
    "mission.registry.skill.write",
}

MISSION_ROLE_BUNDLES: dict[str, set[str]] = {
    MissionRole.MISSION_READONLY_SUBSCRIBER.value: set(MISSION_READONLY_OPERATIONS),
    MissionRole.MISSION_SUBSCRIBER.value: set(MISSION_WRITE_OPERATIONS),
    MissionRole.MISSION_OWNER.value: set(MISSION_OWNER_OPERATIONS),
}

SUPPORTED_OPERATIONS = sorted(
    {
        "mission.join",
        "mission.leave",
        "mission.audit.read",
        "mission.message.send",
        "topic.read",
        "topic.create",
        "topic.write",
        "topic.delete",
        "topic.subscribe",
        "mission.content.read",
        "mission.content.write",
        "mission.zone.read",
        "mission.zone.write",
        "mission.zone.delete",
        "mission.registry.mission.read",
        "mission.registry.mission.write",
        "mission.registry.log.read",
        "mission.registry.log.write",
        "mission.registry.status.read",
        "mission.registry.status.write",
        "mission.registry.team.read",
        "mission.registry.team.write",
        "mission.registry.asset.read",
        "mission.registry.asset.write",
        "mission.registry.skill.read",
        "mission.registry.skill.write",
        "mission.registry.assignment.read",
        "mission.registry.assignment.write",
        "checklist.template.read",
        "checklist.template.write",
        "checklist.template.delete",
        "checklist.read",
        "checklist.write",
        "checklist.join",
        "checklist.upload",
        "checklist.feed.publish",
        "r3akt",
    }
)


class SubjectAwareRightsService:
    """Resolve explicit and mission-derived rights for identities."""

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

    def resolve_topic_mission_uids(self, topic_id: str) -> list[str]:
        """Return missions associated with a topic."""

        normalized_topic_id = str(topic_id or "").strip()
        if not normalized_topic_id:
            return []
        with self._storage._session_scope() as session:  # pylint: disable=protected-access
            rows = (
                session.query(R3aktMissionRecord.uid)
                .filter(R3aktMissionRecord.topic_id == normalized_topic_id)
                .all()
            )
            return sorted({str(row[0]) for row in rows if str(row[0]).strip()})

    def resolve_team_mission_uids(self, team_uid: str) -> list[str]:
        """Return missions associated with a team."""

        normalized_team_uid = str(team_uid or "").strip()
        if not normalized_team_uid:
            return []
        with self._storage._session_scope() as session:  # pylint: disable=protected-access
            return self._team_mission_uids(session, normalized_team_uid)

    def resolve_team_member_mission_uids(self, team_member_uid: str) -> list[str]:
        """Return missions associated with a team member."""

        normalized_team_member_uid = str(team_member_uid or "").strip()
        if not normalized_team_member_uid:
            return []
        with self._storage._session_scope() as session:  # pylint: disable=protected-access
            member = session.get(R3aktTeamMemberRecord, normalized_team_member_uid)
            if member is None:
                return []
            return self._team_mission_uids(session, str(member.team_uid or ""))

    def resolve_asset_mission_uids(self, asset_uid: str) -> list[str]:
        """Return missions associated with an asset."""

        normalized_asset_uid = str(asset_uid or "").strip()
        if not normalized_asset_uid:
            return []
        with self._storage._session_scope() as session:  # pylint: disable=protected-access
            asset = session.get(R3aktAssetRecord, normalized_asset_uid)
            if asset is None:
                return []
            member = session.get(R3aktTeamMemberRecord, str(asset.team_member_uid or ""))
            if member is None:
                return []
            return self._team_mission_uids(session, str(member.team_uid or ""))

    def resolve_assignment_mission_uid(self, assignment_uid: str) -> str | None:
        """Return the mission for an assignment."""

        normalized_assignment_uid = str(assignment_uid or "").strip()
        if not normalized_assignment_uid:
            return None
        with self._storage._session_scope() as session:  # pylint: disable=protected-access
            row = session.get(R3aktMissionTaskAssignmentRecord, normalized_assignment_uid)
            if row is None:
                return None
            mission_uid = str(row.mission_uid or "").strip()
            return mission_uid or None

    def resolve_checklist_mission_uid(self, checklist_uid: str) -> str | None:
        """Return the mission for a checklist."""

        normalized_checklist_uid = str(checklist_uid or "").strip()
        if not normalized_checklist_uid:
            return None
        with self._storage._session_scope() as session:  # pylint: disable=protected-access
            row = session.get(R3aktChecklistRecord, normalized_checklist_uid)
            if row is None:
                return None
            mission_uid = str(row.mission_uid or "").strip()
            return mission_uid or None

    def resolve_mission_uid_for_feed(self, mission_feed_uid: str) -> str | None:
        """Return the mission that owns a mission feed identifier."""

        normalized_mission_feed_uid = str(mission_feed_uid or "").strip()
        if not normalized_mission_feed_uid:
            return None
        with self._storage._session_scope() as session:  # pylint: disable=protected-access
            rows = (
                session.query(R3aktMissionRecord)
                .order_by(R3aktMissionRecord.created_at.asc())
                .all()
            )
            for row in rows:
                feeds = [str(item).strip() for item in (row.feeds_json or []) if str(item).strip()]
                if normalized_mission_feed_uid in feeds:
                    mission_uid = str(row.uid or "").strip()
                    if mission_uid:
                        return mission_uid
        return None

    @staticmethod
    def _serialize_operation_right(record: SubjectOperationGrantRecord) -> dict[str, Any]:
        return {
            "grant_uid": record.grant_uid,
            "subject_type": record.subject_type,
            "subject_id": record.subject_id,
            "operation": record.operation,
            "scope_type": record.scope_type,
            "scope_id": record.scope_id,
            "granted": bool(record.granted),
            "granted_by": record.granted_by,
            "granted_at": record.granted_at.isoformat() if record.granted_at else None,
            "expires_at": record.expires_at.isoformat() if record.expires_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }

    @staticmethod
    def _serialize_mission_access_assignment(
        record: MissionAccessAssignmentRecord,
    ) -> dict[str, Any]:
        return {
            "assignment_uid": record.assignment_uid,
            "mission_uid": record.mission_uid,
            "subject_type": record.subject_type,
            "subject_id": record.subject_id,
            "role": record.role,
            "operations": sorted(MISSION_ROLE_BUNDLES.get(record.role, set())),
            "assigned_by": record.assigned_by,
            "assigned_at": record.assigned_at.isoformat() if record.assigned_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }

    @staticmethod
    def _normalize_subject_type(subject_type: str) -> str:
        normalized_subject_type = str(subject_type or "").strip().lower()
        if normalized_subject_type not in {"identity", "team_member"}:
            raise ValueError("subject_type must be one of: identity, team_member")
        return normalized_subject_type

    @staticmethod
    def _normalize_subject_id(subject_type: str, subject_id: str) -> str:
        normalized_subject_type = SubjectAwareRightsService._normalize_subject_type(subject_type)
        normalized_subject_id = str(subject_id or "").strip()
        if not normalized_subject_id:
            raise ValueError("subject_id is required")
        if normalized_subject_type == "identity":
            return normalized_subject_id.lower()
        return normalized_subject_id

    @staticmethod
    def _normalize_mission_role(role: str) -> str:
        normalized_role = str(role or "").strip().upper()
        if normalized_role not in MISSION_ROLE_BUNDLES:
            allowed = ", ".join(sorted(MISSION_ROLE_BUNDLES))
            raise ValueError(f"role must be one of: {allowed}")
        return normalized_role

    @staticmethod
    def _team_map(session) -> dict[str, R3aktTeamRecord]:
        return {
            str(record.uid): record
            for record in session.query(R3aktTeamRecord).all()
        }

    @staticmethod
    def _mission_team_uids(session, mission_uid: str) -> list[str]:
        linked_rows = (
            session.query(R3aktMissionTeamLinkRecord.team_uid)
            .filter(R3aktMissionTeamLinkRecord.mission_uid == mission_uid)
            .all()
        )
        legacy_rows = (
            session.query(R3aktTeamRecord.uid)
            .filter(R3aktTeamRecord.mission_uid == mission_uid)
            .all()
        )
        return sorted(
            {
                str(row[0]).strip()
                for row in [*linked_rows, *legacy_rows]
                if str(row[0]).strip()
            }
        )

    def _team_mission_uids(self, session, team_uid: str) -> list[str]:
        normalized_team_uid = str(team_uid or "").strip()
        if not normalized_team_uid:
            return []
        linked_rows = (
            session.query(R3aktMissionTeamLinkRecord.mission_uid)
            .filter(R3aktMissionTeamLinkRecord.team_uid == normalized_team_uid)
            .all()
        )
        team_row = session.get(R3aktTeamRecord, normalized_team_uid)
        mission_uids = {
            str(row[0]).strip()
            for row in linked_rows
            if str(row[0]).strip()
        }
        if team_row is not None and str(team_row.mission_uid or "").strip():
            mission_uids.add(str(team_row.mission_uid).strip())
        return sorted(mission_uids)

    @staticmethod
    def _client_links_by_member(session) -> dict[str, set[str]]:
        payload: dict[str, set[str]] = {}
        for link in session.query(R3aktTeamMemberClientLinkRecord).all():
            payload.setdefault(str(link.team_member_uid), set()).add(
                str(link.client_identity)
            )
        return payload

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
