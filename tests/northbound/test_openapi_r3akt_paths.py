from __future__ import annotations

from pathlib import Path

import yaml


def _spec_paths() -> dict:
    spec = yaml.safe_load(
        Path("API/ReticulumCommunityHub-OAS.yaml").read_text(encoding="utf-8")
    )
    return spec["paths"]


def _spec() -> dict:
    return yaml.safe_load(Path("API/ReticulumCommunityHub-OAS.yaml").read_text(encoding="utf-8"))


def test_openapi_includes_phase2_checklist_paths() -> None:
    paths = _spec_paths()

    required = {
        "/checklists/templates": {"get", "post"},
        "/checklists/templates/{template_id}": {"get", "patch", "delete"},
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
        "/api/r3akt/teams/{team_uid}": {"get", "delete"},
        "/api/r3akt/teams/{team_uid}/missions": {"get"},
        "/api/r3akt/teams/{team_uid}/missions/{mission_uid}": {"put", "delete"},
        "/api/r3akt/team-members": {"get", "post"},
        "/api/r3akt/team-members/{team_member_uid}": {"get", "delete"},
        "/api/r3akt/team-members/{team_member_uid}/clients": {"get"},
        "/api/r3akt/team-members/{team_member_uid}/clients/{client_identity}": {"put", "delete"},
        "/api/r3akt/assets": {"get", "post"},
        "/api/r3akt/assets/{asset_uid}": {"get", "delete"},
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


def test_openapi_exposes_r3akt_domain_schemas() -> None:
    schemas = _spec()["components"]["schemas"]

    required = {
        "R3aktMission",
        "R3aktMissionChange",
        "R3aktLogEntry",
        "R3aktTeam",
        "R3aktTeamMember",
        "R3aktAsset",
        "R3aktSkill",
        "R3aktTeamMemberSkill",
        "R3aktTaskSkillRequirement",
        "R3aktMissionTaskAssignment",
        "R3aktChecklist",
        "R3aktChecklistTask",
        "R3aktChecklistCell",
        "R3aktChecklistColumn",
        "R3aktChecklistTemplate",
        "R3aktChecklistFeedPublication",
    }

    assert required.issubset(set(schemas))


def test_openapi_r3akt_endpoints_reference_domain_schemas() -> None:
    paths = _spec_paths()

    assert (
        paths["/api/r3akt/missions"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["items"]["$ref"]
        == "#/components/schemas/R3aktMission"
    )
    assert (
        paths["/api/r3akt/teams"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktTeam"
    )
    assert (
        paths["/api/r3akt/team-members"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktTeamMember"
    )
    assert (
        paths["/api/r3akt/assignments"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["items"]["$ref"]
        == "#/components/schemas/R3aktMissionTaskAssignment"
    )
    assert (
        paths["/checklists/{checklist_id}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktChecklist"
    )
    assert (
        paths["/checklists/templates"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktChecklistTemplateListResponse"
    )


def test_openapi_r3akt_mission_change_schema_includes_delta() -> None:
    schemas = _spec()["components"]["schemas"]
    mission_change = schemas["R3aktMissionChange"]
    mission_change_request = schemas["R3aktMissionChangeUpsertRequest"]

    assert "delta" in mission_change["properties"]
    assert mission_change["properties"]["delta"]["type"] == "object"
    assert "delta" in mission_change_request["properties"]
