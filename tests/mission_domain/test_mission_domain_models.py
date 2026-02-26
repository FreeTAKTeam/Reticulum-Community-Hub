from __future__ import annotations

from datetime import datetime
from datetime import timezone

from reticulum_telemetry_hub.mission_domain import models


def test_domain_models_and_json_safe() -> None:
    now = datetime.now(timezone.utc)

    mission = models.Mission(uid="m1", mission_name="Mission", created_at=now, updated_at=now)
    change = models.MissionChange(uid="mc1", mission_uid="m1", timestamp=now)
    log_entry = models.LogEntry(
        entry_uid="log1",
        mission_uid="m1",
        content="Marker observed",
        server_time=now,
        client_time=now,
        content_hashes=["marker-1"],
        keywords=["marker", "observation"],
    )
    team = models.Team(uid="t1", team_name="Alpha", mission_uid="m1")
    member = models.TeamMember(
        uid="tm1",
        team_uid="t1",
        rns_identity="peer-a",
        display_name="Peer A",
    )
    asset = models.Asset(
        asset_uid="a1",
        name="Radio",
        asset_type="COMM",
        serial_number="SN-1",
        status="IN_USE",
        location="truck",
        notes="primary",
    )
    skill = models.Skill(skill_uid="s1", name="Navigation")
    team_skill = models.TeamMemberSkill(
        uid="ts1",
        team_member_rns_identity="peer-a",
        skill_uid="s1",
        level=3,
    )
    requirement = models.TaskSkillRequirement(
        uid="req1",
        task_uid="task-1",
        skill_uid="s1",
        minimum_level=2,
        is_mandatory=True,
    )

    due_column = models.ChecklistColumn(
        column_uid="c1",
        column_name="Due",
        display_order=1,
        column_type="RELATIVE_TIME",
        column_editable=False,
        is_removable=False,
        system_key="DUE_RELATIVE_DTG",
    )
    text_column = models.ChecklistColumn(
        column_uid="c2",
        column_name="Task",
        display_order=2,
        column_type="SHORT_STRING",
        column_editable=True,
        is_removable=True,
    )
    cell = models.ChecklistCell(
        cell_uid="cell1",
        task_uid="task-1",
        column_uid="c2",
        updated_at=now,
        value="Do work",
    )
    task = models.ChecklistTask(
        task_uid="task-1",
        number=1,
        user_status="PENDING",
        task_status="PENDING",
        line_break_enabled=False,
        is_late=False,
        due_dtg=now,
        cells=[cell],
    )
    template = models.ChecklistTemplate(
        uid="tpl1",
        template_name="Template",
        description="Template description",
        created_at=now,
        created_by_team_member_rns_identity="peer-a",
        updated_at=now,
        columns=[due_column, text_column],
    )
    publication = models.ChecklistFeedPublication(
        publication_uid="pub1",
        checklist_uid="cl1",
        mission_feed_uid="feed1",
        published_at=now,
        published_by_team_member_rns_identity="peer-a",
    )
    checklist = models.Checklist(
        uid="cl1",
        name="Checklist",
        description="Checklist description",
        start_time=now,
        mode="ONLINE",
        sync_state="SYNCED",
        origin_type="RCH_TEMPLATE",
        created_at=now,
        created_by_team_member_rns_identity="peer-a",
        updated_at=now,
        checklist_status="PENDING",
        progress_percent=0.0,
        counts={"pending_count": 1, "late_count": 0, "complete_count": 0},
        columns=[due_column, text_column],
        tasks=[task],
    )
    assignment = models.MissionTaskAssignment(
        assignment_uid="as1",
        mission_uid="m1",
        task_uid="task-1",
        team_member_rns_identity="peer-a",
        status="PENDING",
        assigned_at=now,
        assets=["a1"],
    )

    assert mission.uid == "m1"
    assert change.mission_uid == "m1"
    assert log_entry.content_hashes == ["marker-1"]
    assert team.team_name == "Alpha"
    assert member.display_name == "Peer A"
    assert asset.asset_type == "COMM"
    assert asset.serial_number == "SN-1"
    assert asset.status == "IN_USE"
    assert skill.name == "Navigation"
    assert team_skill.level == 3
    assert requirement.minimum_level == 2
    assert template.columns[0].system_key == "DUE_RELATIVE_DTG"
    assert publication.mission_feed_uid == "feed1"
    assert checklist.tasks[0].cells[0].value == "Do work"
    assert assignment.assets == ["a1"]

    safe = models.json_safe(
        {
            "when": now,
            "items": [now],
            "counts": checklist.counts,
        }
    )

    assert safe["when"] == now.isoformat()
    assert safe["items"][0] == now.isoformat()
    assert safe["counts"]["pending_count"] == 1
