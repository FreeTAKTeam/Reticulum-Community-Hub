from __future__ import annotations

from pathlib import Path

import yaml

from reticulum_telemetry_hub.mission_sync.capabilities import MISSION_COMMAND_CAPABILITIES
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


def test_mission_asyncapi_commands_match_router_capabilities() -> None:
    commands = _extract_command_messages(
        Path("docs/architecture/asyncapi/r3akt-mission-sync-lxmf.asyncapi.yaml")
    )

    assert set(commands) == set(MISSION_COMMAND_CAPABILITIES)
    for command_type, capability in MISSION_COMMAND_CAPABILITIES.items():
        assert commands[command_type] == [capability]


def test_mission_asyncapi_result_status_constants() -> None:
    spec = yaml.safe_load(
        Path("docs/architecture/asyncapi/r3akt-mission-sync-lxmf.asyncapi.yaml").read_text(
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


def test_mission_envelope_model_aligns_with_contract_shape() -> None:
    envelope = MissionCommandEnvelope.model_validate(
        {
            "command_id": "cmd-1",
            "source": {"rns_identity": "peer-a"},
            "timestamp": "2026-01-01T00:00:00Z",
            "command_type": "mission.join",
            "args": {"identity": "peer-a"},
            "correlation_id": "corr-1",
            "topics": ["mission"],
        }
    )

    assert envelope.command_type == "mission.join"
    assert envelope.source.rns_identity == "peer-a"
    assert envelope.command_id == "cmd-1"
