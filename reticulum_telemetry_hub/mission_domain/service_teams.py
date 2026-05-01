"""Mission team methods."""
# ruff: noqa: F403,F405

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from reticulum_telemetry_hub.api.storage_models import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.canonical_teams import canonical_team_from_payload
from reticulum_telemetry_hub.mission_domain.enums import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.service_constants import _dt
from reticulum_telemetry_hub.mission_domain.service_constants import *  # noqa: F403


class MissionTeamMixin:
    """Mission team methods."""

    def _serialize_team(self, session: Session, row: R3aktTeamRecord) -> dict[str, Any]:
        mission_uids = self._team_mission_ids(session, row.uid)
        mission_uid = mission_uids[0] if mission_uids else None
        return {
            "uid": row.uid,
            "mission_uid": mission_uid,
            "mission_uids": mission_uids,
            "color": row.color,
            "team_name": row.team_name,
            "team_description": row.team_description or "",
            "created_at": _dt(row.created_at),
            "updated_at": _dt(row.updated_at),
        }

    def upsert_team(self, payload: dict[str, Any]) -> dict[str, Any]:
        requested_uid = str(payload.get("uid") or "").strip()
        canonical_team = canonical_team_from_payload(payload)
        if canonical_team is not None and requested_uid and canonical_team["uid"] != requested_uid:
            # Preserve explicitly provided non-canonical UIDs even if the color
            # happens to match a canonical team color.
            canonical_team = None
        if canonical_team is not None:
            uid = canonical_team["uid"]
        else:
            uid = str(payload.get("uid") or uuid.uuid4().hex)
        with self._session() as session:
            row = session.get(R3aktTeamRecord, uid)
            if row is None:
                row = R3aktTeamRecord(uid=uid, team_name="Team")
                session.add(row)

            mission_refs_provided = any(
                key in payload for key in ("mission_uid", "mission_id", "mission_uids")
            )
            if mission_refs_provided:
                mission_uids: list[str] = []
                if "mission_uids" in payload:
                    mission_uids = self._normalize_string_list(
                        payload.get("mission_uids"),
                        field_name="mission_uids",
                    )
                single_mission = str(
                    payload.get("mission_uid") or payload.get("mission_id") or ""
                ).strip()
                if single_mission:
                    mission_uids.append(single_mission)
                mission_uids = self._dedupe_non_empty(mission_uids)
                for mission_uid in mission_uids:
                    self._ensure_mission_exists(session, mission_uid)
                self._set_team_mission_links(
                    session,
                    team_uid=uid,
                    mission_uids=mission_uids,
                )
            else:
                mission_uids = self._team_mission_ids(session, uid)

            row.mission_uid = mission_uids[0] if mission_uids else None
            if canonical_team is not None:
                row.color = canonical_team["color"]
                row.team_name = canonical_team["team_name"]
            else:
                row.color = self._normalize_optional_enum(
                    payload.get("color"),
                    field_name="color",
                    allowed_values=enum_values(TeamColor),
                    current=row.color,
                )
                row.team_name = str(
                    payload.get("team_name") or payload.get("name") or row.team_name
                )
            row.team_description = str(payload.get("team_description") or payload.get("description") or row.team_description or "")
            session.flush()
            data = self._serialize_team(session, row)
            self._record_event(session, domain="mission", aggregate_type="team", aggregate_uid=uid, event_type="team.upserted", payload=data)
            return data

    def list_teams(self, mission_uid: str | None = None) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(R3aktTeamRecord)
            if mission_uid:
                team_uids = self._mission_team_uids(session, str(mission_uid))
                if not team_uids:
                    return []
                query = query.filter(R3aktTeamRecord.uid.in_(team_uids))
            return [
                self._serialize_team(session, row)
                for row in query.order_by(R3aktTeamRecord.team_name.asc()).all()
            ]

    def get_team(self, team_uid: str) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktTeamRecord, team_uid)
            if row is None:
                raise KeyError(f"Team '{team_uid}' not found")
            return self._serialize_team(session, row)

    def delete_team(self, team_uid: str) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktTeamRecord, team_uid)
            if row is None:
                raise KeyError(f"Team '{team_uid}' not found")
            data = self._serialize_team(session, row)
            (
                session.query(R3aktTeamMemberRecord)
                .filter(R3aktTeamMemberRecord.team_uid == team_uid)
                .update(
                    {R3aktTeamMemberRecord.team_uid: None},
                    synchronize_session=False,
                )
            )
            (
                session.query(R3aktMissionTeamLinkRecord)
                .filter(R3aktMissionTeamLinkRecord.team_uid == team_uid)
                .delete(synchronize_session=False)
            )
            session.delete(row)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="team",
                aggregate_uid=team_uid,
                event_type="team.deleted",
                payload=data,
            )
            return data

    def list_team_missions(self, team_uid: str) -> list[str]:
        with self._session() as session:
            row = session.get(R3aktTeamRecord, team_uid)
            if row is None:
                raise KeyError(f"Team '{team_uid}' not found")
            return self._team_mission_ids(session, team_uid)

    def link_team_mission(self, team_uid: str, mission_uid: str) -> dict[str, Any]:
        mission_uid = str(mission_uid or "").strip()
        if not mission_uid:
            raise ValueError("mission_uid is required")
        with self._session() as session:
            row = session.get(R3aktTeamRecord, team_uid)
            if row is None:
                raise KeyError(f"Team '{team_uid}' not found")
            self._ensure_mission_exists(session, mission_uid)
            existing = self._team_mission_ids(session, team_uid)
            if mission_uid not in existing:
                existing.append(mission_uid)
            existing = self._dedupe_non_empty(existing)
            self._set_team_mission_links(
                session,
                team_uid=team_uid,
                mission_uids=existing,
            )
            row.mission_uid = existing[0] if existing else None
            session.flush()
            data = self._serialize_team(session, row)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="team",
                aggregate_uid=team_uid,
                event_type="team.mission.linked",
                payload={"team_uid": team_uid, "mission_uid": mission_uid},
            )
            return data

    def unlink_team_mission(self, team_uid: str, mission_uid: str) -> dict[str, Any]:
        mission_uid = str(mission_uid or "").strip()
        if not mission_uid:
            raise ValueError("mission_uid is required")
        with self._session() as session:
            row = session.get(R3aktTeamRecord, team_uid)
            if row is None:
                raise KeyError(f"Team '{team_uid}' not found")
            remaining = [
                item
                for item in self._team_mission_ids(session, team_uid)
                if item != mission_uid
            ]
            self._set_team_mission_links(
                session,
                team_uid=team_uid,
                mission_uids=remaining,
            )
            row.mission_uid = remaining[0] if remaining else None
            session.flush()
            data = self._serialize_team(session, row)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="team",
                aggregate_uid=team_uid,
                event_type="team.mission.unlinked",
                payload={"team_uid": team_uid, "mission_uid": mission_uid},
            )
            return data

    def list_mission_team_member_identities(self, mission_uid: str) -> list[str]:
        with self._session() as session:
            self._ensure_mission_exists(session, mission_uid)
            team_uids = self._mission_team_uids(session, mission_uid)
            if not team_uids:
                return []
            members = (
                session.query(R3aktTeamMemberRecord)
                .filter(R3aktTeamMemberRecord.team_uid.in_(team_uids))
                .order_by(R3aktTeamMemberRecord.created_at.asc())
                .all()
            )
            identities: list[str] = []
            for member in members:
                if member.rns_identity:
                    identities.append(str(member.rns_identity).strip().lower())
                identities.extend(self._team_member_clients(session, member.uid))
            return self._dedupe_non_empty(identities)

