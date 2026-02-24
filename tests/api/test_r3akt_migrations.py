from __future__ import annotations

import json
import sqlite3

from reticulum_telemetry_hub.api.models import Topic
from reticulum_telemetry_hub.api.storage import HubStorage
from reticulum_telemetry_hub.mission_domain import MissionDomainService


REQUIRED_PHASE2_TABLES = {
    "identity_capability_grants",
    "r3akt_missions",
    "r3akt_mission_changes",
    "r3akt_log_entries",
    "r3akt_teams",
    "r3akt_team_members",
    "r3akt_assets",
    "r3akt_skills",
    "r3akt_team_member_skills",
    "r3akt_task_skill_requirements",
    "r3akt_checklist_templates",
    "r3akt_checklists",
    "r3akt_checklist_columns",
    "r3akt_checklist_tasks",
    "r3akt_checklist_cells",
    "r3akt_checklist_feed_publications",
    "r3akt_mission_task_assignments",
    "r3akt_assignment_assets",
    "r3akt_mission_team_links",
    "r3akt_mission_zone_links",
    "r3akt_team_member_client_links",
    "r3akt_mission_rde",
    "r3akt_domain_events",
    "r3akt_domain_snapshots",
}


def _list_tables(db_path) -> set[str]:
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    return {row[0] for row in rows}


def test_phase2_startup_creates_required_tables_idempotently(tmp_path) -> None:
    db_path = tmp_path / "hub.sqlite"

    storage = HubStorage(db_path)
    domain = MissionDomainService(db_path)

    storage.create_topic(Topic(topic_name="Status", topic_path="/status"))
    domain.upsert_mission({"uid": "mission-1", "mission_name": "Mission One"})

    tables_after_first_start = _list_tables(db_path)
    assert REQUIRED_PHASE2_TABLES.issubset(tables_after_first_start)

    storage_second_start = HubStorage(db_path)
    domain_second_start = MissionDomainService(db_path)

    tables_after_second_start = _list_tables(db_path)
    assert REQUIRED_PHASE2_TABLES.issubset(tables_after_second_start)

    topics = storage_second_start.list_topics()
    missions = domain_second_start.list_missions()

    assert any(topic.topic_path == "/status" for topic in topics)
    assert any(mission["uid"] == "mission-1" for mission in missions)


def test_phase2_startup_is_additive_for_existing_legacy_schema(tmp_path) -> None:
    db_path = tmp_path / "legacy.sqlite"

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("CREATE TABLE legacy_probe (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO legacy_probe (id) VALUES ('probe-1')")
        conn.commit()

    HubStorage(db_path)
    MissionDomainService(db_path)

    tables = _list_tables(db_path)
    assert "legacy_probe" in tables
    assert REQUIRED_PHASE2_TABLES.issubset(tables)

    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute("SELECT id FROM legacy_probe WHERE id='probe-1'").fetchone()
    assert row is not None
    assert row[0] == "probe-1"


def test_assignment_assets_dual_read_backfills_legacy_json(tmp_path) -> None:
    db_path = tmp_path / "legacy_assets.sqlite"
    domain = MissionDomainService(db_path)

    mission = domain.upsert_mission({"uid": "mission-1", "mission_name": "Mission One"})
    domain.upsert_team(
        {
            "uid": "team-1",
            "mission_uid": mission["uid"],
            "team_name": "Ops",
            "color": "RED",
        }
    )
    domain.upsert_team_member(
        {
            "uid": "member-1",
            "team_uid": "team-1",
            "rns_identity": "peer-a",
            "display_name": "Peer A",
            "role": "TEAM_MEMBER",
        }
    )
    domain.upsert_asset(
        {
            "asset_uid": "asset-1",
            "team_member_uid": "member-1",
            "name": "Radio 1",
            "asset_type": "COMM",
            "status": "AVAILABLE",
        }
    )
    domain.upsert_asset(
        {
            "asset_uid": "asset-2",
            "team_member_uid": "member-1",
            "name": "Radio 2",
            "asset_type": "COMM",
            "status": "AVAILABLE",
        }
    )

    template = domain.create_checklist_template(
        {
            "uid": "tpl-1",
            "template_name": "Template",
            "created_by_team_member_rns_identity": "peer-a",
            "columns": [
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
            ],
        }
    )
    checklist = domain.create_checklist_online(
        {
            "template_uid": template["uid"],
            "name": "Checklist",
            "mission_uid": mission["uid"],
            "source_identity": "peer-a",
        }
    )
    checklist = domain.add_checklist_task_row(checklist["uid"], {"number": 1})
    task_uid = checklist["tasks"][0]["task_uid"]

    domain.upsert_assignment(
        {
            "assignment_uid": "assignment-1",
            "mission_uid": mission["uid"],
            "task_uid": task_uid,
            "team_member_rns_identity": "peer-a",
            "assets": ["asset-1"],
        }
    )

    # Simulate legacy state where only JSON assets are present and link rows are absent.
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "DELETE FROM r3akt_assignment_assets WHERE assignment_uid = ?",
            ("assignment-1",),
        )
        conn.commit()

    listed = domain.list_assignments(mission_uid=mission["uid"])
    assert listed[0]["assets"] == ["asset-1"]

    updated = domain.set_assignment_assets("assignment-1", ["asset-2"])
    assert updated["assets"] == ["asset-2"]

    with sqlite3.connect(str(db_path)) as conn:
        linked_assets = conn.execute(
            "SELECT asset_uid FROM r3akt_assignment_assets WHERE assignment_uid = ?",
            ("assignment-1",),
        ).fetchall()
        assets_json_row = conn.execute(
            "SELECT assets FROM r3akt_mission_task_assignments WHERE assignment_uid = ?",
            ("assignment-1",),
        ).fetchone()

    assert {row[0] for row in linked_assets} == {"asset-2"}
    assert assets_json_row is not None
    assets_json_value = assets_json_row[0]
    if isinstance(assets_json_value, str):
        assets_json_value = json.loads(assets_json_value)
    assert assets_json_value == ["asset-2"]


def test_mission_change_delta_column_is_added_for_legacy_table(tmp_path) -> None:
    db_path = tmp_path / "legacy_mission_change.sqlite"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE r3akt_mission_changes (
                uid TEXT PRIMARY KEY,
                mission_uid TEXT NOT NULL,
                name TEXT,
                team_member_rns_identity TEXT,
                timestamp TEXT,
                notes TEXT,
                change_type TEXT,
                is_federated_change INTEGER NOT NULL DEFAULT 0,
                hashes TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO r3akt_mission_changes (
                uid, mission_uid, name, change_type, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("legacy-change-1", "mission-legacy", "Legacy", "ADD_CONTENT", "2026-02-24T00:00:00+00:00"),
        )
        conn.commit()

    MissionDomainService(db_path)

    with sqlite3.connect(str(db_path)) as conn:
        columns = [
            row[1]
            for row in conn.execute("PRAGMA table_info(r3akt_mission_changes);").fetchall()
        ]
        row = conn.execute(
            "SELECT uid FROM r3akt_mission_changes WHERE uid = ?",
            ("legacy-change-1",),
        ).fetchone()

    assert "delta" in columns
    assert row is not None
    assert row[0] == "legacy-change-1"
