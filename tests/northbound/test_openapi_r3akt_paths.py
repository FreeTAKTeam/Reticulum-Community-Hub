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
        "/api/r3akt/rights/definitions": {"get"},
        "/api/r3akt/rights/subjects": {"get"},
        "/api/r3akt/rights/grants": {"get", "put", "delete"},
        "/api/r3akt/rights/mission-access": {"get", "put", "delete"},
    }

    for route, methods in required.items():
        assert route in paths, route
        for method in methods:
            assert method in paths[route], f"{route} missing {method}"


def test_openapi_keeps_rch_and_rth_alias_paths() -> None:
    spec = _spec()
    paths = spec["paths"]
    parameters = spec["components"]["parameters"]
    schemas = spec["components"]["schemas"]

    assert "/RCH" in paths
    assert "post" in paths["/RCH"]
    assert "put" in paths["/RCH"]

    assert "/RTH" in paths
    assert "post" in paths["/RTH"]
    assert "put" in paths["/RTH"]

    assert parameters["identity"]["name"] == "identity"
    for route in ("/RCH", "/RTH"):
        for method in ("post", "put"):
            assert (
                paths[route][method]["parameters"][0]["$ref"]
                == "#/components/parameters/identity"
            )
            assert (
                paths[route][method]["responses"]["200"]["content"]["application/json"]["schema"]["type"]
                == "boolean"
            )

    assert "Error" in schemas
    announce = paths["/Control/Announce"]["post"]
    assert announce["responses"]["200"]["content"]["application/json"]["schema"][
        "required"
    ] == ["status"]
    assert (
        announce["responses"]["503"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/Error"
    )


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


def test_openapi_r3akt_list_and_upsert_contracts_reference_domain_schemas() -> None:
    paths = _spec_paths()

    expected_lists = {
        "/api/r3akt/missions": "R3aktMission",
        "/api/r3akt/mission-changes": "R3aktMissionChange",
        "/api/r3akt/log-entries": "R3aktLogEntry",
        "/api/r3akt/teams": "R3aktTeam",
        "/api/r3akt/team-members": "R3aktTeamMember",
        "/api/r3akt/assets": "R3aktAsset",
        "/api/r3akt/skills": "R3aktSkill",
        "/api/r3akt/team-member-skills": "R3aktTeamMemberSkill",
        "/api/r3akt/task-skill-requirements": "R3aktTaskSkillRequirement",
        "/api/r3akt/assignments": "R3aktMissionTaskAssignment",
    }
    for path, schema in expected_lists.items():
        assert (
            paths[path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["items"]["$ref"]
            == f"#/components/schemas/{schema}"
        )

    expected_upserts = {
        "/api/r3akt/missions": ("R3aktMissionUpsertRequest", "R3aktMission"),
        "/api/r3akt/mission-changes": (
            "R3aktMissionChangeUpsertRequest",
            "R3aktMissionChange",
        ),
        "/api/r3akt/log-entries": ("R3aktLogEntryUpsertRequest", "R3aktLogEntry"),
        "/api/r3akt/teams": ("R3aktTeamUpsertRequest", "R3aktTeam"),
        "/api/r3akt/team-members": (
            "R3aktTeamMemberUpsertRequest",
            "R3aktTeamMember",
        ),
        "/api/r3akt/assets": ("R3aktAssetUpsertRequest", "R3aktAsset"),
        "/api/r3akt/skills": ("R3aktSkillUpsertRequest", "R3aktSkill"),
        "/api/r3akt/team-member-skills": (
            "R3aktTeamMemberSkillUpsertRequest",
            "R3aktTeamMemberSkill",
        ),
        "/api/r3akt/task-skill-requirements": (
            "R3aktTaskSkillRequirementUpsertRequest",
            "R3aktTaskSkillRequirement",
        ),
        "/api/r3akt/assignments": (
            "R3aktMissionTaskAssignmentUpsertRequest",
            "R3aktMissionTaskAssignment",
        ),
    }
    for path, (request_schema, response_schema) in expected_upserts.items():
        assert (
            paths[path]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
            == f"#/components/schemas/{request_schema}"
        )
        assert (
            paths[path]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
            == f"#/components/schemas/{response_schema}"
        )


def test_openapi_r3akt_mission_detail_and_link_contracts_reference_domain_schemas() -> None:
    paths = _spec_paths()
    schemas = _spec()["components"]["schemas"]

    assert {
        "R3aktMissionPatchRequest",
        "R3aktMissionParentRequest",
        "R3aktMissionZonesResponse",
        "R3aktMissionRde",
        "R3aktMissionRdeRequest",
    }.issubset(set(schemas))

    mission_detail = paths["/api/r3akt/missions/{mission_uid}"]
    assert (
        mission_detail["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktMission"
    )
    mission_detail_params = {
        parameter["name"] for parameter in mission_detail["get"]["parameters"]
    }
    assert {"mission_uid", "expand"}.issubset(mission_detail_params)
    assert (
        mission_detail["patch"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktMissionPatchRequest"
    )
    assert (
        mission_detail["patch"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktMission"
    )
    assert (
        mission_detail["delete"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktMission"
    )
    for method in ("patch", "delete"):
        assert "mission_uid" in {
            parameter["name"] for parameter in mission_detail[method]["parameters"]
        }

    parent = paths["/api/r3akt/missions/{mission_uid}/parent"]["put"]
    assert (
        parent["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktMissionParentRequest"
    )
    assert (
        parent["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktMission"
    )
    assert "mission_uid" in {parameter["name"] for parameter in parent["parameters"]}

    zones = paths["/api/r3akt/missions/{mission_uid}/zones"]["get"]
    assert (
        zones["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktMissionZonesResponse"
    )
    assert "mission_uid" in {parameter["name"] for parameter in zones["parameters"]}

    zone_link = paths["/api/r3akt/missions/{mission_uid}/zones/{zone_id}"]
    for method in ("put", "delete"):
        operation = zone_link[method]
        assert (
            operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
            == "#/components/schemas/R3aktMission"
        )
        assert {"mission_uid", "zone_id"}.issubset(
            {parameter["name"] for parameter in operation["parameters"]}
        )

    rde = paths["/api/r3akt/missions/{mission_uid}/rde"]
    assert (
        rde["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktMissionRde"
    )
    assert (
        rde["put"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktMissionRdeRequest"
    )
    assert (
        rde["put"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktMissionRde"
    )
    for method in ("get", "put"):
        assert "mission_uid" in {
            parameter["name"] for parameter in rde[method]["parameters"]
        }


def test_openapi_r3akt_registry_detail_and_link_contracts_reference_domain_schemas() -> None:
    paths = _spec_paths()
    schemas = _spec()["components"]["schemas"]

    assert {
        "R3aktMissionUidsResponse",
        "R3aktClientIdentitiesResponse",
        "R3aktAssignmentAssetSetRequest",
    }.issubset(set(schemas))

    expected_list_params = {
        "/api/r3akt/teams": {"mission_uid"},
        "/api/r3akt/team-members": {"team_uid"},
        "/api/r3akt/assets": {"team_member_uid"},
        "/api/r3akt/team-member-skills": {"team_member_rns_identity"},
        "/api/r3akt/task-skill-requirements": {"task_uid"},
        "/api/r3akt/assignments": {"mission_uid", "task_uid"},
    }
    for path, names in expected_list_params.items():
        assert names.issubset(
            {parameter["name"] for parameter in paths[path]["get"]["parameters"]}
        )

    for method in ("get", "delete"):
        team_detail = paths["/api/r3akt/teams/{team_uid}"][method]
        assert (
            team_detail["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
            == "#/components/schemas/R3aktTeam"
        )
        assert "team_uid" in {
            parameter["name"] for parameter in team_detail["parameters"]
        }

    team_missions = paths["/api/r3akt/teams/{team_uid}/missions"]["get"]
    assert (
        team_missions["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktMissionUidsResponse"
    )
    assert "team_uid" in {
        parameter["name"] for parameter in team_missions["parameters"]
    }

    team_mission_link = paths["/api/r3akt/teams/{team_uid}/missions/{mission_uid}"]
    for method in ("put", "delete"):
        operation = team_mission_link[method]
        assert (
            operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
            == "#/components/schemas/R3aktTeam"
        )
        assert {"team_uid", "mission_uid"}.issubset(
            {parameter["name"] for parameter in operation["parameters"]}
        )

    for method in ("get", "delete"):
        member_detail = paths["/api/r3akt/team-members/{team_member_uid}"][method]
        assert (
            member_detail["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
            == "#/components/schemas/R3aktTeamMember"
        )
        assert "team_member_uid" in {
            parameter["name"] for parameter in member_detail["parameters"]
        }

    member_clients = paths["/api/r3akt/team-members/{team_member_uid}/clients"]["get"]
    assert (
        member_clients["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktClientIdentitiesResponse"
    )
    assert "team_member_uid" in {
        parameter["name"] for parameter in member_clients["parameters"]
    }

    member_client_link = paths[
        "/api/r3akt/team-members/{team_member_uid}/clients/{client_identity}"
    ]
    for method in ("put", "delete"):
        operation = member_client_link[method]
        assert (
            operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
            == "#/components/schemas/R3aktTeamMember"
        )
        assert {"team_member_uid", "client_identity"}.issubset(
            {parameter["name"] for parameter in operation["parameters"]}
        )

    for method in ("get", "delete"):
        asset_detail = paths["/api/r3akt/assets/{asset_uid}"][method]
        assert (
            asset_detail["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
            == "#/components/schemas/R3aktAsset"
        )
        assert "asset_uid" in {
            parameter["name"] for parameter in asset_detail["parameters"]
        }

    assignment_assets = paths["/api/r3akt/assignments/{assignment_uid}/assets"]["put"]
    assert (
        assignment_assets["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktAssignmentAssetSetRequest"
    )
    assert (
        assignment_assets["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktMissionTaskAssignment"
    )
    assert "assignment_uid" in {
        parameter["name"] for parameter in assignment_assets["parameters"]
    }

    assignment_asset_link = paths[
        "/api/r3akt/assignments/{assignment_uid}/assets/{asset_uid}"
    ]
    for method in ("put", "delete"):
        operation = assignment_asset_link[method]
        assert (
            operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
            == "#/components/schemas/R3aktMissionTaskAssignment"
        )
        assert {"assignment_uid", "asset_uid"}.issubset(
            {parameter["name"] for parameter in operation["parameters"]}
        )


def test_openapi_checklist_mutation_contracts_reference_domain_schemas() -> None:
    paths = _spec_paths()

    assert (
        paths["/checklists"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktChecklistListResponse"
    )

    expected_mutations = {
        "/checklists": ("post", "R3aktChecklistCreateOnlineRequest"),
        "/checklists/offline": ("post", "R3aktChecklistCreateOfflineRequest"),
        "/checklists/import/csv": ("post", "R3aktChecklistImportCsvRequest"),
        "/checklists/{checklist_id}/tasks": (
            "post",
            "R3aktChecklistTaskAddRequest",
        ),
        "/checklists/{checklist_id}/tasks/{task_id}/status": (
            "post",
            "R3aktChecklistTaskStatusRequest",
        ),
        "/checklists/{checklist_id}/tasks/{task_id}/row-style": (
            "patch",
            "R3aktChecklistTaskRowStyleRequest",
        ),
        "/checklists/{checklist_id}/tasks/{task_id}/cells/{column_id}": (
            "patch",
            "R3aktChecklistTaskCellRequest",
        ),
    }
    for path, (method, request_schema) in expected_mutations.items():
        assert (
            paths[path][method]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
            == f"#/components/schemas/{request_schema}"
        )
        assert (
            paths[path][method]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
            == "#/components/schemas/R3aktChecklist"
        )

    cell_param_names = {
        parameter["name"]
        for parameter in paths["/checklists/{checklist_id}/tasks/{task_id}/cells/{column_id}"]["patch"]["parameters"]
    }
    assert {"checklist_id", "task_id", "column_id"}.issubset(cell_param_names)


def test_openapi_checklist_template_detail_and_feed_contracts_reference_domain_schemas() -> None:
    paths = _spec_paths()
    schemas = _spec()["components"]["schemas"]

    assert {
        "R3aktChecklistTemplateCreateRequest",
        "R3aktChecklistTemplateCloneRequest",
        "R3aktChecklistTemplateListResponse",
        "R3aktChecklistUpdateRequest",
        "R3aktChecklistSourceIdentityRequest",
        "R3aktChecklistFeedPublication",
    }.issubset(set(schemas))

    template_list_param_names = {
        parameter["name"] for parameter in paths["/checklists/templates"]["get"]["parameters"]
    }
    assert {"search", "sort_by"}.issubset(template_list_param_names)
    assert (
        paths["/checklists/templates"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktChecklistTemplateCreateRequest"
    )
    assert (
        paths["/checklists/templates"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktChecklistTemplate"
    )

    for method in ("get", "patch", "delete"):
        operation = paths["/checklists/templates/{template_id}"][method]
        assert (
            operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
            == "#/components/schemas/R3aktChecklistTemplate"
        )
        assert "template_id" in {
            parameter["name"] for parameter in operation["parameters"]
        }

    clone = paths["/checklists/templates/{template_id}/clone"]["post"]
    assert (
        clone["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktChecklistTemplateCloneRequest"
    )
    assert (
        clone["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktChecklistTemplate"
    )

    assert (
        paths["/checklists/{checklist_id}"]["patch"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktChecklistUpdateRequest"
    )
    assert (
        paths["/checklists/{checklist_id}"]["patch"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktChecklist"
    )
    assert (
        paths["/checklists/{checklist_id}"]["delete"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktChecklist"
    )

    for route in (
        "/checklists/{checklist_id}/join",
        "/checklists/{checklist_id}/upload",
    ):
        operation = paths[route]["post"]
        assert (
            operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
            == "#/components/schemas/R3aktChecklistSourceIdentityRequest"
        )
        assert (
            operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
            == "#/components/schemas/R3aktChecklist"
        )

    feed = paths["/checklists/{checklist_id}/feeds/{feed_id}"]["post"]
    assert (
        feed["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktChecklistSourceIdentityRequest"
    )
    assert (
        feed["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktChecklistFeedPublication"
    )
    feed_param_names = {parameter["name"] for parameter in feed["parameters"]}
    assert {"checklist_id", "feed_id"}.issubset(feed_param_names)


def test_openapi_r3akt_events_capabilities_and_rights_contracts() -> None:
    paths = _spec_paths()
    schemas = _spec()["components"]["schemas"]

    assert {
        "R3aktDomainEvent",
        "R3aktDomainSnapshot",
        "R3aktCapabilityGrantRequest",
        "R3aktCapabilityGrant",
        "R3aktCapabilityState",
    }.issubset(set(schemas))

    assert (
        paths["/api/r3akt/events"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["items"]["$ref"]
        == "#/components/schemas/R3aktDomainEvent"
    )
    assert (
        paths["/api/r3akt/snapshots"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["items"]["$ref"]
        == "#/components/schemas/R3aktDomainSnapshot"
    )
    assert (
        paths["/api/r3akt/capabilities/{identity}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/R3aktCapabilityState"
    )

    for method in ("put", "delete"):
        operation = paths["/api/r3akt/capabilities/{identity}/{capability}"][method]
        assert (
            operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
            == "#/components/schemas/R3aktCapabilityGrantRequest"
        )
        assert (
            operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
            == "#/components/schemas/R3aktCapabilityGrant"
        )

    rights_grant_params = {
        parameter["name"]
        for parameter in paths["/api/r3akt/rights/grants"]["get"]["parameters"]
    }
    assert {
        "subject_type",
        "subject_id",
        "operation",
        "scope_type",
        "scope_id",
    }.issubset(rights_grant_params)

    mission_access_params = {
        parameter["name"]
        for parameter in paths["/api/r3akt/rights/mission-access"]["get"]["parameters"]
    }
    assert {"mission_uid", "subject_type", "subject_id"}.issubset(
        mission_access_params
    )


def test_openapi_r3akt_mission_change_schema_includes_delta() -> None:
    schemas = _spec()["components"]["schemas"]
    mission_change = schemas["R3aktMissionChange"]
    mission_change_request = schemas["R3aktMissionChangeUpsertRequest"]

    assert "delta" in mission_change["properties"]
    assert mission_change["properties"]["delta"]["type"] == "object"
    assert "delta" in mission_change_request["properties"]


def test_openapi_r3akt_log_entry_schema_includes_callsign_and_optional_mission() -> None:
    schemas = _spec()["components"]["schemas"]
    log_entry = schemas["R3aktLogEntry"]
    log_entry_request = schemas["R3aktLogEntryUpsertRequest"]

    assert "callsign" in log_entry["properties"]
    assert log_entry["properties"]["callsign"]["type"] == "string"
    assert "mission_uid" in log_entry_request["properties"]
    assert log_entry_request["properties"]["mission_uid"]["nullable"] is True
