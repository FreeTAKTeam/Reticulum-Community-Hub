"""Tests for the optional Rust mission-sync bridge."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

from reticulum_telemetry_hub.config.models import HubRuntimeConfig
from reticulum_telemetry_hub.mission_sync.rust_bridge import DEFAULT_RUST_RUNTIME_DB_FILENAME
from reticulum_telemetry_hub.mission_sync.rust_bridge import RustMissionSyncBridge
from reticulum_telemetry_hub.mission_sync.rust_bridge import build_rust_bridge_from_runtime_config
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandEnvelope


def _command() -> MissionCommandEnvelope:
    return MissionCommandEnvelope.model_validate(
        {
            "command_id": "cmd-rust-bridge",
            "source": {"rns_identity": "ABCDEF", "display_name": "Field Agent"},
            "timestamp": "2026-05-03T12:00:00Z",
            "command_type": "topic.create",
            "args": {"topic_path": "mission-bridge"},
            "correlation_id": "corr-rust-bridge",
            "topics": ["mission-bridge"],
        }
    )


def test_rust_bridge_normalizes_field_keys_and_preserves_group() -> None:
    def runner(*args, **kwargs):  # type: ignore[no-untyped-def]
        request = json.loads(kwargs["input"])
        assert request["type"] == "mission_command"
        assert request["command"]["command_id"] == "cmd-rust-bridge"
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=json.dumps(
                {
                    "type": "mission_command",
                    "responses": [
                        {
                            "content": "mission-sync",
                            "fields": {
                                "10": {
                                    "command_id": "cmd-rust-bridge",
                                    "status": "accepted",
                                }
                            },
                        },
                        {
                            "content": "mission-sync",
                            "fields": {
                                "10": {
                                    "command_id": "cmd-rust-bridge",
                                    "status": "result",
                                    "result": {"topic_id": "mission-bridge"},
                                },
                                "13": {"event_type": "mission.topic.created"},
                            },
                        },
                    ],
                }
            ),
            stderr="",
        )

    bridge = RustMissionSyncBridge(
        binary_path="r3akt-rch-bridge",
        db_path="runtime.sqlite",
        field_results=10,
        field_event=13,
        field_group=4,
        runner=runner,
    )

    responses = bridge.handle_command(_command(), group="grp-1")

    assert responses[0].fields[10]["status"] == "accepted"
    assert responses[0].fields[4] == "grp-1"
    assert responses[1].fields[10]["status"] == "result"
    assert responses[1].fields[13]["event_type"] == "mission.topic.created"


def test_rust_bridge_handles_silent_checklist_success() -> None:
    def runner(*args, **kwargs):  # type: ignore[no-untyped-def]
        request = json.loads(kwargs["input"])
        assert request["type"] == "checklist_command"
        assert request["command"]["command_id"] == "cmd-rust-bridge"
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=json.dumps(
                {
                    "type": "checklist_command",
                    "responses": [],
                    "checklists": 1,
                }
            ),
            stderr="",
        )

    bridge = RustMissionSyncBridge(
        binary_path="r3akt-rch-bridge",
        db_path="runtime.sqlite",
        field_results=10,
        field_event=13,
        field_group=4,
        runner=runner,
    )

    responses = bridge.handle_checklist_command(_command(), group="grp-1")

    assert responses == []


def test_rust_bridge_exposes_state_control_requests() -> None:
    seen_requests: list[dict[str, object]] = []

    def runner(*args, **kwargs):  # type: ignore[no-untyped-def]
        seen_requests.append(json.loads(kwargs["input"]))
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=json.dumps({"type": "state_updated", "ok": True}),
            stderr="",
        )

    bridge = RustMissionSyncBridge(
        binary_path="r3akt-rch-bridge",
        db_path="runtime.sqlite",
        field_results=10,
        field_event=13,
        field_group=4,
        runner=runner,
    )

    bridge.set_authorization_required(True)
    bridge.grant_capability("ABCDEF", "topic.create")

    assert seen_requests == [
        {"type": "set_authorization", "required": True},
        {"type": "grant_capability", "identity": "ABCDEF", "capability": "topic.create"},
    ]


def test_rust_bridge_lists_persisted_topics() -> None:
    def runner(*args, **kwargs):  # type: ignore[no-untyped-def]
        request = json.loads(kwargs["input"])
        assert request == {"type": "list_topics"}
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=json.dumps(
                {
                    "type": "list_topics",
                    "topics": [
                        {
                            "topic_id": "mission-1",
                            "topic_name": "Mission 1",
                            "topic_path": "mission-1",
                            "retention": "persistent",
                            "visibility": "public",
                        }
                    ],
                }
            ),
            stderr="",
        )

    bridge = RustMissionSyncBridge(
        binary_path="r3akt-rch-bridge",
        db_path="runtime.sqlite",
        field_results=10,
        field_event=13,
        field_group=4,
        runner=runner,
    )

    topics = bridge.list_topics()

    assert len(topics) == 1
    assert topics[0].topic_id == "mission-1"
    assert topics[0].payload["visibility"] == "public"


def test_rust_bridge_builder_returns_none_when_disabled(tmp_path: Path) -> None:
    bridge = build_rust_bridge_from_runtime_config(
        HubRuntimeConfig(rust_runtime_enabled=False),
        storage_path=tmp_path,
        field_results=10,
        field_event=13,
        field_group=4,
    )

    assert bridge is None


def test_rust_bridge_builder_requires_bridge_path(tmp_path: Path) -> None:
    bridge = build_rust_bridge_from_runtime_config(
        HubRuntimeConfig(rust_runtime_enabled=True),
        storage_path=tmp_path,
        field_results=10,
        field_event=13,
        field_group=4,
    )

    assert bridge is None


def test_rust_bridge_builder_defaults_db_path(tmp_path: Path) -> None:
    bridge = build_rust_bridge_from_runtime_config(
        HubRuntimeConfig(
            rust_runtime_enabled=True,
            rust_runtime_bridge_path=tmp_path / "r3akt-rch-bridge.exe",
        ),
        storage_path=tmp_path,
        field_results=10,
        field_event=13,
        field_group=4,
    )

    assert bridge is not None
    assert bridge.binary_path == str(tmp_path / "r3akt-rch-bridge.exe")
    assert bridge.db_path == str(tmp_path / DEFAULT_RUST_RUNTIME_DB_FILENAME)


def test_rust_bridge_builder_uses_configured_db_path(tmp_path: Path) -> None:
    bridge = build_rust_bridge_from_runtime_config(
        HubRuntimeConfig(
            rust_runtime_enabled=True,
            rust_runtime_bridge_path=tmp_path / "r3akt-rch-bridge.exe",
            rust_runtime_db_path=tmp_path / "custom.sqlite",
        ),
        storage_path=tmp_path,
        field_results=10,
        field_event=13,
        field_group=4,
    )

    assert bridge is not None
    assert bridge.db_path == str(tmp_path / "custom.sqlite")
