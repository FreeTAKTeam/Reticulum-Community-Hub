"""Extended REST route coverage for northbound API."""
# pylint: disable=import-error

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from reticulum_telemetry_hub.api.marker_service import MarkerUpdateResult
from reticulum_telemetry_hub.api.models import Marker
from reticulum_telemetry_hub.api.models import Zone
from reticulum_telemetry_hub.api.models import ZonePoint
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.api.storage import HubStorage
from reticulum_telemetry_hub.api.zone_service import ZoneUpdateResult
from reticulum_telemetry_hub.config import HubConfigurationManager
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_enum import (
    SID_LOCATION,
    SID_TIME,
)
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.mission_domain import MissionDomainService
from reticulum_telemetry_hub.mission_sync.rust_bridge import RustMissionSyncBridge
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandEnvelope
from reticulum_telemetry_hub.northbound.app import create_app
from reticulum_telemetry_hub.northbound.auth import ApiAuth
from reticulum_telemetry_hub.northbound.routes_rest import register_core_routes
from reticulum_telemetry_hub.northbound.services import NorthboundServices
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog
from reticulum_telemetry_hub.reticulum_server.runtime_events import (
    report_nonfatal_exception,
)
from tests.factories import build_location_payload
from tests.test_rth_api import RustTopicSubscriberApi


FIELD_RESULTS = 10
FIELD_GROUP = 11
FIELD_EVENT = 13


class RustR3aktDomain:
    """R3AKT route domain subset backed by the Rust RCH bridge."""

    def __init__(self, bridge: RustMissionSyncBridge) -> None:
        self._bridge = bridge

    def upsert_mission(self, payload: dict[str, object]) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.mission.upsert",
            payload,
        )

    def get_mission(
        self,
        mission_uid: str,
        *,
        expand_topic: bool = False,
        expand: set[str] | None = None,
    ) -> dict[str, object]:
        _ = expand_topic
        mission = _run_rust_command(
            self._bridge,
            "mission.registry.mission.get",
            {"mission_uid": mission_uid},
        )
        expand_values = expand or set()
        if "all" in expand_values or "teams" in expand_values:
            mission["teams"] = self.list_teams(mission_uid=mission_uid)
        if "all" in expand_values or "team_members" in expand_values:
            team_uids = [
                str(team.get("uid"))
                for team in self.list_teams(mission_uid=mission_uid)
                if team.get("uid")
            ]
            mission["team_members"] = [
                member
                for team_uid in team_uids
                for member in self.list_team_members(team_uid=team_uid)
            ]
        if "all" in expand_values or "assets" in expand_values:
            members = mission.get("team_members")
            if not isinstance(members, list):
                members = [
                    member
                    for team in self.list_teams(mission_uid=mission_uid)
                    for member in self.list_team_members(team_uid=str(team.get("uid") or ""))
                ]
            mission["assets"] = [
                asset
                for member in members
                if isinstance(member, dict)
                for asset in self.list_assets(
                    team_member_uid=str(member.get("uid") or "")
                )
            ]
        if "all" in expand_values or "mission_changes" in expand_values:
            mission["mission_changes"] = self.list_mission_changes(mission_uid=mission_uid)
        if "all" in expand_values or "log_entries" in expand_values:
            mission["log_entries"] = self.list_log_entries(mission_uid=mission_uid)
        if "all" in expand_values or "assignments" in expand_values:
            mission["assignments"] = self.list_assignments(mission_uid=mission_uid)
        if "all" in expand_values or "checklists" in expand_values:
            mission["checklists"] = [
                checklist
                for checklist in self.list_active_checklists()
                if checklist.get("mission_id") == mission_uid
            ]
        if "all" in expand_values or "mission_rde" in expand_values:
            mission["mission_rde"] = self.get_mission_rde(mission_uid)
        return mission

    def list_missions(
        self,
        *,
        expand_topic: bool = False,
        expand: set[str] | None = None,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        _ = expand_topic, expand
        return _run_rust_command(
            self._bridge,
            "mission.registry.mission.list",
            {"limit": limit},
        )["missions"]

    def patch_mission(
        self,
        mission_uid: str,
        patch: dict[str, object],
    ) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.mission.patch",
            {"mission_uid": mission_uid, "patch": patch},
        )

    def delete_mission(self, mission_uid: str) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.mission.delete",
            {"mission_uid": mission_uid},
        )

    def set_mission_parent(
        self,
        mission_uid: str,
        *,
        parent_uid: str | None = None,
    ) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.mission.parent.set",
            {"mission_uid": mission_uid, "parent_uid": parent_uid},
        )

    def list_mission_markers(self, mission_uid: str) -> list[str]:
        mission = self.get_mission(mission_uid)
        return [str(marker_id) for marker_id in mission.get("markers", [])]

    def list_mission_zones(self, mission_uid: str) -> list[str]:
        mission = self.get_mission(mission_uid)
        return [str(zone_id) for zone_id in mission.get("zones", [])]

    def list_checklist_templates(
        self,
        *,
        search: str | None = None,
        sort_by: str | None = None,
    ) -> list[dict[str, object]]:
        _run_rust_checklist_command(self._bridge, "checklist.template.list", {})
        templates = [self._checklist_template_value(row) for row in self._snapshot_rows("checklist_templates")]
        if search:
            lowered = search.lower()
            templates = [
                template
                for template in templates
                if lowered in str(template.get("template_name") or "").lower()
            ]
        if sort_by:
            templates.sort(key=lambda item: str(item.get(sort_by) or ""))
        return templates

    def get_checklist_template(self, template_uid: str) -> dict[str, object]:
        row = self._find_snapshot_row("checklist_templates", "uid", template_uid)
        if row is None:
            raise KeyError(f"Checklist template '{template_uid}' not found")
        return self._checklist_template_value(row)

    def create_checklist_template(self, template: dict[str, object]) -> dict[str, object]:
        before = self._snapshot_ids("checklist_templates", "uid")
        _run_rust_checklist_command(
            self._bridge,
            "checklist.template.create",
            {"template": template},
        )
        return self._new_or_named_template(before, str(template.get("uid") or ""))

    def update_checklist_template(
        self,
        template_uid: str,
        patch: dict[str, object],
    ) -> dict[str, object]:
        _run_rust_checklist_command(
            self._bridge,
            "checklist.template.update",
            {"template_uid": template_uid, "patch": patch},
        )
        return self.get_checklist_template(template_uid)

    def clone_checklist_template(
        self,
        template_uid: str,
        *,
        template_name: str,
        description: str | None = None,
        created_by_team_member_rns_identity: str | None = None,
    ) -> dict[str, object]:
        before = self._snapshot_ids("checklist_templates", "uid")
        args: dict[str, object] = {
            "source_template_uid": template_uid,
            "template_name": template_name,
        }
        if description is not None:
            args["description"] = description
        if created_by_team_member_rns_identity is not None:
            args["created_by_team_member_rns_identity"] = (
                created_by_team_member_rns_identity
            )
        _run_rust_checklist_command(self._bridge, "checklist.template.clone", args)
        return self._new_or_named_template(before, "")

    def delete_checklist_template(self, template_uid: str) -> dict[str, object]:
        template = self.get_checklist_template(template_uid)
        _run_rust_checklist_command(
            self._bridge,
            "checklist.template.delete",
            {"template_uid": template_uid},
        )
        return template

    def list_active_checklists(
        self,
        *,
        search: str | None = None,
        sort_by: str | None = None,
    ) -> list[dict[str, object]]:
        _run_rust_checklist_command(self._bridge, "checklist.list.active", {})
        checklists = [self._checklist_value(row) for row in self._snapshot_rows("checklists")]
        if search:
            lowered = search.lower()
            checklists = [
                checklist
                for checklist in checklists
                if lowered in str(checklist.get("name") or "").lower()
            ]
        if sort_by:
            checklists.sort(key=lambda item: str(item.get(sort_by) or ""))
        return checklists

    def create_checklist_online(self, payload: dict[str, object]) -> dict[str, object]:
        before = self._snapshot_ids("checklists", "uid")
        _run_rust_checklist_command(self._bridge, "checklist.create.online", payload)
        return self._new_or_named_checklist(before, str(payload.get("checklist_uid") or payload.get("uid") or ""))

    def create_checklist_offline(self, payload: dict[str, object]) -> dict[str, object]:
        before = self._snapshot_ids("checklists", "uid")
        _run_rust_checklist_command(self._bridge, "checklist.create.offline", payload)
        return self._new_or_named_checklist(before, str(payload.get("checklist_uid") or payload.get("uid") or ""))

    def import_checklist_csv(self, payload: dict[str, object]) -> dict[str, object]:
        before = self._snapshot_ids("checklists", "uid")
        _run_rust_checklist_command(self._bridge, "checklist.import.csv", payload)
        return self._new_or_named_checklist(before, "")

    def join_checklist(
        self,
        checklist_uid: str,
        *,
        source_identity: str | None = None,
    ) -> dict[str, object]:
        _run_rust_checklist_command(
            self._bridge,
            "checklist.join",
            {"checklist_uid": checklist_uid, "source_identity": source_identity},
        )
        return self.get_checklist(checklist_uid)

    def get_checklist(self, checklist_uid: str) -> dict[str, object]:
        row = self._find_snapshot_row("checklists", "uid", checklist_uid)
        if row is None:
            raise KeyError(f"Checklist '{checklist_uid}' not found")
        return self._checklist_value(row)

    def update_checklist(
        self,
        checklist_uid: str,
        patch: dict[str, object],
    ) -> dict[str, object]:
        _run_rust_checklist_command(
            self._bridge,
            "checklist.update",
            {"checklist_uid": checklist_uid, "patch": patch},
        )
        return self.get_checklist(checklist_uid)

    def delete_checklist(self, checklist_uid: str) -> dict[str, object]:
        checklist = self.get_checklist(checklist_uid)
        _run_rust_checklist_command(
            self._bridge,
            "checklist.delete",
            {"checklist_uid": checklist_uid},
        )
        return checklist

    def upload_checklist(
        self,
        checklist_uid: str,
        *,
        source_identity: str | None = None,
    ) -> dict[str, object]:
        _run_rust_checklist_command(
            self._bridge,
            "checklist.upload",
            {"checklist_uid": checklist_uid, "source_identity": source_identity},
        )
        return self.get_checklist(checklist_uid)

    def publish_checklist_feed(
        self,
        checklist_uid: str,
        mission_feed_uid: str,
        *,
        source_identity: str | None = None,
    ) -> dict[str, object]:
        before = self._snapshot_ids("checklist_feed_publications", "publication_uid")
        _run_rust_checklist_command(
            self._bridge,
            "checklist.feed.publish",
            {
                "checklist_uid": checklist_uid,
                "mission_feed_uid": mission_feed_uid,
                "source_identity": source_identity,
            },
        )
        publications = self._snapshot_rows("checklist_feed_publications")
        for row in publications:
            if str(row.get("publication_uid") or "") not in before:
                return self._checklist_feed_value(row)
        if publications:
            return self._checklist_feed_value(publications[-1])
        raise KeyError(f"Checklist '{checklist_uid}' feed publication not found")

    def add_checklist_task_row(
        self,
        checklist_uid: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        args = {"checklist_uid": checklist_uid, **payload}
        _run_rust_checklist_command(self._bridge, "checklist.task.row.add", args)
        return self.get_checklist(checklist_uid)

    def delete_checklist_task_row(
        self,
        checklist_uid: str,
        task_uid: str,
    ) -> dict[str, object]:
        _run_rust_checklist_command(
            self._bridge,
            "checklist.task.row.delete",
            {"checklist_uid": checklist_uid, "task_uid": task_uid},
        )
        return self.get_checklist(checklist_uid)

    def set_checklist_task_row_style(
        self,
        checklist_uid: str,
        task_uid: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        _run_rust_checklist_command(
            self._bridge,
            "checklist.task.row.style.set",
            {"checklist_uid": checklist_uid, "task_uid": task_uid, **payload},
        )
        return self.get_checklist(checklist_uid)

    def set_checklist_task_cell(
        self,
        checklist_uid: str,
        task_uid: str,
        column_uid: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        _run_rust_checklist_command(
            self._bridge,
            "checklist.task.cell.set",
            {
                "checklist_uid": checklist_uid,
                "task_uid": task_uid,
                "column_uid": column_uid,
                **payload,
            },
        )
        return self.get_checklist(checklist_uid)

    def set_checklist_task_status(
        self,
        checklist_uid: str,
        task_uid: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        _run_rust_checklist_command(
            self._bridge,
            "checklist.task.status.set",
            {"checklist_uid": checklist_uid, "task_uid": task_uid, **payload},
        )
        return self.get_checklist(checklist_uid)

    def _new_or_named_template(
        self,
        before: set[str],
        requested_uid: str,
    ) -> dict[str, object]:
        if requested_uid:
            return self.get_checklist_template(requested_uid)
        for row in self._snapshot_rows("checklist_templates"):
            if str(row.get("uid") or "") not in before:
                return self._checklist_template_value(row)
        raise KeyError("Checklist template was not created")

    def _new_or_named_checklist(
        self,
        before: set[str],
        requested_uid: str,
    ) -> dict[str, object]:
        if requested_uid:
            return self.get_checklist(requested_uid)
        for row in self._snapshot_rows("checklists"):
            if str(row.get("uid") or "") not in before:
                return self._checklist_value(row)
        raise KeyError("Checklist was not created")

    def _snapshot_rows(self, key: str) -> list[dict[str, object]]:
        rows = self._bridge.state_snapshot().get(key)
        assert isinstance(rows, list)
        return [dict(row) for row in rows if isinstance(row, dict)]

    def _snapshot_ids(self, key: str, field: str) -> set[str]:
        return {str(row.get(field) or "") for row in self._snapshot_rows(key)}

    def _find_snapshot_row(
        self,
        key: str,
        field: str,
        value: str,
    ) -> dict[str, object] | None:
        for row in self._snapshot_rows(key):
            if str(row.get(field) or "") == value:
                return row
        return None

    def _checklist_template_value(self, row: dict[str, object]) -> dict[str, object]:
        uid = str(row.get("uid") or "")
        return {
            "uid": uid,
            "template_name": row.get("template_name"),
            "description": row.get("description") or "",
            "created_by_team_member_rns_identity": row.get(
                "created_by_team_member_rns_identity"
            ),
            "source_template_uid": row.get("source_template_uid"),
            "server_only": row.get("server_only") or False,
            "columns": [
                self._checklist_column_value(column)
                for column in self._snapshot_rows("checklist_columns")
                if str(column.get("template_uid") or "") == uid
            ],
        }

    def _checklist_value(self, row: dict[str, object]) -> dict[str, object]:
        uid = str(row.get("uid") or "")
        return {
            "uid": uid,
            "mission_id": row.get("mission_uid"),
            "template_uid": row.get("template_uid"),
            "template_version": row.get("template_version"),
            "template_name": row.get("template_name"),
            "name": row.get("name"),
            "description": row.get("description") or "",
            "mode": row.get("mode"),
            "sync_state": row.get("sync_state"),
            "origin_type": row.get("origin_type"),
            "checklist_status": row.get("checklist_status"),
            "progress_percent": row.get("progress_percent") or 0,
            "counts": {
                "pending_count": row.get("pending_count") or 0,
                "late_count": row.get("late_count") or 0,
                "complete_count": row.get("complete_count") or 0,
            },
            "columns": [
                self._checklist_column_value(column)
                for column in self._snapshot_rows("checklist_columns")
                if str(column.get("checklist_uid") or "") == uid
            ],
            "tasks": [
                self._checklist_task_value(task)
                for task in self._snapshot_rows("checklist_tasks")
                if str(task.get("checklist_uid") or "") == uid
            ],
            "feed_publications": [
                self._checklist_feed_value(publication)
                for publication in self._snapshot_rows("checklist_feed_publications")
                if str(publication.get("checklist_uid") or "") == uid
            ],
        }

    @staticmethod
    def _checklist_column_value(row: dict[str, object]) -> dict[str, object]:
        return {
            "column_uid": row.get("column_uid"),
            "column_name": row.get("column_name"),
            "display_order": row.get("display_order"),
            "column_type": row.get("column_type"),
            "column_editable": row.get("column_editable"),
            "background_color": row.get("background_color"),
            "text_color": row.get("text_color"),
            "is_removable": row.get("is_removable"),
            "system_key": row.get("system_key"),
        }

    def _checklist_task_value(self, row: dict[str, object]) -> dict[str, object]:
        task_uid = str(row.get("task_uid") or "")
        return {
            "task_uid": task_uid,
            "number": row.get("number"),
            "user_status": row.get("user_status"),
            "task_status": row.get("task_status"),
            "is_late": row.get("is_late") or False,
            "custom_status": row.get("custom_status"),
            "due_relative_minutes": row.get("due_relative_minutes"),
            "notes": row.get("notes"),
            "row_background_color": row.get("row_background_color"),
            "line_break_enabled": row.get("line_break_enabled") or False,
            "completed_by_team_member_rns_identity": row.get(
                "completed_by_team_member_rns_identity"
            ),
            "legacy_value": row.get("legacy_value"),
            "cells": [
                self._checklist_cell_value(cell)
                for cell in self._snapshot_rows("checklist_cells")
                if str(cell.get("task_uid") or "") == task_uid
            ],
        }

    @staticmethod
    def _checklist_cell_value(row: dict[str, object]) -> dict[str, object]:
        return {
            "cell_uid": row.get("cell_uid"),
            "task_uid": row.get("task_uid"),
            "column_uid": row.get("column_uid"),
            "value": row.get("value"),
            "updated_by_team_member_rns_identity": row.get(
                "updated_by_team_member_rns_identity"
            ),
        }

    @staticmethod
    def _checklist_feed_value(row: dict[str, object]) -> dict[str, object]:
        return {
            "publication_uid": row.get("publication_uid"),
            "checklist_uid": row.get("checklist_uid"),
            "mission_feed_uid": row.get("mission_feed_uid"),
            "published_by_team_member_rns_identity": row.get(
                "published_by_team_member_rns_identity"
            ),
        }

    def link_mission_marker(self, mission_uid: str, marker_id: str) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.mission.marker.link",
            {"mission_uid": mission_uid, "marker_id": marker_id},
        )

    def unlink_mission_marker(self, mission_uid: str, marker_id: str) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.mission.marker.unlink",
            {"mission_uid": mission_uid, "marker_id": marker_id},
        )

    def link_mission_zone(self, mission_uid: str, zone_id: str) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.mission.zone.link",
            {"mission_uid": mission_uid, "zone_id": zone_id},
        )

    def unlink_mission_zone(self, mission_uid: str, zone_id: str) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.mission.zone.unlink",
            {"mission_uid": mission_uid, "zone_id": zone_id},
        )

    def upsert_mission_rde(self, mission_uid: str, role: str) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.mission.rde.set",
            {"mission_uid": mission_uid, "role": role},
        )

    def get_mission_rde(self, mission_uid: str) -> dict[str, object]:
        mission = self.get_mission(mission_uid)
        role = mission.get("mission_rde_role")
        if role is None:
            raise KeyError(f"Mission RDE for '{mission_uid}' not found")
        return {"mission_uid": mission_uid, "role": role}

    def upsert_mission_change(self, payload: dict[str, object]) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.mission_change.upsert",
            payload,
        )

    def list_mission_changes(
        self,
        mission_uid: str | None = None,
    ) -> list[dict[str, object]]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.mission_change.list",
            {"mission_uid": mission_uid},
        )["mission_changes"]

    def upsert_log_entry(self, payload: dict[str, object]) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.log_entry.upsert",
            payload,
        )

    def list_log_entries(
        self,
        mission_uid: str | None = None,
        marker_ref: str | None = None,
    ) -> list[dict[str, object]]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.log_entry.list",
            {"mission_uid": mission_uid, "marker_ref": marker_ref},
        )["log_entries"]

    def upsert_team(self, payload: dict[str, object]) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.team.upsert",
            payload,
        )

    def list_teams(self, mission_uid: str | None = None) -> list[dict[str, object]]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.team.list",
            {"mission_uid": mission_uid},
        )["teams"]

    def get_team(self, team_uid: str) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.team.get",
            {"team_uid": team_uid},
        )

    def delete_team(self, team_uid: str) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.team.delete",
            {"team_uid": team_uid},
        )

    def list_team_missions(self, team_uid: str) -> list[str]:
        team = self.get_team(team_uid)
        return [str(uid) for uid in team.get("mission_uids", [])]

    def link_team_mission(self, team_uid: str, mission_uid: str) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.team.mission.link",
            {"team_uid": team_uid, "mission_uid": mission_uid},
        )

    def unlink_team_mission(self, team_uid: str, mission_uid: str) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.team.mission.unlink",
            {"team_uid": team_uid, "mission_uid": mission_uid},
        )

    def upsert_team_member(self, payload: dict[str, object]) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.team_member.upsert",
            payload,
        )

    def list_team_members(
        self,
        team_uid: str | None = None,
    ) -> list[dict[str, object]]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.team_member.list",
            {"team_uid": team_uid},
        )["team_members"]

    def get_team_member(self, team_member_uid: str) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.team_member.get",
            {"team_member_uid": team_member_uid},
        )

    def delete_team_member(self, team_member_uid: str) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.team_member.delete",
            {"team_member_uid": team_member_uid},
        )

    def list_team_member_clients(self, team_member_uid: str) -> list[str]:
        member = self.get_team_member(team_member_uid)
        return [str(identity) for identity in member.get("client_identities", [])]

    def link_team_member_client(
        self,
        team_member_uid: str,
        client_identity: str,
    ) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.team_member.client.link",
            {"team_member_uid": team_member_uid, "client_identity": client_identity},
        )

    def unlink_team_member_client(
        self,
        team_member_uid: str,
        client_identity: str,
    ) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.team_member.client.unlink",
            {"team_member_uid": team_member_uid, "client_identity": client_identity},
        )

    def upsert_asset(self, payload: dict[str, object]) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.asset.upsert",
            payload,
        )

    def list_assets(
        self,
        team_member_uid: str | None = None,
    ) -> list[dict[str, object]]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.asset.list",
            {"team_member_uid": team_member_uid},
        )["assets"]

    def get_asset(self, asset_uid: str) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.asset.get",
            {"asset_uid": asset_uid},
        )

    def delete_asset(self, asset_uid: str) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.asset.delete",
            {"asset_uid": asset_uid},
        )

    def upsert_skill(self, payload: dict[str, object]) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.skill.upsert",
            payload,
        )

    def list_skills(self) -> list[dict[str, object]]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.skill.list",
            {},
        )["skills"]

    def upsert_team_member_skill(self, payload: dict[str, object]) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.team_member_skill.upsert",
            payload,
        )

    def list_team_member_skills(
        self,
        team_member_rns_identity: str | None = None,
    ) -> list[dict[str, object]]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.team_member_skill.list",
            {"team_member_rns_identity": team_member_rns_identity},
        )["team_member_skills"]

    def upsert_task_skill_requirement(
        self,
        payload: dict[str, object],
    ) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.task_skill_requirement.upsert",
            payload,
        )

    def list_task_skill_requirements(
        self,
        task_uid: str | None = None,
    ) -> list[dict[str, object]]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.task_skill_requirement.list",
            {"task_uid": task_uid},
        )["task_skill_requirements"]

    def upsert_assignment(self, payload: dict[str, object]) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.assignment.upsert",
            payload,
        )

    def list_assignments(
        self,
        mission_uid: str | None = None,
        task_uid: str | None = None,
    ) -> list[dict[str, object]]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.assignment.list",
            {"mission_uid": mission_uid, "task_uid": task_uid},
        )["assignments"]

    def set_assignment_assets(
        self,
        assignment_uid: str,
        assets: list[str],
    ) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.assignment.asset.set",
            {"assignment_uid": assignment_uid, "assets": assets},
        )

    def link_assignment_asset(
        self,
        assignment_uid: str,
        asset_uid: str,
    ) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.assignment.asset.link",
            {"assignment_uid": assignment_uid, "asset_uid": asset_uid},
        )

    def unlink_assignment_asset(
        self,
        assignment_uid: str,
        asset_uid: str,
    ) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.assignment.asset.unlink",
            {"assignment_uid": assignment_uid, "asset_uid": asset_uid},
        )

    def list_domain_events(self, *, limit: int = 200) -> list[dict[str, object]]:
        snapshot = self._bridge.state_snapshot()
        rows = snapshot.get("audit_events")
        if isinstance(rows, list) and rows:
            return [dict(row) for row in rows[:limit] if isinstance(row, dict)]
        commands = snapshot.get("command_results")
        if isinstance(commands, list):
            return [
                {"event_type": "command_result", **dict(row)}
                for row in commands[:limit]
                if isinstance(row, dict)
            ]
        return []

    def list_domain_snapshots(self, *, limit: int = 200) -> list[dict[str, object]]:
        _ = limit
        return [{"snapshot": self._bridge.state_snapshot()}]


class RustMarkerService:
    """Marker service subset backed by the same Rust RCH bridge as R3AKT routes."""

    def __init__(self, bridge: RustMissionSyncBridge) -> None:
        self._bridge = bridge

    def create_marker(
        self,
        *,
        name: str | None,
        marker_type: str,
        symbol: str,
        category: str,
        lat: float,
        lon: float,
        origin_rch: str,
        notes: str | None = None,
        ttl_seconds: int | None = None,
    ) -> Marker:
        return _marker_from_payload(
            _run_rust_command(
                self._bridge,
                "mission.marker.create",
                {
                    "name": name,
                    "marker_type": marker_type,
                    "symbol": symbol,
                    "category": category,
                    "lat": lat,
                    "lon": lon,
                    "origin_rch": origin_rch,
                    "notes": notes,
                    "ttl_seconds": ttl_seconds,
                },
            )
        )

    def list_markers(self) -> list[Marker]:
        markers = _run_rust_command(self._bridge, "mission.marker.list", {})["markers"]
        return [_marker_from_payload(dict(marker)) for marker in markers if isinstance(marker, dict)]

    def update_marker_position(
        self,
        object_destination_hash: str,
        *,
        lat: float,
        lon: float,
    ) -> MarkerUpdateResult:
        current = self._get_marker(object_destination_hash)
        if current.lat == float(lat) and current.lon == float(lon):
            return MarkerUpdateResult(marker=current, changed=False)
        marker = _marker_from_payload(
            _run_rust_command(
                self._bridge,
                "mission.marker.position.patch",
                {
                    "object_destination_hash": object_destination_hash,
                    "lat": lat,
                    "lon": lon,
                },
            )
        )
        return MarkerUpdateResult(marker=marker, changed=True)

    def update_marker_name(
        self,
        object_destination_hash: str,
        *,
        name: str,
    ) -> MarkerUpdateResult:
        current = self._get_marker(object_destination_hash)
        if current.name == name.strip():
            return MarkerUpdateResult(marker=current, changed=False)
        marker = _marker_from_payload(
            _run_rust_command(
                self._bridge,
                "mission.marker.patch",
                {"object_destination_hash": object_destination_hash, "name": name},
            )
        )
        return MarkerUpdateResult(marker=marker, changed=True)

    def delete_marker(self, object_destination_hash: str) -> Marker:
        return _marker_from_payload(
            _run_rust_command(
                self._bridge,
                "mission.marker.delete",
                {"object_destination_hash": object_destination_hash},
            )
        )

    def _get_marker(self, object_destination_hash: str) -> Marker:
        for marker in self.list_markers():
            if marker.object_destination_hash == object_destination_hash:
                return marker
        raise KeyError(f"Marker '{object_destination_hash}' not found")


class RustZoneService:
    """Zone service subset backed by the same Rust RCH bridge as R3AKT routes."""

    def __init__(self, bridge: RustMissionSyncBridge) -> None:
        self._bridge = bridge

    def list_zones(self) -> list[Zone]:
        result = _run_rust_command(self._bridge, "mission.zone.list", {})
        zones = result.get("zones")
        assert isinstance(zones, list)
        return [_zone_from_payload(dict(zone)) for zone in zones if isinstance(zone, dict)]

    def create_zone(self, *, name: str, points: list[ZonePoint]) -> Zone:
        return _zone_from_payload(
            _run_rust_command(
                self._bridge,
                "mission.zone.create",
                {
                    "name": name,
                    "points": [point.to_dict() for point in points],
                },
            )
        )

    def update_zone(
        self,
        zone_id: str,
        *,
        name: str | None = None,
        points: list[ZonePoint] | None = None,
    ) -> ZoneUpdateResult:
        zone = _zone_from_payload(
            _run_rust_command(
                self._bridge,
                "mission.zone.patch",
                {
                    "zone_id": zone_id,
                    "name": name,
                    "points": [point.to_dict() for point in points] if points else None,
                },
            )
        )
        return ZoneUpdateResult(zone=zone)

    def delete_zone(self, zone_id: str) -> Zone:
        return _zone_from_payload(
            _run_rust_command(self._bridge, "mission.zone.delete", {"zone_id": zone_id})
        )


class RustR3aktApi:
    """API facade that delegates R3AKT rights state to the Rust bridge."""

    def __init__(
        self,
        delegate: ReticulumTelemetryHubAPI,
        bridge: RustMissionSyncBridge,
    ) -> None:
        self._delegate = delegate
        self._bridge = bridge

    def __getattr__(self, name: str) -> object:
        return getattr(self._delegate, name)

    def list_team_member_subjects(
        self,
        *,
        mission_uid: str | None = None,
    ) -> list[dict[str, object]]:
        result = _run_rust_command(
            self._bridge,
            "mission.registry.rights.subjects.list",
            {"mission_uid": mission_uid},
        )
        subjects = result.get("subjects")
        assert isinstance(subjects, list)
        return [dict(subject) for subject in subjects if isinstance(subject, dict)]

    def assign_mission_access_role(
        self,
        mission_uid: str,
        subject_type: str,
        subject_id: str,
        *,
        role: str | None = None,
        assigned_by: str | None = None,
    ) -> dict[str, object]:
        _ = assigned_by
        return _run_rust_command(
            self._bridge,
            "mission.registry.rights.mission_access.assign",
            {
                "mission_uid": mission_uid,
                "subject_type": subject_type,
                "subject_id": subject_id,
                "role": role,
            },
        )

    def revoke_mission_access_role(
        self,
        mission_uid: str,
        subject_type: str,
        subject_id: str,
    ) -> dict[str, object]:
        return _run_rust_command(
            self._bridge,
            "mission.registry.rights.mission_access.revoke",
            {
                "mission_uid": mission_uid,
                "subject_type": subject_type,
                "subject_id": subject_id,
            },
        )

    def list_mission_access_assignments(
        self,
        *,
        mission_uid: str | None = None,
        subject_type: str | None = None,
        subject_id: str | None = None,
    ) -> list[dict[str, object]]:
        result = _run_rust_command(
            self._bridge,
            "mission.registry.rights.mission_access.list",
            {
                "mission_uid": mission_uid,
                "subject_type": subject_type,
                "subject_id": subject_id,
            },
        )
        assignments = result.get("mission_access_assignments")
        assert isinstance(assignments, list)
        return [
            dict(assignment)
            for assignment in assignments
            if isinstance(assignment, dict)
        ]


def _marker_from_payload(payload: dict[str, object]) -> Marker:
    position = payload.get("position")
    if not isinstance(position, dict):
        position = {"lat": payload.get("lat"), "lon": payload.get("lon")}
    updated_at = _parse_datetime(payload.get("updated_at") or payload.get("time"))
    created_at = _parse_datetime(payload.get("created_at") or updated_at)
    stale_at = _parse_datetime(payload.get("stale_at") or updated_at)
    if stale_at <= datetime.now(timezone.utc):
        stale_at = updated_at + timedelta(hours=24)
    return Marker(
        local_id=str(payload.get("local_id") or payload.get("object_destination_hash") or ""),
        object_destination_hash=str(payload.get("object_destination_hash") or ""),
        origin_rch=str(payload.get("origin_rch") or ""),
        object_identity_storage_key=None,
        marker_type=str(payload.get("type") or payload.get("marker_type") or "marker"),
        symbol=str(payload.get("symbol") or "marker"),
        name=str(payload.get("name") or "Marker"),
        category=str(payload.get("category") or "marker"),
        lat=float(position.get("lat") or 0.0),
        lon=float(position.get("lon") or 0.0),
        notes=payload.get("notes") if isinstance(payload.get("notes"), str) else None,
        time=_parse_datetime(payload.get("time") or updated_at),
        stale_at=stale_at,
        created_at=created_at,
        updated_at=updated_at,
    )


def _zone_from_payload(payload: dict[str, object]) -> Zone:
    points = payload.get("points")
    assert isinstance(points, list)
    updated_at = _parse_datetime(payload.get("updated_at"))
    return Zone(
        zone_id=str(payload.get("zone_id") or ""),
        name=str(payload.get("name") or ""),
        points=[
            ZonePoint(lat=float(point.get("lat")), lon=float(point.get("lon")))
            for point in points
            if isinstance(point, dict)
        ],
        created_at=_parse_datetime(payload.get("created_at") or updated_at),
        updated_at=updated_at,
    )


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


def _runtime_root() -> Path:
    candidates = [
        Path(__file__).resolve().parents[4] / "New project" / "R3AKT-Runtime",
        Path(r"C:\Users\broth\Documents\New project\R3AKT-Runtime"),
    ]
    for candidate in candidates:
        if (candidate / "Cargo.toml").exists():
            return candidate
    pytest.fail("R3AKT-Runtime workspace not found for Rust R3AKT route parity tests")


def _bridge(db_path: Path) -> RustMissionSyncBridge:
    runtime_root = _runtime_root()

    def runner(args, **kwargs):  # type: ignore[no-untyped-def]
        request_db_path = args[args.index("--db") + 1]
        return subprocess.run(
            ["cargo", "run", "-q", "-p", "r3akt-rch-bridge", "--", "--db", request_db_path],
            cwd=runtime_root,
            input=kwargs["input"],
            text=True,
            capture_output=True,
            check=False,
        )

    return RustMissionSyncBridge(
        binary_path="cargo-run-r3akt-rch-bridge",
        db_path=str(db_path),
        field_results=FIELD_RESULTS,
        field_event=FIELD_EVENT,
        field_group=FIELD_GROUP,
        runner=runner,
    )


def _run_rust_command(
    bridge: RustMissionSyncBridge,
    command_type: str,
    args: dict[str, object],
) -> dict[str, object]:
    responses = bridge.handle_command(
        MissionCommandEnvelope.model_validate(
            {
                "command_id": f"cmd-rust-r3akt-route-{command_type}",
                "source": {"rns_identity": "peer-a"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "command_type": command_type,
                "args": args,
            }
        ),
        source_identity="peer-a",
    )
    payload = responses[-1].fields[FIELD_RESULTS]
    if not isinstance(payload, dict):
        raise RuntimeError(f"Rust R3AKT command returned malformed payload: {command_type}")
    if payload.get("status") == "rejected":
        reason_code = str(payload.get("reason_code") or "")
        reason = str(payload.get("reason") or payload.get("detail") or command_type)
        if reason_code in {"not_found", "not_found_error"} or "not found" in reason.lower():
            if command_type.endswith(".get") or command_type.endswith(".delete"):
                raise KeyError(reason)
            raise ValueError(reason)
        raise ValueError(reason)
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"Rust R3AKT command returned non-object result: {command_type}")
    return result


def _run_rust_checklist_command(
    bridge: RustMissionSyncBridge,
    command_type: str,
    args: dict[str, object],
) -> None:
    responses = bridge.handle_checklist_command(
        MissionCommandEnvelope.model_validate(
            {
                "command_id": f"cmd-rust-checklist-route-{command_type}",
                "source": {"rns_identity": "peer-a"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "command_type": command_type,
                "args": args,
            }
        ),
        source_identity="peer-a",
    )
    if not responses:
        return
    payload = responses[-1].fields[FIELD_RESULTS]
    if not isinstance(payload, dict):
        raise RuntimeError(f"Rust checklist command returned malformed payload: {command_type}")
    if payload.get("status") == "rejected":
        reason_code = str(payload.get("reason_code") or "")
        reason = str(payload.get("reason") or payload.get("detail") or command_type)
        if reason.lower() == "mission not found":
            raise ValueError(reason)
        if reason_code in {"not_found", "not_found_error"} or "not found" in reason.lower():
            raise KeyError(reason)
        raise ValueError(reason)


def _build_client(
    tmp_path: Path,
    *,
    backend: str = "python",
) -> tuple[
    TestClient,
    ReticulumTelemetryHubAPI | RustTopicSubscriberApi,
    EventLog,
    TelemetryController,
]:
    if backend == "rust":
        api = RustTopicSubscriberApi(tmp_path)
    else:
        config_manager = HubConfigurationManager(storage_path=tmp_path)
        storage = HubStorage(tmp_path / "hub.sqlite")
        api = ReticulumTelemetryHubAPI(config_manager=config_manager, storage=storage)
    event_log = EventLog()
    telemetry = TelemetryController(
        db_path=tmp_path / "telemetry.db",
        api=api,
        event_log=event_log,
    )
    rust_bridge = _bridge(tmp_path / "r3akt-routes.sqlite") if backend == "rust" else None
    route_api = RustR3aktApi(api, rust_bridge) if rust_bridge is not None else api
    app = create_app(
        api=route_api,
        telemetry_controller=telemetry,
        event_log=event_log,
        auth=ApiAuth(api_key="secret"),
        routing_provider=lambda: ["dest-1"],
        message_dispatcher=lambda content, topic_id=None, destination=None, fields=None: None,
        mission_domain_service=RustR3aktDomain(rust_bridge) if rust_bridge is not None else None,
        marker_service=RustMarkerService(rust_bridge) if rust_bridge is not None else None,
        zone_service=RustZoneService(rust_bridge) if rust_bridge is not None else None,
    )
    return TestClient(app), api, event_log, telemetry


def test_openapi_yaml_returns_payload(tmp_path: Path) -> None:
    client, _, _, _ = _build_client(tmp_path)

    response = client.get("/openapi.yaml")

    assert response.status_code == 200
    assert "openapi" in response.text.lower()


def test_openapi_yaml_missing_returns_404(tmp_path: Path) -> None:
    config_manager = HubConfigurationManager(storage_path=tmp_path)
    api = ReticulumTelemetryHubAPI(
        config_manager=config_manager,
        storage=HubStorage(tmp_path / "hub.sqlite"),
    )
    event_log = EventLog()
    telemetry = TelemetryController(
        db_path=tmp_path / "telemetry.db",
        api=api,
        event_log=event_log,
    )
    services = NorthboundServices(
        api=api,
        telemetry=telemetry,
        event_log=event_log,
        started_at=datetime.now(timezone.utc),
    )
    app = FastAPI()
    register_core_routes(
        app,
        services=services,
        api=api,
        telemetry_controller=telemetry,
        require_protected=lambda: None,
        resolve_openapi_spec=lambda: None,
    )
    client = TestClient(app)

    response = client.get("/openapi.yaml")

    assert response.status_code == 404


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_client_list_pagination_preserves_legacy_response(
    tmp_path: Path, backend: str
) -> None:
    client, api, _, _ = _build_client(tmp_path, backend=backend)
    headers = {"X-API-Key": "secret"}
    for identity in ("client-1", "client-2", "client-3"):
        api.join(identity)

    legacy_response = client.get("/Client", headers=headers)
    paged_response = client.get(
        "/Client",
        params={"page": 1, "per_page": 2},
        headers=headers,
    )

    assert legacy_response.status_code == 200
    assert isinstance(legacy_response.json(), list)
    assert len(legacy_response.json()) == 3
    assert paged_response.status_code == 200
    payload = paged_response.json()
    assert len(payload["items"]) == 2
    assert payload["page"] == 1
    assert payload["per_page"] == 2
    assert payload["total"] == 3
    assert payload["total_pages"] == 2
    assert payload["has_next"] is True
    assert payload["has_previous"] is False


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_core_routes_endpoints(tmp_path: Path, backend: str) -> None:
    reticulum_path = tmp_path / "reticulum.conf"
    reticulum_path.write_text("[reticulum]\nshare_instance = yes\n", encoding="utf-8")
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        f"[hub]\nreticulum_config_path = {reticulum_path}\n", encoding="utf-8"
    )

    client, api, event_log, telemetry = _build_client(tmp_path, backend=backend)
    headers = {"X-API-Key": "secret"}

    help_response = client.get("/Help")
    examples_response = client.get("/Examples")

    assert help_response.status_code == 200
    assert examples_response.status_code == 200

    config_path = api._config_manager.config_path  # pylint: disable=protected-access
    config_path.write_text("[app]\nname=RTH\n", encoding="utf-8")

    status_response = client.get("/Status", headers=headers)
    assert status_response.status_code == 200
    diagnostics_response = client.get("/diagnostics/runtime", headers=headers)
    assert diagnostics_response.status_code == 200
    assert isinstance(diagnostics_response.json(), dict)
    diagnostics_alias_response = client.get("/Diagnostics/Runtime", headers=headers)
    assert diagnostics_alias_response.status_code == 200

    event_log.add_event("test_event", "Event recorded")
    events_response = client.get("/Events", headers=headers)
    assert events_response.status_code == 200
    assert events_response.json()

    now = datetime.now(timezone.utc)
    telemetry_response = client.get(
        "/Telemetry",
        params={"since": int(now.timestamp())},
        headers=headers,
    )
    assert telemetry_response.status_code == 200

    config_response = client.get("/Config", headers=headers)
    assert config_response.status_code == 200

    validate_response = client.post(
        "/Config/Validate",
        data="[app]\nname=RTH\n",
        headers={**headers, "Content-Type": "text/plain"},
    )
    assert validate_response.status_code == 200

    apply_response = client.put(
        "/Config",
        data="[app]\nname=RTH\n",
        headers={**headers, "Content-Type": "text/plain"},
    )
    assert apply_response.status_code == 200

    rollback_response = client.post("/Config/Rollback", headers=headers)
    assert rollback_response.status_code == 200

    reticulum_response = client.get("/Reticulum/Config", headers=headers)
    assert reticulum_response.status_code == 200

    reticulum_validate_response = client.post(
        "/Reticulum/Config/Validate",
        data="[reticulum]\nenable_transport = yes\n",
        headers={**headers, "Content-Type": "text/plain"},
    )
    assert reticulum_validate_response.status_code == 200

    reticulum_apply_response = client.put(
        "/Reticulum/Config",
        data="[reticulum]\nenable_transport = yes\n",
        headers={**headers, "Content-Type": "text/plain"},
    )
    assert reticulum_apply_response.status_code == 200

    reticulum_rollback_response = client.post(
        "/Reticulum/Config/Rollback", headers=headers
    )
    assert reticulum_rollback_response.status_code == 200

    capabilities_response = client.get(
        "/Reticulum/Interfaces/Capabilities", headers=headers
    )
    assert capabilities_response.status_code == 200
    capabilities_payload = capabilities_response.json()
    assert "supported_interface_types" in capabilities_payload
    assert "unsupported_interface_types" in capabilities_payload
    assert "identity_hash_hex_length" in capabilities_payload

    discovery_response = client.get("/Reticulum/Discovery", headers=headers)
    assert discovery_response.status_code == 200
    discovery_payload = discovery_response.json()
    assert "runtime_active" in discovery_payload
    assert "discovered_interfaces" in discovery_payload
    assert "refreshed_at" in discovery_payload

    telemetry.save_telemetry(
        {
            SID_TIME: int(now.timestamp()),
            SID_LOCATION: build_location_payload(int(now.timestamp())),
        },
        "peer-1",
        timestamp=now,
    )

    flush_response = client.post("/Command/FlushTelemetry", headers=headers)
    assert flush_response.status_code == 200

    reload_response = client.post("/Command/ReloadConfig", headers=headers)
    assert reload_response.status_code == 200

    message_response = client.post(
        "/Message",
        json={"Content": "hello"},
        headers=headers,
    )
    assert message_response.status_code == 200

    routing_response = client.get("/Command/DumpRouting", headers=headers)
    assert routing_response.status_code == 200
    assert routing_response.json()["destinations"] == ["dest-1"]

    join_response = client.post("/RTH", params={"identity": "dest-1"}, headers=headers)
    assert join_response.status_code == 200
    api.record_identity_announce(
        "dest-1",
        display_name="REM Alpha",
        announce_capabilities="R3AKT,EMergencyMessages",
    )
    api.set_rem_mode("dest-1", "connected")

    join_alias_response = client.post("/RCH", params={"identity": "dest-2"}, headers=headers)
    assert join_alias_response.status_code == 200
    api.record_identity_announce(
        "dest-2",
        display_name="Generic Bravo",
        announce_capabilities=["telemetry"],
    )

    capability_response = client.put(
        "/api/r3akt/capabilities/dest-1/mission.join",
        json={"granted_by": "tester"},
        headers=headers,
    )
    assert capability_response.status_code == 200

    missions_response = client.post(
        "/api/r3akt/missions",
        json={"mission_name": "Mission Alpha"},
        headers=headers,
    )
    assert missions_response.status_code == 200
    mission_uid = missions_response.json()["uid"]

    mission_get_response = client.get(
        f"/api/r3akt/missions/{mission_uid}",
        headers=headers,
    )
    assert mission_get_response.status_code == 200

    template_response = client.post(
        "/checklists/templates",
        json={
            "template": {
                "template_name": "Template Alpha",
                "description": "Template",
                "created_by_team_member_rns_identity": "dest-1",
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
        },
        headers=headers,
    )
    assert template_response.status_code == 200
    template_uid = template_response.json()["uid"]

    checklist_response = client.post(
        "/checklists",
        json={
            "template_uid": template_uid,
            "name": "Checklist Alpha",
            "description": "Checklist",
            "start_time": datetime.now(timezone.utc).isoformat(),
            "source_identity": "dest-1",
        },
        headers=headers,
    )
    assert checklist_response.status_code == 200
    checklist_uid = checklist_response.json()["uid"]

    task_add_response = client.post(
        f"/checklists/{checklist_uid}/tasks",
        json={"number": 1, "due_relative_minutes": 10},
        headers=headers,
    )
    assert task_add_response.status_code == 200

    client_list = client.get("/Client", headers=headers)
    assert client_list.status_code == 200
    client_map = {entry["identity"]: entry for entry in client_list.json()}
    assert client_map["dest-1"]["client_type"] == "rem"
    assert client_map["dest-1"]["rem_mode"] == "connected"
    assert client_map["dest-1"]["is_rem_capable"] is True
    assert client_map["dest-2"]["client_type"] == "generic_lxmf"
    assert client_map["dest-2"]["rem_mode"] is None

    identities_response = client.get("/Identities", headers=headers)
    assert identities_response.status_code == 200
    identity_map = {entry["Identity"]: entry for entry in identities_response.json()}
    assert identity_map["dest-1"]["ClientType"] == "rem"
    assert identity_map["dest-1"]["RemMode"] == "connected"
    assert identity_map["dest-2"]["RemMode"] is None

    rem_peers_response = client.get("/api/rem/peers", headers=headers)
    assert rem_peers_response.status_code == 200
    assert rem_peers_response.json()["effective_connected_mode"] is True
    assert rem_peers_response.json()["items"][0]["identity"] == "dest-1"

    leave_response = client.put("/RTH", params={"identity": "dest-1"}, headers=headers)
    assert leave_response.status_code == 200

    leave_alias_response = client.put("/RCH", params={"identity": "dest-2"}, headers=headers)
    assert leave_alias_response.status_code == 200

    info_response = client.get("/api/v1/app/info")
    assert info_response.status_code == 200


def test_events_endpoint_returns_nonfatal_exception_entry(tmp_path: Path) -> None:
    client, _api, event_log, _telemetry = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}

    report_nonfatal_exception(
        event_log,
        "telemetry_error",
        "Telemetry collector failed: boom",
        RuntimeError("boom"),
        metadata={"operation": "collect"},
        log_level=1,
    )

    response = client.get("/Events", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert any(entry["type"] == "telemetry_error" for entry in payload)


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_apply_config_rejects_invalid_payload(
    tmp_path: Path, backend: str
) -> None:
    """Return HTTP 400 when a config payload is invalid."""

    client, api, _, _ = _build_client(tmp_path, backend=backend)
    headers = {"X-API-Key": "secret", "Content-Type": "text/plain"}

    config_path = api._config_manager.config_path  # pylint: disable=protected-access
    config_path.write_text("[app]\nname=RTH\n", encoding="utf-8")
    original = api.get_config_text()

    response = client.put("/Config", data="hub]\nname=Broken\n", headers=headers)

    assert response.status_code == 400
    assert "Invalid configuration payload" in response.json().get("detail", "")
    assert api.get_config_text() == original


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_apply_reticulum_config_rejects_invalid_payload(
    tmp_path: Path, backend: str
) -> None:
    """Return HTTP 400 when a Reticulum config payload is invalid."""

    reticulum_path = tmp_path / "reticulum.conf"
    reticulum_path.write_text("[reticulum]\nshare_instance = yes\n", encoding="utf-8")
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        f"[hub]\nreticulum_config_path = {reticulum_path}\n", encoding="utf-8"
    )

    client, api, _, _ = _build_client(tmp_path, backend=backend)
    headers = {"X-API-Key": "secret", "Content-Type": "text/plain"}

    original = api.get_reticulum_config_text()

    response = client.put("/Reticulum/Config", data="reticulum]\nnope", headers=headers)

    assert response.status_code == 400
    assert "Invalid Reticulum configuration payload" in response.json().get("detail", "")
    assert api.get_reticulum_config_text() == original


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_identity_moderation_routes(tmp_path: Path, backend: str) -> None:
    client, _, _, _ = _build_client(tmp_path, backend=backend)
    headers = {"X-API-Key": "secret"}

    ban_response = client.post("/Client/abc/Ban", headers=headers)
    assert ban_response.status_code == 200

    unban_response = client.post("/Client/abc/Unban", headers=headers)
    assert unban_response.status_code == 200

    blackhole_response = client.post("/Client/abc/Blackhole", headers=headers)
    assert blackhole_response.status_code == 200

    identities_response = client.get("/Identities", headers=headers)
    assert identities_response.status_code == 200


def test_reticulum_capabilities_route_runtime_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    """Return a safe capabilities response when runtime is unavailable."""

    client, _, _, _ = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}
    monkeypatch.setattr(
        "reticulum_telemetry_hub.northbound.services.get_interface_capabilities",
        lambda: {
            "runtime_active": False,
            "os": "windows",
            "identity_hash_hex_length": 0,
            "supported_interface_types": [],
            "unsupported_interface_types": ["TCPClientInterface"],
            "discoverable_interface_types": [],
            "autoconnect_interface_types": [],
            "rns_version": "unavailable",
        },
    )

    response = client.get("/Reticulum/Interfaces/Capabilities", headers=headers)

    assert response.status_code == 200
    assert response.json()["runtime_active"] is False


def test_reticulum_discovery_route_runtime_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    """Return a safe discovery response when runtime is unavailable."""

    client, _, _, _ = _build_client(tmp_path)
    headers = {"X-API-Key": "secret"}
    monkeypatch.setattr(
        "reticulum_telemetry_hub.northbound.services.get_discovery_snapshot",
        lambda: {
            "runtime_active": False,
            "should_autoconnect": False,
            "max_autoconnected_interfaces": None,
            "required_discovery_value": None,
            "interface_discovery_sources": [],
            "discovered_interfaces": [],
            "refreshed_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    response = client.get("/Reticulum/Discovery", headers=headers)

    assert response.status_code == 200
    assert response.json()["runtime_active"] is False
    assert response.json()["discovered_interfaces"] == []

@pytest.mark.parametrize("backend", ["python", "rust"])
def test_r3akt_registry_routes_matrix(tmp_path: Path, backend: str) -> None:
    client, _, _, _ = _build_client(tmp_path, backend=backend)
    headers = {"X-API-Key": "secret"}

    invalid_grant = client.put(
        "/api/r3akt/capabilities/peer-a/mission.join",
        json={"expires_at": "not-iso"},
        headers=headers,
    )
    assert invalid_grant.status_code == 400

    grant = client.put(
        "/api/r3akt/capabilities/peer-a/mission.join",
        json={
            "granted_by": "admin",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
        headers=headers,
    )
    assert grant.status_code == 200

    capabilities = client.get("/api/r3akt/capabilities/peer-a", headers=headers)
    assert capabilities.status_code == 200
    assert "mission.join" in capabilities.json()["capabilities"]

    revoke = client.delete(
        "/api/r3akt/capabilities/peer-a/mission.join",
        headers=headers,
    )
    assert revoke.status_code == 200

    mission = client.post(
        "/api/r3akt/missions",
        json={"uid": "mission-1", "mission_name": "Mission One"},
        headers=headers,
    )
    assert mission.status_code == 200
    mission_uid = mission.json()["uid"]

    mission_get = client.get(f"/api/r3akt/missions/{mission_uid}", headers=headers)
    assert mission_get.status_code == 200

    mission_missing = client.get("/api/r3akt/missions/missing", headers=headers)
    assert mission_missing.status_code == 404

    mission_patch = client.patch(
        f"/api/r3akt/missions/{mission_uid}",
        json={
            "mission_priority": 12,
            "default_role": "MISSION_SUBSCRIBER",
            "owner_role": "MISSION_OWNER",
            "feeds": ["feed-1"],
        },
        headers=headers,
    )
    assert mission_patch.status_code == 200
    assert mission_patch.json()["mission_priority"] == 12

    mission_rde = client.put(
        f"/api/r3akt/missions/{mission_uid}/rde",
        json={"role": "MISSION_OWNER"},
        headers=headers,
    )
    assert mission_rde.status_code == 200
    mission_rde_get = client.get(f"/api/r3akt/missions/{mission_uid}/rde", headers=headers)
    assert mission_rde_get.status_code == 200
    assert mission_rde_get.json()["role"] == "MISSION_OWNER"

    parent_mission = client.post(
        "/api/r3akt/missions",
        json={"uid": "mission-parent", "mission_name": "Mission Parent"},
        headers=headers,
    )
    assert parent_mission.status_code == 200
    set_parent = client.put(
        f"/api/r3akt/missions/{mission_uid}/parent",
        json={"parent_uid": "mission-parent"},
        headers=headers,
    )
    assert set_parent.status_code == 200
    assert set_parent.json()["parent_uid"] == "mission-parent"

    zone_create = client.post(
        "/api/zones",
        headers=headers,
        json={
            "name": "Mission Zone",
            "points": [
                {"lat": 30.0, "lon": -110.0},
                {"lat": 30.1, "lon": -110.0},
                {"lat": 30.1, "lon": -109.9},
            ],
        },
    )
    assert zone_create.status_code == 201
    zone_id = zone_create.json()["zone_id"]
    zone_link = client.put(f"/api/r3akt/missions/{mission_uid}/zones/{zone_id}", headers=headers)
    assert zone_link.status_code == 200
    mission_zones = client.get(f"/api/r3akt/missions/{mission_uid}/zones", headers=headers)
    assert mission_zones.status_code == 200
    assert zone_id in mission_zones.json()["zone_ids"]

    mission_change_invalid = client.post(
        "/api/r3akt/mission-changes",
        json={"name": "bad"},
        headers=headers,
    )
    assert mission_change_invalid.status_code == 400

    mission_change = client.post(
        "/api/r3akt/mission-changes",
        json={"uid": "change-1", "mission_uid": mission_uid, "name": "Updated"},
        headers=headers,
    )
    assert mission_change.status_code == 200

    marker = client.post(
        "/api/markers",
        json={
            "name": "Log Marker",
            "type": "marker",
            "symbol": "marker",
            "category": "test",
            "lat": 35.0,
            "lon": -120.0,
        },
        headers=headers,
    )
    assert marker.status_code == 201
    marker_ref = marker.json()["object_destination_hash"]

    marker_link = client.put(
        f"/api/r3akt/missions/{mission_uid}/markers/{marker_ref}",
        headers=headers,
    )
    assert marker_link.status_code == 200
    mission_markers = client.get(f"/api/r3akt/missions/{mission_uid}/markers", headers=headers)
    assert mission_markers.status_code == 200
    assert marker_ref in mission_markers.json()["marker_ids"]

    log_missing_mission = client.post(
        "/api/r3akt/log-entries",
        json={"entry_uid": "log-missing-mission", "content": "No mission"},
        headers=headers,
    )
    assert log_missing_mission.status_code == 200
    assert log_missing_mission.json()["mission_uid"] == "mission-default"

    log_missing_marker = client.post(
        "/api/r3akt/log-entries",
        json={
            "entry_uid": "log-missing-marker",
            "mission_uid": mission_uid,
            "content": "Bad marker ref",
            "content_hashes": ["missing-marker"],
        },
        headers=headers,
    )
    assert log_missing_marker.status_code == 400

    log_entry = client.post(
        "/api/r3akt/log-entries",
        json={
            "entry_uid": "log-1",
            "mission_uid": mission_uid,
            "content": "Marker observed",
            "content_hashes": [marker_ref],
            "keywords": ["marker", "observation"],
        },
        headers=headers,
    )
    assert log_entry.status_code == 200

    logs_by_mission = client.get(
        "/api/r3akt/log-entries",
        params={"mission_uid": mission_uid},
        headers=headers,
    )
    assert logs_by_mission.status_code == 200
    assert logs_by_mission.json()[0]["entry_uid"] == "log-1"

    logs_by_marker = client.get(
        "/api/r3akt/log-entries",
        params={"marker_ref": marker_ref},
        headers=headers,
    )
    assert logs_by_marker.status_code == 200
    assert logs_by_marker.json()[0]["entry_uid"] == "log-1"

    team_invalid = client.post(
        "/api/r3akt/teams",
        json={"uid": "team-invalid", "mission_uid": "missing-mission", "team_name": "Ops"},
        headers=headers,
    )
    assert team_invalid.status_code == 400

    team = client.post(
        "/api/r3akt/teams",
        json={"uid": "team-1", "mission_uid": mission_uid, "team_name": "Ops"},
        headers=headers,
    )
    assert team.status_code == 200
    assert team.json()["mission_uids"] == [mission_uid]
    team_get = client.get("/api/r3akt/teams/team-1", headers=headers)
    assert team_get.status_code == 200
    team_missing = client.get("/api/r3akt/teams/missing", headers=headers)
    assert team_missing.status_code == 404
    team_missions = client.get("/api/r3akt/teams/team-1/missions", headers=headers)
    assert team_missions.status_code == 200
    assert team_missions.json()["mission_uids"] == [mission_uid]
    team_link_second = client.put(
        "/api/r3akt/teams/team-1/missions/mission-parent",
        headers=headers,
    )
    assert team_link_second.status_code == 200
    assert set(team_link_second.json()["mission_uids"]) == {mission_uid, "mission-parent"}
    teams_for_parent = client.get(
        "/api/r3akt/teams",
        params={"mission_uid": "mission-parent"},
        headers=headers,
    )
    assert teams_for_parent.status_code == 200
    assert any(item["uid"] == "team-1" for item in teams_for_parent.json())

    member_invalid = client.post("/api/r3akt/team-members", json={}, headers=headers)
    assert member_invalid.status_code == 400

    member = client.post(
        "/api/r3akt/team-members",
        json={
            "uid": "member-1",
            "team_uid": "team-1",
            "rns_identity": "peer-a",
            "display_name": "Peer A",
        },
        headers=headers,
    )
    assert member.status_code == 200
    member_get = client.get("/api/r3akt/team-members/member-1", headers=headers)
    assert member_get.status_code == 200
    member_missing = client.get("/api/r3akt/team-members/missing", headers=headers)
    assert member_missing.status_code == 404

    join_client = client.post("/RCH", params={"identity": "peer-a"}, headers=headers)
    assert join_client.status_code == 200
    member_client_link = client.put(
        "/api/r3akt/team-members/member-1/clients/peer-a",
        headers=headers,
    )
    assert member_client_link.status_code == 200
    member_clients = client.get(
        "/api/r3akt/team-members/member-1/clients",
        headers=headers,
    )
    assert member_clients.status_code == 200
    assert "peer-a" in member_clients.json()["client_identities"]

    rights_definitions = client.get("/api/r3akt/rights/definitions", headers=headers)
    assert rights_definitions.status_code == 200
    assert "MISSION_OWNER" in rights_definitions.json()["mission_role_bundles"]

    rights_subjects = client.get(
        "/api/r3akt/rights/subjects",
        params={"mission_uid": mission_uid},
        headers=headers,
    )
    assert rights_subjects.status_code == 200
    assert rights_subjects.json()[0]["subject_id"] == "member-1"
    assert "peer-a" in rights_subjects.json()[0]["client_identities"]

    mission_access = client.put(
        "/api/r3akt/rights/mission-access",
        json={
            "mission_uid": mission_uid,
            "subject_type": "team_member",
            "subject_id": "member-1",
            "assigned_by": "admin",
        },
        headers=headers,
    )
    assert mission_access.status_code == 200
    assert mission_access.json()["role"] == "MISSION_SUBSCRIBER"
    mission_access_list = client.get(
        "/api/r3akt/rights/mission-access",
        params={"mission_uid": mission_uid},
        headers=headers,
    )
    assert mission_access_list.status_code == 200
    assert mission_access_list.json()[0]["subject_id"] == "member-1"

    operation_grant = client.put(
        "/api/r3akt/rights/grants",
        json={
            "subject_type": "team_member",
            "subject_id": "member-1",
            "operation": "topic.delete",
            "scope_type": "mission",
            "scope_id": mission_uid,
            "granted_by": "admin",
        },
        headers=headers,
    )
    assert operation_grant.status_code == 200
    rights_grants = client.get(
        "/api/r3akt/rights/grants",
        params={
            "subject_type": "team_member",
            "subject_id": "member-1",
            "scope_type": "mission",
            "scope_id": mission_uid,
        },
        headers=headers,
    )
    assert rights_grants.status_code == 200
    assert any(item["operation"] == "topic.delete" for item in rights_grants.json())

    operation_revoke = client.request(
        "DELETE",
        "/api/r3akt/rights/grants",
        json={
            "subject_type": "team_member",
            "subject_id": "member-1",
            "operation": "topic.delete",
            "scope_type": "mission",
            "scope_id": mission_uid,
            "granted_by": "admin",
        },
        headers=headers,
    )
    assert operation_revoke.status_code == 200

    asset_invalid = client.post(
        "/api/r3akt/assets",
        json={
            "asset_uid": "asset-invalid",
            "team_member_uid": "missing-member",
            "name": "Radio",
            "asset_type": "COMM",
        },
        headers=headers,
    )
    assert asset_invalid.status_code == 400

    asset_invalid_status = client.post(
        "/api/r3akt/assets",
        json={
            "asset_uid": "asset-invalid-status",
            "team_member_uid": "member-1",
            "name": "Radio",
            "asset_type": "COMM",
            "status": "BROKEN",
        },
        headers=headers,
    )
    assert asset_invalid_status.status_code == 400

    asset = client.post(
        "/api/r3akt/assets",
        json={
            "asset_uid": "asset-1",
            "team_member_uid": "member-1",
            "name": "Radio",
            "asset_type": "COMM",
        },
        headers=headers,
    )
    assert asset.status_code == 200
    asset_get = client.get("/api/r3akt/assets/asset-1", headers=headers)
    assert asset_get.status_code == 200
    asset_missing = client.get("/api/r3akt/assets/missing", headers=headers)
    assert asset_missing.status_code == 404

    skill = client.post(
        "/api/r3akt/skills",
        json={"skill_uid": "skill-1", "name": "Navigation"},
        headers=headers,
    )
    assert skill.status_code == 200

    template = client.post(
        "/checklists/templates",
        json={
            "template": {
                "template_name": "Registry Template",
                "description": "Template for registry route task references",
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
        },
        headers=headers,
    )
    assert template.status_code == 200
    template_uid = template.json()["uid"]

    checklist = client.post(
        "/checklists",
        json={
            "template_uid": template_uid,
            "name": "Registry Checklist",
            "mission_uid": mission_uid,
        },
        headers=headers,
    )
    assert checklist.status_code == 200
    checklist_uid = checklist.json()["uid"]

    task_row = client.post(
        f"/checklists/{checklist_uid}/tasks",
        json={"number": 1},
        headers=headers,
    )
    assert task_row.status_code == 200
    task_uid = task_row.json()["tasks"][0]["task_uid"]

    member_skill_invalid = client.post(
        "/api/r3akt/team-member-skills",
        json={"team_member_rns_identity": "peer-a"},
        headers=headers,
    )
    assert member_skill_invalid.status_code == 400

    member_skill = client.post(
        "/api/r3akt/team-member-skills",
        json={
            "uid": "member-skill-1",
            "team_member_rns_identity": "peer-a",
            "skill_uid": "skill-1",
            "level": 3,
        },
        headers=headers,
    )
    assert member_skill.status_code == 200

    req_invalid = client.post(
        "/api/r3akt/task-skill-requirements",
        json={"task_uid": "task-1"},
        headers=headers,
    )
    assert req_invalid.status_code == 400

    requirement = client.post(
        "/api/r3akt/task-skill-requirements",
        json={
            "uid": "req-1",
            "task_uid": task_uid,
            "skill_uid": "skill-1",
            "minimum_level": 2,
        },
        headers=headers,
    )
    assert requirement.status_code == 200

    requirement_missing_task = client.post(
        "/api/r3akt/task-skill-requirements",
        json={
            "uid": "req-missing-task",
            "task_uid": "missing-task",
            "skill_uid": "skill-1",
            "minimum_level": 2,
        },
        headers=headers,
    )
    assert requirement_missing_task.status_code == 400

    assignment_invalid = client.post(
        "/api/r3akt/assignments",
        json={"mission_uid": mission_uid},
        headers=headers,
    )
    assert assignment_invalid.status_code == 400

    assignment = client.post(
        "/api/r3akt/assignments",
        json={
            "assignment_uid": "assignment-1",
            "mission_uid": mission_uid,
            "task_uid": task_uid,
            "team_member_rns_identity": "peer-a",
            "assets": ["asset-1"],
        },
        headers=headers,
    )
    assert assignment.status_code == 200
    assignment_asset_link = client.put(
        "/api/r3akt/assignments/assignment-1/assets/asset-1",
        headers=headers,
    )
    assert assignment_asset_link.status_code == 200
    assignment_asset_set = client.put(
        "/api/r3akt/assignments/assignment-1/assets",
        json={"assets": ["asset-1"]},
        headers=headers,
    )
    assert assignment_asset_set.status_code == 200
    assignment_asset_unlink = client.delete(
        "/api/r3akt/assignments/assignment-1/assets/asset-1",
        headers=headers,
    )
    assert assignment_asset_unlink.status_code == 200

    assignment_missing_task = client.post(
        "/api/r3akt/assignments",
        json={
            "assignment_uid": "assignment-missing-task",
            "mission_uid": mission_uid,
            "task_uid": "missing-task",
            "team_member_rns_identity": "peer-a",
        },
        headers=headers,
    )
    assert assignment_missing_task.status_code == 400

    mission_expanded = client.get(
        f"/api/r3akt/missions/{mission_uid}",
        params={
            "expand": "topic,teams,team_members,assets,mission_changes,log_entries,assignments,checklists,mission_rde"
        },
        headers=headers,
    )
    assert mission_expanded.status_code == 200
    mission_expanded_payload = mission_expanded.json()
    assert mission_expanded_payload["teams"]
    assert mission_expanded_payload["team_members"]
    assert mission_expanded_payload["assets"]
    assert mission_expanded_payload["mission_changes"]
    assert mission_expanded_payload["log_entries"]
    assert mission_expanded_payload["assignments"]
    assert mission_expanded_payload["checklists"]
    assert mission_expanded_payload["mission_rde"]["role"] == "MISSION_OWNER"

    team_delete = client.post(
        "/api/r3akt/teams",
        json={"uid": "team-delete", "team_name": "Delete Team", "mission_uid": mission_uid},
        headers=headers,
    )
    assert team_delete.status_code == 200
    member_delete_seed = client.post(
        "/api/r3akt/team-members",
        json={
            "uid": "member-delete",
            "team_uid": "team-delete",
            "rns_identity": "peer-delete",
            "display_name": "Peer Delete",
        },
        headers=headers,
    )
    assert member_delete_seed.status_code == 200
    asset_delete_seed = client.post(
        "/api/r3akt/assets",
        json={
            "asset_uid": "asset-delete",
            "team_member_uid": "member-delete",
            "name": "Delete Asset",
            "asset_type": "COMM",
        },
        headers=headers,
    )
    assert asset_delete_seed.status_code == 200
    assert client.get("/api/r3akt/teams/team-delete", headers=headers).status_code == 200
    assert client.get("/api/r3akt/team-members/member-delete", headers=headers).status_code == 200
    assert client.get("/api/r3akt/assets/asset-delete", headers=headers).status_code == 200
    asset_delete = client.delete("/api/r3akt/assets/asset-delete", headers=headers)
    assert asset_delete.status_code == 200
    assert client.get("/api/r3akt/assets/asset-delete", headers=headers).status_code == 404
    member_delete = client.delete("/api/r3akt/team-members/member-delete", headers=headers)
    assert member_delete.status_code == 200
    assert client.get("/api/r3akt/team-members/member-delete", headers=headers).status_code == 404
    team_delete_call = client.delete("/api/r3akt/teams/team-delete", headers=headers)
    assert team_delete_call.status_code == 200
    assert client.get("/api/r3akt/teams/team-delete", headers=headers).status_code == 404

    assert client.get("/api/r3akt/missions", headers=headers).status_code == 200
    assert client.get("/api/r3akt/mission-changes", headers=headers).status_code == 200
    assert client.get("/api/r3akt/log-entries", headers=headers).status_code == 200
    assert client.get("/api/r3akt/teams", headers=headers).status_code == 200
    assert client.get("/api/r3akt/team-members", headers=headers).status_code == 200
    assert client.get("/api/r3akt/assets", headers=headers).status_code == 200
    assert client.get("/api/r3akt/skills", headers=headers).status_code == 200
    assert client.get("/api/r3akt/team-member-skills", headers=headers).status_code == 200
    assert client.get("/api/r3akt/task-skill-requirements", headers=headers).status_code == 200
    assert client.get("/api/r3akt/assignments", headers=headers).status_code == 200
    mission_zone_unlink = client.delete(
        f"/api/r3akt/missions/{mission_uid}/zones/{zone_id}",
        headers=headers,
    )
    assert mission_zone_unlink.status_code == 200
    member_client_unlink = client.delete(
        "/api/r3akt/team-members/member-1/clients/peer-a",
        headers=headers,
    )
    assert member_client_unlink.status_code == 200
    mission_access_delete = client.request(
        "DELETE",
        "/api/r3akt/rights/mission-access",
        json={
            "mission_uid": mission_uid,
            "subject_type": "team_member",
            "subject_id": "member-1",
        },
        headers=headers,
    )
    assert mission_access_delete.status_code == 200
    team_unlink_second = client.delete(
        "/api/r3akt/teams/team-1/missions/mission-parent",
        headers=headers,
    )
    assert team_unlink_second.status_code == 200
    assert team_unlink_second.json()["mission_uids"] == [mission_uid]
    mission_delete = client.delete("/api/r3akt/missions/mission-parent", headers=headers)
    assert mission_delete.status_code == 200

    events = client.get("/api/r3akt/events", headers=headers)
    snapshots = client.get("/api/r3akt/snapshots", headers=headers)
    assert events.status_code == 200
    assert snapshots.status_code == 200
    assert events.json()


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_r3akt_core_registry_routes_use_selected_backend(
    tmp_path: Path,
    backend: str,
) -> None:
    client, _, _, _ = _build_client(tmp_path, backend=backend)
    headers = {"X-API-Key": "secret"}

    mission = client.post(
        "/api/r3akt/missions",
        json={"uid": "mission-core", "mission_name": "Mission Core"},
        headers=headers,
    )
    parent = client.post(
        "/api/r3akt/missions",
        json={"uid": "mission-parent", "mission_name": "Parent"},
        headers=headers,
    )
    assert mission.status_code == 200
    assert parent.status_code == 200

    patched = client.patch(
        "/api/r3akt/missions/mission-core",
        json={"mission_priority": 7, "default_role": "MISSION_SUBSCRIBER"},
        headers=headers,
    )
    assert patched.status_code == 200
    assert patched.json()["mission_priority"] == 7

    parent_link = client.put(
        "/api/r3akt/missions/mission-core/parent",
        json={"parent_uid": "mission-parent"},
        headers=headers,
    )
    assert parent_link.status_code == 200
    assert parent_link.json()["parent_uid"] == "mission-parent"

    rde = client.put(
        "/api/r3akt/missions/mission-core/rde",
        json={"role": "MISSION_OWNER"},
        headers=headers,
    )
    assert rde.status_code == 200
    assert client.get("/api/r3akt/missions/mission-core/rde", headers=headers).json()[
        "role"
    ] == "MISSION_OWNER"

    team = client.post(
        "/api/r3akt/teams",
        json={
            "uid": "team-core",
            "mission_uid": "mission-core",
            "team_name": "Core Team",
        },
        headers=headers,
    )
    assert team.status_code == 200
    assert team.json()["mission_uids"] == ["mission-core"]

    team_link = client.put(
        "/api/r3akt/teams/team-core/missions/mission-parent",
        headers=headers,
    )
    assert team_link.status_code == 200
    assert set(team_link.json()["mission_uids"]) == {"mission-core", "mission-parent"}
    team_missions = client.get("/api/r3akt/teams/team-core/missions", headers=headers)
    assert team_missions.status_code == 200
    assert set(team_missions.json()["mission_uids"]) == {"mission-core", "mission-parent"}

    marker = client.post(
        "/api/markers",
        json={
            "name": "Core Marker",
            "type": "marker",
            "symbol": "marker",
            "category": "test",
            "lat": 35.0,
            "lon": -120.0,
        },
        headers=headers,
    )
    assert marker.status_code == 201
    marker_ref = marker.json()["object_destination_hash"]
    marker_link = client.put(
        f"/api/r3akt/missions/mission-core/markers/{marker_ref}",
        headers=headers,
    )
    assert marker_link.status_code == 200
    mission_markers = client.get(
        "/api/r3akt/missions/mission-core/markers",
        headers=headers,
    )
    assert mission_markers.status_code == 200
    assert mission_markers.json()["marker_ids"] == [marker_ref]

    member = client.post(
        "/api/r3akt/team-members",
        json={
            "uid": "member-core",
            "team_uid": "team-core",
            "rns_identity": "peer-core",
            "display_name": "Peer Core",
        },
        headers=headers,
    )
    assert member.status_code == 200
    member_link = client.put(
        "/api/r3akt/team-members/member-core/clients/peer-core",
        headers=headers,
    )
    assert member_link.status_code == 200
    member_clients = client.get(
        "/api/r3akt/team-members/member-core/clients",
        headers=headers,
    )
    assert member_clients.status_code == 200
    assert member_clients.json()["client_identities"] == ["peer-core"]

    asset = client.post(
        "/api/r3akt/assets",
        json={
            "asset_uid": "asset-core",
            "team_member_uid": "member-core",
            "name": "Radio",
            "asset_type": "COMM",
        },
        headers=headers,
    )
    assert asset.status_code == 200
    assert client.get("/api/r3akt/assets/asset-core", headers=headers).status_code == 200
    assert client.get(
        "/api/r3akt/assets",
        params={"team_member_uid": "member-core"},
        headers=headers,
    ).json()[0]["asset_uid"] == "asset-core"

    skill = client.post(
        "/api/r3akt/skills",
        json={"skill_uid": "skill-core", "name": "Navigation"},
        headers=headers,
    )
    assert skill.status_code == 200
    assert client.get("/api/r3akt/skills", headers=headers).json()[0]["skill_uid"] == "skill-core"

    assert client.delete("/api/r3akt/assets/asset-core", headers=headers).status_code == 200
    assert client.delete(
        "/api/r3akt/team-members/member-core/clients/peer-core",
        headers=headers,
    ).status_code == 200
    assert client.delete("/api/r3akt/team-members/member-core", headers=headers).status_code == 200
    assert client.delete(
        "/api/r3akt/teams/team-core/missions/mission-parent",
        headers=headers,
    ).status_code == 200
    assert client.delete(
        f"/api/r3akt/missions/mission-core/markers/{marker_ref}",
        headers=headers,
    ).status_code == 200
    assert client.delete("/api/r3akt/teams/team-core", headers=headers).status_code == 200
    assert client.delete("/api/r3akt/missions/mission-parent", headers=headers).status_code == 200


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_r3akt_log_routes_use_selected_backend(
    tmp_path: Path,
    backend: str,
) -> None:
    client, _, _, _ = _build_client(tmp_path, backend=backend)
    headers = {"X-API-Key": "secret"}

    mission = client.post(
        "/api/r3akt/missions",
        json={"uid": "mission-log", "mission_name": "Mission Log"},
        headers=headers,
    )
    assert mission.status_code == 200

    change = client.post(
        "/api/r3akt/mission-changes",
        json={"uid": "change-log", "mission_uid": "mission-log", "name": "Updated"},
        headers=headers,
    )
    assert change.status_code == 200
    changes = client.get(
        "/api/r3akt/mission-changes",
        params={"mission_uid": "mission-log"},
        headers=headers,
    )
    assert changes.status_code == 200
    assert changes.json()[0]["uid"] == "change-log"

    default_log = client.post(
        "/api/r3akt/log-entries",
        json={"entry_uid": "log-default", "content": "No mission"},
        headers=headers,
    )
    assert default_log.status_code == 200
    assert default_log.json()["mission_uid"] == "mission-default"

    log_entry = client.post(
        "/api/r3akt/log-entries",
        json={
            "entry_uid": "log-entry",
            "mission_uid": "mission-log",
            "content": "Mission observed",
            "keywords": ["observation"],
        },
        headers=headers,
    )
    assert log_entry.status_code == 200
    logs = client.get(
        "/api/r3akt/log-entries",
        params={"mission_uid": "mission-log"},
        headers=headers,
    )
    assert logs.status_code == 200
    assert logs.json()[0]["entry_uid"] == "log-entry"


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_r3akt_assignment_skill_routes_use_selected_backend(
    tmp_path: Path,
    backend: str,
) -> None:
    client, _, _, _ = _build_client(tmp_path, backend=backend)
    headers = {"X-API-Key": "secret"}

    assert client.post(
        "/api/r3akt/missions",
        json={"uid": "mission-assign", "mission_name": "Mission Assign"},
        headers=headers,
    ).status_code == 200
    assert client.post(
        "/api/r3akt/teams",
        json={
            "uid": "team-assign",
            "mission_uid": "mission-assign",
            "team_name": "Assign Team",
        },
        headers=headers,
    ).status_code == 200
    assert client.post(
        "/api/r3akt/team-members",
        json={
            "uid": "member-assign",
            "team_uid": "team-assign",
            "rns_identity": "peer-assign",
            "display_name": "Peer Assign",
        },
        headers=headers,
    ).status_code == 200
    assert client.post(
        "/api/r3akt/assets",
        json={
            "asset_uid": "asset-assign",
            "team_member_uid": "member-assign",
            "name": "Radio",
            "asset_type": "COMM",
        },
        headers=headers,
    ).status_code == 200
    assert client.post(
        "/api/r3akt/skills",
        json={"skill_uid": "skill-assign", "name": "Navigation"},
        headers=headers,
    ).status_code == 200

    task_uid = "task-assign"
    if backend == "python":
        domain = MissionDomainService(
            HubConfigurationManager(storage_path=tmp_path).config.hub_database_path
        )
        template = domain.create_checklist_template(
            {
                "uid": "template-assign",
                "template_name": "Assignment Template",
                "created_by_team_member_rns_identity": "peer-assign",
            }
        )
        checklist = domain.create_checklist_online(
            {
                "checklist_uid": "checklist-assign",
                "template_uid": template["uid"],
                "name": "Assignment Checklist",
                "mission_uid": "mission-assign",
            }
        )
        domain.add_checklist_task_row(
            str(checklist["uid"]),
            {"task_uid": task_uid, "number": 1},
        )
    else:
        template = client.post(
            "/checklists/templates",
            json={
                "template": {
                    "uid": "template-assign",
                    "template_name": "Assignment Template",
                    "created_by_team_member_rns_identity": "peer-assign",
                }
            },
            headers=headers,
        )
        assert template.status_code == 200
        checklist = client.post(
            "/checklists",
            json={
                "checklist_uid": "checklist-assign",
                "template_uid": "template-assign",
                "name": "Assignment Checklist",
                "mission_uid": "mission-assign",
            },
            headers=headers,
        )
        assert checklist.status_code == 200
        row = client.post(
            "/checklists/checklist-assign/tasks",
            json={"task_uid": task_uid, "number": 1},
            headers=headers,
        )
        assert row.status_code == 200

    member_skill = client.post(
        "/api/r3akt/team-member-skills",
        json={
            "uid": "member-skill-assign",
            "team_member_rns_identity": "peer-assign",
            "skill_uid": "skill-assign",
            "level": 3,
        },
        headers=headers,
    )
    assert member_skill.status_code == 200
    assert client.get(
        "/api/r3akt/team-member-skills",
        params={"team_member_rns_identity": "peer-assign"},
        headers=headers,
    ).json()[0]["skill_uid"] == "skill-assign"

    requirement = client.post(
        "/api/r3akt/task-skill-requirements",
        json={
            "uid": "req-assign",
            "task_uid": task_uid,
            "skill_uid": "skill-assign",
            "minimum_level": 2,
        },
        headers=headers,
    )
    assert requirement.status_code == 200
    assert client.get(
        "/api/r3akt/task-skill-requirements",
        params={"task_uid": task_uid},
        headers=headers,
    ).json()[0]["skill_uid"] == "skill-assign"

    assignment = client.post(
        "/api/r3akt/assignments",
        json={
            "assignment_uid": "assignment-assign",
            "mission_uid": "mission-assign",
            "task_uid": task_uid,
            "team_member_rns_identity": "peer-assign",
            "assets": ["asset-assign"],
        },
        headers=headers,
    )
    assert assignment.status_code == 200
    assert assignment.json()["assets"] == ["asset-assign"]

    assert client.put(
        "/api/r3akt/assignments/assignment-assign/assets/asset-assign",
        headers=headers,
    ).status_code == 200
    assert client.put(
        "/api/r3akt/assignments/assignment-assign/assets",
        json={"assets": ["asset-assign"]},
        headers=headers,
    ).status_code == 200
    assert client.get(
        "/api/r3akt/assignments",
        params={"mission_uid": "mission-assign", "task_uid": task_uid},
        headers=headers,
    ).json()[0]["assignment_uid"] == "assignment-assign"
    assert client.delete(
        "/api/r3akt/assignments/assignment-assign/assets/asset-assign",
        headers=headers,
    ).status_code == 200


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_r3akt_missions_route_applies_limit(tmp_path: Path, backend: str) -> None:
    client, _, _, _ = _build_client(tmp_path, backend=backend)
    headers = {"X-API-Key": "secret"}

    for mission_uid in ("mission-1", "mission-2", "mission-3"):
        response = client.post(
            "/api/r3akt/missions",
            json={"uid": mission_uid, "mission_name": mission_uid},
            headers=headers,
        )
        assert response.status_code == 200

    limited = client.get("/api/r3akt/missions", params={"limit": 2}, headers=headers)
    single = client.get("/api/r3akt/missions", params={"limit": 1}, headers=headers)

    assert limited.status_code == 200
    assert len(limited.json()) == 2
    assert single.status_code == 200
    assert len(single.json()) == 1


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_sensitive_core_routes_require_auth_for_remote_clients(
    tmp_path: Path, backend: str
) -> None:
    client, _, _, _ = _build_client(tmp_path, backend=backend)
    remote_client = TestClient(client.app, client=("198.51.100.10", 50000))
    now = int(datetime.now(timezone.utc).timestamp())

    assert remote_client.get("/Telemetry", params={"since": now}).status_code == 401
    assert remote_client.post("/RTH", params={"identity": "dest-1"}).status_code == 401
    assert remote_client.put("/RTH", params={"identity": "dest-1"}).status_code == 401
    assert remote_client.post("/RCH", params={"identity": "dest-1"}).status_code == 401
    assert remote_client.put("/RCH", params={"identity": "dest-1"}).status_code == 401


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_checklist_routes_matrix_and_errors(tmp_path: Path, backend: str) -> None:
    client, _, _, _ = _build_client(tmp_path, backend=backend)
    headers = {"X-API-Key": "secret"}

    template_bad_payload = client.post(
        "/checklists/templates",
        json={"template": "invalid"},
        headers=headers,
    )
    assert template_bad_payload.status_code == 400

    template = client.post(
        "/checklists/templates",
        json={
            "template": {
                "template_name": "Template Alpha",
                "description": "Template",
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
        },
        headers=headers,
    )
    assert template.status_code == 200
    template_uid = template.json()["uid"]

    template_get = client.get(f"/checklists/templates/{template_uid}", headers=headers)
    assert template_get.status_code == 200
    assert template_get.json()["uid"] == template_uid

    list_templates = client.get("/checklists/templates", headers=headers)
    assert list_templates.status_code == 200

    patch_bad_payload = client.patch(
        f"/checklists/templates/{template_uid}",
        json={"patch": "invalid"},
        headers=headers,
    )
    assert patch_bad_payload.status_code == 400

    patch_template = client.patch(
        f"/checklists/templates/{template_uid}",
        json={"patch": {"template_name": "Template Beta"}},
        headers=headers,
    )
    assert patch_template.status_code == 200

    clone_missing_name = client.post(
        f"/checklists/templates/{template_uid}/clone",
        json={},
        headers=headers,
    )
    assert clone_missing_name.status_code == 400

    clone_template = client.post(
        f"/checklists/templates/{template_uid}/clone",
        json={"template_name": "Template Clone", "description": "Clone"},
        headers=headers,
    )
    assert clone_template.status_code == 200
    clone_uid = clone_template.json()["uid"]

    delete_missing_template = client.delete(
        "/checklists/templates/missing-template",
        headers=headers,
    )
    assert delete_missing_template.status_code == 404

    checklist_online_bad = client.post(
        "/checklists",
        json={"name": "Missing template"},
        headers=headers,
    )
    assert checklist_online_bad.status_code == 400

    checklist_online = client.post(
        "/checklists",
        json={
            "template_uid": template_uid,
            "name": "Checklist Online",
            "description": "Online checklist",
            "start_time": datetime.now(timezone.utc).isoformat(),
            "source_identity": "peer-a",
        },
        headers=headers,
    )
    assert checklist_online.status_code == 200
    checklist_uid = checklist_online.json()["uid"]

    checklist_offline = client.post(
        "/checklists/offline",
        json={
            "name": "Checklist Offline",
            "description": "Offline checklist",
            "source_identity": "peer-a",
            "origin_type": "BLANK_TEMPLATE",
        },
        headers=headers,
    )
    assert checklist_offline.status_code == 200
    offline_uid = checklist_offline.json()["uid"]

    list_checklists = client.get("/checklists", headers=headers)
    assert list_checklists.status_code == 200

    join_missing = client.post("/checklists/missing/join", json={}, headers=headers)
    assert join_missing.status_code == 404

    join_checklist = client.post(
        f"/checklists/{checklist_uid}/join",
        json={"source_identity": "peer-a"},
        headers=headers,
    )
    assert join_checklist.status_code == 200

    get_checklist = client.get(f"/checklists/{checklist_uid}", headers=headers)
    assert get_checklist.status_code == 200

    mission = client.post(
        "/api/r3akt/missions",
        json={"mission_name": "Checklist Link Mission"},
        headers=headers,
    )
    assert mission.status_code == 200
    mission_uid = mission.json()["uid"]

    checklist_patch_bad_payload = client.patch(
        f"/checklists/{checklist_uid}",
        json={"patch": "invalid"},
        headers=headers,
    )
    assert checklist_patch_bad_payload.status_code == 400

    checklist_patch_missing = client.patch(
        "/checklists/missing",
        json={"patch": {"mission_uid": mission_uid}},
        headers=headers,
    )
    assert checklist_patch_missing.status_code == 404

    checklist_patch_missing_mission = client.patch(
        f"/checklists/{checklist_uid}",
        json={"patch": {"mission_uid": "missing-mission"}},
        headers=headers,
    )
    assert checklist_patch_missing_mission.status_code == 400

    checklist_patch = client.patch(
        f"/checklists/{checklist_uid}",
        json={"patch": {"mission_uid": mission_uid}},
        headers=headers,
    )
    assert checklist_patch.status_code == 200
    assert checklist_patch.json()["mission_id"] == mission_uid

    delete_missing_checklist = client.delete("/checklists/missing", headers=headers)
    assert delete_missing_checklist.status_code == 404

    upload_missing = client.post("/checklists/missing/upload", json={}, headers=headers)
    assert upload_missing.status_code == 404

    upload_checklist = client.post(
        f"/checklists/{offline_uid}/upload",
        json={"source_identity": "peer-a"},
        headers=headers,
    )
    assert upload_checklist.status_code == 200

    publish_missing = client.post(
        "/checklists/missing/feeds/feed-1",
        json={},
        headers=headers,
    )
    assert publish_missing.status_code == 404

    publish_feed = client.post(
        f"/checklists/{offline_uid}/feeds/feed-1",
        json={"source_identity": "peer-a"},
        headers=headers,
    )
    assert publish_feed.status_code == 200

    task_add = client.post(
        f"/checklists/{checklist_uid}/tasks",
        json={"number": 1, "due_relative_minutes": 10},
        headers=headers,
    )
    assert task_add.status_code == 200
    task_uid = task_add.json()["tasks"][0]["task_uid"]
    column_uid = next(
        item["column_uid"]
        for item in task_add.json()["columns"]
        if item["column_type"] == "SHORT_STRING"
    )

    task_status_invalid = client.post(
        f"/checklists/{checklist_uid}/tasks/{task_uid}/status",
        json={"user_status": "INVALID"},
        headers=headers,
    )
    assert task_status_invalid.status_code == 400

    task_status = client.post(
        f"/checklists/{checklist_uid}/tasks/{task_uid}/status",
        json={"user_status": "COMPLETE", "changed_by_team_member_rns_identity": "peer-a"},
        headers=headers,
    )
    assert task_status.status_code == 200

    task_style = client.patch(
        f"/checklists/{checklist_uid}/tasks/{task_uid}/row-style",
        json={"row_background_color": "#112233", "line_break_enabled": True},
        headers=headers,
    )
    assert task_style.status_code == 200

    task_cell_missing = client.patch(
        f"/checklists/{checklist_uid}/tasks/{task_uid}/cells/missing",
        json={"value": "x"},
        headers=headers,
    )
    assert task_cell_missing.status_code == 404

    task_cell = client.patch(
        f"/checklists/{checklist_uid}/tasks/{task_uid}/cells/{column_uid}",
        json={"value": "Inspect", "updated_by_team_member_rns_identity": "peer-a"},
        headers=headers,
    )
    assert task_cell.status_code == 200

    task_delete = client.delete(
        f"/checklists/{checklist_uid}/tasks/{task_uid}",
        headers=headers,
    )
    assert task_delete.status_code == 200

    task_delete_missing = client.delete(
        f"/checklists/{checklist_uid}/tasks/{task_uid}",
        headers=headers,
    )
    assert task_delete_missing.status_code == 404

    import_missing_csv = client.post(
        "/checklists/import/csv",
        json={},
        headers=headers,
    )
    assert import_missing_csv.status_code == 400

    encoded_csv = base64.b64encode(b"Task,Description\nTask 1,Inspect\nTask 2,Secure\n").decode("ascii")
    import_csv = client.post(
        "/checklists/import/csv",
        json={"csv_filename": "import.csv", "csv_base64": encoded_csv},
        headers=headers,
    )
    assert import_csv.status_code == 200
    import_payload = import_csv.json()
    assert len(import_payload["tasks"]) == 2
    assert any(column["column_name"] == "Task" for column in import_payload["columns"])
    assert import_payload["tasks"][0]["legacy_value"] == "Task 1"
    assert [task["due_relative_minutes"] for task in import_payload["tasks"]] == [30, 60]

    delete_checklist = client.delete(f"/checklists/{offline_uid}", headers=headers)
    assert delete_checklist.status_code == 200

    delete_clone = client.delete(f"/checklists/templates/{clone_uid}", headers=headers)
    assert delete_clone.status_code == 200
