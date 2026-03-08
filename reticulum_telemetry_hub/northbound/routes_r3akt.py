"""R3AKT domain registry and capability routes."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from fastapi import Body
from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Query
from fastapi import status

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.mission_domain import MissionDomainService


def register_r3akt_routes(
    app: FastAPI,
    *,
    api: ReticulumTelemetryHubAPI,
    domain: MissionDomainService,
    require_protected: Callable[[], None],
) -> None:
    """Register R3AKT registry/capability routes."""

    def _expand_tokens(value: str | None) -> set[str]:
        if not value:
            return set()
        return {
            item.strip().lower()
            for item in value.split(",")
            if item and item.strip()
        }

    def _parse_iso_datetime(value: object) -> datetime | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="expires_at must be ISO-8601",
            ) from exc

    @app.get("/api/r3akt/capabilities/{identity}", dependencies=[Depends(require_protected)])
    def get_identity_capabilities(identity: str) -> dict:
        return {
            "identity": identity,
            "capabilities": api.list_identity_capabilities(identity),
            "grants": api.list_capability_grants(identity=identity),
        }

    @app.put("/api/r3akt/capabilities/{identity}/{capability}", dependencies=[Depends(require_protected)])
    def grant_identity_capability(
        identity: str,
        capability: str,
        payload: dict | None = Body(default=None),
    ) -> dict:
        granted_by = None
        expires_at = None
        if isinstance(payload, dict):
            granted_by = payload.get("granted_by")
            expires_at = _parse_iso_datetime(payload.get("expires_at"))
        try:
            return api.grant_identity_capability(
                identity,
                capability,
                granted_by=granted_by,
                expires_at=expires_at,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.delete("/api/r3akt/capabilities/{identity}/{capability}", dependencies=[Depends(require_protected)])
    def revoke_identity_capability(
        identity: str,
        capability: str,
        payload: dict | None = Body(default=None),
    ) -> dict:
        granted_by = payload.get("granted_by") if isinstance(payload, dict) else None
        try:
            return api.revoke_identity_capability(
                identity,
                capability,
                granted_by=granted_by,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get("/api/r3akt/rights/definitions", dependencies=[Depends(require_protected)])
    def get_rights_definitions() -> dict:
        return api.rights.operation_definitions()

    @app.get("/api/r3akt/rights/subjects", dependencies=[Depends(require_protected)])
    def list_rights_subjects(
        mission_uid: str | None = Query(default=None),
    ) -> list[dict]:
        return api.list_team_member_subjects(mission_uid=mission_uid)

    @app.get("/api/r3akt/rights/grants", dependencies=[Depends(require_protected)])
    def list_operation_rights(
        subject_type: str | None = Query(default=None),
        subject_id: str | None = Query(default=None),
        operation: str | None = Query(default=None),
        scope_type: str | None = Query(default=None),
        scope_id: str | None = Query(default=None),
    ) -> list[dict]:
        try:
            return api.list_operation_rights(
                subject_type=subject_type,
                subject_id=subject_id,
                operation=operation,
                scope_type=scope_type,
                scope_id=scope_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.put("/api/r3akt/rights/grants", dependencies=[Depends(require_protected)])
    def grant_operation_right(payload: dict = Body(default_factory=dict)) -> dict:
        try:
            return api.grant_operation_right(
                str(payload.get("subject_type") or ""),
                str(payload.get("subject_id") or ""),
                str(payload.get("operation") or ""),
                scope_type=payload.get("scope_type"),
                scope_id=payload.get("scope_id"),
                granted_by=payload.get("granted_by"),
                expires_at=_parse_iso_datetime(payload.get("expires_at")),
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.delete("/api/r3akt/rights/grants", dependencies=[Depends(require_protected)])
    def revoke_operation_right(payload: dict = Body(default_factory=dict)) -> dict:
        try:
            return api.revoke_operation_right(
                str(payload.get("subject_type") or ""),
                str(payload.get("subject_id") or ""),
                str(payload.get("operation") or ""),
                scope_type=payload.get("scope_type"),
                scope_id=payload.get("scope_id"),
                granted_by=payload.get("granted_by"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get("/api/r3akt/rights/mission-access", dependencies=[Depends(require_protected)])
    def list_mission_access_assignments(
        mission_uid: str | None = Query(default=None),
        subject_type: str | None = Query(default=None),
        subject_id: str | None = Query(default=None),
    ) -> list[dict]:
        try:
            return api.list_mission_access_assignments(
                mission_uid=mission_uid,
                subject_type=subject_type,
                subject_id=subject_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.put("/api/r3akt/rights/mission-access", dependencies=[Depends(require_protected)])
    def assign_mission_access_role(payload: dict = Body(default_factory=dict)) -> dict:
        try:
            return api.assign_mission_access_role(
                str(payload.get("mission_uid") or ""),
                str(payload.get("subject_type") or ""),
                str(payload.get("subject_id") or ""),
                role=payload.get("role"),
                assigned_by=payload.get("assigned_by"),
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.delete("/api/r3akt/rights/mission-access", dependencies=[Depends(require_protected)])
    def revoke_mission_access_role(payload: dict = Body(default_factory=dict)) -> dict:
        try:
            return api.revoke_mission_access_role(
                str(payload.get("mission_uid") or ""),
                str(payload.get("subject_type") or ""),
                str(payload.get("subject_id") or ""),
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get("/api/r3akt/events", dependencies=[Depends(require_protected)])
    def list_domain_events(limit: int = Query(default=200, ge=1, le=2000)) -> list[dict]:
        return domain.list_domain_events(limit=limit)

    @app.get("/api/r3akt/snapshots", dependencies=[Depends(require_protected)])
    def list_domain_snapshots(limit: int = Query(default=200, ge=1, le=2000)) -> list[dict]:
        return domain.list_domain_snapshots(limit=limit)

    @app.get("/api/r3akt/missions", dependencies=[Depends(require_protected)])
    def list_missions(expand: str | None = Query(default=None)) -> list[dict]:
        expand_values = _expand_tokens(expand)
        expand_topic = "topic" in expand_values or "all" in expand_values
        return domain.list_missions(expand_topic=expand_topic, expand=expand_values)

    @app.post("/api/r3akt/missions", dependencies=[Depends(require_protected)])
    def upsert_mission(payload: dict = Body(default_factory=dict)) -> dict:
        try:
            return domain.upsert_mission(payload)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    @app.get("/api/r3akt/missions/{mission_uid}", dependencies=[Depends(require_protected)])
    def get_mission(
        mission_uid: str,
        expand: str | None = Query(default=None),
    ) -> dict:
        expand_values = _expand_tokens(expand)
        expand_topic = "topic" in expand_values or "all" in expand_values
        try:
            return domain.get_mission(
                mission_uid,
                expand_topic=expand_topic,
                expand=expand_values,
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.patch("/api/r3akt/missions/{mission_uid}", dependencies=[Depends(require_protected)])
    def patch_mission(mission_uid: str, payload: dict = Body(default_factory=dict)) -> dict:
        patch = payload.get("patch") if "patch" in payload else payload
        if not isinstance(patch, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="patch payload must be an object",
            )
        try:
            return domain.patch_mission(mission_uid, patch)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.delete("/api/r3akt/missions/{mission_uid}", dependencies=[Depends(require_protected)])
    def delete_mission(mission_uid: str) -> dict:
        try:
            return domain.delete_mission(mission_uid)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.put("/api/r3akt/missions/{mission_uid}/parent", dependencies=[Depends(require_protected)])
    def set_mission_parent(mission_uid: str, payload: dict = Body(default_factory=dict)) -> dict:
        parent_uid = payload.get("parent_uid")
        try:
            return domain.set_mission_parent(mission_uid, parent_uid=parent_uid)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get("/api/r3akt/missions/{mission_uid}/zones", dependencies=[Depends(require_protected)])
    def list_mission_zones(mission_uid: str) -> dict:
        try:
            return {"zone_ids": domain.list_mission_zones(mission_uid)}
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.put("/api/r3akt/missions/{mission_uid}/zones/{zone_id}", dependencies=[Depends(require_protected)])
    def link_mission_zone(mission_uid: str, zone_id: str) -> dict:
        try:
            return domain.link_mission_zone(mission_uid, zone_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.delete("/api/r3akt/missions/{mission_uid}/zones/{zone_id}", dependencies=[Depends(require_protected)])
    def unlink_mission_zone(mission_uid: str, zone_id: str) -> dict:
        try:
            return domain.unlink_mission_zone(mission_uid, zone_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get("/api/r3akt/missions/{mission_uid}/markers", dependencies=[Depends(require_protected)])
    def list_mission_markers(mission_uid: str) -> dict:
        try:
            return {"marker_ids": domain.list_mission_markers(mission_uid)}
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.put("/api/r3akt/missions/{mission_uid}/markers/{marker_id}", dependencies=[Depends(require_protected)])
    def link_mission_marker(mission_uid: str, marker_id: str) -> dict:
        try:
            return domain.link_mission_marker(mission_uid, marker_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.delete("/api/r3akt/missions/{mission_uid}/markers/{marker_id}", dependencies=[Depends(require_protected)])
    def unlink_mission_marker(mission_uid: str, marker_id: str) -> dict:
        try:
            return domain.unlink_mission_marker(mission_uid, marker_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get("/api/r3akt/missions/{mission_uid}/rde", dependencies=[Depends(require_protected)])
    def get_mission_rde(mission_uid: str) -> dict:
        try:
            return domain.get_mission_rde(mission_uid)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.put("/api/r3akt/missions/{mission_uid}/rde", dependencies=[Depends(require_protected)])
    def put_mission_rde(mission_uid: str, payload: dict = Body(default_factory=dict)) -> dict:
        role = payload.get("role")
        try:
            return domain.upsert_mission_rde(mission_uid, str(role or ""))
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get("/api/r3akt/mission-changes", dependencies=[Depends(require_protected)])
    def list_mission_changes(mission_uid: str | None = Query(default=None)) -> list[dict]:
        return domain.list_mission_changes(mission_uid=mission_uid)

    @app.post("/api/r3akt/mission-changes", dependencies=[Depends(require_protected)])
    def upsert_mission_change(payload: dict = Body(default_factory=dict)) -> dict:
        try:
            return domain.upsert_mission_change(payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get("/api/r3akt/log-entries", dependencies=[Depends(require_protected)])
    def list_log_entries(
        mission_uid: str | None = Query(default=None),
        marker_ref: str | None = Query(default=None),
    ) -> list[dict]:
        return domain.list_log_entries(mission_uid=mission_uid, marker_ref=marker_ref)

    @app.post("/api/r3akt/log-entries", dependencies=[Depends(require_protected)])
    def upsert_log_entry(payload: dict = Body(default_factory=dict)) -> dict:
        try:
            return domain.upsert_log_entry(payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get("/api/r3akt/teams", dependencies=[Depends(require_protected)])
    def list_teams(mission_uid: str | None = Query(default=None)) -> list[dict]:
        return domain.list_teams(mission_uid=mission_uid)

    @app.post("/api/r3akt/teams", dependencies=[Depends(require_protected)])
    def upsert_team(payload: dict = Body(default_factory=dict)) -> dict:
        try:
            return domain.upsert_team(payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get("/api/r3akt/teams/{team_uid}", dependencies=[Depends(require_protected)])
    def get_team(team_uid: str) -> dict:
        try:
            return domain.get_team(team_uid)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.delete("/api/r3akt/teams/{team_uid}", dependencies=[Depends(require_protected)])
    def delete_team(team_uid: str) -> dict:
        try:
            return domain.delete_team(team_uid)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.get("/api/r3akt/teams/{team_uid}/missions", dependencies=[Depends(require_protected)])
    def list_team_missions(team_uid: str) -> dict:
        try:
            return {"mission_uids": domain.list_team_missions(team_uid)}
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.put(
        "/api/r3akt/teams/{team_uid}/missions/{mission_uid}",
        dependencies=[Depends(require_protected)],
    )
    def link_team_mission(team_uid: str, mission_uid: str) -> dict:
        try:
            return domain.link_team_mission(team_uid, mission_uid)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.delete(
        "/api/r3akt/teams/{team_uid}/missions/{mission_uid}",
        dependencies=[Depends(require_protected)],
    )
    def unlink_team_mission(team_uid: str, mission_uid: str) -> dict:
        try:
            return domain.unlink_team_mission(team_uid, mission_uid)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get("/api/r3akt/team-members", dependencies=[Depends(require_protected)])
    def list_team_members(team_uid: str | None = Query(default=None)) -> list[dict]:
        return domain.list_team_members(team_uid=team_uid)

    @app.post("/api/r3akt/team-members", dependencies=[Depends(require_protected)])
    def upsert_team_member(payload: dict = Body(default_factory=dict)) -> dict:
        try:
            return domain.upsert_team_member(payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get("/api/r3akt/team-members/{team_member_uid}", dependencies=[Depends(require_protected)])
    def get_team_member(team_member_uid: str) -> dict:
        try:
            return domain.get_team_member(team_member_uid)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.delete("/api/r3akt/team-members/{team_member_uid}", dependencies=[Depends(require_protected)])
    def delete_team_member(team_member_uid: str) -> dict:
        try:
            return domain.delete_team_member(team_member_uid)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.get("/api/r3akt/team-members/{team_member_uid}/clients", dependencies=[Depends(require_protected)])
    def list_team_member_clients(team_member_uid: str) -> dict:
        try:
            return {"client_identities": domain.list_team_member_clients(team_member_uid)}
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.put(
        "/api/r3akt/team-members/{team_member_uid}/clients/{client_identity}",
        dependencies=[Depends(require_protected)],
    )
    def link_team_member_client(team_member_uid: str, client_identity: str) -> dict:
        try:
            return domain.link_team_member_client(team_member_uid, client_identity)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.delete(
        "/api/r3akt/team-members/{team_member_uid}/clients/{client_identity}",
        dependencies=[Depends(require_protected)],
    )
    def unlink_team_member_client(team_member_uid: str, client_identity: str) -> dict:
        try:
            return domain.unlink_team_member_client(team_member_uid, client_identity)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get("/api/r3akt/assets", dependencies=[Depends(require_protected)])
    def list_assets(team_member_uid: str | None = Query(default=None)) -> list[dict]:
        return domain.list_assets(team_member_uid=team_member_uid)

    @app.post("/api/r3akt/assets", dependencies=[Depends(require_protected)])
    def upsert_asset(payload: dict = Body(default_factory=dict)) -> dict:
        try:
            return domain.upsert_asset(payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get("/api/r3akt/assets/{asset_uid}", dependencies=[Depends(require_protected)])
    def get_asset(asset_uid: str) -> dict:
        try:
            return domain.get_asset(asset_uid)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.delete("/api/r3akt/assets/{asset_uid}", dependencies=[Depends(require_protected)])
    def delete_asset(asset_uid: str) -> dict:
        try:
            return domain.delete_asset(asset_uid)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.get("/api/r3akt/skills", dependencies=[Depends(require_protected)])
    def list_skills() -> list[dict]:
        return domain.list_skills()

    @app.post("/api/r3akt/skills", dependencies=[Depends(require_protected)])
    def upsert_skill(payload: dict = Body(default_factory=dict)) -> dict:
        return domain.upsert_skill(payload)

    @app.get("/api/r3akt/team-member-skills", dependencies=[Depends(require_protected)])
    def list_team_member_skills(
        team_member_rns_identity: str | None = Query(default=None),
    ) -> list[dict]:
        return domain.list_team_member_skills(
            team_member_rns_identity=team_member_rns_identity
        )

    @app.post("/api/r3akt/team-member-skills", dependencies=[Depends(require_protected)])
    def upsert_team_member_skill(payload: dict = Body(default_factory=dict)) -> dict:
        try:
            return domain.upsert_team_member_skill(payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get("/api/r3akt/task-skill-requirements", dependencies=[Depends(require_protected)])
    def list_task_skill_requirements(task_uid: str | None = Query(default=None)) -> list[dict]:
        return domain.list_task_skill_requirements(task_uid=task_uid)

    @app.post("/api/r3akt/task-skill-requirements", dependencies=[Depends(require_protected)])
    def upsert_task_skill_requirement(payload: dict = Body(default_factory=dict)) -> dict:
        try:
            return domain.upsert_task_skill_requirement(payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get("/api/r3akt/assignments", dependencies=[Depends(require_protected)])
    def list_assignments(
        mission_uid: str | None = Query(default=None),
        task_uid: str | None = Query(default=None),
    ) -> list[dict]:
        return domain.list_assignments(mission_uid=mission_uid, task_uid=task_uid)

    @app.post("/api/r3akt/assignments", dependencies=[Depends(require_protected)])
    def upsert_assignment(payload: dict = Body(default_factory=dict)) -> dict:
        try:
            return domain.upsert_assignment(payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.put("/api/r3akt/assignments/{assignment_uid}/assets", dependencies=[Depends(require_protected)])
    def set_assignment_assets(assignment_uid: str, payload: dict = Body(default_factory=dict)) -> dict:
        assets = payload.get("assets")
        if not isinstance(assets, list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="assets must be a list",
            )
        try:
            return domain.set_assignment_assets(assignment_uid, [str(item) for item in assets])
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.put("/api/r3akt/assignments/{assignment_uid}/assets/{asset_uid}", dependencies=[Depends(require_protected)])
    def link_assignment_asset(assignment_uid: str, asset_uid: str) -> dict:
        try:
            return domain.link_assignment_asset(assignment_uid, asset_uid)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.delete("/api/r3akt/assignments/{assignment_uid}/assets/{asset_uid}", dependencies=[Depends(require_protected)])
    def unlink_assignment_asset(assignment_uid: str, asset_uid: str) -> dict:
        try:
            return domain.unlink_assignment_asset(assignment_uid, asset_uid)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
