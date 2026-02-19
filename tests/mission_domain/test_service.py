from __future__ import annotations

import base64
from datetime import datetime
from datetime import timedelta
from datetime import timezone

import pytest

from reticulum_telemetry_hub.api.storage_models import R3aktDomainEventRecord
from reticulum_telemetry_hub.api.storage_models import R3aktDomainSnapshotRecord
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
            "change_type": "EDIT",
            "is_federated_change": True,
            "hashes": ["abc"],
        }
    )
    assert service.list_mission_changes(mission_uid="mission-1")[0]["uid"] == change["uid"]

    with pytest.raises(ValueError):
        service.upsert_team({"uid": "team-invalid", "mission_uid": "missing", "team_name": "Ops"})

    team = service.upsert_team(
        {
            "uid": "team-1",
            "mission_uid": "mission-1",
            "team_name": "Ops",
            "color": "#ff0000",
        }
    )
    assert service.list_teams(mission_uid="mission-1")[0]["uid"] == team["uid"]

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
            "role": "LEAD",
            "callsign": "ALPHA",
        }
    )
    assert service.list_team_members(team_uid="team-1")[0]["uid"] == member["uid"]

    with pytest.raises(ValueError):
        service.upsert_asset(
            {
                "asset_uid": "asset-invalid",
                "team_member_uid": "missing-member",
                "name": "Invalid",
                "asset_type": "COMM",
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

    assert service.list_domain_events(limit=10)
    assert service.list_domain_snapshots(limit=10)


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

    deleted_row = service.delete_checklist_task_row(online["uid"], task_uid)
    assert deleted_row["tasks"] == []

    with pytest.raises(KeyError):
        service.delete_checklist_task_row(online["uid"], task_uid)

    with pytest.raises(ValueError):
        service.import_checklist_csv({})

    with pytest.raises(ValueError):
        service.import_checklist_csv({"csv_base64": "abc"})

    encoded_csv = base64.b64encode(b"10,Task 1\n20,Task 2\nX,Task 3\n").decode("ascii")
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
