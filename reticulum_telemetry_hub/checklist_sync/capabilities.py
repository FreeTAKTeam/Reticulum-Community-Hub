"""Checklist-sync capability requirements."""

from __future__ import annotations


CHECKLIST_COMMAND_CAPABILITIES: dict[str, str] = {
    "checklist.template.list": "checklist.template.read",
    "checklist.template.create": "checklist.template.write",
    "checklist.template.update": "checklist.template.write",
    "checklist.template.clone": "checklist.template.write",
    "checklist.template.delete": "checklist.template.delete",
    "checklist.list.active": "checklist.read",
    "checklist.create.online": "checklist.write",
    "checklist.create.offline": "checklist.write",
    "checklist.import.csv": "checklist.write",
    "checklist.join": "checklist.join",
    "checklist.get": "checklist.read",
    "checklist.upload": "checklist.upload",
    "checklist.feed.publish": "checklist.feed.publish",
    "checklist.task.status.set": "checklist.write",
    "checklist.task.row.add": "checklist.write",
    "checklist.task.row.delete": "checklist.write",
    "checklist.task.row.style.set": "checklist.write",
    "checklist.task.cell.set": "checklist.write",
}
