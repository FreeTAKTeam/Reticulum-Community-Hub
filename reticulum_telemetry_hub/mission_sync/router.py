"""Mission-sync command routing and response building."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
import uuid
from typing import Any
from typing import Callable
from typing import Optional

from pydantic import ValidationError

from reticulum_telemetry_hub.api.models import Topic
from reticulum_telemetry_hub.api.models import ZonePoint
from reticulum_telemetry_hub.api.marker_service import MarkerService
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.api.zone_service import ZoneService
from reticulum_telemetry_hub.mission_domain.service import MissionDomainService
from reticulum_telemetry_hub.mission_sync.capabilities import MISSION_COMMAND_CAPABILITIES
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandAccepted
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandEnvelope
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandRejected
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandResult
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog


def _utcnow() -> datetime:
    """Return the current aware UTC timestamp."""

    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class MissionSyncResponse:
    """Normalized mission-sync response payload."""

    content: str
    fields: dict[int | str, object]


class MissionCommandError(Exception):
    """Error raised for mission command execution failures."""

    def __init__(
        self,
        reason_code: str,
        reason: str,
        *,
        required_capabilities: Optional[list[str]] = None,
    ) -> None:
        super().__init__(reason)
        self.reason_code = reason_code
        self.reason = reason
        self.required_capabilities = list(required_capabilities or [])


class MissionSyncRouter:
    """Route mission-sync command envelopes to backend operations."""

    def __init__(
        self,
        *,
        api: ReticulumTelemetryHubAPI,
        send_message: Callable[[str, str | None, str | None], bool],
        marker_service: MarkerService | None,
        zone_service: ZoneService | None,
        domain_service: MissionDomainService | None,
        event_log: EventLog | None,
        hub_identity_resolver: Callable[[], str | None],
        field_results: int,
        field_event: int,
        field_group: int,
    ) -> None:
        self._api = api
        self._send_message = send_message
        self._marker_service = marker_service
        self._zone_service = zone_service
        self._domain = domain_service
        self._event_log = event_log
        self._hub_identity_resolver = hub_identity_resolver
        self._field_results = field_results
        self._field_event = field_event
        self._field_group = field_group

    def handle_commands(
        self,
        commands: list[dict[str, Any]],
        *,
        source_identity: str | None,
        group: object | None = None,
    ) -> list[MissionSyncResponse]:
        """Handle mission-sync command payloads."""

        responses: list[MissionSyncResponse] = []
        for raw_command in commands:
            responses.extend(
                self._handle_single(
                    raw_command,
                    source_identity=source_identity,
                    group=group,
                )
            )
        return responses

    def _handle_single(
        self,
        raw_command: dict[str, Any],
        *,
        source_identity: str | None,
        group: object | None,
    ) -> list[MissionSyncResponse]:
        command_id = self._extract_command_id(raw_command)
        correlation_id = self._extract_correlation_id(raw_command)
        try:
            envelope = MissionCommandEnvelope.model_validate(raw_command)
        except ValidationError as exc:
            rejected = MissionCommandRejected(
                command_id=command_id,
                reason_code="invalid_payload",
                reason=str(exc),
                correlation_id=correlation_id,
            )
            return [self._response_from_results(rejected.model_dump(mode="json"), group=group)]

        envelope_source = str(envelope.source.rns_identity or "").strip().lower()
        if source_identity and envelope_source and envelope_source != source_identity.lower():
            rejected = MissionCommandRejected(
                command_id=envelope.command_id,
                reason_code="unauthorized",
                reason="Envelope source identity does not match transport sender",
                correlation_id=envelope.correlation_id,
            )
            return [self._response_from_results(rejected.model_dump(mode="json"), group=group)]

        required_capability = MISSION_COMMAND_CAPABILITIES.get(envelope.command_type)
        if required_capability is None:
            rejected = MissionCommandRejected(
                command_id=envelope.command_id,
                reason_code="unknown_command",
                reason=f"Unsupported mission command '{envelope.command_type}'",
                correlation_id=envelope.correlation_id,
            )
            return [self._response_from_results(rejected.model_dump(mode="json"), group=group)]

        if not source_identity:
            rejected = MissionCommandRejected(
                command_id=envelope.command_id,
                reason_code="unauthorized",
                reason="Source identity is required",
                correlation_id=envelope.correlation_id,
                required_capabilities=[required_capability],
            )
            return [self._response_from_results(rejected.model_dump(mode="json"), group=group)]

        capabilities = set(self._api.list_identity_capabilities(source_identity))
        if required_capability not in capabilities:
            rejected = MissionCommandRejected(
                command_id=envelope.command_id,
                reason_code="unauthorized",
                reason=f"Capability '{required_capability}' is required",
                correlation_id=envelope.correlation_id,
                required_capabilities=[required_capability],
            )
            self._record_event(
                "mission_command_rejected",
                {
                    "command_id": envelope.command_id,
                    "command_type": envelope.command_type,
                    "reason_code": "unauthorized",
                    "identity": source_identity,
                },
            )
            return [self._response_from_results(rejected.model_dump(mode="json"), group=group)]

        accepted = MissionCommandAccepted(
            command_id=envelope.command_id,
            accepted_at=_utcnow(),
            correlation_id=envelope.correlation_id,
            by_identity=self._hub_identity_resolver(),
        )
        responses: list[MissionSyncResponse] = [
            self._response_from_results(accepted.model_dump(mode="json"), group=group)
        ]

        try:
            result_payload, event_type, event_payload = self._execute_command(
                envelope, source_identity=source_identity
            )
        except MissionCommandError as exc:
            rejected = MissionCommandRejected(
                command_id=envelope.command_id,
                reason_code=exc.reason_code,
                reason=exc.reason,
                correlation_id=envelope.correlation_id,
                required_capabilities=exc.required_capabilities,
            )
            responses.append(
                self._response_from_results(rejected.model_dump(mode="json"), group=group)
            )
            self._record_event(
                "mission_command_rejected",
                {
                    "command_id": envelope.command_id,
                    "command_type": envelope.command_type,
                    "reason_code": exc.reason_code,
                    "reason": exc.reason,
                    "identity": source_identity,
                },
            )
            return responses

        result = MissionCommandResult(
            command_id=envelope.command_id,
            correlation_id=envelope.correlation_id,
            result=result_payload,
        )
        responses.append(
            self._response_from_results(
                result.model_dump(mode="json"),
                group=group,
                event=self._build_event_envelope(
                    event_type=event_type,
                    payload=event_payload,
                    source_identity=source_identity,
                    topics=envelope.topics,
                ),
            )
        )
        self._record_event(
            "mission_command_processed",
            {
                "command_id": envelope.command_id,
                "command_type": envelope.command_type,
                "identity": source_identity,
                "event_type": event_type,
            },
        )
        return responses

    def _execute_command(
        self, envelope: MissionCommandEnvelope, *, source_identity: str
    ) -> tuple[dict[str, Any], str, dict[str, Any]]:
        command_type = envelope.command_type
        args = dict(envelope.args or {})
        try:
            if command_type == "mission.join":
                identity = str(args.get("identity") or source_identity)
                joined = self._api.join(identity)
                payload = {"identity": identity, "joined": bool(joined)}
                return payload, "mission.joined", payload
            if command_type == "mission.leave":
                identity = str(args.get("identity") or source_identity)
                left = self._api.leave(identity)
                payload = {"identity": identity, "left": bool(left)}
                return payload, "mission.left", payload
            if command_type == "mission.events.list":
                events = self._event_log.list_events(limit=50) if self._event_log else []
                payload = {"events": events}
                return payload, "mission.events.listed", payload
            if command_type == "mission.message.send":
                content = str(args.get("content") or "").strip()
                if not content:
                    raise MissionCommandError("invalid_payload", "content is required")
                topic_id = self._value_as_str(args.get("topic_id"))
                destination = self._value_as_str(args.get("destination"))
                sent = self._send_message(content, topic_id, destination)
                payload = {
                    "sent": bool(sent),
                    "content": content,
                    "topic_id": topic_id,
                    "destination": destination,
                }
                return payload, "mission.message.sent", payload
            if command_type == "topic.list":
                topics = [topic.to_dict() for topic in self._api.list_topics()]
                payload = {"topics": topics}
                return payload, "mission.topic.listed", payload
            if command_type == "topic.create":
                topic = self._build_topic_from_args(args)
                created = self._api.create_topic(topic)
                payload = created.to_dict()
                return payload, "mission.topic.created", payload
            if command_type == "topic.patch":
                topic_id = self._require_topic_id(args)
                topic = self._api.patch_topic(
                    topic_id,
                    topic_name=args.get("topic_name"),
                    topic_path=args.get("topic_path"),
                    topic_description=args.get("topic_description"),
                )
                payload = topic.to_dict()
                return payload, "mission.topic.updated", payload
            if command_type == "topic.delete":
                topic_id = self._require_topic_id(args)
                topic = self._api.delete_topic(topic_id)
                payload = topic.to_dict()
                return payload, "mission.topic.deleted", payload
            if command_type == "topic.subscribe":
                topic_id = self._require_topic_id(args)
                destination = self._value_as_str(args.get("destination")) or source_identity
                subscriber = self._api.subscribe_topic(
                    topic_id,
                    destination,
                    reject_tests=self._value_as_int(args.get("reject_tests")),
                    metadata=args.get("metadata") if isinstance(args.get("metadata"), dict) else None,
                )
                payload = subscriber.to_dict()
                return payload, "mission.topic.subscribed", payload
            if command_type == "mission.marker.list":
                service = self._require_marker_service()
                markers = [marker.to_dict() for marker in service.list_markers()]
                payload = {"markers": markers}
                return payload, "mission.marker.listed", payload
            if command_type == "mission.marker.create":
                service = self._require_marker_service()
                lat = self._required_float(args.get("lat"), field_name="lat")
                lon = self._required_float(args.get("lon"), field_name="lon")
                marker = service.create_marker(
                    name=self._value_as_str(args.get("name")),
                    marker_type=self._value_as_str(args.get("marker_type")) or "marker",
                    symbol=self._value_as_str(args.get("symbol")) or "marker",
                    category=self._value_as_str(args.get("category")) or "marker",
                    lat=lat,
                    lon=lon,
                    origin_rch=self._hub_identity_resolver() or "",
                    notes=self._value_as_str(args.get("notes")),
                    ttl_seconds=self._value_as_int(args.get("ttl_seconds")),
                )
                payload = marker.to_dict()
                return payload, "mission.marker.created", payload
            if command_type == "mission.marker.position.patch":
                service = self._require_marker_service()
                marker_hash = self._value_as_str(args.get("object_destination_hash"))
                if not marker_hash:
                    raise MissionCommandError(
                        "invalid_payload", "object_destination_hash is required"
                    )
                lat = self._required_float(args.get("lat"), field_name="lat")
                lon = self._required_float(args.get("lon"), field_name="lon")
                updated = service.update_marker_position(marker_hash, lat=lat, lon=lon)
                payload = updated.marker.to_dict()
                return payload, "mission.marker.position.updated", payload
            if command_type == "mission.zone.list":
                service = self._require_zone_service()
                zones = [zone.to_dict() for zone in service.list_zones()]
                payload = {"zones": zones}
                return payload, "mission.zone.listed", payload
            if command_type == "mission.zone.create":
                service = self._require_zone_service()
                name = self._value_as_str(args.get("name")) or "Zone"
                points = self._coerce_zone_points(args.get("points"))
                zone = service.create_zone(name=name, points=points)
                payload = zone.to_dict()
                return payload, "mission.zone.created", payload
            if command_type == "mission.zone.patch":
                service = self._require_zone_service()
                zone_id = self._value_as_str(args.get("zone_id"))
                if not zone_id:
                    raise MissionCommandError("invalid_payload", "zone_id is required")
                points = None
                if "points" in args:
                    points = self._coerce_zone_points(args.get("points"))
                result = service.update_zone(
                    zone_id,
                    name=self._value_as_str(args.get("name")),
                    points=points,
                )
                payload = result.zone.to_dict()
                return payload, "mission.zone.updated", payload
            if command_type == "mission.zone.delete":
                service = self._require_zone_service()
                zone_id = self._value_as_str(args.get("zone_id"))
                if not zone_id:
                    raise MissionCommandError("invalid_payload", "zone_id is required")
                zone = service.delete_zone(zone_id)
                payload = zone.to_dict()
                return payload, "mission.zone.deleted", payload
            if command_type == "mission.registry.mission.upsert":
                domain = self._require_domain_service()
                updated = domain.upsert_mission(args)
                return updated, "mission.registry.mission.upserted", updated
            if command_type == "mission.registry.mission.get":
                domain = self._require_domain_service()
                mission_uid = self._value_as_str(args.get("mission_uid"))
                if not mission_uid:
                    raise MissionCommandError("invalid_payload", "mission_uid is required")
                expand_values = self._expand_values(args.get("expand"))
                expand_topic = bool(args.get("expand_topic")) or "topic" in expand_values or "all" in expand_values
                mission = domain.get_mission(
                    mission_uid,
                    expand_topic=expand_topic,
                    expand=expand_values,
                )
                return mission, "mission.registry.mission.retrieved", mission
            if command_type == "mission.registry.mission.list":
                domain = self._require_domain_service()
                expand_values = self._expand_values(args.get("expand"))
                expand_topic = bool(args.get("expand_topic")) or "topic" in expand_values or "all" in expand_values
                missions = domain.list_missions(
                    expand_topic=expand_topic,
                    expand=expand_values,
                )
                payload = {"missions": missions}
                return payload, "mission.registry.mission.listed", payload
            if command_type == "mission.registry.mission.patch":
                domain = self._require_domain_service()
                mission_uid = self._value_as_str(args.get("mission_uid"))
                if not mission_uid:
                    raise MissionCommandError("invalid_payload", "mission_uid is required")
                patch = args.get("patch")
                resolved_patch = patch if isinstance(patch, dict) else {
                    key: value for key, value in args.items() if key != "mission_uid"
                }
                updated = domain.patch_mission(mission_uid, resolved_patch)
                return updated, "mission.registry.mission.updated", updated
            if command_type == "mission.registry.mission.delete":
                domain = self._require_domain_service()
                mission_uid = self._value_as_str(args.get("mission_uid"))
                if not mission_uid:
                    raise MissionCommandError("invalid_payload", "mission_uid is required")
                deleted = domain.delete_mission(mission_uid)
                return deleted, "mission.registry.mission.deleted", deleted
            if command_type == "mission.registry.mission.parent.set":
                domain = self._require_domain_service()
                mission_uid = self._value_as_str(args.get("mission_uid"))
                if not mission_uid:
                    raise MissionCommandError("invalid_payload", "mission_uid is required")
                parent_uid = self._value_as_str(args.get("parent_uid"))
                updated = domain.set_mission_parent(mission_uid, parent_uid=parent_uid)
                return updated, "mission.registry.mission.parent.updated", updated
            if command_type == "mission.registry.mission_change.upsert":
                domain = self._require_domain_service()
                updated = domain.upsert_mission_change(args)
                return updated, "mission.registry.mission_change.upserted", updated
            if command_type == "mission.registry.mission_change.list":
                domain = self._require_domain_service()
                mission_uid = self._value_as_str(args.get("mission_uid"))
                payload = {"mission_changes": domain.list_mission_changes(mission_uid=mission_uid)}
                return payload, "mission.registry.mission_change.listed", payload
            if command_type == "mission.registry.log_entry.upsert":
                domain = self._require_domain_service()
                updated = domain.upsert_log_entry(args)
                return updated, "mission.registry.log_entry.upserted", updated
            if command_type == "mission.registry.log_entry.list":
                domain = self._require_domain_service()
                mission_uid = self._value_as_str(args.get("mission_uid"))
                marker_ref = self._value_as_str(args.get("marker_ref"))
                payload = {
                    "log_entries": domain.list_log_entries(
                        mission_uid=mission_uid,
                        marker_ref=marker_ref,
                    )
                }
                return payload, "mission.registry.log_entry.listed", payload
            if command_type == "mission.registry.team.upsert":
                domain = self._require_domain_service()
                updated = domain.upsert_team(args)
                return updated, "mission.registry.team.upserted", updated
            if command_type == "mission.registry.team.get":
                domain = self._require_domain_service()
                team_uid = self._value_as_str(args.get("team_uid"))
                if not team_uid:
                    raise MissionCommandError("invalid_payload", "team_uid is required")
                team = domain.get_team(team_uid)
                return team, "mission.registry.team.retrieved", team
            if command_type == "mission.registry.team.list":
                domain = self._require_domain_service()
                mission_uid = self._value_as_str(args.get("mission_uid"))
                payload = {"teams": domain.list_teams(mission_uid=mission_uid)}
                return payload, "mission.registry.team.listed", payload
            if command_type == "mission.registry.team.delete":
                domain = self._require_domain_service()
                team_uid = self._value_as_str(args.get("team_uid"))
                if not team_uid:
                    raise MissionCommandError("invalid_payload", "team_uid is required")
                deleted = domain.delete_team(team_uid)
                return deleted, "mission.registry.team.deleted", deleted
            if command_type == "mission.registry.team.mission.link":
                domain = self._require_domain_service()
                team_uid = self._value_as_str(args.get("team_uid"))
                mission_uid = self._value_as_str(args.get("mission_uid"))
                if not team_uid or not mission_uid:
                    raise MissionCommandError(
                        "invalid_payload", "team_uid and mission_uid are required"
                    )
                updated = domain.link_team_mission(team_uid, mission_uid)
                return updated, "mission.registry.team.mission.linked", updated
            if command_type == "mission.registry.team.mission.unlink":
                domain = self._require_domain_service()
                team_uid = self._value_as_str(args.get("team_uid"))
                mission_uid = self._value_as_str(args.get("mission_uid"))
                if not team_uid or not mission_uid:
                    raise MissionCommandError(
                        "invalid_payload", "team_uid and mission_uid are required"
                    )
                updated = domain.unlink_team_mission(team_uid, mission_uid)
                return updated, "mission.registry.team.mission.unlinked", updated
            if command_type == "mission.registry.mission.zone.link":
                domain = self._require_domain_service()
                mission_uid = self._value_as_str(args.get("mission_uid"))
                zone_id = self._value_as_str(args.get("zone_id"))
                if not mission_uid or not zone_id:
                    raise MissionCommandError(
                        "invalid_payload", "mission_uid and zone_id are required"
                    )
                updated = domain.link_mission_zone(mission_uid, zone_id)
                return updated, "mission.registry.mission.zone.linked", updated
            if command_type == "mission.registry.mission.zone.unlink":
                domain = self._require_domain_service()
                mission_uid = self._value_as_str(args.get("mission_uid"))
                zone_id = self._value_as_str(args.get("zone_id"))
                if not mission_uid or not zone_id:
                    raise MissionCommandError(
                        "invalid_payload", "mission_uid and zone_id are required"
                    )
                updated = domain.unlink_mission_zone(mission_uid, zone_id)
                return updated, "mission.registry.mission.zone.unlinked", updated
            if command_type == "mission.registry.mission.rde.set":
                domain = self._require_domain_service()
                mission_uid = self._value_as_str(args.get("mission_uid"))
                role = self._value_as_str(args.get("role"))
                if not mission_uid or not role:
                    raise MissionCommandError(
                        "invalid_payload", "mission_uid and role are required"
                    )
                updated = domain.upsert_mission_rde(mission_uid, role)
                return updated, "mission.registry.mission.rde.updated", updated
            if command_type == "mission.registry.team_member.upsert":
                domain = self._require_domain_service()
                updated = domain.upsert_team_member(args)
                return updated, "mission.registry.team_member.upserted", updated
            if command_type == "mission.registry.team_member.get":
                domain = self._require_domain_service()
                team_member_uid = self._value_as_str(args.get("team_member_uid"))
                if not team_member_uid:
                    raise MissionCommandError(
                        "invalid_payload", "team_member_uid is required"
                    )
                member = domain.get_team_member(team_member_uid)
                return member, "mission.registry.team_member.retrieved", member
            if command_type == "mission.registry.team_member.list":
                domain = self._require_domain_service()
                team_uid = self._value_as_str(args.get("team_uid"))
                payload = {"team_members": domain.list_team_members(team_uid=team_uid)}
                return payload, "mission.registry.team_member.listed", payload
            if command_type == "mission.registry.team_member.delete":
                domain = self._require_domain_service()
                team_member_uid = self._value_as_str(args.get("team_member_uid"))
                if not team_member_uid:
                    raise MissionCommandError(
                        "invalid_payload", "team_member_uid is required"
                    )
                deleted = domain.delete_team_member(team_member_uid)
                return deleted, "mission.registry.team_member.deleted", deleted
            if command_type == "mission.registry.team_member.client.link":
                domain = self._require_domain_service()
                team_member_uid = self._value_as_str(args.get("team_member_uid"))
                client_identity = self._value_as_str(args.get("client_identity"))
                if not team_member_uid or not client_identity:
                    raise MissionCommandError(
                        "invalid_payload",
                        "team_member_uid and client_identity are required",
                    )
                updated = domain.link_team_member_client(team_member_uid, client_identity)
                return updated, "mission.registry.team_member.client.linked", updated
            if command_type == "mission.registry.team_member.client.unlink":
                domain = self._require_domain_service()
                team_member_uid = self._value_as_str(args.get("team_member_uid"))
                client_identity = self._value_as_str(args.get("client_identity"))
                if not team_member_uid or not client_identity:
                    raise MissionCommandError(
                        "invalid_payload",
                        "team_member_uid and client_identity are required",
                    )
                updated = domain.unlink_team_member_client(team_member_uid, client_identity)
                return updated, "mission.registry.team_member.client.unlinked", updated
            if command_type == "mission.registry.asset.upsert":
                domain = self._require_domain_service()
                updated = domain.upsert_asset(args)
                return updated, "mission.registry.asset.upserted", updated
            if command_type == "mission.registry.asset.get":
                domain = self._require_domain_service()
                asset_uid = self._value_as_str(args.get("asset_uid"))
                if not asset_uid:
                    raise MissionCommandError("invalid_payload", "asset_uid is required")
                asset = domain.get_asset(asset_uid)
                return asset, "mission.registry.asset.retrieved", asset
            if command_type == "mission.registry.asset.list":
                domain = self._require_domain_service()
                team_member_uid = self._value_as_str(args.get("team_member_uid"))
                payload = {"assets": domain.list_assets(team_member_uid=team_member_uid)}
                return payload, "mission.registry.asset.listed", payload
            if command_type == "mission.registry.asset.delete":
                domain = self._require_domain_service()
                asset_uid = self._value_as_str(args.get("asset_uid"))
                if not asset_uid:
                    raise MissionCommandError("invalid_payload", "asset_uid is required")
                deleted = domain.delete_asset(asset_uid)
                return deleted, "mission.registry.asset.deleted", deleted
            if command_type == "mission.registry.skill.upsert":
                domain = self._require_domain_service()
                updated = domain.upsert_skill(args)
                return updated, "mission.registry.skill.upserted", updated
            if command_type == "mission.registry.skill.list":
                domain = self._require_domain_service()
                payload = {"skills": domain.list_skills()}
                return payload, "mission.registry.skill.listed", payload
            if command_type == "mission.registry.team_member_skill.upsert":
                domain = self._require_domain_service()
                updated = domain.upsert_team_member_skill(args)
                return updated, "mission.registry.team_member_skill.upserted", updated
            if command_type == "mission.registry.team_member_skill.list":
                domain = self._require_domain_service()
                team_member_identity = self._value_as_str(
                    args.get("team_member_rns_identity")
                )
                payload = {
                    "team_member_skills": domain.list_team_member_skills(
                        team_member_rns_identity=team_member_identity
                    )
                }
                return payload, "mission.registry.team_member_skill.listed", payload
            if command_type == "mission.registry.task_skill_requirement.upsert":
                domain = self._require_domain_service()
                updated = domain.upsert_task_skill_requirement(args)
                return updated, "mission.registry.task_skill_requirement.upserted", updated
            if command_type == "mission.registry.task_skill_requirement.list":
                domain = self._require_domain_service()
                task_uid = self._value_as_str(args.get("task_uid"))
                payload = {
                    "task_skill_requirements": domain.list_task_skill_requirements(
                        task_uid=task_uid
                    )
                }
                return payload, "mission.registry.task_skill_requirement.listed", payload
            if command_type == "mission.registry.assignment.upsert":
                domain = self._require_domain_service()
                updated = domain.upsert_assignment(args)
                return updated, "mission.registry.assignment.upserted", updated
            if command_type == "mission.registry.assignment.list":
                domain = self._require_domain_service()
                mission_uid = self._value_as_str(args.get("mission_uid"))
                task_uid = self._value_as_str(args.get("task_uid"))
                payload = {
                    "assignments": domain.list_assignments(
                        mission_uid=mission_uid,
                        task_uid=task_uid,
                    )
                }
                return payload, "mission.registry.assignment.listed", payload
            if command_type == "mission.registry.assignment.asset.set":
                domain = self._require_domain_service()
                assignment_uid = self._value_as_str(args.get("assignment_uid"))
                assets = args.get("assets")
                if not assignment_uid or not isinstance(assets, list):
                    raise MissionCommandError(
                        "invalid_payload", "assignment_uid and assets[] are required"
                    )
                updated = domain.set_assignment_assets(
                    assignment_uid,
                    [str(item) for item in assets],
                )
                return updated, "mission.registry.assignment.asset.set", updated
            if command_type == "mission.registry.assignment.asset.link":
                domain = self._require_domain_service()
                assignment_uid = self._value_as_str(args.get("assignment_uid"))
                asset_uid = self._value_as_str(args.get("asset_uid"))
                if not assignment_uid or not asset_uid:
                    raise MissionCommandError(
                        "invalid_payload", "assignment_uid and asset_uid are required"
                    )
                updated = domain.link_assignment_asset(assignment_uid, asset_uid)
                return updated, "mission.registry.assignment.asset.linked", updated
            if command_type == "mission.registry.assignment.asset.unlink":
                domain = self._require_domain_service()
                assignment_uid = self._value_as_str(args.get("assignment_uid"))
                asset_uid = self._value_as_str(args.get("asset_uid"))
                if not assignment_uid or not asset_uid:
                    raise MissionCommandError(
                        "invalid_payload", "assignment_uid and asset_uid are required"
                    )
                updated = domain.unlink_assignment_asset(assignment_uid, asset_uid)
                return updated, "mission.registry.assignment.asset.unlinked", updated
        except (KeyError, ValueError) as exc:
            raise MissionCommandError("invalid_payload", str(exc)) from exc

        raise MissionCommandError(
            "unsupported_operation",
            f"Unsupported mission operation '{command_type}'",
        )

    def _response_from_results(
        self,
        results_payload: dict[str, Any],
        *,
        group: object | None,
        event: dict[str, Any] | None = None,
    ) -> MissionSyncResponse:
        fields: dict[int | str, object] = {self._field_results: results_payload}
        if group is not None:
            fields[self._field_group] = group
        if event is not None:
            fields[self._field_event] = event
        return MissionSyncResponse(content="mission-sync", fields=fields)

    def _build_event_envelope(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
        source_identity: str,
        topics: list[str] | None,
    ) -> dict[str, Any]:
        return {
            "event_id": uuid.uuid4().hex,
            "source": {"rns_identity": source_identity},
            "timestamp": _utcnow().isoformat(),
            "event_type": event_type,
            "topics": list(topics or []),
            "payload": payload,
        }

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

    def _record_event(self, event_type: str, metadata: dict[str, Any]) -> None:
        if self._event_log is None:
            return
        self._event_log.add_event(
            event_type,
            event_type.replace("_", " "),
            metadata=metadata,
        )
