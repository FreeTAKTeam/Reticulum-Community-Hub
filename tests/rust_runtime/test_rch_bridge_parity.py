"""Python-vs-Rust RCH command parity smoke tests.

These tests intentionally live in the Python RCH suite. They replay identical
southbound command envelope shapes against the Python routers and the Rust
``r3akt-rch-bridge`` binary, then assert the same observable contract.
"""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from pathlib import Path
import subprocess
import sqlite3

import msgpack
import pytest

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.api.marker_service import MarkerService
from reticulum_telemetry_hub.api.marker_storage import MarkerStorage
from reticulum_telemetry_hub.api.zone_service import ZoneService
from reticulum_telemetry_hub.api.zone_storage import ZoneStorage
from reticulum_telemetry_hub.checklist_sync.router import ChecklistSyncRouter
from reticulum_telemetry_hub.mission_domain import EmergencyActionMessageService
from reticulum_telemetry_hub.mission_domain import MissionDomainService
from reticulum_telemetry_hub.mission_domain.canonical_teams import CANONICAL_COLOR_TEAM_UIDS
from reticulum_telemetry_hub.mission_sync.rust_bridge import RustMissionSyncBridge
from reticulum_telemetry_hub.mission_sync.router import MissionSyncRouter
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandEnvelope
from tests.test_rth_api import make_config_manager


FIELD_RESULTS = 10
FIELD_GROUP = 11
FIELD_EVENT = 13


class PythonRchBackend:
    """Python RCH reference backend for shared parity assertions."""

    def __init__(self, tmp_path: Path) -> None:
        cfg = make_config_manager(tmp_path)
        self.api = ReticulumTelemetryHubAPI(config_manager=cfg)
        self.domain = MissionDomainService(cfg.config.hub_database_path)
        status = EmergencyActionMessageService(cfg.config.hub_database_path)
        marker_service = MarkerService(
            MarkerStorage(cfg.config.hub_database_path),
            identity_key_provider=lambda: b"\x11" * 32,
        )
        zone_service = ZoneService(ZoneStorage(cfg.config.hub_database_path))
        self.mission_router = MissionSyncRouter(
            api=self.api,
            send_message=lambda _content, _topic_id, _destination: True,
            marker_service=marker_service,
            zone_service=zone_service,
            domain_service=self.domain,
            emergency_action_message_service=status,
            event_log=None,
            hub_identity_resolver=lambda: "hub-1",
            field_results=FIELD_RESULTS,
            field_event=FIELD_EVENT,
            field_group=FIELD_GROUP,
        )
        self.checklist_router = ChecklistSyncRouter(
            api=self.api,
            domain_service=self.domain,
            event_log=None,
            hub_identity_resolver=lambda: "hub-1",
            field_results=FIELD_RESULTS,
            field_event=FIELD_EVENT,
            field_group=FIELD_GROUP,
        )

    def grant_capability(self, identity: str, capability: str) -> None:
        self.api.grant_identity_capability(identity, capability)

    @staticmethod
    def set_authorization_required(_required: bool) -> None:
        return None

    def handle_command(self, envelope: MissionCommandEnvelope, *, group: object | None = None):
        return self.mission_router.handle_commands(
            [envelope.model_dump(mode="json")],
            source_identity="peer-a",
            group=group,
        )

    def handle_checklist_command(
        self,
        envelope: MissionCommandEnvelope,
        *,
        group: object | None = None,
    ):
        return self.checklist_router.handle_commands(
            [envelope.model_dump(mode="json")],
            source_identity="peer-a",
            group=group,
        )

    def checklist_snapshot(self) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        checklists = [self.domain.get_checklist(item["uid"]) for item in self.domain.list_active_checklists()]
        tasks = [task for checklist in checklists for task in checklist.get("tasks", [])]
        return checklists, tasks


class RustRchBackend:
    """Rust bridge backend for shared parity assertions."""

    def __init__(self, tmp_path: Path) -> None:
        self.bridge = _bridge(tmp_path)

    @property
    def db_path(self) -> str:
        return self.bridge.db_path

    def grant_capability(self, identity: str, capability: str) -> None:
        self.bridge.grant_capability(identity, capability)

    def set_authorization_required(self, required: bool) -> None:
        self.bridge.set_authorization_required(required)

    def handle_command(self, envelope: MissionCommandEnvelope, *, group: object | None = None):
        return self.bridge.handle_command(envelope, group=group)

    def handle_checklist_command(
        self,
        envelope: MissionCommandEnvelope,
        *,
        group: object | None = None,
    ):
        return self.bridge.handle_checklist_command(envelope, group=group)

    def checklist_snapshot(self) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        return (
            _sqlite_msgpack_rows(self.db_path, "rch_checklists"),
            _sqlite_msgpack_rows(self.db_path, "rch_checklist_tasks"),
        )


@pytest.fixture(params=["python", "rust"])
def backend(request, tmp_path: Path):  # type: ignore[no-untyped-def]
    if request.param == "python":
        return PythonRchBackend(tmp_path)
    return RustRchBackend(tmp_path)


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


def _grant(backend, *capabilities: str) -> None:  # type: ignore[no-untyped-def]
    backend.set_authorization_required(True)
    for capability in capabilities:
        backend.grant_capability("peer-a", capability)


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


def test_backend_replays_mission_registry_command_flow(backend) -> None:  # type: ignore[no-untyped-def]
    _grant(
        backend,
        "mission.registry.mission.write",
        "mission.registry.mission.read",
        "mission.registry.log.write",
        "mission.registry.log.read",
    )

    upsert = backend.handle_command(
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

    fetched = backend.handle_command(
        _command(
            "mission.registry.mission.get",
            {"mission_uid": "mission-1"},
            command_id="cmd-rust-mission-get",
        )
    )
    assert _terminal_event(fetched)["event_type"] == "mission.registry.mission.retrieved"
    assert _terminal_result(fetched)["mission_name"] == "Mission One"

    log_entry = backend.handle_command(
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

    listed = backend.handle_command(
        _command(
            "mission.registry.log_entry.list",
            {"mission_uid": "mission-1"},
            command_id="cmd-rust-log-list",
        )
    )
    assert _terminal_event(listed)["event_type"] == "mission.registry.log_entry.listed"
    assert _terminal_result(listed)["log_entries"][0]["entry_uid"] == "log-1"


def test_backend_replays_checklist_command_flow(backend) -> None:  # type: ignore[no-untyped-def]
    _grant(backend, "checklist.write", "checklist.read", "checklist.upload", "checklist.feed.publish")

    created = backend.handle_checklist_command(
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

    row_added = backend.handle_checklist_command(
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

    fetched = backend.handle_checklist_command(
        _command(
            "checklist.get",
            {"checklist_uid": "checklist-1"},
            command_id="cmd-rust-checklist-get",
        )
    )
    assert fetched == []
    checklists, tasks = backend.checklist_snapshot()
    assert checklists[0]["name"] == "Rust Parity Checklist"
    assert tasks[0]["number"] == 1

    uploaded = backend.handle_checklist_command(
        _command(
            "checklist.upload",
            {"checklist_uid": "checklist-1", "uploaded_by_team_member_rns_identity": "peer-a"},
            command_id="cmd-rust-checklist-upload",
        )
    )
    assert uploaded == []

    published = backend.handle_checklist_command(
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


def test_backend_replays_eam_command_flow(backend) -> None:  # type: ignore[no-untyped-def]
    _grant(backend, "mission.registry.status.write", "mission.registry.status.read")

    team_uid = CANONICAL_COLOR_TEAM_UIDS["ORANGE"]
    upsert = backend.handle_command(
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

    listed = backend.handle_command(
        _command(
            "mission.registry.eam.list",
            {"team_uid": team_uid},
            command_id="cmd-rust-eam-list",
        )
    )
    assert _terminal_event(listed)["event_type"] == "mission.registry.eam.listed"
    assert _terminal_result(listed)["eams"][0]["callsign"] == "ORANGE-1"

    summary = backend.handle_command(
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

    deleted = backend.handle_command(
        _command(
            "mission.registry.eam.delete",
            {"callsign": "ORANGE-1"},
            command_id="cmd-rust-eam-delete",
        )
    )
    assert _terminal_event(deleted)["event_type"] == "mission.registry.eam.deleted"
    assert _terminal_result(deleted)["eam"]["callsign"] == "ORANGE-1"
    assert _terminal_result(deleted)["eam"]["group_name"] == "ORANGE"


def test_backend_replays_team_asset_skill_assignment_flow(backend) -> None:  # type: ignore[no-untyped-def]
    _grant(
        backend,
        "mission.registry.mission.write",
        "mission.registry.team.write",
        "mission.registry.team.read",
        "mission.registry.team_member.write",
        "mission.registry.team_member.read",
        "mission.registry.asset.write",
        "mission.registry.asset.read",
        "mission.registry.skill.write",
        "mission.registry.skill.read",
        "mission.registry.assignment.write",
        "mission.registry.assignment.read",
        "checklist.write",
    )

    mission = backend.handle_command(
        _command(
            "mission.registry.mission.upsert",
            {"uid": "mission-2", "mission_name": "Mission Two"},
            command_id="cmd-rust-shared-mission-upsert",
        )
    )
    assert _terminal_result(mission)["uid"] == "mission-2"

    team = backend.handle_command(
        _command(
            "mission.registry.team.upsert",
            {"uid": "team-2", "team_name": "Bravo", "mission_uid": "mission-2"},
            command_id="cmd-rust-shared-team-upsert",
        )
    )
    assert _terminal_result(team)["uid"] == "team-2"

    member = backend.handle_command(
        _command(
            "mission.registry.team_member.upsert",
            {
                "uid": "member-2",
                "team_uid": "team-2",
                "rns_identity": "peer-a",
                "display_name": "Peer A",
            },
            command_id="cmd-rust-shared-member-upsert",
        )
    )
    assert _terminal_result(member)["uid"] == "member-2"

    member_link = backend.handle_command(
        _command(
            "mission.registry.team_member.client.link",
            {"team_member_uid": "member-2", "client_identity": "peer-a"},
            command_id="cmd-rust-shared-member-link",
        )
    )
    assert "peer-a" in _terminal_result(member_link)["client_identities"]

    asset = backend.handle_command(
        _command(
            "mission.registry.asset.upsert",
            {
                "asset_uid": "asset-2",
                "team_member_uid": "member-2",
                "name": "Battery Pack",
                "asset_type": "POWER",
            },
            command_id="cmd-rust-shared-asset-upsert",
        )
    )
    assert _terminal_result(asset)["asset_uid"] == "asset-2"

    asset_list = backend.handle_command(
        _command(
            "mission.registry.asset.list",
            {"team_member_uid": "member-2"},
            command_id="cmd-rust-shared-asset-list",
        )
    )
    assert _terminal_result(asset_list)["assets"][0]["asset_uid"] == "asset-2"

    skill = backend.handle_command(
        _command(
            "mission.registry.skill.upsert",
            {"skill_uid": "skill-2", "name": "Navigation"},
            command_id="cmd-rust-shared-skill-upsert",
        )
    )
    assert _terminal_result(skill)["skill_uid"] == "skill-2"

    member_skill = backend.handle_command(
        _command(
            "mission.registry.team_member_skill.upsert",
            {
                "uid": "member-skill-2",
                "team_member_rns_identity": "peer-a",
                "skill_uid": "skill-2",
                "level": 3,
            },
            command_id="cmd-rust-shared-member-skill-upsert",
        )
    )
    assert _terminal_result(member_skill)["uid"] == "member-skill-2"

    created = backend.handle_checklist_command(
        _command(
            "checklist.create.offline",
            {
                "checklist_uid": "checklist-assignment-2",
                "origin_type": "BLANK_TEMPLATE",
                "name": "Assignment Checklist",
                "mission_uid": "mission-2",
            },
            command_id="cmd-rust-shared-checklist-create",
        )
    )
    assert created == []
    row_added = backend.handle_checklist_command(
        _command(
            "checklist.task.row.add",
            {
                "checklist_uid": "checklist-assignment-2",
                "number": 1,
                "due_relative_minutes": 15,
            },
            command_id="cmd-rust-shared-checklist-row",
        )
    )
    assert row_added == []
    _checklists, tasks = backend.checklist_snapshot()
    task_uid = tasks[0]["task_uid"]

    requirement = backend.handle_command(
        _command(
            "mission.registry.task_skill_requirement.upsert",
            {
                "uid": "requirement-2",
                "task_uid": task_uid,
                "skill_uid": "skill-2",
                "minimum_level": 2,
            },
            command_id="cmd-rust-shared-requirement-upsert",
        )
    )
    assert _terminal_result(requirement)["uid"] == "requirement-2"

    assignment = backend.handle_command(
        _command(
            "mission.registry.assignment.upsert",
            {
                "assignment_uid": "assignment-2",
                "mission_uid": "mission-2",
                "task_uid": task_uid,
                "team_member_rns_identity": "peer-a",
            },
            command_id="cmd-rust-shared-assignment-upsert",
        )
    )
    assert _terminal_result(assignment)["assignment_uid"] == "assignment-2"

    assignment_asset = backend.handle_command(
        _command(
            "mission.registry.assignment.asset.link",
            {"assignment_uid": "assignment-2", "asset_uid": "asset-2"},
            command_id="cmd-rust-shared-assignment-asset-link",
        )
    )
    assert _terminal_result(assignment_asset)["assets"] == ["asset-2"]


def test_backend_replays_topic_marker_zone_flow(backend) -> None:  # type: ignore[no-untyped-def]
    _grant(
        backend,
        "topic.create",
        "topic.read",
        "topic.write",
        "topic.subscribe",
        "topic.delete",
        "mission.content.write",
        "mission.content.read",
        "mission.zone.write",
        "mission.zone.read",
        "mission.zone.delete",
    )

    topic = backend.handle_command(
        _command(
            "topic.create",
            {
                "topic_id": "topic-1",
                "topic_name": "Ops",
                "topic_path": "/ops",
                "topic_description": "Operations topic",
            },
            command_id="cmd-shared-topic-create",
        ),
        group="grp-1",
    )
    assert _accepted(topic)["status"] == "accepted"
    assert topic[1].fields[FIELD_GROUP] == "grp-1"
    topic_id = _terminal_result(topic)["TopicID"]

    listed_topics = backend.handle_command(
        _command("topic.list", {}, command_id="cmd-shared-topic-list")
    )
    assert _terminal_result(listed_topics)["topics"]

    patched_topic = backend.handle_command(
        _command(
            "topic.patch",
            {
                "topic_id": topic_id,
                "topic_name": "Ops Renamed",
                "topic_path": "/ops-renamed",
                "topic_description": "Updated",
            },
            command_id="cmd-shared-topic-patch",
        )
    )
    assert _terminal_result(patched_topic)["TopicName"] == "Ops Renamed"

    subscribed = backend.handle_command(
        _command(
            "topic.subscribe",
            {
                "topic_id": topic_id,
                "destination": "dest-2",
                "reject_tests": "not-int",
                "metadata": {"kind": "operator"},
            },
            command_id="cmd-shared-topic-subscribe",
        )
    )
    assert _terminal_result(subscribed)["Destination"] == "dest-2"

    marker = backend.handle_command(
        _command(
            "mission.marker.create",
            {
                "name": "Marker One",
                "marker_type": "marker",
                "symbol": "marker",
                "category": "marker",
                "lat": 45.0,
                "lon": -93.0,
                "notes": "hello",
                "ttl_seconds": 120,
            },
            command_id="cmd-shared-marker-create",
        )
    )
    marker_hash = _terminal_result(marker)["object_destination_hash"]

    listed_markers = backend.handle_command(
        _command("mission.marker.list", {}, command_id="cmd-shared-marker-list")
    )
    assert _terminal_event(listed_markers)["event_type"] == "mission.marker.listed"
    assert _terminal_result(listed_markers)["markers"]

    patched_marker = backend.handle_command(
        _command(
            "mission.marker.position.patch",
            {
                "object_destination_hash": marker_hash,
                "lat": 45.1,
                "lon": -93.1,
            },
            command_id="cmd-shared-marker-patch",
        )
    )
    assert _terminal_result(patched_marker)["object_destination_hash"] == marker_hash

    zone = backend.handle_command(
        _command(
            "mission.zone.create",
            {
                "name": "Zone One",
                "points": [
                    {"lat": 10.0, "lon": 10.0},
                    {"lat": 10.0, "lon": 11.0},
                    {"lat": 11.0, "lon": 10.0},
                ],
            },
            command_id="cmd-shared-zone-create",
        )
    )
    zone_id = _terminal_result(zone)["zone_id"]

    listed_zones = backend.handle_command(
        _command("mission.zone.list", {}, command_id="cmd-shared-zone-list")
    )
    assert _terminal_result(listed_zones)["zones"]

    patched_zone = backend.handle_command(
        _command(
            "mission.zone.patch",
            {
                "zone_id": zone_id,
                "name": "Zone Two",
                "points": [
                    {"lat": 20.0, "lon": 20.0},
                    {"lat": 20.0, "lon": 21.0},
                    {"lat": 21.0, "lon": 20.0},
                ],
            },
            command_id="cmd-shared-zone-patch",
        )
    )
    assert _terminal_result(patched_zone)["name"] == "Zone Two"

    deleted_zone = backend.handle_command(
        _command(
            "mission.zone.delete",
            {"zone_id": zone_id},
            command_id="cmd-shared-zone-delete",
        )
    )
    assert _terminal_result(deleted_zone)["zone_id"] == zone_id

    deleted_topic = backend.handle_command(
        _command(
            "topic.delete",
            {"topic_id": topic_id},
            command_id="cmd-shared-topic-delete",
        )
    )
    assert _terminal_result(deleted_topic)["TopicID"] == topic_id
