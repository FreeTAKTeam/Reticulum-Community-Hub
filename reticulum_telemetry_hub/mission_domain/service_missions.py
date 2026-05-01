"""Mission CRUD and mission linkage methods."""
# ruff: noqa: F403,F405

from __future__ import annotations

import uuid
from typing import Any


from reticulum_telemetry_hub.api.storage_models import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.enums import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.enums import normalize_enum_value
from reticulum_telemetry_hub.mission_domain.service_constants import *  # noqa: F403


class MissionCrudMixin:
    """Mission CRUD and mission linkage methods."""

    def upsert_mission(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("uid") or payload.get("mission_id") or uuid.uuid4().hex).strip()
        if not uid:
            raise ValueError("uid is required")
        with self._session() as session:
            row = session.get(R3aktMissionRecord, uid)
            if row is None:
                row = R3aktMissionRecord(uid=uid, mission_name="Mission")
                session.add(row)

            row.mission_name = str(payload.get("mission_name") or payload.get("name") or row.mission_name).strip()
            if not row.mission_name:
                raise ValueError("mission_name is required")
            row.description = str(payload.get("description") or row.description or "")

            topic_id = payload.get("topic_id")
            if topic_id is not None:
                topic_text = str(topic_id).strip()
                if topic_text:
                    if session.get(TopicRecord, topic_text) is None:
                        raise ValueError(f"Topic '{topic_text}' not found")
                    row.topic_id = topic_text
                else:
                    row.topic_id = None

            row.path = (
                str(payload.get("path")).strip()
                if payload.get("path") is not None
                else row.path
            )
            row.classification = (
                str(payload.get("classification")).strip()
                if payload.get("classification") is not None
                else row.classification
            )
            row.tool = (
                str(payload.get("tool")).strip()
                if payload.get("tool") is not None
                else row.tool
            )
            if "keywords" in payload:
                row.keywords_json = self._normalize_string_list(
                    payload.get("keywords"),
                    field_name="keywords",
                )
            elif row.keywords_json is None:
                row.keywords_json = []

            parent_uid = self._resolve_parent_uid(payload, row.parent_uid)
            self._ensure_parent_chain_is_acyclic(session, mission_uid=uid, parent_uid=parent_uid)
            row.parent_uid = parent_uid

            if "feeds" in payload:
                row.feeds_json = self._normalize_string_list(
                    payload.get("feeds"),
                    field_name="feeds",
                )
            elif row.feeds_json is None:
                row.feeds_json = []

            if payload.get("password_hash") is not None:
                row.password_hash = str(payload.get("password_hash")).strip() or None

            row.default_role = self._normalize_optional_enum(
                payload.get("default_role"),
                field_name="default_role",
                allowed_values=enum_values(MissionRole),
                current=row.default_role,
            )
            row.owner_role = self._normalize_optional_enum(
                payload.get("owner_role"),
                field_name="owner_role",
                allowed_values=enum_values(MissionRole),
                current=row.owner_role,
            )
            row.mission_status = normalize_enum_value(
                payload.get("mission_status"),
                field_name="mission_status",
                allowed_values=enum_values(MissionStatus),
                default=row.mission_status or MissionStatus.MISSION_ACTIVE.value,
            )
            row.mission_priority = self._normalize_integer(
                payload.get("mission_priority"),
                field_name="mission_priority",
                minimum=MISSION_PRIORITY_MIN,
                maximum=MISSION_PRIORITY_MAX,
                default=row.mission_priority,
            )
            if payload.get("token") is not None:
                row.token = str(payload.get("token")).strip() or None
            if payload.get("invite_only") is not None:
                row.invite_only = bool(payload.get("invite_only"))
            if payload.get("expiration") is not None:
                row.expiration = _as_datetime(payload.get("expiration"), default=None)

            mission_rde_role = payload.get("mission_rde_role")
            if mission_rde_role is not None:
                normalized_role = normalize_enum_value(
                    mission_rde_role,
                    field_name="mission_rde_role",
                    allowed_values=enum_values(MissionRole),
                    default=MissionRole.MISSION_SUBSCRIBER.value,
                )
                rde_row = session.get(R3aktMissionRdeRecord, uid)
                if rde_row is None:
                    session.add(
                        R3aktMissionRdeRecord(
                            mission_uid=uid,
                            role=normalized_role,
                        )
                    )
                else:
                    rde_row.role = normalized_role

            session.flush()
            data = self._serialize_mission(session, row)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="mission",
                aggregate_uid=uid,
                event_type="mission.upserted",
                payload=data,
            )
            self._record_snapshot(
                session,
                domain="mission",
                aggregate_type="mission",
                aggregate_uid=uid,
                state=data,
            )
            return data

    def patch_mission(self, mission_uid: str, patch: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(patch, dict):
            raise ValueError("patch must be an object")
        with self._session() as session:
            if session.get(R3aktMissionRecord, mission_uid) is None:
                raise KeyError(f"Mission '{mission_uid}' not found")
        return self.upsert_mission({"uid": mission_uid, **patch})

    def delete_mission(self, mission_uid: str) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktMissionRecord, mission_uid)
            if row is None:
                raise KeyError(f"Mission '{mission_uid}' not found")
            row.mission_status = MissionStatus.MISSION_DELETED.value
            row.updated_at = _utcnow()
            session.flush()
            data = self._serialize_mission(session, row)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="mission",
                aggregate_uid=mission_uid,
                event_type="mission.deleted",
                payload=data,
            )
            self._record_snapshot(
                session,
                domain="mission",
                aggregate_type="mission",
                aggregate_uid=mission_uid,
                state=data,
            )
            return data

    def list_missions(
        self,
        *,
        expand_topic: bool = False,
        expand: set[str] | list[str] | str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        expand_values = self._normalize_mission_expand(expand)
        normalized_limit = max(1, min(int(limit), 2000))
        with self._session() as session:
            return [
                self._serialize_mission(
                    session,
                    row,
                    expand_topic=expand_topic,
                    expand=expand_values,
                )
                for row in session.query(R3aktMissionRecord)
                .order_by(R3aktMissionRecord.created_at.desc())
                .limit(normalized_limit)
                .all()
            ]

    def get_mission(
        self,
        mission_uid: str,
        *,
        expand_topic: bool = False,
        expand: set[str] | list[str] | str | None = None,
    ) -> dict[str, Any]:
        expand_values = self._normalize_mission_expand(expand)
        with self._session() as session:
            row = session.get(R3aktMissionRecord, mission_uid)
            if row is None:
                raise KeyError(f"Mission '{mission_uid}' not found")
            return self._serialize_mission(
                session,
                row,
                expand_topic=expand_topic,
                expand=expand_values,
            )

    def set_mission_parent(
        self, mission_uid: str, *, parent_uid: str | None
    ) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktMissionRecord, mission_uid)
            if row is None:
                raise KeyError(f"Mission '{mission_uid}' not found")
            normalized_parent = str(parent_uid or "").strip() or None
            self._ensure_parent_chain_is_acyclic(
                session,
                mission_uid=mission_uid,
                parent_uid=normalized_parent,
            )
            row.parent_uid = normalized_parent
            row.updated_at = _utcnow()
            session.flush()
            data = self._serialize_mission(session, row)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="mission",
                aggregate_uid=mission_uid,
                event_type="mission.parent.updated",
                payload={"mission_uid": mission_uid, "parent_uid": normalized_parent},
            )
            self._record_snapshot(
                session,
                domain="mission",
                aggregate_type="mission",
                aggregate_uid=mission_uid,
                state=data,
            )
            return data

    def link_mission_zone(self, mission_uid: str, zone_id: str) -> dict[str, Any]:
        zone_id = str(zone_id or "").strip()
        if not zone_id:
            raise ValueError("zone_id is required")
        with self._session() as session:
            mission = session.get(R3aktMissionRecord, mission_uid)
            if mission is None:
                raise KeyError(f"Mission '{mission_uid}' not found")
            if session.get(ZoneRecord, zone_id) is None:
                raise ValueError(f"Zone '{zone_id}' not found")
            row = (
                session.query(R3aktMissionZoneLinkRecord)
                .filter(
                    R3aktMissionZoneLinkRecord.mission_uid == mission_uid,
                    R3aktMissionZoneLinkRecord.zone_id == zone_id,
                )
                .first()
            )
            if row is None:
                session.add(
                    R3aktMissionZoneLinkRecord(
                        link_uid=uuid.uuid4().hex,
                        mission_uid=mission_uid,
                        zone_id=zone_id,
                    )
                )
            session.flush()
            data = self._serialize_mission(session, mission)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="mission",
                aggregate_uid=mission_uid,
                event_type="mission.zone.linked",
                payload={"mission_uid": mission_uid, "zone_id": zone_id},
            )
            return data

    def unlink_mission_zone(self, mission_uid: str, zone_id: str) -> dict[str, Any]:
        zone_id = str(zone_id or "").strip()
        if not zone_id:
            raise ValueError("zone_id is required")
        with self._session() as session:
            mission = session.get(R3aktMissionRecord, mission_uid)
            if mission is None:
                raise KeyError(f"Mission '{mission_uid}' not found")
            (
                session.query(R3aktMissionZoneLinkRecord)
                .filter(
                    R3aktMissionZoneLinkRecord.mission_uid == mission_uid,
                    R3aktMissionZoneLinkRecord.zone_id == zone_id,
                )
                .delete(synchronize_session=False)
            )
            session.flush()
            data = self._serialize_mission(session, mission)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="mission",
                aggregate_uid=mission_uid,
                event_type="mission.zone.unlinked",
                payload={"mission_uid": mission_uid, "zone_id": zone_id},
            )
            return data

    def list_mission_zones(self, mission_uid: str) -> list[str]:
        with self._session() as session:
            if session.get(R3aktMissionRecord, mission_uid) is None:
                raise KeyError(f"Mission '{mission_uid}' not found")
            return self._mission_zone_ids(session, mission_uid)

    def link_mission_marker(self, mission_uid: str, marker_id: str) -> dict[str, Any]:
        marker_id = str(marker_id or "").strip()
        if not marker_id:
            raise ValueError("marker_id is required")
        with self._session() as session:
            mission = session.get(R3aktMissionRecord, mission_uid)
            if mission is None:
                raise KeyError(f"Mission '{mission_uid}' not found")
            self._ensure_marker_exists(session, marker_id)
            row = (
                session.query(R3aktMissionMarkerLinkRecord)
                .filter(
                    R3aktMissionMarkerLinkRecord.mission_uid == mission_uid,
                    R3aktMissionMarkerLinkRecord.marker_id == marker_id,
                )
                .first()
            )
            if row is None:
                session.add(
                    R3aktMissionMarkerLinkRecord(
                        link_uid=uuid.uuid4().hex,
                        mission_uid=mission_uid,
                        marker_id=marker_id,
                    )
                )
            session.flush()
            data = self._serialize_mission(session, mission)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="mission",
                aggregate_uid=mission_uid,
                event_type="mission.marker.linked",
                payload={"mission_uid": mission_uid, "marker_id": marker_id},
            )
            return data

    def unlink_mission_marker(self, mission_uid: str, marker_id: str) -> dict[str, Any]:
        marker_id = str(marker_id or "").strip()
        if not marker_id:
            raise ValueError("marker_id is required")
        with self._session() as session:
            mission = session.get(R3aktMissionRecord, mission_uid)
            if mission is None:
                raise KeyError(f"Mission '{mission_uid}' not found")
            (
                session.query(R3aktMissionMarkerLinkRecord)
                .filter(
                    R3aktMissionMarkerLinkRecord.mission_uid == mission_uid,
                    R3aktMissionMarkerLinkRecord.marker_id == marker_id,
                )
                .delete(synchronize_session=False)
            )
            session.flush()
            data = self._serialize_mission(session, mission)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="mission",
                aggregate_uid=mission_uid,
                event_type="mission.marker.unlinked",
                payload={"mission_uid": mission_uid, "marker_id": marker_id},
            )
            return data

    def list_mission_markers(self, mission_uid: str) -> list[str]:
        with self._session() as session:
            if session.get(R3aktMissionRecord, mission_uid) is None:
                raise KeyError(f"Mission '{mission_uid}' not found")
            return self._mission_marker_ids(session, mission_uid)

    def upsert_mission_rde(self, mission_uid: str, role: str) -> dict[str, Any]:
        normalized_role = normalize_enum_value(
            role,
            field_name="role",
            allowed_values=enum_values(MissionRole),
            default=MissionRole.MISSION_SUBSCRIBER.value,
        )
        with self._session() as session:
            self._ensure_mission_exists(session, mission_uid)
            row = session.get(R3aktMissionRdeRecord, mission_uid)
            if row is None:
                row = R3aktMissionRdeRecord(mission_uid=mission_uid, role=normalized_role)
                session.add(row)
            else:
                row.role = normalized_role
            session.flush()
            payload = {
                "mission_uid": mission_uid,
                "role": row.role,
                "updated_at": _dt(row.updated_at),
            }
            self._record_event(
                session,
                domain="mission",
                aggregate_type="mission_rde",
                aggregate_uid=mission_uid,
                event_type="mission.rde.upserted",
                payload=payload,
            )
            return payload

    def get_mission_rde(self, mission_uid: str) -> dict[str, Any]:
        with self._session() as session:
            if session.get(R3aktMissionRecord, mission_uid) is None:
                raise KeyError(f"Mission '{mission_uid}' not found")
            row = session.get(R3aktMissionRdeRecord, mission_uid)
            if row is None:
                return {"mission_uid": mission_uid, "role": None, "updated_at": None}
            return {
                "mission_uid": mission_uid,
                "role": row.role,
                "updated_at": _dt(row.updated_at),
            }

