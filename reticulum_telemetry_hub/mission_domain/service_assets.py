"""Mission asset methods."""
# ruff: noqa: F403,F405

from __future__ import annotations

import uuid
from typing import Any


from reticulum_telemetry_hub.api.storage_models import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.enums import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.service_constants import _dt
from reticulum_telemetry_hub.mission_domain.service_constants import *  # noqa: F403


class MissionAssetMixin:
    """Mission asset methods."""

    @staticmethod
    def _serialize_asset(row: R3aktAssetRecord) -> dict[str, Any]:
        return {
            "asset_uid": row.asset_uid,
            "team_member_uid": row.team_member_uid,
            "name": row.name,
            "asset_type": row.asset_type,
            "serial_number": row.serial_number,
            "status": row.status,
            "location": row.location,
            "notes": row.notes,
            "created_at": _dt(row.created_at),
            "updated_at": _dt(row.updated_at),
        }

    def upsert_asset(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = str(payload.get("asset_uid") or uuid.uuid4().hex)
        with self._session() as session:
            row = session.get(R3aktAssetRecord, uid)
            if row is None:
                row = R3aktAssetRecord(
                    asset_uid=uid,
                    team_member_uid=None,
                    name="Asset",
                    asset_type="generic",
                    status=ASSET_STATUS_AVAILABLE,
                )
                session.add(row)
            previous_team_member_uid = str(row.team_member_uid or "").strip() or None
            team_member_uid = payload.get("team_member_uid") or row.team_member_uid
            if team_member_uid:
                self._ensure_team_member_uid_exists(session, str(team_member_uid))
            row.team_member_uid = team_member_uid
            row.name = str(payload.get("name") or row.name)
            row.asset_type = str(payload.get("asset_type") or row.asset_type)
            row.serial_number = payload.get("serial_number") or row.serial_number
            row.status = self._normalize_asset_status(
                payload.get("status"),
                default=str(row.status or ASSET_STATUS_AVAILABLE),
            )
            row.location = payload.get("location") or row.location
            row.notes = payload.get("notes") or row.notes
            session.flush()
            data = self._serialize_asset(row)
            self._record_event(session, domain="mission", aggregate_type="asset", aggregate_uid=uid, event_type="asset.upserted", payload=data)
            mission_uids = self._dedupe_non_empty(
                self._team_member_mission_uids(
                    session,
                    str(row.team_member_uid or "").strip(),
                )
                + self._team_member_mission_uids(
                    session,
                    str(previous_team_member_uid or "").strip(),
                )
            )
            asset_delta = {
                "op": "upsert",
                "asset_uid": data["asset_uid"],
                "team_member_uid": data["team_member_uid"],
                "name": data["name"],
                "asset_type": data["asset_type"],
                "status": data["status"],
                "location": data["location"],
                "notes": data["notes"],
            }
            for mission_uid in mission_uids:
                self._emit_auto_mission_change(
                    session,
                    mission_uid=mission_uid,
                    source_event_type="mission.asset.upserted",
                    change_type=MissionChangeType.ADD_CONTENT.value,
                    delta=self._build_delta_envelope(
                        source_event_type="mission.asset.upserted",
                        assets=[asset_delta],
                    ),
                )
            return data

    def list_assets(self, team_member_uid: str | None = None) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(R3aktAssetRecord)
            if team_member_uid:
                query = query.filter(R3aktAssetRecord.team_member_uid == team_member_uid)
            return [self._serialize_asset(row) for row in query.order_by(R3aktAssetRecord.name.asc()).all()]

    def get_asset(self, asset_uid: str) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktAssetRecord, asset_uid)
            if row is None:
                raise KeyError(f"Asset '{asset_uid}' not found")
            return self._serialize_asset(row)

    def delete_asset(self, asset_uid: str) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktAssetRecord, asset_uid)
            if row is None:
                raise KeyError(f"Asset '{asset_uid}' not found")
            data = self._serialize_asset(row)
            mission_uids = self._team_member_mission_uids(
                session,
                str(row.team_member_uid or "").strip(),
            )
            linked_assignments = (
                session.query(R3aktMissionTaskAssignmentRecord.mission_uid)
                .join(
                    R3aktAssignmentAssetLinkRecord,
                    R3aktAssignmentAssetLinkRecord.assignment_uid
                    == R3aktMissionTaskAssignmentRecord.assignment_uid,
                )
                .filter(R3aktAssignmentAssetLinkRecord.asset_uid == asset_uid)
                .all()
            )
            mission_uids.extend(str(item[0]) for item in linked_assignments)
            mission_uids = self._dedupe_non_empty(mission_uids)
            (
                session.query(R3aktAssignmentAssetLinkRecord)
                .filter(R3aktAssignmentAssetLinkRecord.asset_uid == asset_uid)
                .delete(synchronize_session=False)
            )
            assignments = session.query(R3aktMissionTaskAssignmentRecord).all()
            for assignment in assignments:
                existing_assets = [str(item) for item in list(assignment.assets_json or [])]
                filtered_assets = [
                    item for item in existing_assets if item != asset_uid
                ]
                if filtered_assets != existing_assets:
                    assignment.assets_json = filtered_assets
            session.delete(row)
            self._record_event(
                session,
                domain="mission",
                aggregate_type="asset",
                aggregate_uid=asset_uid,
                event_type="asset.deleted",
                payload=data,
            )
            asset_delta = {
                "op": "delete",
                "asset_uid": data["asset_uid"],
                "team_member_uid": data["team_member_uid"],
                "name": data["name"],
                "asset_type": data["asset_type"],
                "status": data["status"],
                "location": data["location"],
                "notes": data["notes"],
            }
            for mission_uid in mission_uids:
                self._emit_auto_mission_change(
                    session,
                    mission_uid=mission_uid,
                    source_event_type="mission.asset.deleted",
                    change_type=MissionChangeType.REMOVE_CONTENT.value,
                    delta=self._build_delta_envelope(
                        source_event_type="mission.asset.deleted",
                        assets=[asset_delta],
                    ),
                )
            return data

