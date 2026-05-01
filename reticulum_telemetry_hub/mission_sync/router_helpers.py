"""Mission-sync router parsing, validation, and authorization helpers."""

from __future__ import annotations

import uuid
from typing import Any


from reticulum_telemetry_hub.api.models import Topic
from reticulum_telemetry_hub.api.models import ZonePoint
from reticulum_telemetry_hub.api.marker_service import MarkerService
from reticulum_telemetry_hub.api.zone_service import ZoneService
from reticulum_telemetry_hub.mission_domain import EmergencyActionMessageService
from reticulum_telemetry_hub.mission_domain.service import DEFAULT_LOG_MISSION_UID
from reticulum_telemetry_hub.mission_domain.service import MissionDomainService
from reticulum_telemetry_hub.mission_sync.router_errors import MissionCommandError


class MissionRouterHelperMixin:
    """Provide helper methods shared by mission-sync route handling."""

    @staticmethod
    def _extract_command_id(raw_command: dict[str, Any]) -> str:
        command_id = raw_command.get("command_id")
        if isinstance(command_id, str) and command_id.strip():
            return command_id
        return uuid.uuid4().hex

    @staticmethod
    def _extract_correlation_id(raw_command: dict[str, Any]) -> str | None:
        value = raw_command.get("correlation_id")
        if isinstance(value, str) and value.strip():
            return value
        return None

    @staticmethod
    def _value_as_str(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _value_as_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _expand_values(value: Any) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, str):
            return {
                item.strip().lower()
                for item in value.split(",")
                if item and item.strip()
            }
        if isinstance(value, (list, tuple, set)):
            return {
                str(item).strip().lower()
                for item in value
                if str(item).strip()
            }
        text = str(value).strip().lower()
        return {text} if text else set()

    @staticmethod
    def _required_float(value: Any, *, field_name: str) -> float:
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise MissionCommandError(
                "invalid_payload", f"{field_name} is required and must be numeric"
            ) from exc

    @staticmethod
    def _coerce_zone_points(value: Any) -> list[ZonePoint]:
        if not isinstance(value, list):
            raise MissionCommandError("invalid_payload", "points must be a list")
        points: list[ZonePoint] = []
        for item in value:
            if not isinstance(item, dict):
                raise MissionCommandError("invalid_payload", "zone points must be objects")
            lat = item.get("lat")
            lon = item.get("lon")
            try:
                points.append(ZonePoint(lat=float(lat), lon=float(lon)))
            except (TypeError, ValueError) as exc:
                raise MissionCommandError(
                    "invalid_payload", "zone point lat/lon must be numeric"
                ) from exc
        return points

    @staticmethod
    def _build_topic_from_args(args: dict[str, Any]) -> Topic:
        topic_id = None
        raw_topic_id = args.get("topic_id")
        if raw_topic_id is not None:
            topic_id = str(raw_topic_id)
        topic_name = str(args.get("topic_name") or topic_id or "").strip()
        topic_path = str(args.get("topic_path") or topic_id or "").strip()
        if not topic_name or not topic_path:
            raise MissionCommandError(
                "invalid_payload", "topic_name and topic_path are required"
            )
        return Topic(
            topic_id=topic_id,
            topic_name=topic_name,
            topic_path=topic_path,
            topic_description=str(args.get("topic_description") or "").strip(),
        )

    @staticmethod
    def _require_topic_id(args: dict[str, Any]) -> str:
        topic_id = args.get("topic_id")
        if topic_id is None:
            topic_id = args.get("id")
        value = str(topic_id or "").strip()
        if not value:
            raise MissionCommandError("invalid_payload", "topic_id is required")
        return value

    def _require_marker_service(self) -> MarkerService:
        if self._marker_service is None:
            raise MissionCommandError(
                "unsupported_operation", "marker service is not configured"
            )
        return self._marker_service

    def _require_zone_service(self) -> ZoneService:
        if self._zone_service is None:
            raise MissionCommandError(
                "unsupported_operation", "zone service is not configured"
            )
        return self._zone_service

    def _require_domain_service(self) -> MissionDomainService:
        if self._domain is None:
            raise MissionCommandError(
                "unsupported_operation", "mission domain service is not configured"
            )
        return self._domain

    def _require_emergency_action_message_service(self) -> EmergencyActionMessageService:
        if self._emergency_action_message_service is None:
            raise MissionCommandError(
                "unsupported_operation",
                "Emergency Action Message service is not configured",
            )
        return self._emergency_action_message_service

    def _candidate_mission_uids(
        self,
        command_type: str,
        args: dict[str, Any],
    ) -> list[str]:
        rights = self._api.rights
        mission_uids: set[str] = set()

        direct_mission_uid = self._value_as_str(args.get("mission_uid")) or self._value_as_str(
            args.get("mission_id")
        )
        if direct_mission_uid:
            mission_uids.add(direct_mission_uid)
        elif command_type == "mission.registry.log_entry.upsert":
            mission_uids.add(DEFAULT_LOG_MISSION_UID)

        topic_id = self._value_as_str(args.get("topic_id")) or self._value_as_str(args.get("id"))
        if topic_id:
            mission_uids.update(rights.resolve_topic_mission_uids(topic_id))

        team_uid = self._value_as_str(args.get("team_uid")) or self._value_as_str(args.get("uid"))
        if (
            command_type.startswith("mission.registry.team.")
            or command_type.startswith("mission.registry.eam.")
        ) and team_uid:
            mission_uids.update(rights.resolve_team_mission_uids(team_uid))

        team_member_uid = self._value_as_str(args.get("team_member_uid")) or self._value_as_str(
            args.get("uid")
        )
        if (
            command_type.startswith("mission.registry.team_member.")
            or command_type.startswith("mission.registry.eam.")
        ) and team_member_uid:
            mission_uids.update(rights.resolve_team_member_mission_uids(team_member_uid))

        asset_uid = self._value_as_str(args.get("asset_uid"))
        if asset_uid:
            mission_uids.update(rights.resolve_asset_mission_uids(asset_uid))
        asset_team_member_uid = self._value_as_str(args.get("team_member_uid"))
        if command_type.startswith("mission.registry.asset.") and asset_team_member_uid:
            mission_uids.update(rights.resolve_team_member_mission_uids(asset_team_member_uid))

        assignment_uid = self._value_as_str(args.get("assignment_uid"))
        if assignment_uid:
            assignment_mission_uid = rights.resolve_assignment_mission_uid(assignment_uid)
            if assignment_mission_uid:
                mission_uids.add(assignment_mission_uid)

        if command_type.startswith("mission.zone.") or command_type.startswith(
            "mission.marker."
        ):
            if direct_mission_uid:
                mission_uids.add(direct_mission_uid)

        return sorted(mission_uids)

    def _is_authorized_for_operation(
        self,
        identity: str,
        operation: str,
        mission_uids: list[str],
    ) -> bool:
        if not mission_uids:
            return self._api.authorize(identity, operation, mission_uid=None)
        return any(
            self._api.authorize(identity, operation, mission_uid=mission_uid)
            for mission_uid in mission_uids
        )

    def _record_event(self, event_type: str, metadata: dict[str, Any]) -> None:
        if self._event_log is None:
            return
        self._event_log.add_event(
            event_type,
            event_type.replace("_", " "),
            metadata=metadata,
        )
