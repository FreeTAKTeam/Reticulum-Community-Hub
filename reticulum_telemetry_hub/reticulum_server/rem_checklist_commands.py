"""REM-compatible checklist command message builders."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import LXMF

from reticulum_telemetry_hub.message_delivery import utc_now_rfc3339


@dataclass(frozen=True)
class RemChecklistCommandMessage:
    """Outbound REM checklist command body and LXMF fields."""

    body: str
    fields: dict[int | str, object]


def _clean_optional_args(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _topic_values(args: dict[str, Any]) -> list[str]:
    topics: list[str] = []
    for key in ("mission_uid", "mission_id", "checklist_uid", "uid"):
        value = str(args.get(key) or "").strip()
        if value and value not in topics:
            topics.append(value)
    return topics


def _command_subject(args: dict[str, Any]) -> str:
    for key in ("checklist_uid", "task_uid", "mission_uid", "mission_id"):
        value = str(args.get(key) or "").strip()
        if value:
            return value
    return "update"


def build_rem_checklist_command_message(
    *,
    command_type: str,
    args: dict[str, Any],
    source_identity: str,
    source_display_name: str | None = None,
    command_id: str | None = None,
    correlation_id: str | None = None,
    timestamp: str | None = None,
) -> RemChecklistCommandMessage:
    """Build one REM-compatible checklist command LXMF message."""

    resolved_command_id = str(command_id or uuid.uuid4().hex)
    resolved_correlation_id = str(correlation_id or resolved_command_id)
    source: dict[str, str] = {"rns_identity": str(source_identity or "").strip()}
    display_name = str(source_display_name or "").strip()
    if display_name:
        source["display_name"] = display_name
    envelope = {
        "command_id": resolved_command_id,
        "correlation_id": resolved_correlation_id,
        "command_type": command_type,
        "source": source,
        "timestamp": timestamp or utc_now_rfc3339(),
        "topics": _topic_values(args),
        "args": _clean_optional_args(dict(args)),
    }
    body = f"Checklist {command_type} {_command_subject(args)}"
    return RemChecklistCommandMessage(
        body=body,
        fields={LXMF.FIELD_COMMANDS: [envelope]},
    )


def checklist_create_args(
    checklist: dict[str, Any],
    *,
    participant_rns_identities: list[str] | None = None,
) -> dict[str, Any]:
    """Return REM-required args for ``checklist.create.online``."""

    checklist_uid = str(checklist.get("uid") or checklist.get("checklist_uid") or "").strip()
    mission_uid = str(
        checklist.get("mission_uid") or checklist.get("mission_id") or ""
    ).strip()
    template_uid = str(checklist.get("template_uid") or "").strip()
    if not template_uid:
        template_uid = f"rch:{checklist_uid}:template"
    created_by = str(checklist.get("created_by_team_member_rns_identity") or "").strip()
    participants: list[str] = []
    for value in (
        checklist.get("participant_rns_identities")
        or participant_rns_identities
        or []
    ):
        normalized = str(value or "").strip()
        if normalized and normalized not in participants:
            participants.append(normalized)
    if created_by and created_by not in participants:
        participants.append(created_by)
    tasks = list(checklist.get("tasks") or [])
    return _clean_optional_args(
        {
            "checklist_uid": checklist_uid,
            "mission_uid": mission_uid,
            "template_uid": template_uid,
            "name": str(checklist.get("name") or "").strip(),
            "description": str(checklist.get("description") or ""),
            "start_time": checklist.get("start_time"),
            "columns": list(checklist.get("columns") or []),
            "participant_rns_identities": participants,
            "total_tasks": len(tasks),
            "created_at": checklist.get("created_at"),
            "created_by_team_member_rns_identity": created_by or None,
            "uploaded_at": checklist.get("uploaded_at"),
        }
    )


def row_add_args(task: dict[str, Any]) -> dict[str, Any]:
    """Return REM args for ``checklist.task.row.add``."""

    return _clean_optional_args(
        {
            "checklist_uid": task.get("checklist_uid"),
            "task_uid": task.get("task_uid"),
            "number": task.get("number"),
            "due_relative_minutes": task.get("due_relative_minutes"),
            "due_dtg": task.get("due_dtg"),
            "notes": task.get("notes"),
            "legacy_value": task.get("legacy_value"),
            "changed_by_team_member_rns_identity": task.get(
                "changed_by_team_member_rns_identity"
            ),
        }
    )


def row_delete_args(task: dict[str, Any]) -> dict[str, Any]:
    """Return REM args for ``checklist.task.row.delete``."""

    return _clean_optional_args(
        {
            "checklist_uid": task.get("checklist_uid"),
            "task_uid": task.get("task_uid"),
        }
    )


def row_style_args(task: dict[str, Any]) -> dict[str, Any]:
    """Return REM args for ``checklist.task.row.style.set``."""

    return _clean_optional_args(
        {
            "checklist_uid": task.get("checklist_uid"),
            "task_uid": task.get("task_uid"),
            "row_background_color": task.get("row_background_color"),
            "line_break_enabled": task.get("line_break_enabled"),
            "changed_by_team_member_rns_identity": task.get(
                "changed_by_team_member_rns_identity"
            ),
        }
    )


def cell_set_args(task: dict[str, Any]) -> dict[str, Any] | None:
    """Return REM args for ``checklist.task.cell.set`` when a string value exists."""

    value = task.get("value")
    if value is None:
        return None
    return _clean_optional_args(
        {
            "checklist_uid": task.get("checklist_uid"),
            "task_uid": task.get("task_uid"),
            "column_uid": task.get("column_uid"),
            "value": str(value),
            "updated_by_team_member_rns_identity": task.get(
                "updated_by_team_member_rns_identity"
            ),
        }
    )


def status_set_args(task: dict[str, Any]) -> dict[str, Any]:
    """Return REM args for ``checklist.task.status.set``."""

    user_status = str(task.get("user_status") or "").strip().upper()
    if not user_status:
        current_status = str(task.get("current_status") or "").strip().upper()
        user_status = "COMPLETE" if current_status.startswith("COMPLETE") else "PENDING"
    return _clean_optional_args(
        {
            "checklist_uid": task.get("checklist_uid"),
            "task_uid": task.get("task_uid"),
            "user_status": user_status,
            "changed_by_team_member_rns_identity": task.get(
                "changed_by_team_member_rns_identity"
            ),
        }
    )


def _with_mission_uid(args: dict[str, Any], mission_uid: str | None) -> dict[str, Any]:
    if mission_uid and "mission_uid" not in args:
        args = {**args, "mission_uid": mission_uid}
    return args


def _command_message(
    *,
    command_type: str,
    args: dict[str, Any],
    source_identity: str,
    source_display_name: str | None,
) -> RemChecklistCommandMessage:
    return build_rem_checklist_command_message(
        command_type=command_type,
        args=args,
        source_identity=source_identity,
        source_display_name=source_display_name,
    )


def initial_checklist_command_messages(
    checklist: dict[str, Any],
    *,
    source_identity: str,
    source_display_name: str | None = None,
    participant_rns_identities: list[str] | None = None,
) -> list[RemChecklistCommandMessage]:
    """Return REM create plus per-row initial synchronization commands."""

    messages = [
        _command_message(
            command_type="checklist.create.online",
            args=checklist_create_args(
                checklist,
                participant_rns_identities=participant_rns_identities,
            ),
            source_identity=source_identity,
            source_display_name=source_display_name,
        )
    ]
    checklist_uid = str(checklist.get("uid") or checklist.get("checklist_uid") or "").strip()
    mission_uid = str(checklist.get("mission_uid") or checklist.get("mission_id") or "").strip()
    for task in checklist.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        task_payload = {"checklist_uid": checklist_uid, **task}
        messages.append(
            _command_message(
                command_type="checklist.task.row.add",
                args=_with_mission_uid(row_add_args(task_payload), mission_uid),
                source_identity=source_identity,
                source_display_name=source_display_name,
            )
        )
        for cell in task.get("cells") or []:
            if not isinstance(cell, dict):
                continue
            cell_payload = {
                "checklist_uid": checklist_uid,
                "task_uid": task.get("task_uid"),
                **cell,
            }
            args = cell_set_args(cell_payload)
            if args is None:
                continue
            messages.append(
                _command_message(
                    command_type="checklist.task.cell.set",
                    args=_with_mission_uid(args, mission_uid),
                    source_identity=source_identity,
                    source_display_name=source_display_name,
                )
            )
        if str(task.get("user_status") or "").strip().upper() == "COMPLETE":
            messages.append(
                _command_message(
                    command_type="checklist.task.status.set",
                    args=_with_mission_uid(status_set_args(task_payload), mission_uid),
                    source_identity=source_identity,
                    source_display_name=source_display_name,
                )
            )
        if task.get("row_background_color") is not None or bool(
            task.get("line_break_enabled")
        ):
            messages.append(
                _command_message(
                    command_type="checklist.task.row.style.set",
                    args=_with_mission_uid(row_style_args(task_payload), mission_uid),
                    source_identity=source_identity,
                    source_display_name=source_display_name,
                )
            )
    return messages


def checklist_command_messages_for_mission_change(
    mission_change: dict[str, Any],
    *,
    source_identity: str,
    source_display_name: str | None = None,
    participant_rns_identities: list[str] | None = None,
) -> list[RemChecklistCommandMessage]:
    """Map a checklist mission-change delta to REM checklist command messages."""

    delta = mission_change.get("delta")
    if not isinstance(delta, dict):
        return []
    source_event_type = str(
        delta.get("source_event_type") or mission_change.get("name") or ""
    ).strip()
    mission_uid = str(
        mission_change.get("mission_uid") or mission_change.get("mission_id") or ""
    ).strip()

    if source_event_type in {"mission.checklist.created", "mission.checklist.uploaded"}:
        messages: list[RemChecklistCommandMessage] = []
        for checklist in delta.get("checklists") or []:
            if isinstance(checklist, dict):
                messages.extend(
                    initial_checklist_command_messages(
                        checklist,
                        source_identity=source_identity,
                        source_display_name=source_display_name,
                        participant_rns_identities=participant_rns_identities,
                    )
                )
        return messages

    command_by_event = {
        "mission.checklist.task.row.added": ("checklist.task.row.add", row_add_args),
        "mission.checklist.task.row.deleted": (
            "checklist.task.row.delete",
            row_delete_args,
        ),
        "mission.checklist.task.row.style_set": (
            "checklist.task.row.style.set",
            row_style_args,
        ),
        "mission.checklist.task.status_set": (
            "checklist.task.status.set",
            status_set_args,
        ),
    }
    messages = []
    if source_event_type == "mission.checklist.task.cell_set":
        for task in delta.get("tasks") or []:
            if not isinstance(task, dict):
                continue
            args = cell_set_args(task)
            if args is None:
                continue
            messages.append(
                _command_message(
                    command_type="checklist.task.cell.set",
                    args=_with_mission_uid(args, mission_uid),
                    source_identity=source_identity,
                    source_display_name=source_display_name,
                )
            )
        return messages

    mapping = command_by_event.get(source_event_type)
    if mapping is None:
        return []
    command_type, builder = mapping
    for task in delta.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        messages.append(
            _command_message(
                command_type=command_type,
                args=_with_mission_uid(builder(task), mission_uid),
                source_identity=source_identity,
                source_display_name=source_display_name,
            )
        )
    return messages
