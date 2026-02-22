"""Mission-sync capability requirements."""

from __future__ import annotations


MISSION_COMMAND_CAPABILITIES: dict[str, str] = {
    "mission.join": "mission.join",
    "mission.leave": "mission.leave",
    "mission.events.list": "mission.audit.read",
    "mission.message.send": "mission.message.send",
    "topic.list": "topic.read",
    "topic.create": "topic.create",
    "topic.patch": "topic.write",
    "topic.delete": "topic.delete",
    "topic.subscribe": "topic.subscribe",
    "mission.marker.list": "mission.content.read",
    "mission.marker.create": "mission.content.write",
    "mission.marker.position.patch": "mission.content.write",
    "mission.zone.list": "mission.zone.read",
    "mission.zone.create": "mission.zone.write",
    "mission.zone.patch": "mission.zone.write",
    "mission.zone.delete": "mission.zone.delete",
    "mission.registry.mission.patch": "mission.registry.mission.write",
    "mission.registry.mission.delete": "mission.registry.mission.write",
    "mission.registry.mission.parent.set": "mission.registry.mission.write",
    "mission.registry.mission.zone.link": "mission.zone.write",
    "mission.registry.mission.zone.unlink": "mission.zone.write",
    "mission.registry.mission.rde.set": "mission.registry.mission.write",
    "mission.registry.team_member.client.link": "mission.registry.team.write",
    "mission.registry.team_member.client.unlink": "mission.registry.team.write",
    "mission.registry.assignment.asset.link": "mission.registry.assignment.write",
    "mission.registry.assignment.asset.unlink": "mission.registry.assignment.write",
}
