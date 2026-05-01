"""Mission command execution helpers."""

from __future__ import annotations

from typing import Any

from reticulum_telemetry_hub.mission_sync.eam_commands import EmergencyActionMessageCommandError
from reticulum_telemetry_hub.mission_sync.eam_commands import execute_eam_command
from reticulum_telemetry_hub.mission_sync.router_errors import MissionCommandError
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandEnvelope


class MissionCommandExecutionMixin:
    """Execute validated mission-sync commands."""

    def _execute_command(
        self, envelope: MissionCommandEnvelope, *, source_identity: str
    ) -> tuple[dict[str, Any], str, dict[str, Any]]:
        command_type = envelope.command_type
        args = dict(envelope.args or {})
        try:
            if command_type == "mission.join":
                identity = str(source_identity)
                joined = self._api.join(identity)
                payload = {"identity": identity, "joined": bool(joined)}
                return payload, "mission.joined", payload
            if command_type == "mission.leave":
                identity = str(source_identity)
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
                payload = dict(args)
                payload.setdefault("source_identity", source_identity)
                updated = domain.upsert_log_entry(payload)
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
            if command_type.startswith("mission.registry.eam."):
                status_service = self._require_emergency_action_message_service()
                try:
                    return execute_eam_command(
                        command_type,
                        args,
                        status_service=status_service,
                    )
                except EmergencyActionMessageCommandError as exc:
                    raise MissionCommandError(exc.reason_code, exc.reason) from exc
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

