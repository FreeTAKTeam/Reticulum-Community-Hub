"""Mission team member methods."""
# ruff: noqa: F403,F405

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from reticulum_telemetry_hub.api.storage_models import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.enums import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.service_constants import *  # noqa: F403


class MissionTeamMemberMixin:
    """Mission team member methods."""

    def _team_member_clients(
        self, session: Session, team_member_uid: str
    ) -> list[str]:
        rows = (
            session.query(R3aktTeamMemberClientLinkRecord.client_identity)
            .filter(R3aktTeamMemberClientLinkRecord.team_member_uid == team_member_uid)
            .order_by(R3aktTeamMemberClientLinkRecord.created_at.asc())
            .all()
        )
        return [str(row[0]) for row in rows]

    def _serialize_team_member(
        self, session: Session, row: R3aktTeamMemberRecord
    ) -> dict[str, Any]:
        return {
            "uid": row.uid,
            "team_uid": row.team_uid,
            "rns_identity": row.rns_identity,
            "display_name": row.display_name,
            "icon": row.icon,
            "role": row.role,
            "callsign": row.callsign,
            "freq": row.freq,
            "email": row.email,
            "phone": row.phone,
            "modulation": row.modulation,
            "availability": row.availability,
            "certifications": list(row.certifications_json or []),
            "last_active": _dt(row.last_active),
            "client_identities": self._team_member_clients(session, row.uid),
            "created_at": _dt(row.created_at),
            "updated_at": _dt(row.updated_at),
        }

    def upsert_team_member(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("uid") or uuid.uuid4().hex)
        identity = str(payload.get("rns_identity") or payload.get("team_member_rns_identity") or "").strip()
        if not identity:
            raise ValueError("rns_identity is required")
        with self._session() as session:
            row = session.get(R3aktTeamMemberRecord, uid)
            if row is None:
                row = R3aktTeamMemberRecord(uid=uid, team_uid=None, rns_identity=identity, display_name=identity)
                session.add(row)
            if "team_uid" in payload:
                team_uid = str(payload.get("team_uid") or "").strip()
            else:
                team_uid = str(row.team_uid or "").strip()
            if team_uid:
                self._ensure_team_exists(session, team_uid)
            row.team_uid = team_uid or None
            row.rns_identity = identity
            row.display_name = str(payload.get("display_name") or payload.get("callsign") or row.display_name)
            row.icon = payload.get("icon") or row.icon
            row.role = self._normalize_optional_enum(
                payload.get("role"),
                field_name="role",
                allowed_values=enum_values(TeamRole),
                current=row.role,
            )
            row.callsign = payload.get("callsign") or row.callsign
            if payload.get("freq") is not None:
                try:
                    row.freq = float(payload.get("freq"))
                except (TypeError, ValueError) as exc:
                    raise ValueError("freq must be numeric") from exc
            row.email = payload.get("email") or row.email
            row.phone = payload.get("phone") or row.phone
            row.modulation = payload.get("modulation") or row.modulation
            row.availability = payload.get("availability") or row.availability
            if "certifications" in payload:
                row.certifications_json = self._normalize_string_list(
                    payload.get("certifications"),
                    field_name="certifications",
                )
            elif row.certifications_json is None:
                row.certifications_json = []
            if payload.get("last_active") is not None:
                row.last_active = _as_datetime(payload.get("last_active"), default=None)
            session.flush()
            data = self._serialize_team_member(session, row)
            self._record_event(session, domain="mission", aggregate_type="team_member", aggregate_uid=uid, event_type="team_member.upserted", payload=data)
            return data

    def list_team_members(self, team_uid: str | None = None) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(R3aktTeamMemberRecord)
            if team_uid:
                query = query.filter(R3aktTeamMemberRecord.team_uid == team_uid)
            return [
                self._serialize_team_member(session, row)
                for row in query.order_by(R3aktTeamMemberRecord.display_name.asc()).all()
            ]

    def get_team_member(self, team_member_uid: str) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktTeamMemberRecord, team_member_uid)
            if row is None:
                raise KeyError(f"Team member '{team_member_uid}' not found")
            return self._serialize_team_member(session, row)

    def delete_team_member(self, team_member_uid: str) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktTeamMemberRecord, team_member_uid)
            if row is None:
                raise KeyError(f"Team member '{team_member_uid}' not found")
            data = self._serialize_team_member(session, row)
            member_identity = str(row.rns_identity or "").strip()
            (
                session.query(R3aktAssetRecord)
                .filter(R3aktAssetRecord.team_member_uid == team_member_uid)
                .update(
                    {R3aktAssetRecord.team_member_uid: None},
                    synchronize_session=False,
                )
            )
            (
                session.query(R3aktTeamMemberClientLinkRecord)
                .filter(R3aktTeamMemberClientLinkRecord.team_member_uid == team_member_uid)
                .delete(synchronize_session=False)
            )
            if member_identity:
                (
                    session.query(R3aktTeamMemberSkillRecord)
                    .filter(
                        R3aktTeamMemberSkillRecord.team_member_rns_identity
                        == member_identity
                    )
                    .delete(synchronize_session=False)
                )
            session.delete(row)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="team_member",
                aggregate_uid=team_member_uid,
                event_type="team_member.deleted",
                payload=data,
            )
            return data

    def link_team_member_client(self, team_member_uid: str, client_identity: str) -> dict[str, Any]:
        normalized_identity = self._normalize_identity(
            client_identity, field_name="client_identity"
        )
        with self._session() as session:
            member = session.get(R3aktTeamMemberRecord, team_member_uid)
            if member is None:
                raise KeyError(f"Team member '{team_member_uid}' not found")
            row = (
                session.query(R3aktTeamMemberClientLinkRecord)
                .filter(
                    R3aktTeamMemberClientLinkRecord.team_member_uid == team_member_uid,
                    R3aktTeamMemberClientLinkRecord.client_identity
                    == normalized_identity,
                )
                .first()
            )
            if row is None:
                session.add(
                    R3aktTeamMemberClientLinkRecord(
                        link_uid=uuid.uuid4().hex,
                        team_member_uid=team_member_uid,
                        client_identity=normalized_identity,
                    )
                )
            session.flush()
            data = self._serialize_team_member(session, member)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="team_member",
                aggregate_uid=team_member_uid,
                event_type="team_member.client.linked",
                payload={
                    "team_member_uid": team_member_uid,
                    "client_identity": normalized_identity,
                },
            )
            return data

    def unlink_team_member_client(self, team_member_uid: str, client_identity: str) -> dict[str, Any]:
        normalized_identity = self._normalize_identity(
            client_identity, field_name="client_identity"
        )
        with self._session() as session:
            member = session.get(R3aktTeamMemberRecord, team_member_uid)
            if member is None:
                raise KeyError(f"Team member '{team_member_uid}' not found")
            (
                session.query(R3aktTeamMemberClientLinkRecord)
                .filter(
                    R3aktTeamMemberClientLinkRecord.team_member_uid == team_member_uid,
                    R3aktTeamMemberClientLinkRecord.client_identity
                    == normalized_identity,
                )
                .delete(synchronize_session=False)
            )
            session.flush()
            data = self._serialize_team_member(session, member)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="team_member",
                aggregate_uid=team_member_uid,
                event_type="team_member.client.unlinked",
                payload={
                    "team_member_uid": team_member_uid,
                    "client_identity": normalized_identity,
                },
            )
            return data

    def list_team_member_clients(self, team_member_uid: str) -> list[str]:
        with self._session() as session:
            if session.get(R3aktTeamMemberRecord, team_member_uid) is None:
                raise KeyError(f"Team member '{team_member_uid}' not found")
            return self._team_member_clients(session, team_member_uid)
