from __future__ import annotations

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
