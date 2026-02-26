from __future__ import annotations

from pathlib import Path

import yaml

from reticulum_telemetry_hub.checklist_sync.capabilities import CHECKLIST_COMMAND_CAPABILITIES
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandEnvelope


def _extract_command_messages(spec_path: Path) -> dict[str, list[str]]:
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    messages = spec.get("components", {}).get("messages", {})

    commands: dict[str, list[str]] = {}
    for message in messages.values():
        if not isinstance(message, dict):
            continue
        payload = message.get("payload")
        if not isinstance(payload, dict):
            continue
        all_of = payload.get("allOf")
        if not isinstance(all_of, list):
            continue
        command_type = None
        for item in all_of:
            if not isinstance(item, dict):
                continue
            cmd = (
                item.get("properties", {})
                .get("command_type", {})
                .get("const")
            )
            if isinstance(cmd, str) and cmd:
                command_type = cmd
                break
        if command_type:
            capabilities = message.get("x-capability-required") or []
            commands[command_type] = [str(value) for value in capabilities]

    return commands


def test_checklist_asyncapi_commands_match_router_capabilities() -> None:
    commands = _extract_command_messages(
        Path("docs/architecture/asyncapi/r3akt-checklist-lxmf.asyncapi.yaml")
    )

    assert set(commands) == set(CHECKLIST_COMMAND_CAPABILITIES)
    for command_type, capability in CHECKLIST_COMMAND_CAPABILITIES.items():
        assert commands[command_type] == [capability]


def test_checklist_asyncapi_result_status_constants() -> None:
    spec = yaml.safe_load(
        Path("docs/architecture/asyncapi/r3akt-checklist-lxmf.asyncapi.yaml").read_text(
            encoding="utf-8"
        )
    )
    messages = spec["components"]["messages"]

    accepted_status = messages["CommandAccepted"]["payload"]["properties"]["status"]["const"]
    rejected_status = messages["CommandRejected"]["payload"]["properties"]["status"]["const"]
    result_status = messages["CommandResult"]["payload"]["properties"]["status"]["const"]

    assert accepted_status == "accepted"
    assert rejected_status == "rejected"
    assert result_status == "result"


def test_checklist_envelope_model_aligns_with_contract_shape() -> None:
    envelope = MissionCommandEnvelope.model_validate(
        {
            "command_id": "cmd-1",
            "source": {"rns_identity": "peer-a"},
            "timestamp": "2026-01-01T00:00:00Z",
            "command_type": "checklist.create.offline",
            "args": {"name": "Checklist", "origin_type": "BLANK_TEMPLATE"},
            "correlation_id": "corr-1",
            "topics": ["checklist"],
        }
    )

    assert envelope.command_type == "checklist.create.offline"
    assert envelope.source.rns_identity == "peer-a"
    assert envelope.command_id == "cmd-1"
