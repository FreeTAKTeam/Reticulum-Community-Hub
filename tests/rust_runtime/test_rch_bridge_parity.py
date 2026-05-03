"""Rust-backed RCH command parity smoke tests.

These tests intentionally live in the Python RCH suite. They replay the same
southbound command envelope shapes used by the Python router tests, but execute
them through the Rust ``r3akt-rch-bridge`` binary and its SQLite state.
"""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from pathlib import Path
import subprocess
import sqlite3

import msgpack
import pytest

from reticulum_telemetry_hub.mission_domain.canonical_teams import CANONICAL_COLOR_TEAM_UIDS
from reticulum_telemetry_hub.mission_sync.rust_bridge import RustMissionSyncBridge
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandEnvelope


FIELD_RESULTS = 10
FIELD_GROUP = 11
FIELD_EVENT = 13


def _runtime_root() -> Path:
    candidates = [
        Path(__file__).resolve().parents[4] / "New project" / "R3AKT-Runtime",
        Path(r"C:\Users\broth\Documents\New project\R3AKT-Runtime"),
    ]
    for candidate in candidates:
        if (candidate / "Cargo.toml").exists():
            return candidate
    pytest.fail("R3AKT-Runtime workspace not found for Rust parity tests")


def _bridge(tmp_path: Path) -> RustMissionSyncBridge:
    runtime_root = _runtime_root()

    def runner(args, **kwargs):  # type: ignore[no-untyped-def]
        db_path = args[args.index("--db") + 1]
        return subprocess.run(
            ["cargo", "run", "-q", "-p", "r3akt-rch-bridge", "--", "--db", db_path],
            cwd=runtime_root,
            input=kwargs["input"],
            text=True,
            capture_output=True,
            check=False,
        )

    return RustMissionSyncBridge(
        binary_path="cargo-run-r3akt-rch-bridge",
        db_path=str(tmp_path / "rch-rust-parity.sqlite"),
        field_results=FIELD_RESULTS,
        field_event=FIELD_EVENT,
        field_group=FIELD_GROUP,
        runner=runner,
    )


def _command(command_type: str, args: dict[str, object], *, command_id: str) -> MissionCommandEnvelope:
    return MissionCommandEnvelope.model_validate(
        {
            "command_id": command_id,
            "source": {"rns_identity": "peer-a", "display_name": "Peer A"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "command_type": command_type,
            "args": args,
        }
    )


def _grant(bridge: RustMissionSyncBridge, *capabilities: str) -> None:
    bridge.set_authorization_required(True)
    for capability in capabilities:
        bridge.grant_capability("peer-a", capability)


def _sqlite_msgpack_rows(db_path: str, table: str) -> list[dict[str, object]]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(f"SELECT payload FROM {table} ORDER BY rowid").fetchall()
    return [msgpack.unpackb(row[0], raw=False) for row in rows]


def _accepted(responses: list) -> dict[str, object]:
    return responses[0].fields[FIELD_RESULTS]  # type: ignore[return-value]


def _terminal_result(responses: list) -> dict[str, object]:
    return responses[1].fields[FIELD_RESULTS]["result"]  # type: ignore[index,return-value]


def _terminal_event(responses: list) -> dict[str, object]:
    return responses[1].fields[FIELD_EVENT]  # type: ignore[return-value]


def test_rust_bridge_replays_python_mission_registry_command_flow(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    _grant(
        bridge,
        "mission.registry.mission.write",
        "mission.registry.mission.read",
        "mission.registry.log.write",
        "mission.registry.log.read",
    )

    upsert = bridge.handle_command(
        _command(
            "mission.registry.mission.upsert",
            {
                "uid": "mission-1",
                "mission_name": "Mission One",
                "description": "Parity mission",
            },
            command_id="cmd-rust-mission-upsert",
        ),
        group="grp-1",
    )
    assert _accepted(upsert)["status"] == "accepted"
    assert upsert[1].fields[FIELD_GROUP] == "grp-1"
    assert _terminal_event(upsert)["event_type"] == "mission.registry.mission.upserted"
    assert _terminal_result(upsert)["uid"] == "mission-1"

    fetched = bridge.handle_command(
        _command(
            "mission.registry.mission.get",
            {"mission_uid": "mission-1"},
            command_id="cmd-rust-mission-get",
        )
    )
    assert _terminal_event(fetched)["event_type"] == "mission.registry.mission.retrieved"
    assert _terminal_result(fetched)["mission_name"] == "Mission One"

    log_entry = bridge.handle_command(
        _command(
            "mission.registry.log_entry.upsert",
            {
                "entry_uid": "log-1",
                "mission_uid": "mission-1",
                "content": "Checked in",
                "team_member_rns_identity": "peer-a",
            },
            command_id="cmd-rust-log-upsert",
        )
    )
    assert _terminal_event(log_entry)["event_type"] == "mission.registry.log_entry.upserted"
    assert _terminal_result(log_entry)["entry_uid"] == "log-1"

    listed = bridge.handle_command(
        _command(
            "mission.registry.log_entry.list",
            {"mission_uid": "mission-1"},
            command_id="cmd-rust-log-list",
        )
    )
    assert _terminal_event(listed)["event_type"] == "mission.registry.log_entry.listed"
    assert _terminal_result(listed)["log_entries"][0]["entry_uid"] == "log-1"


def test_rust_bridge_replays_python_checklist_command_flow(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    _grant(bridge, "checklist.write", "checklist.read", "checklist.upload", "checklist.feed.publish")

    created = bridge.handle_checklist_command(
        _command(
            "checklist.create.offline",
            {
                "checklist_uid": "checklist-1",
                "origin_type": "BLANK_TEMPLATE",
                "name": "Rust Parity Checklist",
                "description": "created by parity test",
            },
            command_id="cmd-rust-checklist-create",
        )
    )
    assert created == []

    row_added = bridge.handle_checklist_command(
        _command(
            "checklist.task.row.add",
            {
                "checklist_uid": "checklist-1",
                "number": 1,
                "due_relative_minutes": 10,
            },
            command_id="cmd-rust-checklist-row-add",
        )
    )
    assert row_added == []

    fetched = bridge.handle_checklist_command(
        _command(
            "checklist.get",
            {"checklist_uid": "checklist-1"},
            command_id="cmd-rust-checklist-get",
        )
    )
    assert fetched == []
    checklists = _sqlite_msgpack_rows(bridge.db_path, "rch_checklists")
    tasks = _sqlite_msgpack_rows(bridge.db_path, "rch_checklist_tasks")
    assert checklists[0]["name"] == "Rust Parity Checklist"
    assert tasks[0]["number"] == 1

    uploaded = bridge.handle_checklist_command(
        _command(
            "checklist.upload",
            {"checklist_uid": "checklist-1", "uploaded_by_team_member_rns_identity": "peer-a"},
            command_id="cmd-rust-checklist-upload",
        )
    )
    assert uploaded == []

    published = bridge.handle_checklist_command(
        _command(
            "checklist.feed.publish",
            {
                "checklist_uid": "checklist-1",
                "mission_feed_uid": "feed-ops",
                "published_by_team_member_rns_identity": "peer-a",
            },
            command_id="cmd-rust-checklist-publish",
        )
    )
    assert published == []


def test_rust_bridge_replays_python_eam_command_flow(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    _grant(bridge, "mission.registry.status.write", "mission.registry.status.read")

    team_uid = CANONICAL_COLOR_TEAM_UIDS["ORANGE"]
    upsert = bridge.handle_command(
        _command(
            "mission.registry.eam.upsert",
            {
                "callsign": "ORANGE-1",
                "team_member_uid": "member-1",
                "team_uid": team_uid,
                "reported_by": "peer-a",
                "reported_at": datetime.now(timezone.utc).isoformat(),
                "security_status": "Green",
                "capability_status": "Yellow",
                "preparedness_status": "Green",
                "medical_status": "Unknown",
                "mobility_status": "Green",
                "comms_status": "Red",
                "notes": "Alternate comms required",
                "confidence": 0.8,
                "ttl_seconds": 3600,
                "source": {"rns_identity": "peer-a", "display_name": "Peer A"},
            },
            command_id="cmd-rust-eam-upsert",
        )
    )
    assert _accepted(upsert)["status"] == "accepted"
    assert _terminal_event(upsert)["event_type"] == "mission.registry.eam.upserted"
    snapshot = _terminal_result(upsert)["eam"]
    assert snapshot["team_uid"] == team_uid
    assert snapshot["group_name"] == "ORANGE"
    assert snapshot["overall_status"] == "Red"

    listed = bridge.handle_command(
        _command(
            "mission.registry.eam.list",
            {"team_uid": team_uid},
            command_id="cmd-rust-eam-list",
        )
    )
    assert _terminal_event(listed)["event_type"] == "mission.registry.eam.listed"
    assert _terminal_result(listed)["eams"][0]["callsign"] == "ORANGE-1"

    summary = bridge.handle_command(
        _command(
            "mission.registry.eam.team.summary",
            {"team_uid": team_uid},
            command_id="cmd-rust-eam-summary",
        )
    )
    summary_payload = _terminal_result(summary)["summary"]
    assert summary_payload["team_uid"] == team_uid
    assert summary_payload["total"] == 1
    assert summary_payload["active_total"] == 1
    assert summary_payload["overall_status"] == "Red"

    deleted = bridge.handle_command(
        _command(
            "mission.registry.eam.delete",
            {"callsign": "ORANGE-1"},
            command_id="cmd-rust-eam-delete",
        )
    )
    assert _terminal_event(deleted)["event_type"] == "mission.registry.eam.deleted"
    assert _terminal_result(deleted)["eam"]["callsign"] == "ORANGE-1"
    assert _terminal_result(deleted)["eam"]["group_name"] == "ORANGE"
