from __future__ import annotations

import base64
from datetime import datetime
from datetime import timedelta
from datetime import timezone

import pytest

from reticulum_telemetry_hub.api.storage_models import R3aktDomainEventRecord
from reticulum_telemetry_hub.api.storage_models import R3aktDomainSnapshotRecord
from reticulum_telemetry_hub.api.storage_models import MarkerRecord
from reticulum_telemetry_hub.api.storage_models import ClientRecord
from reticulum_telemetry_hub.api.storage_models import TopicRecord
from reticulum_telemetry_hub.api.storage_models import ZoneRecord
from reticulum_telemetry_hub.mission_domain.service import CHECKLIST_TASK_COMPLETE
from reticulum_telemetry_hub.mission_domain.service import CHECKLIST_TASK_COMPLETE_LATE
from reticulum_telemetry_hub.mission_domain.service import CHECKLIST_TASK_LATE
from reticulum_telemetry_hub.mission_domain.service import CHECKLIST_TASK_PENDING
from reticulum_telemetry_hub.mission_domain.service import MissionDomainService
from reticulum_telemetry_hub.mission_domain.service import _as_datetime
from reticulum_telemetry_hub.mission_domain.service import _dt


def _service(tmp_path, *, retention_days: int = 90) -> MissionDomainService:
    return MissionDomainService(tmp_path / "r3akt.sqlite", event_retention_days=retention_days)


def _columns() -> list[dict[str, object]]:
    return [
        {
            "column_name": "Due",
            "display_order": 1,
            "column_type": "RELATIVE_TIME",
            "column_editable": False,
            "is_removable": False,
            "system_key": "DUE_RELATIVE_DTG",
        },
        {
            "column_name": "Task",
            "display_order": 2,
            "column_type": "SHORT_STRING",
            "column_editable": True,
            "is_removable": True,
        },
    ]


def test_registry_domain_crud_and_filters(tmp_path) -> None:
    service = _service(tmp_path)

    with service._session() as session:  # pylint: disable=protected-access
        session.add(
            TopicRecord(
                id="topic-alpha",
                name="Topic Alpha",
                path="/topic-alpha",
                description="Topic for mission tests",
            )
        )
        session.add(ClientRecord(identity="peer-a"))

    mission = service.upsert_mission(
        {
            "uid": "mission-1",
            "mission_name": "Mission Alpha",
            "description": "Primary mission",
            "topic_id": "topic-alpha",
            "invite_only": True,
        }
    )
    assert mission["uid"] == "mission-1"
    assert service.get_mission("mission-1")["mission_name"] == "Mission Alpha"
    assert service.list_missions()[0]["uid"] == "mission-1"
    assert service.get_mission("mission-1", expand_topic=True)["topic"]["topic_id"] == "topic-alpha"

    service.upsert_mission({"uid": "mission-2", "mission_name": "Mission Two"})
    service.set_mission_parent("mission-2", parent_uid="mission-1")
    assert service.get_mission("mission-2")["parent_uid"] == "mission-1"
    with pytest.raises(ValueError):
        service.set_mission_parent("mission-1", parent_uid="mission-2")

    with service._session() as session:  # pylint: disable=protected-access
        session.add(
            ZoneRecord(
                id="zone-1",
                name="Zone One",
                points_json=[
                    {"lat": 1.0, "lon": 1.0},
                    {"lat": 1.0, "lon": 2.0},
                    {"lat": 2.0, "lon": 1.0},
                ],
            )
        )
    linked_mission = service.link_mission_zone("mission-1", "zone-1")
    assert linked_mission["zones"] == ["zone-1"]
    assert service.list_mission_zones("mission-1") == ["zone-1"]
    unlinked_mission = service.unlink_mission_zone("mission-1", "zone-1")
    assert unlinked_mission["zones"] == []

    mission_rde = service.upsert_mission_rde("mission-1", "MISSION_OWNER")
    assert mission_rde["role"] == "MISSION_OWNER"
    assert service.get_mission_rde("mission-1")["role"] == "MISSION_OWNER"

    patched_mission = service.patch_mission(
        "mission-1",
        {
            "mission_priority": 10,
            "default_role": "MISSION_SUBSCRIBER",
            "owner_role": "MISSION_OWNER",
            "feeds": ["feed-a"],
        },
    )
    assert patched_mission["mission_priority"] == 10
    assert patched_mission["feeds"] == ["feed-a"]
    deleted = service.delete_mission("mission-2")
    assert deleted["mission_status"] == "MISSION_DELETED"

    with pytest.raises(KeyError):
        service.get_mission("missing")

    with pytest.raises(ValueError):
        service.upsert_mission_change({"name": "invalid"})

    change = service.upsert_mission_change(
        {
            "uid": "change-1",
            "mission_uid": "mission-1",
            "name": "Mission updated",
            "team_member_rns_identity": "peer-a",
            "notes": "Changed objectives",
            "change_type": "ADD_CONTENT",
            "is_federated_change": True,
            "hashes": [],
        }
    )
    assert service.list_mission_changes(mission_uid="mission-1")[0]["uid"] == change["uid"]

    with pytest.raises(ValueError):
        service.upsert_log_entry({"content": "Mission log without mission"})

    with service._session() as session:  # pylint: disable=protected-access
        session.add(
            MarkerRecord(
                id="marker-1",
                object_destination_hash="hash-1",
                marker_type="marker",
                symbol="marker",
                name="Marker One",
                category="test",
                lat=34.1,
                lon=-117.2,
            )
        )

    with pytest.raises(ValueError):
        service.upsert_log_entry(
            {
                "entry_uid": "log-invalid-marker",
                "mission_uid": "mission-1",
                "content": "Bad marker reference",
                "content_hashes": ["missing-marker"],
            }
        )

    log_entry = service.upsert_log_entry(
        {
            "entry_uid": "log-1",
            "mission_uid": "mission-1",
            "content": "Marker observed at waypoint",
            "server_time": datetime.now(timezone.utc).isoformat(),
            "client_time": datetime.now(timezone.utc).isoformat(),
            "content_hashes": ["hash-1"],
            "keywords": ["marker", "waypoint"],
        }
    )
    assert log_entry["entry_uid"] == "log-1"
    assert log_entry["content_hashes"] == ["hash-1"]
    assert service.list_log_entries(mission_uid="mission-1")[0]["entry_uid"] == "log-1"
    assert service.list_log_entries(marker_ref="hash-1")[0]["entry_uid"] == "log-1"

    with pytest.raises(ValueError):
        service.upsert_team({"uid": "team-invalid", "mission_uid": "missing", "team_name": "Ops"})

    team = service.upsert_team(
        {
            "uid": "team-1",
            "mission_uid": "mission-1",
            "team_name": "Ops",
            "color": "RED",
        }
    )
    assert service.list_teams(mission_uid="mission-1")[0]["uid"] == team["uid"]
    assert service.list_team_missions("team-1") == ["mission-1"]
    linked_team = service.link_team_mission("team-1", "mission-2")
    assert set(linked_team["mission_uids"]) == {"mission-1", "mission-2"}
    assert any(item["uid"] == "team-1" for item in service.list_teams(mission_uid="mission-2"))

    with pytest.raises(ValueError):
        service.upsert_team_member({"uid": "member-invalid"})

    with pytest.raises(ValueError):
        service.upsert_team_member(
            {
                "uid": "member-invalid-team",
                "team_uid": "missing-team",
                "rns_identity": "peer-missing",
            }
        )

    member = service.upsert_team_member(
        {
            "uid": "member-1",
            "team_uid": "team-1",
            "rns_identity": "peer-a",
            "display_name": "Peer A",
            "role": "TEAM_LEAD",
            "callsign": "ALPHA",
        }
    )
    assert service.list_team_members(team_uid="team-1")[0]["uid"] == member["uid"]
    unassigned_member = service.upsert_team_member(
        {
            "uid": "member-1",
            "team_uid": None,
            "rns_identity": "peer-a",
            "display_name": "Peer A",
        }
    )
    assert unassigned_member["team_uid"] is None
    assert service.list_team_members(team_uid="team-1") == []
    reassigned_member = service.upsert_team_member(
        {
            "uid": "member-1",
            "team_uid": "team-1",
            "rns_identity": "peer-a",
            "display_name": "Peer A",
        }
    )
    assert reassigned_member["team_uid"] == "team-1"

    linked_member = service.link_team_member_client("member-1", "peer-a")
    assert linked_member["client_identities"] == ["peer-a"]
    assert service.list_team_member_clients("member-1") == ["peer-a"]
    assert service.list_mission_team_member_identities("mission-1") == ["peer-a"]

    with pytest.raises(ValueError):
        service.upsert_asset(
            {
                "asset_uid": "asset-invalid",
                "team_member_uid": "missing-member",
                "name": "Invalid",
                "asset_type": "COMM",
            }
        )

    with pytest.raises(ValueError):
        service.upsert_asset(
            {
                "asset_uid": "asset-invalid-status",
                "team_member_uid": "member-1",
                "name": "Invalid Status",
                "asset_type": "COMM",
                "status": "BROKEN",
            }
        )

    asset = service.upsert_asset(
        {
            "asset_uid": "asset-1",
            "team_member_uid": "member-1",
            "name": "Radio",
            "asset_type": "COMM",
            "serial_number": "SN-1",
            "status": "IN_USE",
            "location": "truck",
            "notes": "primary",
        }
    )
    assert service.list_assets(team_member_uid="member-1")[0]["asset_uid"] == asset["asset_uid"]

    skill = service.upsert_skill(
        {
            "skill_uid": "skill-1",
            "name": "Navigation",
            "category": "field",
            "description": "Nav skill",
            "proficiency_scale": "1-5",
        }
    )
    assert service.list_skills()[0]["skill_uid"] == skill["skill_uid"]

    with pytest.raises(ValueError):
        service.upsert_team_member_skill({"team_member_rns_identity": "peer-a"})

    with pytest.raises(ValueError):
        service.upsert_team_member_skill(
            {
                "uid": "member-skill-missing-member",
                "team_member_rns_identity": "missing-member",
                "skill_uid": "skill-1",
            }
        )

    with pytest.raises(ValueError):
        service.upsert_team_member_skill(
            {
                "uid": "member-skill-missing-skill",
                "team_member_rns_identity": "peer-a",
                "skill_uid": "missing-skill",
            }
        )

    member_skill = service.upsert_team_member_skill(
        {
            "uid": "member-skill-1",
            "team_member_rns_identity": "peer-a",
            "skill_uid": "skill-1",
            "level": 3,
            "validated_by": "supervisor",
            "validated_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        }
    )
    updated_member_skill = service.upsert_team_member_skill(
        {
            "team_member_rns_identity": "peer-a",
            "skill_uid": "skill-1",
            "level": 4,
        }
    )
    assert updated_member_skill["uid"] == member_skill["uid"]
    assert updated_member_skill["level"] == 4
    zeroed_member_skill = service.upsert_team_member_skill(
        {
            "team_member_rns_identity": "peer-a",
            "skill_uid": "skill-1",
            "level": 0,
        }
    )
    assert zeroed_member_skill["level"] == 0
    assert (
        service.list_team_member_skills(team_member_rns_identity="peer-a")[0]["uid"]
        == member_skill["uid"]
    )

    template = service.create_checklist_template(
        {
            "uid": "registry-template",
            "template_name": "Registry Template",
            "description": "Template used for registry task references",
            "created_by_team_member_rns_identity": "peer-a",
            "columns": _columns(),
        }
    )
    checklist = service.create_checklist_online(
        {
            "template_uid": template["uid"],
            "name": "Registry Checklist",
            "mission_uid": mission["uid"],
            "source_identity": "peer-a",
        }
    )
    checklist_with_task = service.add_checklist_task_row(
        checklist["uid"],
        {"number": 1},
    )
    task_uid = checklist_with_task["tasks"][0]["task_uid"]

    with pytest.raises(ValueError):
        service.upsert_task_skill_requirement({"task_uid": "task-1"})

    with pytest.raises(ValueError):
        service.upsert_task_skill_requirement(
            {
                "uid": "req-missing-skill",
                "task_uid": "task-1",
                "skill_uid": "missing-skill",
            }
        )

    with pytest.raises(ValueError):
        service.upsert_task_skill_requirement(
            {
                "uid": "req-missing-task",
                "task_uid": "missing-task",
                "skill_uid": "skill-1",
            }
        )

    requirement = service.upsert_task_skill_requirement(
        {
            "uid": "req-1",
            "task_uid": task_uid,
            "skill_uid": "skill-1",
            "minimum_level": 2,
            "is_mandatory": True,
        }
    )
    assert (
        service.list_task_skill_requirements(task_uid=task_uid)[0]["uid"]
        == requirement["uid"]
    )
    zeroed_requirement = service.upsert_task_skill_requirement(
        {
            "task_uid": task_uid,
            "skill_uid": "skill-1",
            "minimum_level": 0,
        }
    )
    assert zeroed_requirement["minimum_level"] == 0

    with pytest.raises(ValueError):
        service.upsert_assignment({"mission_uid": "mission-1"})

    with pytest.raises(ValueError):
        service.upsert_assignment(
            {
                "assignment_uid": "assign-missing-mission",
                "mission_uid": "missing-mission",
                "task_uid": "task-1",
                "team_member_rns_identity": "peer-a",
            }
        )

    with pytest.raises(ValueError):
        service.upsert_assignment(
            {
                "assignment_uid": "assign-missing-member",
                "mission_uid": "mission-1",
                "task_uid": task_uid,
                "team_member_rns_identity": "missing-member",
            }
        )

    with pytest.raises(ValueError):
        service.upsert_assignment(
            {
                "assignment_uid": "assign-missing-task",
                "mission_uid": "mission-1",
                "task_uid": "missing-task",
                "team_member_rns_identity": "peer-a",
            }
        )

    with pytest.raises(ValueError):
        service.upsert_assignment(
            {
                "assignment_uid": "assign-missing-asset",
                "mission_uid": "mission-1",
                "task_uid": task_uid,
                "team_member_rns_identity": "peer-a",
                "assets": ["missing-asset"],
            }
        )

    assignment = service.upsert_assignment(
        {
            "assignment_uid": "assign-1",
            "mission_uid": "mission-1",
            "task_uid": task_uid,
            "team_member_rns_identity": "peer-a",
            "assigned_by": "peer-b",
            "status": "PENDING",
            "notes": "do this",
            "assets": ["asset-1"],
        }
    )
    assert service.list_assignments(mission_uid="mission-1")[0]["assignment_uid"] == assignment["assignment_uid"]
    assert service.list_assignments(task_uid=task_uid)[0]["assignment_uid"] == assignment["assignment_uid"]
    assert service.list_assignments(task_uid=task_uid)[0]["assets"] == ["asset-1"]

    linked_assignment = service.link_assignment_asset("assign-1", "asset-1")
    assert linked_assignment["assets"] == ["asset-1"]
    service.upsert_asset(
        {
            "asset_uid": "asset-2",
            "team_member_uid": "member-1",
            "name": "Spare Radio",
            "asset_type": "COMM",
            "status": "AVAILABLE",
        }
    )
    linked_assignment = service.link_assignment_asset("assign-1", "asset-2")
    assert linked_assignment["assets"] == ["asset-1", "asset-2"]
    unlinked_assignment = service.unlink_assignment_asset("assign-1", "asset-1")
    assert unlinked_assignment["assets"] == ["asset-2"]
    reset_assets = service.set_assignment_assets("assign-1", ["asset-1"])
    assert reset_assets["assets"] == ["asset-1"]

    expanded_mission = service.get_mission(
        "mission-1",
        expand="topic,teams,team_members,assets,mission_changes,log_entries,assignments,checklists,mission_rde",
    )
    assert expanded_mission["topic"]["topic_id"] == "topic-alpha"
    assert expanded_mission["teams"]
    assert expanded_mission["team_members"]
    assert expanded_mission["assets"]
    assert expanded_mission["mission_changes"]
    assert expanded_mission["log_entries"]
    assert expanded_mission["assignments"]
    assert expanded_mission["checklists"]
    assert expanded_mission["mission_rde"]["role"] == "MISSION_OWNER"

    expanded_list = service.list_missions(expand="all")
    expanded_match = next(item for item in expanded_list if item["uid"] == "mission-1")
    assert "teams" in expanded_match
    assert "checklists" in expanded_match

    assert service.list_domain_events(limit=10)
    assert service.list_domain_snapshots(limit=10)


def test_mission_delta_auto_emission_for_logs_assets_and_tasks(tmp_path) -> None:
    service = _service(tmp_path)
    captured_changes: list[dict[str, object]] = []
    remove_listener = service.register_mission_change_listener(
        lambda change: captured_changes.append(dict(change))
    )

    mission = service.upsert_mission({"uid": "mission-1", "mission_name": "Mission"})
    service.upsert_team(
        {"uid": "team-1", "mission_uid": mission["uid"], "team_name": "Ops"}
    )
    service.upsert_team_member(
        {
            "uid": "member-1",
            "team_uid": "team-1",
            "rns_identity": "peer-a",
            "display_name": "Peer A",
        }
    )

    service.upsert_log_entry(
        {
            "entry_uid": "log-1",
            "mission_uid": mission["uid"],
            "content": "Initial log",
            "keywords": ["ops"],
        }
    )
    service.upsert_asset(
        {
            "asset_uid": "asset-1",
            "team_member_uid": "member-1",
            "name": "Radio 1",
            "asset_type": "COMM",
        }
    )
    service.upsert_asset(
        {
            "asset_uid": "asset-2",
            "team_member_uid": "member-1",
            "name": "Radio 2",
            "asset_type": "COMM",
        }
    )

    template = service.create_checklist_template(
        {
            "uid": "tpl-1",
            "template_name": "Template",
            "created_by_team_member_rns_identity": "peer-a",
            "columns": _columns(),
        }
    )
    checklist = service.create_checklist_online(
        {
            "template_uid": template["uid"],
            "name": "Checklist",
            "mission_uid": mission["uid"],
            "source_identity": "peer-a",
        }
    )
    checklist = service.add_checklist_task_row(checklist["uid"], {"number": 1})
    task_uid = checklist["tasks"][0]["task_uid"]
    text_column_uid = next(
        column["column_uid"]
        for column in checklist["columns"]
        if column["column_type"] == "SHORT_STRING"
    )
    checklist = service.set_checklist_task_row_style(
        checklist["uid"],
        task_uid,
        {"row_background_color": "#123456", "line_break_enabled": True},
    )
    checklist = service.set_checklist_task_cell(
        checklist["uid"],
        task_uid,
        text_column_uid,
        {"value": "Inspect path", "updated_by_team_member_rns_identity": "peer-a"},
    )
    checklist = service.set_checklist_task_status(
        checklist["uid"],
        task_uid,
        {"user_status": "COMPLETE", "changed_by_team_member_rns_identity": "peer-a"},
    )
    assignment = service.upsert_assignment(
        {
            "assignment_uid": "assignment-1",
            "mission_uid": mission["uid"],
            "task_uid": task_uid,
            "team_member_rns_identity": "peer-a",
            "assets": ["asset-1"],
        }
    )
    service.set_assignment_assets(assignment["assignment_uid"], ["asset-1"])
    service.link_assignment_asset(assignment["assignment_uid"], "asset-2")
    service.unlink_assignment_asset(assignment["assignment_uid"], "asset-2")
    service.delete_checklist_task_row(checklist["uid"], task_uid)
    service.delete_asset("asset-1")
    remove_listener()

    mission_changes = service.list_mission_changes(mission_uid=mission["uid"])
    assert mission_changes
    assert captured_changes
    assert len({item["uid"] for item in captured_changes}) == len(captured_changes)
    assert all(item.get("mission_id") == mission["uid"] for item in mission_changes)

    log_ops: set[str] = set()
    asset_ops: set[str] = set()
    task_ops: set[str] = set()
    for change in mission_changes:
        delta = change.get("delta") or {}
        if not isinstance(delta, dict):
            continue
        if delta.get("contract_version"):
            assert delta["contract_version"] == "r3akt.mission.change.v1"
        for item in list(delta.get("logs") or []):
            if isinstance(item, dict):
                log_ops.add(str(item.get("op")))
        for item in list(delta.get("assets") or []):
            if isinstance(item, dict):
                asset_ops.add(str(item.get("op")))
        for item in list(delta.get("tasks") or []):
            if isinstance(item, dict):
                task_ops.add(str(item.get("op")))

    assert {"upsert"} <= log_ops
    assert {"upsert", "delete"} <= asset_ops
    assert {
        "row_added",
        "row_deleted",
        "row_style_set",
        "cell_set",
        "status_set",
        "assignment_upsert",
        "assignment_assets_set",
        "assignment_asset_linked",
        "assignment_asset_unlinked",
    } <= task_ops


def test_checklist_task_mutations_without_mission_skip_mission_change(tmp_path) -> None:
    service = _service(tmp_path)
    checklist = service.create_checklist_offline({"name": "Offline"})
    checklist = service.add_checklist_task_row(checklist["uid"], {"number": 1})
    task_uid = checklist["tasks"][0]["task_uid"]
    text_column_uid = next(
        column["column_uid"]
        for column in checklist["columns"]
        if column["column_type"] == "SHORT_STRING"
    )
    service.set_checklist_task_row_style(
        checklist["uid"], task_uid, {"line_break_enabled": True}
    )
    service.set_checklist_task_cell(
        checklist["uid"],
        task_uid,
        text_column_uid,
        {"value": "offline"},
    )
    service.set_checklist_task_status(
        checklist["uid"], task_uid, {"user_status": "COMPLETE"}
    )
    service.delete_checklist_task_row(checklist["uid"], task_uid)

    assert service.list_mission_changes() == []


def test_team_member_asset_get_and_delete_cleanup(tmp_path) -> None:
    service = _service(tmp_path)

    mission = service.upsert_mission({"uid": "mission-1", "mission_name": "Mission One"})
    service.upsert_team(
        {
            "uid": "team-1",
            "team_name": "Ops",
            "mission_uid": mission["uid"],
        }
    )
    service.upsert_team_member(
        {
            "uid": "member-1",
            "team_uid": "team-1",
            "rns_identity": "peer-a",
            "display_name": "Peer A",
        }
    )
    service.link_team_member_client("member-1", "client-a")
    service.upsert_skill({"skill_uid": "skill-1", "name": "Navigation"})
    service.upsert_team_member_skill(
        {
            "uid": "member-skill-1",
            "team_member_rns_identity": "peer-a",
            "skill_uid": "skill-1",
            "level": 2,
        }
    )

    template = service.create_checklist_template(
        {
            "uid": "template-1",
            "template_name": "Task Template",
            "description": "Template for assignment references",
            "created_by_team_member_rns_identity": "peer-a",
            "columns": _columns(),
        }
    )
    checklist = service.create_checklist_online(
        {
            "template_uid": template["uid"],
            "name": "Checklist Alpha",
            "mission_uid": mission["uid"],
            "source_identity": "peer-a",
        }
    )
    task_uid = service.add_checklist_task_row(checklist["uid"], {"number": 1})["tasks"][0]["task_uid"]

    service.upsert_asset(
        {
            "asset_uid": "asset-1",
            "team_member_uid": "member-1",
            "name": "Radio",
            "asset_type": "COMM",
        }
    )
    service.upsert_assignment(
        {
            "assignment_uid": "assignment-1",
            "mission_uid": mission["uid"],
            "task_uid": task_uid,
            "team_member_rns_identity": "peer-a",
            "assets": ["asset-1"],
        }
    )

    assert service.get_team("team-1")["uid"] == "team-1"
    assert service.get_team_member("member-1")["uid"] == "member-1"
    assert service.get_asset("asset-1")["asset_uid"] == "asset-1"

    deleted_asset = service.delete_asset("asset-1")
    assert deleted_asset["asset_uid"] == "asset-1"
    assert service.list_assignments(task_uid=task_uid)[0]["assets"] == []
    with pytest.raises(KeyError):
        service.get_asset("asset-1")

    deleted_member = service.delete_team_member("member-1")
    assert deleted_member["uid"] == "member-1"
    assert service.list_team_member_skills(team_member_rns_identity="peer-a") == []
    with pytest.raises(KeyError):
        service.get_team_member("member-1")
    with pytest.raises(KeyError):
        service.list_team_member_clients("member-1")

    service.upsert_team_member(
        {
            "uid": "member-2",
            "team_uid": "team-1",
            "rns_identity": "peer-b",
            "display_name": "Peer B",
        }
    )
    deleted_team = service.delete_team("team-1")
    assert deleted_team["uid"] == "team-1"
    assert service.get_team_member("member-2")["team_uid"] is None
    with pytest.raises(KeyError):
        service.get_team("team-1")


def test_template_and_checklist_lifecycle_and_constraints(tmp_path) -> None:
    service = _service(tmp_path)

    with pytest.raises(ValueError):
        service.create_checklist_template(
            {
                "template_name": "bad",
                "columns": [
                    {
                        "column_name": "Task",
                        "display_order": 1,
                        "column_type": "SHORT_STRING",
                        "column_editable": True,
                        "is_removable": True,
                    }
                ],
            }
        )

    with pytest.raises(ValueError):
        service.create_checklist_template(
            {
                "template_name": "bad due column",
                "columns": [
                    {
                        "column_name": "Due",
                        "display_order": 1,
                        "column_type": "RELATIVE_TIME",
                        "column_editable": False,
                        "is_removable": True,
                        "system_key": "DUE_RELATIVE_DTG",
                    }
                ],
            }
        )

    template = service.create_checklist_template(
        {
            "uid": "tpl-1",
            "template_name": "Template Alpha",
            "description": "Initial template",
            "created_by_team_member_rns_identity": "peer-a",
            "columns": _columns(),
        }
    )
    fetched_template = service.get_checklist_template(template["uid"])
    assert fetched_template["uid"] == template["uid"]

    updated_template = service.update_checklist_template(
        template["uid"],
        {
            "template_name": "Template Beta",
            "description": "Updated template",
            "columns": _columns(),
        },
    )
    assert updated_template["template_name"] == "Template Beta"

    with pytest.raises(KeyError):
        service.update_checklist_template("missing-template", {"template_name": "x"})

    with pytest.raises(KeyError):
        service.get_checklist_template("missing-template")

    clone = service.clone_checklist_template(
        template["uid"],
        template_name="Template Clone",
        description="clone",
        created_by_team_member_rns_identity="peer-b",
    )
    assert clone["source_template_uid"] == template["uid"]

    with pytest.raises(KeyError):
        service.clone_checklist_template("missing-template", template_name="x")

    assert service.list_checklist_templates(search="Template", sort_by="name_desc")
    assert service.list_checklist_templates(sort_by="created_at_asc")
    assert service.list_checklist_templates(sort_by="created_at_desc")

    deleted = service.delete_checklist_template(clone["uid"])
    assert deleted["uid"] == clone["uid"]

    with pytest.raises(KeyError):
        service.delete_checklist_template(clone["uid"])

    with pytest.raises(ValueError):
        service.create_checklist_online({"name": "No template"})

    with pytest.raises(ValueError):
        service.create_checklist_online({"template_uid": template["uid"]})

    with pytest.raises(ValueError):
        service.create_checklist_online(
            {
                "template_uid": template["uid"],
                "name": "Invalid Mission Checklist",
                "mission_uid": "missing-mission",
            }
        )

    with pytest.raises(ValueError):
        service.create_checklist_offline({"description": "missing name"})

    with pytest.raises(ValueError):
        service.create_checklist_offline(
            {
                "name": "Offline Invalid Mission",
                "mission_uid": "missing-mission",
            }
        )

    service.upsert_mission({"uid": "mission-1", "mission_name": "Mission One"})

    online = service.create_checklist_online(
        {
            "template_uid": template["uid"],
            "name": "Online Checklist",
            "description": "Checklist for mission",
            "start_time": datetime.now(timezone.utc).isoformat(),
            "source_identity": "peer-a",
            "mission_uid": "mission-1",
        }
    )
    offline = service.create_checklist_offline(
        {
            "name": "Offline Checklist",
            "description": "Offline checklist",
            "source_identity": "peer-a",
            "origin_type": "BLANK_TEMPLATE",
        }
    )

    assert service.list_active_checklists(search="Checklist", sort_by="name_desc")
    assert service.list_active_checklists(sort_by="created_at_asc")
    assert service.list_active_checklists(sort_by="created_at_desc")

    with pytest.raises(KeyError):
        service.get_checklist("missing-checklist")

    first_row = service.add_checklist_task_row(
        online["uid"],
        {
            "number": 1,
            "due_relative_minutes": 5,
        },
    )
    task_uid = first_row["tasks"][0]["task_uid"]
    short_text_column = next(
        col for col in first_row["columns"] if col["column_type"] == "SHORT_STRING"
    )

    with pytest.raises(KeyError):
        service.add_checklist_task_row("missing-checklist", {"number": 1})

    updated_cell = service.set_checklist_task_cell(
        online["uid"],
        task_uid,
        short_text_column["column_uid"],
        {
            "value": "Review task",
            "updated_by_team_member_rns_identity": "peer-a",
        },
    )
    updated_task_cells = updated_cell["tasks"][0]["cells"]
    updated_value = next(
        item["value"]
        for item in updated_task_cells
        if item["column_uid"] == short_text_column["column_uid"]
    )
    assert updated_value == "Review task"

    with pytest.raises(KeyError):
        service.set_checklist_task_cell(online["uid"], task_uid, "missing-column", {})

    with pytest.raises(KeyError):
        service.set_checklist_task_cell(online["uid"], "missing-task", short_text_column["column_uid"], {})

    styled = service.set_checklist_task_row_style(
        online["uid"],
        task_uid,
        {
            "row_background_color": "#00ff00",
            "line_break_enabled": True,
        },
    )
    assert styled["tasks"][0]["line_break_enabled"] is True

    with pytest.raises(KeyError):
        service.set_checklist_task_row_style(online["uid"], "missing-task", {})

    with pytest.raises(ValueError):
        service.set_checklist_task_status(online["uid"], task_uid, {"user_status": "INVALID"})

    completed = service.set_checklist_task_status(
        online["uid"],
        task_uid,
        {
            "user_status": "COMPLETE",
            "changed_by_team_member_rns_identity": "peer-a",
        },
    )
    assert completed["counts"]["complete_count"] == 1

    reset = service.set_checklist_task_status(
        online["uid"],
        task_uid,
        {
            "user_status": "PENDING",
        },
    )
    assert reset["counts"]["pending_count"] == 1

    with pytest.raises(KeyError):
        service.set_checklist_task_status(online["uid"], "missing-task", {"user_status": "PENDING"})

    joined = service.join_checklist(online["uid"], source_identity="peer-a")
    assert joined["uid"] == online["uid"]

    with pytest.raises(KeyError):
        service.join_checklist("missing-checklist")

    with pytest.raises(ValueError):
        service.publish_checklist_feed(offline["uid"], "feed-1", source_identity="peer-a")

    pending_upload = service.mark_checklist_upload_pending(offline["uid"], source_identity="peer-a")
    assert pending_upload["sync_state"] == "UPLOAD_PENDING"

    uploaded = service.upload_checklist(offline["uid"], source_identity="peer-a")
    assert uploaded["sync_state"] == "SYNCED"

    with pytest.raises(KeyError):
        service.upload_checklist("missing-checklist")

    with pytest.raises(ValueError):
        service.publish_checklist_feed(offline["uid"], "", source_identity="peer-a")

    publication = service.publish_checklist_feed(
        offline["uid"],
        "feed-1",
        source_identity="peer-a",
    )
    assert publication["mission_feed_uid"] == "feed-1"

    with pytest.raises(KeyError):
        service.publish_checklist_feed("missing-checklist", "feed-1", source_identity="peer-a")

    deleted_checklist = service.delete_checklist(offline["uid"])
    assert deleted_checklist["uid"] == offline["uid"]

    with pytest.raises(KeyError):
        service.delete_checklist(offline["uid"])

    deleted_row = service.delete_checklist_task_row(online["uid"], task_uid)
    assert deleted_row["tasks"] == []

    with pytest.raises(KeyError):
        service.delete_checklist_task_row(online["uid"], task_uid)

    with pytest.raises(ValueError):
        service.import_checklist_csv({})

    with pytest.raises(ValueError):
        service.import_checklist_csv({"csv_base64": "abc"})

    encoded_csv = base64.b64encode(b"Task,Description\nTask 1,Inspect ridge\nTask 2,Secure path\nTask 3,Report status\n").decode("ascii")
    imported = service.import_checklist_csv(
        {
            "csv_filename": "ops.csv",
            "csv_base64": encoded_csv,
            "source_identity": "peer-a",
        }
    )
    assert imported["origin_type"] == "CSV_IMPORT"
    assert imported["name"] == "ops"
    assert len(imported["tasks"]) == 3
    assert any(column["column_name"] == "Task" for column in imported["columns"])
    assert any(column["column_name"] == "Description" for column in imported["columns"])
    task_column_uid = next(
        column["column_uid"]
        for column in imported["columns"]
        if column["column_name"] == "Task"
    )
    description_column_uid = next(
        column["column_uid"]
        for column in imported["columns"]
        if column["column_name"] == "Description"
    )
    first_task_cells = {
        cell["column_uid"]: cell["value"]
        for cell in imported["tasks"][0]["cells"]
    }
    assert first_task_cells[task_column_uid] == "Task 1"
    assert first_task_cells[description_column_uid] == "Inspect ridge"
    assert imported["tasks"][0]["legacy_value"] == "Task 1"
    assert [task["due_relative_minutes"] for task in imported["tasks"]] == [30, 60, 90]


def test_domain_history_retention_prunes_old_rows(tmp_path) -> None:
    service = _service(tmp_path, retention_days=1)
    old_time = datetime.now(timezone.utc) - timedelta(days=30)

    with service._session() as session:  # pylint: disable=protected-access
        session.add(
            R3aktDomainEventRecord(
                event_uid="old-event",
                domain="mission",
                aggregate_type="mission",
                aggregate_uid="m-old",
                event_type="mission.old",
                payload_json={"stale": True},
                created_at=old_time,
            )
        )
        session.add(
            R3aktDomainSnapshotRecord(
                snapshot_uid="old-snapshot",
                domain="mission",
                aggregate_type="mission",
                aggregate_uid="m-old",
                version=1,
                state_json={"stale": True},
                created_at=old_time,
            )
        )

    service.upsert_mission({"uid": "mission-now", "mission_name": "Current"})

    event_ids = {event["event_uid"] for event in service.list_domain_events(limit=500)}
    snapshot_ids = {
        snapshot["snapshot_uid"] for snapshot in service.list_domain_snapshots(limit=500)
    }

    assert "old-event" not in event_ids
    assert "old-snapshot" not in snapshot_ids


def test_datetime_helpers_and_status_derivation(tmp_path) -> None:
    default = datetime.now(timezone.utc)
    naive = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)

    assert _as_datetime(None, default=default) == default
    parsed_naive = _as_datetime(naive)
    assert parsed_naive is not None
    assert parsed_naive.tzinfo is not None

    parsed_iso = _as_datetime("2026-01-02T03:04:05Z")
    assert parsed_iso is not None
    assert parsed_iso.tzinfo is not None

    assert _as_datetime("", default=default) == default
    assert _as_datetime("not-a-date", default=default) == default

    assert _dt(None) is None
    assert _dt(default) == default.isoformat()

    service = _service(tmp_path)
    now = datetime.now(timezone.utc)
    due_past = now - timedelta(minutes=1)

    late_status, late_flag = service._derive_task_status(  # pylint: disable=protected-access
        user_status="PENDING",
        due_dtg=due_past,
        completed_at=None,
    )
    assert late_status == CHECKLIST_TASK_LATE
    assert late_flag is True

    complete_status, complete_flag = service._derive_task_status(  # pylint: disable=protected-access
        user_status="COMPLETE",
        due_dtg=now,
        completed_at=now,
    )
    assert complete_status == CHECKLIST_TASK_COMPLETE
    assert complete_flag is False

    complete_late_status, complete_late_flag = service._derive_task_status(  # pylint: disable=protected-access
        user_status="COMPLETE",
        due_dtg=due_past,
        completed_at=now,
    )
    assert complete_late_status == CHECKLIST_TASK_COMPLETE_LATE
    assert complete_late_flag is True

    pending_status, pending_flag = service._derive_task_status(  # pylint: disable=protected-access
        user_status="PENDING",
        due_dtg=None,
        completed_at=None,
    )
    assert pending_status == CHECKLIST_TASK_PENDING
    assert pending_flag is False
