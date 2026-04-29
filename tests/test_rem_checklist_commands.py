from __future__ import annotations

import LXMF

from reticulum_telemetry_hub.reticulum_server.rem_checklist_commands import (
    build_rem_checklist_command_message,
)
from reticulum_telemetry_hub.reticulum_server.rem_checklist_commands import (
    checklist_create_args,
)
from reticulum_telemetry_hub.reticulum_server.rem_checklist_commands import (
    row_add_args,
)


def test_build_rem_checklist_command_message_uses_rem_field_contract() -> None:
    message = build_rem_checklist_command_message(
        command_type="checklist.task.cell.set",
        args={
            "mission_uid": "mission-1",
            "checklist_uid": "checklist-1",
            "task_uid": "task-1",
            "column_uid": "column-1",
            "value": "Inspect area",
        },
        source_identity="hub-1",
        source_display_name="RCH",
        command_id="cmd-1",
        correlation_id="corr-1",
        timestamp="2026-04-02T12:00:00Z",
    )

    assert message.body == "Checklist checklist.task.cell.set checklist-1"
    command = message.fields[LXMF.FIELD_COMMANDS][0]
    assert command["command_id"] == "cmd-1"
    assert command["correlation_id"] == "corr-1"
    assert command["command_type"] == "checklist.task.cell.set"
    assert command["source"] == {"rns_identity": "hub-1", "display_name": "RCH"}
    assert command["timestamp"] == "2026-04-02T12:00:00Z"
    assert command["topics"] == ["mission-1", "checklist-1"]
    assert command["args"]["value"] == "Inspect area"


def test_checklist_create_args_match_rem_required_shape() -> None:
    args = checklist_create_args(
        {
            "uid": "checklist-1",
            "mission_id": "mission-1",
            "template_uid": None,
            "name": "Shared ExCheck",
            "description": "Shared to REM",
            "start_time": "2026-04-02T12:00:00Z",
            "created_at": "2026-04-02T12:01:00Z",
            "created_by_team_member_rns_identity": "hub-1",
            "columns": [{"column_uid": "col-1", "column_name": "Task"}],
            "tasks": [{"task_uid": "task-1"}],
        }
    )

    assert args["checklist_uid"] == "checklist-1"
    assert args["mission_uid"] == "mission-1"
    assert args["template_uid"] == "rch:checklist-1:template"
    assert args["columns"] == [{"column_uid": "col-1", "column_name": "Task"}]
    assert args["participant_rns_identities"] == ["hub-1"]
    assert args["total_tasks"] == 1


def test_row_add_args_preserve_rem_task_identity_and_metadata() -> None:
    args = row_add_args(
        {
            "checklist_uid": "checklist-1",
            "task_uid": "task-1",
            "number": 2,
            "due_relative_minutes": 15,
            "due_dtg": "2026-04-02T12:15:00Z",
            "notes": "Bring med kit",
            "legacy_value": "Inspect area",
        }
    )

    assert args == {
        "checklist_uid": "checklist-1",
        "task_uid": "task-1",
        "number": 2,
        "due_relative_minutes": 15,
        "due_dtg": "2026-04-02T12:15:00Z",
        "notes": "Bring med kit",
        "legacy_value": "Inspect area",
    }
