from __future__ import annotations

from pathlib import Path

import yaml


def _spec_paths() -> dict:
    spec = yaml.safe_load(
        Path("API/ReticulumCommunityHub-OAS.yaml").read_text(encoding="utf-8")
    )
    return spec["paths"]


def test_openapi_includes_phase2_checklist_paths() -> None:
    paths = _spec_paths()

    required = {
        "/checklists/templates": {"get", "post"},
        "/checklists/templates/{template_id}": {"patch", "delete"},
        "/checklists/templates/{template_id}/clone": {"post"},
        "/checklists": {"get", "post"},
        "/checklists/offline": {"post"},
        "/checklists/import/csv": {"post"},
        "/checklists/{checklist_id}": {"get", "patch", "delete"},
        "/checklists/{checklist_id}/join": {"post"},
        "/checklists/{checklist_id}/upload": {"post"},
        "/checklists/{checklist_id}/feeds/{feed_id}": {"post"},
        "/checklists/{checklist_id}/tasks": {"post"},
        "/checklists/{checklist_id}/tasks/{task_id}": {"delete"},
        "/checklists/{checklist_id}/tasks/{task_id}/status": {"post"},
        "/checklists/{checklist_id}/tasks/{task_id}/row-style": {"patch"},
        "/checklists/{checklist_id}/tasks/{task_id}/cells/{column_id}": {"patch"},
    }

    for route, methods in required.items():
        assert route in paths, route
        for method in methods:
            assert method in paths[route], f"{route} missing {method}"


def test_openapi_includes_phase2_r3akt_paths() -> None:
    paths = _spec_paths()

    required = {
        "/api/r3akt/missions": {"get", "post"},
        "/api/r3akt/missions/{mission_uid}": {"get", "patch", "delete"},
        "/api/r3akt/missions/{mission_uid}/parent": {"put"},
        "/api/r3akt/missions/{mission_uid}/zones": {"get"},
        "/api/r3akt/missions/{mission_uid}/zones/{zone_id}": {"put", "delete"},
        "/api/r3akt/missions/{mission_uid}/rde": {"get", "put"},
        "/api/r3akt/mission-changes": {"get", "post"},
        "/api/r3akt/log-entries": {"get", "post"},
        "/api/r3akt/teams": {"get", "post"},
        "/api/r3akt/team-members": {"get", "post"},
        "/api/r3akt/team-members/{team_member_uid}/clients": {"get"},
        "/api/r3akt/team-members/{team_member_uid}/clients/{client_identity}": {"put", "delete"},
        "/api/r3akt/assets": {"get", "post"},
        "/api/r3akt/skills": {"get", "post"},
        "/api/r3akt/team-member-skills": {"get", "post"},
        "/api/r3akt/task-skill-requirements": {"get", "post"},
        "/api/r3akt/assignments": {"get", "post"},
        "/api/r3akt/assignments/{assignment_uid}/assets": {"put"},
        "/api/r3akt/assignments/{assignment_uid}/assets/{asset_uid}": {"put", "delete"},
        "/api/r3akt/events": {"get"},
        "/api/r3akt/snapshots": {"get"},
        "/api/r3akt/capabilities/{identity}": {"get"},
        "/api/r3akt/capabilities/{identity}/{capability}": {"put", "delete"},
    }

    for route, methods in required.items():
        assert route in paths, route
        for method in methods:
            assert method in paths[route], f"{route} missing {method}"


def test_openapi_keeps_rch_and_rth_alias_paths() -> None:
    paths = _spec_paths()

    assert "/RCH" in paths
    assert "post" in paths["/RCH"]
    assert "put" in paths["/RCH"]

    assert "/RTH" in paths
    assert "post" in paths["/RTH"]
    assert "put" in paths["/RTH"]
