"""REM-compatible routes for Emergency Action Message status snapshots."""

from __future__ import annotations

from typing import Callable

from fastapi import Body
from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Query
from fastapi import status

from reticulum_telemetry_hub.mission_domain.status_service import (
    EmergencyActionMessageService,
)
from reticulum_telemetry_hub.northbound.models import EamTeamSummaryPayload
from reticulum_telemetry_hub.northbound.models import EmergencyActionMessagePayload
from reticulum_telemetry_hub.northbound.models import EmergencyActionMessageUpsertPayload


def register_eam_routes(
    app: FastAPI,
    *,
    status_service: EmergencyActionMessageService,
    require_protected: Callable[[], None],
) -> None:
    """Register REM-compatible routes for member-scoped EAM status."""

    @app.get(
        "/api/EmergencyActionMessage",
        dependencies=[Depends(require_protected)],
        response_model=list[EmergencyActionMessagePayload],
    )
    def list_emergency_action_messages(
        team_uid: str | None = Query(default=None),
        overall_status: str | None = Query(default=None),
    ) -> list[dict]:
        try:
            return status_service.list_messages(
                team_uid=team_uid,
                overall_status=overall_status,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.post(
        "/api/EmergencyActionMessage",
        dependencies=[Depends(require_protected)],
        response_model=EmergencyActionMessagePayload,
    )
    def create_emergency_action_message(
        payload: EmergencyActionMessageUpsertPayload = Body(...)
    ) -> dict:
        try:
            return status_service.upsert_message(payload.model_dump(mode="json", exclude_none=True))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get(
        "/api/EmergencyActionMessage/latest/{team_member_uid}",
        dependencies=[Depends(require_protected)],
        response_model=EmergencyActionMessagePayload,
    )
    def get_latest_emergency_action_message(team_member_uid: str) -> dict:
        try:
            return status_service.get_latest_message(team_member_uid)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get(
        "/api/EmergencyActionMessage/team/{team_uid}/summary",
        dependencies=[Depends(require_protected)],
        response_model=EamTeamSummaryPayload,
    )
    def get_team_status_summary(team_uid: str) -> dict:
        try:
            return status_service.get_team_summary(team_uid)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get(
        "/api/EmergencyActionMessage/{callsign}",
        dependencies=[Depends(require_protected)],
        response_model=EmergencyActionMessagePayload,
    )
    def get_emergency_action_message(callsign: str) -> dict:
        try:
            return status_service.get_message_by_callsign(callsign)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.put(
        "/api/EmergencyActionMessage/{callsign}",
        dependencies=[Depends(require_protected)],
        response_model=EmergencyActionMessagePayload,
    )
    def update_emergency_action_message(
        callsign: str, payload: EmergencyActionMessageUpsertPayload = Body(...)
    ) -> dict:
        try:
            return status_service.upsert_message(
                payload.model_dump(mode="json", exclude_none=True),
                expected_callsign=callsign,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.delete(
        "/api/EmergencyActionMessage/{callsign}",
        dependencies=[Depends(require_protected)],
        response_model=EmergencyActionMessagePayload,
    )
    def delete_emergency_action_message(callsign: str) -> dict:
        try:
            return status_service.delete_message(callsign)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
