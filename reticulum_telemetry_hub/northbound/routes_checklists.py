"""Checklist backend routes aligned to the checklist AsyncAPI contract."""

from __future__ import annotations

from typing import Callable

from fastapi import Body
from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Query
from fastapi import status

from reticulum_telemetry_hub.mission_domain import MissionDomainService


def register_checklist_routes(
    app: FastAPI,
    *,
    domain: MissionDomainService,
    require_protected: Callable[[], None],
) -> None:
    """Register checklist contract routes."""

    @app.get("/checklists/templates", dependencies=[Depends(require_protected)])
    def list_templates(
        search: str | None = Query(default=None),
        sort_by: str | None = Query(default=None),
    ) -> dict:
        return {
            "templates": domain.list_checklist_templates(search=search, sort_by=sort_by)
        }

    @app.get("/checklists/templates/{template_id}", dependencies=[Depends(require_protected)])
    def get_template(template_id: str) -> dict:
        try:
            return domain.get_checklist_template(template_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.post("/checklists/templates", dependencies=[Depends(require_protected)])
    def create_template(payload: dict = Body(default_factory=dict)) -> dict:
        template = payload.get("template") if "template" in payload else payload
        if not isinstance(template, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="template payload must be an object",
            )
        try:
            return domain.create_checklist_template(template)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.patch("/checklists/templates/{template_id}", dependencies=[Depends(require_protected)])
    def update_template(template_id: str, payload: dict = Body(default_factory=dict)) -> dict:
        patch = payload.get("patch") if "patch" in payload else payload
        if not isinstance(patch, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="patch payload must be an object",
            )
        try:
            return domain.update_checklist_template(template_id, patch)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.post("/checklists/templates/{template_id}/clone", dependencies=[Depends(require_protected)])
    def clone_template(template_id: str, payload: dict = Body(default_factory=dict)) -> dict:
        template_name = str(payload.get("template_name") or "").strip()
        if not template_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="template_name is required",
            )
        try:
            return domain.clone_checklist_template(
                template_id,
                template_name=template_name,
                description=payload.get("description"),
                created_by_team_member_rns_identity=str(
                    payload.get("created_by_team_member_rns_identity") or "unknown"
                ),
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.delete("/checklists/templates/{template_id}", dependencies=[Depends(require_protected)])
    def delete_template(template_id: str) -> dict:
        try:
            return domain.delete_checklist_template(template_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.get("/checklists", dependencies=[Depends(require_protected)])
    def list_checklists(
        search: str | None = Query(default=None),
        sort_by: str | None = Query(default=None),
        state: str | None = Query(default=None),
    ) -> dict:
        _ = state  # state is accepted for contract compatibility
        return {
            "checklists": domain.list_active_checklists(search=search, sort_by=sort_by)
        }

    @app.post("/checklists", dependencies=[Depends(require_protected)])
    def create_checklist_online(payload: dict = Body(default_factory=dict)) -> dict:
        try:
            return domain.create_checklist_online(payload)
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.post("/checklists/offline", dependencies=[Depends(require_protected)])
    def create_checklist_offline(payload: dict = Body(default_factory=dict)) -> dict:
        try:
            return domain.create_checklist_offline(payload)
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.post("/checklists/import/csv", dependencies=[Depends(require_protected)])
    def import_checklist_csv(payload: dict = Body(default_factory=dict)) -> dict:
        try:
            return domain.import_checklist_csv(payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.post("/checklists/{checklist_id}/join", dependencies=[Depends(require_protected)])
    def join_checklist(checklist_id: str, payload: dict = Body(default_factory=dict)) -> dict:
        try:
            return domain.join_checklist(
                checklist_id,
                source_identity=payload.get("source_identity"),
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.get("/checklists/{checklist_id}", dependencies=[Depends(require_protected)])
    def get_checklist(checklist_id: str) -> dict:
        try:
            return domain.get_checklist(checklist_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.patch("/checklists/{checklist_id}", dependencies=[Depends(require_protected)])
    def update_checklist(checklist_id: str, payload: dict = Body(default_factory=dict)) -> dict:
        patch = payload.get("patch") if "patch" in payload else payload
        if not isinstance(patch, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="patch payload must be an object",
            )
        try:
            return domain.update_checklist(checklist_id, patch)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.delete("/checklists/{checklist_id}", dependencies=[Depends(require_protected)])
    def delete_checklist(checklist_id: str) -> dict:
        try:
            return domain.delete_checklist(checklist_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.post("/checklists/{checklist_id}/upload", dependencies=[Depends(require_protected)])
    def upload_checklist(checklist_id: str, payload: dict = Body(default_factory=dict)) -> dict:
        try:
            return domain.upload_checklist(
                checklist_id,
                source_identity=payload.get("source_identity"),
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.post("/checklists/{checklist_id}/feeds/{feed_id}", dependencies=[Depends(require_protected)])
    def publish_checklist_feed(
        checklist_id: str,
        feed_id: str,
        payload: dict = Body(default_factory=dict),
    ) -> dict:
        try:
            return domain.publish_checklist_feed(
                checklist_id,
                feed_id,
                source_identity=payload.get("source_identity"),
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.post("/checklists/{checklist_id}/tasks/{task_id}/status", dependencies=[Depends(require_protected)])
    def set_task_status(
        checklist_id: str,
        task_id: str,
        payload: dict = Body(default_factory=dict),
    ) -> dict:
        try:
            return domain.set_checklist_task_status(checklist_id, task_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.post("/checklists/{checklist_id}/tasks", dependencies=[Depends(require_protected)])
    def add_task_row(checklist_id: str, payload: dict = Body(default_factory=dict)) -> dict:
        try:
            return domain.add_checklist_task_row(checklist_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.delete("/checklists/{checklist_id}/tasks/{task_id}", dependencies=[Depends(require_protected)])
    def delete_task_row(checklist_id: str, task_id: str) -> dict:
        try:
            return domain.delete_checklist_task_row(checklist_id, task_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.patch("/checklists/{checklist_id}/tasks/{task_id}/row-style", dependencies=[Depends(require_protected)])
    def set_task_row_style(
        checklist_id: str,
        task_id: str,
        payload: dict = Body(default_factory=dict),
    ) -> dict:
        try:
            return domain.set_checklist_task_row_style(checklist_id, task_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.patch(
        "/checklists/{checklist_id}/tasks/{task_id}/cells/{column_id}",
        dependencies=[Depends(require_protected)],
    )
    def set_task_cell(
        checklist_id: str,
        task_id: str,
        column_id: str,
        payload: dict = Body(default_factory=dict),
    ) -> dict:
        try:
            return domain.set_checklist_task_cell(checklist_id, task_id, column_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
