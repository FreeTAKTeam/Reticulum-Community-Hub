from __future__ import annotations

import sqlite3

from reticulum_telemetry_hub.mission_domain import MissionDomainService
from reticulum_telemetry_hub.mission_domain.enums import AssetStatus
from reticulum_telemetry_hub.mission_domain.enums import ChecklistMode
from reticulum_telemetry_hub.mission_domain.enums import ChecklistOriginType
from reticulum_telemetry_hub.mission_domain.enums import ChecklistSyncState
from reticulum_telemetry_hub.mission_domain.enums import MissionChangeType
from reticulum_telemetry_hub.mission_domain.enums import MissionRole
from reticulum_telemetry_hub.mission_domain.enums import MissionStatus
from reticulum_telemetry_hub.mission_domain.enums import TeamColor
from reticulum_telemetry_hub.mission_domain.enums import TeamRole


def test_diagram_enum_sets_are_present() -> None:
    assert MissionRole.MISSION_OWNER.value == "MISSION_OWNER"
    assert MissionStatus.MISSION_ACTIVE.value == "MISSION_ACTIVE"
    assert MissionChangeType.CREATE_MISSION.value == "CREATE_MISSION"
    assert TeamRole.TEAM_MEMBER.value == "TEAM_MEMBER"
    assert TeamColor.RED.value == "RED"
    assert ChecklistMode.OFFLINE.value == "OFFLINE"
    assert ChecklistSyncState.UPLOAD_PENDING.value == "UPLOAD_PENDING"
    assert ChecklistOriginType.CSV_IMPORT.value == "CSV_IMPORT"
    assert AssetStatus.RETIRED.value == "RETIRED"


def test_diagram_relationship_methods_exist(tmp_path) -> None:
    service = MissionDomainService(tmp_path / "diagram.sqlite")
    required_methods = {
        "set_mission_parent",
        "link_mission_zone",
        "unlink_mission_zone",
        "list_mission_zones",
        "upsert_mission_rde",
        "get_mission_rde",
        "link_team_member_client",
        "unlink_team_member_client",
        "list_team_member_clients",
        "set_assignment_assets",
        "link_assignment_asset",
        "unlink_assignment_asset",
    }
    for name in required_methods:
        assert hasattr(service, name), name


def test_diagram_relation_tables_exist(tmp_path) -> None:
    db_path = tmp_path / "diagram.sqlite"
    MissionDomainService(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    table_names = {row[0] for row in rows}
    assert "r3akt_mission_zone_links" in table_names
    assert "r3akt_team_member_client_links" in table_names
    assert "r3akt_assignment_assets" in table_names
    assert "r3akt_mission_rde" in table_names
