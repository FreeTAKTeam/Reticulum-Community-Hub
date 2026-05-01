"""Mission change and log entry methods."""
# ruff: noqa: F403,F405

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from reticulum_telemetry_hub.api.storage_models import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.enums import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.enums import normalize_enum_value
from reticulum_telemetry_hub.mission_domain.service_constants import *  # noqa: F403


class MissionChangeLogMixin:
    """Mission change and log entry methods."""

    @staticmethod
    def _serialize_mission_change(row: R3aktMissionChangeRecord) -> dict[str, Any]:
        return {
            "uid": row.uid,
            "mission_uid": row.mission_uid,
            "mission_id": row.mission_uid,
            "name": row.name,
            "team_member_rns_identity": row.team_member_rns_identity,
            "timestamp": _dt(row.timestamp),
            "notes": row.notes,
            "change_type": row.change_type,
            "is_federated_change": bool(row.is_federated_change),
            "hashes": list(row.hashes_json or []),
            "delta": dict(row.delta_json or {}),
        }

    @staticmethod
    def _normalize_mission_change_delta(payload: Any) -> dict[str, Any]:
        if payload is None:
            return {}
        if not isinstance(payload, dict):
            raise ValueError("delta must be an object")
        return dict(payload)

    def _upsert_mission_change_in_session(
        self,
        session: Session,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        uid = str(payload.get("uid") or uuid.uuid4().hex)
        mission_uid = str(
            payload.get("mission_uid") or payload.get("mission_id") or ""
        ).strip()
        if not mission_uid:
            raise ValueError("mission_uid is required")
        self._ensure_mission_exists(session, mission_uid)
        row = session.get(R3aktMissionChangeRecord, uid)
        if row is None:
            row = R3aktMissionChangeRecord(uid=uid, mission_uid=mission_uid)
            session.add(row)
        row.mission_uid = mission_uid
        row.name = payload.get("name")
        row.team_member_rns_identity = payload.get("team_member_rns_identity")
        row.timestamp = _as_datetime(payload.get("timestamp"), default=_utcnow()) or _utcnow()
        row.notes = payload.get("notes")
        row.change_type = normalize_enum_value(
            payload.get("change_type"),
            field_name="change_type",
            allowed_values=enum_values(MissionChangeType),
            default=row.change_type or MissionChangeType.ADD_CONTENT.value,
        )
        if payload.get("is_federated_change") is not None:
            row.is_federated_change = bool(payload.get("is_federated_change"))
        hashes = self._normalize_string_list(payload.get("hashes"), field_name="hashes")
        for marker_ref in hashes:
            self._ensure_marker_exists(session, marker_ref)
        row.hashes_json = hashes
        row.delta_json = self._normalize_mission_change_delta(payload.get("delta"))
        session.flush()
        data = self._serialize_mission_change(row)
        self._record_event(
            session,
            domain="mission",
            aggregate_type="mission_change",
            aggregate_uid=uid,
            event_type="mission.change.upserted",
            payload=data,
        )
        self._queue_mission_change_listener_notification(session, data)
        return data

    def upsert_mission_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._session() as session:
            return self._upsert_mission_change_in_session(session, payload)

    def list_mission_changes(self, mission_uid: str | None = None) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(R3aktMissionChangeRecord)
            if mission_uid:
                query = query.filter(R3aktMissionChangeRecord.mission_uid == mission_uid)
            return [self._serialize_mission_change(row) for row in query.order_by(R3aktMissionChangeRecord.timestamp.desc()).all()]

    @staticmethod
    def _build_delta_envelope(
        *,
        source_event_type: str,
        logs: list[dict[str, Any]] | None = None,
        assets: list[dict[str, Any]] | None = None,
        tasks: list[dict[str, Any]] | None = None,
        checklists: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "version": 1,
            "contract_version": MISSION_DELTA_CONTRACT_VERSION,
            "source_event_type": source_event_type,
            "emitted_at": _dt(_utcnow()),
            "logs": list(logs or []),
            "assets": list(assets or []),
            "tasks": list(tasks or []),
            "checklists": list(checklists or []),
        }

    def _emit_auto_mission_change(
        self,
        session: Session,
        *,
        mission_uid: str | None,
        source_event_type: str,
        change_type: str,
        delta: dict[str, Any],
        notes: str | None = None,
        team_member_rns_identity: str | None = None,
        hashes: list[str] | None = None,
    ) -> dict[str, Any] | None:
        normalized_mission_uid = str(mission_uid or "").strip()
        if not normalized_mission_uid:
            return None
        payload: dict[str, Any] = {
            "uid": uuid.uuid4().hex,
            "mission_uid": normalized_mission_uid,
            "timestamp": _dt(_utcnow()),
            "change_type": change_type,
            "notes": notes,
            "team_member_rns_identity": team_member_rns_identity,
            "hashes": list(hashes or []),
            "delta": delta,
            "name": source_event_type,
        }
        return self._upsert_mission_change_in_session(session, payload)

    @staticmethod
    def _serialize_log_entry(row: R3aktLogEntryRecord) -> dict[str, Any]:
        return {
            "entry_uid": row.entry_uid,
            "mission_uid": row.mission_uid,
            "callsign": row.callsign,
            "content": row.content,
            "server_time": _dt(row.server_time),
            "client_time": _dt(row.client_time),
            "content_hashes": list(row.content_hashes_json or []),
            "keywords": list(row.keywords_json or []),
            "created_at": _dt(row.created_at),
            "updated_at": _dt(row.updated_at),
        }

    @staticmethod
    def _team_member_callsign_for_identity(
        session: Session, identity: str | None
    ) -> str | None:
        """Return a team-member callsign or display name for a known identity."""

        normalized_identity = str(identity or "").strip().lower()
        if not normalized_identity:
            return None
        row = (
            session.query(
                R3aktTeamMemberRecord.callsign,
                R3aktTeamMemberRecord.display_name,
            )
            .filter(R3aktTeamMemberRecord.rns_identity == normalized_identity)
            .first()
        )
        if row is None:
            return None
        callsign = str(row[0] or "").strip()
        if callsign:
            return callsign
        display_name = str(row[1] or "").strip()
        return display_name or None

    def upsert_log_entry(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("entry_uid") or payload.get("uid") or uuid.uuid4().hex)
        raw_content = payload.get("content")
        with self._session() as session:
            row = session.get(R3aktLogEntryRecord, uid)
            raw_mission_uid = payload.get("mission_uid")
            if raw_mission_uid is None:
                raw_mission_uid = payload.get("mission_id")
            if raw_mission_uid is None:
                mission_uid = str(row.mission_uid or "").strip() if row is not None else ""
            else:
                mission_uid = str(raw_mission_uid or "").strip()
            if mission_uid:
                self._ensure_mission_exists(session, mission_uid)
            else:
                mission_uid = self._ensure_default_log_mission(session)
            if row is None:
                content_text = str(raw_content or "").strip()
                if not content_text:
                    raise ValueError("content is required")
                row = R3aktLogEntryRecord(
                    entry_uid=uid,
                    mission_uid=mission_uid,
                    content=content_text,
                )
                session.add(row)
            row.mission_uid = mission_uid
            if any(key in payload for key in ("callsign", "author_callsign")):
                raw_callsign = payload.get("callsign")
                if raw_callsign is None:
                    raw_callsign = payload.get("author_callsign")
                callsign = str(raw_callsign or "").strip()
                row.callsign = callsign or None
            elif not str(row.callsign or "").strip():
                row.callsign = self._team_member_callsign_for_identity(
                    session,
                    payload.get("source_identity")
                    or payload.get("team_member_rns_identity"),
                )
            if raw_content is not None:
                content_text = str(raw_content).strip()
                if not content_text:
                    raise ValueError("content must not be empty")
                row.content = content_text

            raw_server_time = payload.get("server_time")
            if raw_server_time is None:
                raw_server_time = payload.get("servertime")
            row.server_time = (
                _as_datetime(raw_server_time, default=row.server_time or _utcnow())
                or _utcnow()
            )

            has_client_time = any(
                key in payload for key in ("client_time", "clientTime", "clienttime")
            )
            if has_client_time:
                raw_client_time = payload.get("client_time")
                if raw_client_time is None:
                    raw_client_time = payload.get("clientTime")
                if raw_client_time is None:
                    raw_client_time = payload.get("clienttime")
                row.client_time = _as_datetime(raw_client_time, default=None)

            has_content_hashes = "content_hashes" in payload or "contenthashes" in payload
            if has_content_hashes:
                raw_hashes = payload.get("content_hashes")
                if raw_hashes is None:
                    raw_hashes = payload.get("contenthashes")
                content_hashes = self._normalize_string_list(
                    raw_hashes, field_name="content_hashes"
                )
                for marker_ref in content_hashes:
                    self._ensure_marker_exists(session, marker_ref)
                row.content_hashes_json = content_hashes
            elif row.content_hashes_json is None:
                row.content_hashes_json = []

            if "keywords" in payload:
                row.keywords_json = self._normalize_string_list(
                    payload.get("keywords"),
                    field_name="keywords",
                )
            elif row.keywords_json is None:
                row.keywords_json = []

            row.updated_at = _utcnow()
            session.flush()
            data = self._serialize_log_entry(row)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="log_entry",
                aggregate_uid=uid,
                event_type="mission.log_entry.upserted",
                payload=data,
            )
            log_delta = {
                "op": "upsert",
                "entry_uid": data["entry_uid"],
                "mission_uid": data["mission_uid"],
                "callsign": data["callsign"],
                "content": data["content"],
                "server_time": data["server_time"],
                "client_time": data["client_time"],
                "keywords": list(data.get("keywords") or []),
                "content_hashes": list(data.get("content_hashes") or []),
            }
            self._emit_auto_mission_change(
                session,
                mission_uid=mission_uid,
                source_event_type="mission.log_entry.upserted",
                change_type=MissionChangeType.ADD_CONTENT.value,
                delta=self._build_delta_envelope(
                    source_event_type="mission.log_entry.upserted",
                    logs=[log_delta],
                ),
                hashes=list(data.get("content_hashes") or []),
            )
            return data

    def list_log_entries(
        self,
        *,
        mission_uid: str | None = None,
        marker_ref: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(R3aktLogEntryRecord)
            if mission_uid:
                query = query.filter(R3aktLogEntryRecord.mission_uid == mission_uid)
            rows = query.order_by(R3aktLogEntryRecord.server_time.desc()).all()
            entries = [self._serialize_log_entry(row) for row in rows]
            if marker_ref:
                value = str(marker_ref).strip()
                if value:
                    entries = [
                        entry for entry in entries if value in entry["content_hashes"]
                    ]
            return entries

