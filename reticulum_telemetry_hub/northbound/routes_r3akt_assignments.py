"""R3AKT asset, skill, and assignment routes."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Body
from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Query
from fastapi import status

from reticulum_telemetry_hub.mission_domain import MissionDomainService


def register_r3akt_assignment_routes(
    app: FastAPI,
    *,
    domain: MissionDomainService,
    require_protected: Callable[[], None],
) -> None:
    """Register R3AKT asset, skill, and assignment routes."""

    @app.get("/api/r3akt/assets", dependencies=[Depends(require_protected)])
    def list_assets(team_member_uid: str | None = Query(default=None)) -> list[dict]:
        return domain.list_assets(team_member_uid=team_member_uid)

    @app.post("/api/r3akt/assets", dependencies=[Depends(require_protected)])
    def upsert_asset(payload: dict = Body(default_factory=dict)) -> dict:
        try:
            return domain.upsert_asset(payload)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc

    @app.get("/api/r3akt/assets/{asset_uid}", dependencies=[Depends(require_protected)])
    def get_asset(asset_uid: str) -> dict:
        try:
            return domain.get_asset(asset_uid)
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from exc

    @app.delete(
        "/api/r3akt/assets/{asset_uid}", dependencies=[Depends(require_protected)]
    )
    def delete_asset(asset_uid: str) -> dict:
        try:
            return domain.delete_asset(asset_uid)
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from exc

    @app.get("/api/r3akt/skills", dependencies=[Depends(require_protected)])
    def list_skills() -> list[dict]:
        return domain.list_skills()

    @app.post("/api/r3akt/skills", dependencies=[Depends(require_protected)])
    def upsert_skill(payload: dict = Body(default_factory=dict)) -> dict:
        return domain.upsert_skill(payload)

    @app.get(
        "/api/r3akt/team-member-skills", dependencies=[Depends(require_protected)]
    )
    def list_team_member_skills(
        team_member_rns_identity: str | None = Query(default=None),
    ) -> list[dict]:
        return domain.list_team_member_skills(
            team_member_rns_identity=team_member_rns_identity
        )

    @app.post(
        "/api/r3akt/team-member-skills", dependencies=[Depends(require_protected)]
    )
    def upsert_team_member_skill(payload: dict = Body(default_factory=dict)) -> dict:
        try:
            return domain.upsert_team_member_skill(payload)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc

    @app.get(
        "/api/r3akt/task-skill-requirements",
        dependencies=[Depends(require_protected)],
    )
    def list_task_skill_requirements(
        task_uid: str | None = Query(default=None),
    ) -> list[dict]:
        return domain.list_task_skill_requirements(task_uid=task_uid)

    @app.post(
        "/api/r3akt/task-skill-requirements",
        dependencies=[Depends(require_protected)],
    )
    def upsert_task_skill_requirement(
        payload: dict = Body(default_factory=dict),
    ) -> dict:
        try:
            return domain.upsert_task_skill_requirement(payload)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc

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
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc

    @app.put(
        "/api/r3akt/assignments/{assignment_uid}/assets",
        dependencies=[Depends(require_protected)],
    )
    def set_assignment_assets(
        assignment_uid: str, payload: dict = Body(default_factory=dict)
    ) -> dict:
        assets = payload.get("assets")
        if not isinstance(assets, list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="assets must be a list",
            )
        try:
            return domain.set_assignment_assets(
                assignment_uid, [str(item) for item in assets]
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc

    @app.put(
        "/api/r3akt/assignments/{assignment_uid}/assets/{asset_uid}",
        dependencies=[Depends(require_protected)],
    )
    def link_assignment_asset(assignment_uid: str, asset_uid: str) -> dict:
        try:
            return domain.link_assignment_asset(assignment_uid, asset_uid)
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc

    @app.delete(
        "/api/r3akt/assignments/{assignment_uid}/assets/{asset_uid}",
        dependencies=[Depends(require_protected)],
    )
    def unlink_assignment_asset(assignment_uid: str, asset_uid: str) -> dict:
        try:
            return domain.unlink_assignment_asset(assignment_uid, asset_uid)
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
