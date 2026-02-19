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
}
