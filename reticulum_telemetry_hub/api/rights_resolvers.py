"""Mission-scope resolution helpers for rights checks."""

from __future__ import annotations

from .storage_models import R3aktAssetRecord
from .storage_models import R3aktChecklistRecord
from .storage_models import R3aktMissionRecord
from .storage_models import R3aktMissionTaskAssignmentRecord
from .storage_models import R3aktMissionTeamLinkRecord
from .storage_models import R3aktTeamMemberRecord
from .storage_models import R3aktTeamRecord


class RightsMissionResolverMixin:
    """Resolve mission ownership for related R3AKT entities."""

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
                feeds = [
                    str(item).strip()
                    for item in (row.feeds_json or [])
                    if str(item).strip()
                ]
                if normalized_mission_feed_uid in feeds:
                    mission_uid = str(row.uid or "").strip()
                    if mission_uid:
                        return mission_uid
        return None

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
        mission_uids = {str(row[0]).strip() for row in linked_rows if str(row[0]).strip()}
        if team_row is not None and str(team_row.mission_uid or "").strip():
            mission_uids.add(str(team_row.mission_uid).strip())
        return sorted(mission_uids)
