"""Name resolution helpers for mission-delta markdown rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from reticulum_telemetry_hub.reticulum_server.mission_delta_text import clean_text
from reticulum_telemetry_hub.reticulum_server.mission_delta_text import status_label


@dataclass
class _ChecklistCache:
    """Cached checklist labels for markdown rendering."""

    task_labels: dict[str, str]
    column_names: dict[str, str]


class MissionDeltaNameResolver:
    """Resolve mission-delta labels from the mission-domain service."""

    def __init__(self, domain_service: Any):
        """Initialize resolver with per-message caches.

        Args:
            domain_service: Mission domain service instance.
        """

        self._domain = domain_service
        self._mission_names: dict[str, str] = {}
        self._team_members_loaded_for_mission: set[str] = set()
        self._team_member_identity_names: dict[str, str] = {}
        self._team_member_uid_names: dict[str, str] = {}
        self._checklists: dict[str, _ChecklistCache] = {}
        self._asset_names: dict[str, str] = {}

    def mission_name(self, mission_uid: str) -> str:
        """Resolve mission display name."""

        normalized = clean_text(mission_uid)
        if not normalized:
            return "Mission"
        cached = self._mission_names.get(normalized)
        if cached:
            return cached
        name = ""
        try:
            payload = self._domain.get_mission(normalized)
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            name = clean_text(payload.get("mission_name") or payload.get("name"))
        resolved = name or "Mission"
        self._mission_names[normalized] = resolved
        return resolved

    def team_member_name_from_identity(
        self, mission_uid: str, identity: Any
    ) -> str | None:
        """Resolve a team-member display name by identity hash."""

        normalized_identity = clean_text(identity).lower()
        if not normalized_identity:
            return None
        self._load_mission_team_members(mission_uid)
        return self._team_member_identity_names.get(normalized_identity)

    def team_member_name_from_uid(self, mission_uid: str, team_member_uid: Any) -> str | None:
        """Resolve a team-member display name by team-member UID."""

        normalized_uid = clean_text(team_member_uid)
        if not normalized_uid:
            return None
        self._load_mission_team_members(mission_uid)
        return self._team_member_uid_names.get(normalized_uid)

    def task_label(self, checklist_uid: Any, task_uid: Any) -> str:
        """Resolve a checklist task label."""

        normalized_checklist_uid = clean_text(checklist_uid)
        normalized_task_uid = clean_text(task_uid)
        if not normalized_checklist_uid or not normalized_task_uid:
            return "Checklist task"
        cache = self._load_checklist(normalized_checklist_uid)
        return cache.task_labels.get(normalized_task_uid, "Checklist task")

    def column_name(self, checklist_uid: Any, column_uid: Any) -> str:
        """Resolve a checklist column name."""

        normalized_checklist_uid = clean_text(checklist_uid)
        normalized_column_uid = clean_text(column_uid)
        if not normalized_checklist_uid or not normalized_column_uid:
            return "field"
        cache = self._load_checklist(normalized_checklist_uid)
        return cache.column_names.get(normalized_column_uid, "field")

    def asset_name(self, asset_uid: Any, fallback_name: Any = None) -> str:
        """Resolve an asset name from UID, with fallback."""

        fallback = clean_text(fallback_name)
        if fallback:
            return fallback
        normalized_uid = clean_text(asset_uid)
        if not normalized_uid:
            return "asset"
        cached = self._asset_names.get(normalized_uid)
        if cached:
            return cached
        name = ""
        try:
            payload = self._domain.get_asset(normalized_uid)
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            name = clean_text(payload.get("name"))
        resolved = name or "asset"
        self._asset_names[normalized_uid] = resolved
        return resolved

    def _load_mission_team_members(self, mission_uid: str) -> None:
        """Populate team-member caches for a mission."""

        normalized_mission_uid = clean_text(mission_uid)
        if not normalized_mission_uid:
            return
        if normalized_mission_uid in self._team_members_loaded_for_mission:
            return
        self._team_members_loaded_for_mission.add(normalized_mission_uid)

        try:
            teams = self._domain.list_teams(mission_uid=normalized_mission_uid)
        except Exception:
            teams = []

        team_uids = []
        for team in teams if isinstance(teams, list) else []:
            if isinstance(team, dict):
                team_uid = clean_text(team.get("uid"))
                if team_uid:
                    team_uids.append(team_uid)

        for team_uid in team_uids:
            try:
                members = self._domain.list_team_members(team_uid=team_uid)
            except Exception:
                members = []
            for member in members if isinstance(members, list) else []:
                if not isinstance(member, dict):
                    continue
                name = clean_text(
                    member.get("display_name")
                    or member.get("callsign")
                    or member.get("name")
                )
                if not name:
                    continue
                identity = clean_text(member.get("rns_identity")).lower()
                if identity:
                    self._team_member_identity_names.setdefault(identity, name)
                member_uid = clean_text(member.get("uid"))
                if member_uid:
                    self._team_member_uid_names.setdefault(member_uid, name)

    def _load_checklist(self, checklist_uid: str) -> _ChecklistCache:
        """Load checklist task/column labels for lookups."""

        cached = self._checklists.get(checklist_uid)
        if cached is not None:
            return cached

        task_labels: dict[str, str] = {}
        column_names: dict[str, str] = {}
        short_string_columns: set[str] = set()

        try:
            checklist = self._domain.get_checklist(checklist_uid)
        except Exception:
            checklist = {}

        if isinstance(checklist, dict):
            columns = checklist.get("columns")
            for column in columns if isinstance(columns, list) else []:
                if not isinstance(column, dict):
                    continue
                column_uid = clean_text(column.get("column_uid"))
                column_name = clean_text(column.get("column_name") or column.get("name"))
                if column_uid and column_name:
                    column_names[column_uid] = column_name
                column_type = status_label(column.get("column_type"))
                if column_uid and column_type == "SHORT_STRING":
                    short_string_columns.add(column_uid)

            tasks = checklist.get("tasks")
            for task in tasks if isinstance(tasks, list) else []:
                if not isinstance(task, dict):
                    continue
                task_uid = clean_text(task.get("task_uid"))
                if not task_uid:
                    continue
                label = clean_text(task.get("legacy_value"))
                if not label:
                    cells = task.get("cells")
                    for cell in cells if isinstance(cells, list) else []:
                        if not isinstance(cell, dict):
                            continue
                        column_uid = clean_text(cell.get("column_uid"))
                        if column_uid not in short_string_columns:
                            continue
                        label = clean_text(cell.get("value"))
                        if label:
                            break
                if not label:
                    number = task.get("number")
                    number_text = clean_text(number)
                    label = f"Checklist task #{number_text}" if number_text else "Checklist task"
                task_labels[task_uid] = label

        result = _ChecklistCache(task_labels=task_labels, column_names=column_names)
        self._checklists[checklist_uid] = result
        return result
