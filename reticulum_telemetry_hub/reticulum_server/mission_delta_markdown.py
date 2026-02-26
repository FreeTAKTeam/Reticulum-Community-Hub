"""Render compact mission-delta markdown payloads for generic LXMF clients."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_MAX_MARKDOWN_BYTES = 700


def _clean_text(value: Any) -> str:
    """Return a flattened, trimmed text value.

    Args:
        value: Raw value from domain payloads.

    Returns:
        Sanitized string value with single-space whitespace.
    """

    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    return " ".join(text.split())


def _clip_text(value: Any, max_chars: int) -> str:
    """Return a clipped text value.

    Args:
        value: Raw text value.
        max_chars: Maximum character count for the returned string.

    Returns:
        Clipped string using ellipsis when needed.
    """

    text = _clean_text(value)
    if not text:
        return ""
    limit = max(1, int(max_chars))
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return f"{text[: limit - 3].rstrip()}..."


def _status_label(value: Any) -> str:
    """Return a human-readable status string.

    Args:
        value: Raw status value.

    Returns:
        Uppercase status token with underscores preserved.
    """

    status = _clean_text(value)
    return status.upper() if status else "UNKNOWN"


def _bytes_len(text: str) -> int:
    """Return UTF-8 byte length for text.

    Args:
        text: Input text.

    Returns:
        UTF-8 byte length.
    """

    return len(text.encode("utf-8"))


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
        """Resolve mission display name.

        Args:
            mission_uid: Mission identifier.

        Returns:
            Human-readable mission name, or ``Mission`` fallback.
        """

        normalized = _clean_text(mission_uid)
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
            name = _clean_text(payload.get("mission_name") or payload.get("name"))
        resolved = name or "Mission"
        self._mission_names[normalized] = resolved
        return resolved

    def team_member_name_from_identity(
        self, mission_uid: str, identity: Any
    ) -> str | None:
        """Resolve a team-member display name by identity hash.

        Args:
            mission_uid: Mission identifier.
            identity: Team-member identity hash.

        Returns:
            Display name when found, otherwise ``None``.
        """

        normalized_identity = _clean_text(identity).lower()
        if not normalized_identity:
            return None
        self._load_mission_team_members(mission_uid)
        return self._team_member_identity_names.get(normalized_identity)

    def team_member_name_from_uid(self, mission_uid: str, team_member_uid: Any) -> str | None:
        """Resolve a team-member display name by team-member UID.

        Args:
            mission_uid: Mission identifier.
            team_member_uid: Team-member UID.

        Returns:
            Display name when found, otherwise ``None``.
        """

        normalized_uid = _clean_text(team_member_uid)
        if not normalized_uid:
            return None
        self._load_mission_team_members(mission_uid)
        return self._team_member_uid_names.get(normalized_uid)

    def task_label(self, checklist_uid: Any, task_uid: Any) -> str:
        """Resolve a checklist task label.

        Args:
            checklist_uid: Checklist UID.
            task_uid: Task UID.

        Returns:
            Human-readable task label with no UID content.
        """

        normalized_checklist_uid = _clean_text(checklist_uid)
        normalized_task_uid = _clean_text(task_uid)
        if not normalized_checklist_uid or not normalized_task_uid:
            return "Checklist task"
        cache = self._load_checklist(normalized_checklist_uid)
        return cache.task_labels.get(normalized_task_uid, "Checklist task")

    def column_name(self, checklist_uid: Any, column_uid: Any) -> str:
        """Resolve a checklist column name.

        Args:
            checklist_uid: Checklist UID.
            column_uid: Column UID.

        Returns:
            Column display name with ``field`` fallback.
        """

        normalized_checklist_uid = _clean_text(checklist_uid)
        normalized_column_uid = _clean_text(column_uid)
        if not normalized_checklist_uid or not normalized_column_uid:
            return "field"
        cache = self._load_checklist(normalized_checklist_uid)
        return cache.column_names.get(normalized_column_uid, "field")

    def asset_name(self, asset_uid: Any, fallback_name: Any = None) -> str:
        """Resolve an asset name from UID, with fallback.

        Args:
            asset_uid: Asset UID.
            fallback_name: Optional name already present in delta payload.

        Returns:
            Human-readable asset name with ``asset`` fallback.
        """

        fallback = _clean_text(fallback_name)
        if fallback:
            return fallback
        normalized_uid = _clean_text(asset_uid)
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
            name = _clean_text(payload.get("name"))
        resolved = name or "asset"
        self._asset_names[normalized_uid] = resolved
        return resolved

    def _load_mission_team_members(self, mission_uid: str) -> None:
        """Populate team-member caches for a mission.

        Args:
            mission_uid: Mission identifier.
        """

        normalized_mission_uid = _clean_text(mission_uid)
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
                team_uid = _clean_text(team.get("uid"))
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
                name = _clean_text(
                    member.get("display_name")
                    or member.get("callsign")
                    or member.get("name")
                )
                if not name:
                    continue
                identity = _clean_text(member.get("rns_identity")).lower()
                if identity:
                    self._team_member_identity_names.setdefault(identity, name)
                member_uid = _clean_text(member.get("uid"))
                if member_uid:
                    self._team_member_uid_names.setdefault(member_uid, name)

    def _load_checklist(self, checklist_uid: str) -> _ChecklistCache:
        """Load checklist task/column labels for lookups.

        Args:
            checklist_uid: Checklist UID.

        Returns:
            Cached checklist labels.
        """

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
                column_uid = _clean_text(column.get("column_uid"))
                column_name = _clean_text(column.get("column_name") or column.get("name"))
                if column_uid and column_name:
                    column_names[column_uid] = column_name
                column_type = _status_label(column.get("column_type"))
                if column_uid and column_type == "SHORT_STRING":
                    short_string_columns.add(column_uid)

            tasks = checklist.get("tasks")
            for task in tasks if isinstance(tasks, list) else []:
                if not isinstance(task, dict):
                    continue
                task_uid = _clean_text(task.get("task_uid"))
                if not task_uid:
                    continue
                label = _clean_text(task.get("legacy_value"))
                if not label:
                    cells = task.get("cells")
                    for cell in cells if isinstance(cells, list) else []:
                        if not isinstance(cell, dict):
                            continue
                        column_uid = _clean_text(cell.get("column_uid"))
                        if column_uid not in short_string_columns:
                            continue
                        label = _clean_text(cell.get("value"))
                        if label:
                            break
                if not label:
                    number = task.get("number")
                    number_text = _clean_text(number)
                    label = f"Checklist task #{number_text}" if number_text else "Checklist task"
                task_labels[task_uid] = label

        result = _ChecklistCache(task_labels=task_labels, column_names=column_names)
        self._checklists[checklist_uid] = result
        return result


def _join_lines(lines: list[str]) -> str:
    """Return newline-joined markdown lines.

    Args:
        lines: Markdown lines.

    Returns:
        Joined markdown body.
    """

    return "\n".join([line for line in lines if _clean_text(line)])


def _ensure_within_budget(
    *,
    header: str,
    required_lines: list[str],
    optional_lines: list[str],
    max_bytes: int,
) -> str:
    """Render markdown while respecting byte limits.

    Args:
        header: Markdown heading line.
        required_lines: Required markdown bullet lines.
        optional_lines: Optional markdown bullet lines.
        max_bytes: Maximum UTF-8 body size.

    Returns:
        Budget-compliant markdown payload.
    """

    target_bytes = max(64, int(max_bytes))
    lines = [header, *required_lines, *optional_lines]
    text = _join_lines(lines)
    if _bytes_len(text) <= target_bytes:
        return text

    trimmed_optional = list(optional_lines)
    while trimmed_optional:
        trimmed_optional.pop()
        text = _join_lines([header, *required_lines, *trimmed_optional])
        if _bytes_len(text) <= target_bytes:
            return text

    generic = _join_lines(
        [
            header,
            "- Update: Mission content updated",
            "- Detail: Additional details unavailable on this link",
        ]
    )
    if _bytes_len(generic) <= target_bytes:
        return generic

    mission_name = _clip_text(header.replace("### Mission ", ""), max_chars=64)
    shortened_header = f"### Mission {mission_name}" if mission_name else "### Mission"
    shortened = _join_lines([shortened_header, "- Update: Mission content updated"])
    if _bytes_len(shortened) <= target_bytes:
        return shortened

    encoded = shortened.encode("utf-8")
    return encoded[:target_bytes].decode("utf-8", errors="ignore").rstrip()


def _render_log_delta(
    *,
    mission_name: str,
    log_delta: dict[str, Any],
) -> str:
    """Render markdown for a log delta.

    Args:
        mission_name: Mission display name.
        log_delta: Log delta payload.

    Returns:
        Markdown summary text.
    """

    header = f"### Mission {_clip_text(mission_name, 120)}"
    client_time = _clip_text(log_delta.get("client_time"), 32)
    content = _clip_text(log_delta.get("content"), 180)
    detail_components = [part for part in (client_time, content) if part]
    detail_text = ", ".join(detail_components) if detail_components else "log update"
    required_lines = [
        "- Update: Log added",
        f'- Detail: "{detail_text}"',
    ]
    keywords = log_delta.get("keywords")
    tags = ""
    if isinstance(keywords, list):
        normalized = [_clip_text(item, 24) for item in keywords if _clean_text(item)]
        normalized = [item for item in normalized if item]
        if normalized:
            tags = ", ".join(normalized[:4])
    optional_lines = [f"- Tags: {tags}"] if tags else []
    return _ensure_within_budget(
        header=header,
        required_lines=required_lines,
        optional_lines=optional_lines,
        max_bytes=DEFAULT_MAX_MARKDOWN_BYTES,
    )


def render_mission_delta_markdown(
    *,
    mission_uid: str,
    mission_change: dict[str, Any],
    delta: dict[str, Any],
    resolver: MissionDeltaNameResolver,
    max_bytes: int = DEFAULT_MAX_MARKDOWN_BYTES,
) -> str:
    """Render a compact markdown body for generic LXMF consumers.

    Args:
        mission_uid: Mission UID for lookup context.
        mission_change: Mission change payload.
        delta: Delta payload from the mission change.
        resolver: Resolver used for human-readable names.
        max_bytes: Maximum UTF-8 payload size.

    Returns:
        Markdown body within requested byte budget.
    """

    mission_name = resolver.mission_name(mission_uid)
    header = f"### Mission {_clip_text(mission_name, 120)}"
    max_payload_bytes = max(64, int(max_bytes))
    logs = list(delta.get("logs") or [])
    assets = list(delta.get("assets") or [])
    tasks = list(delta.get("tasks") or [])

    if logs and isinstance(logs[0], dict):
        rendered = _render_log_delta(mission_name=mission_name, log_delta=logs[0])
        if _bytes_len(rendered) <= max_payload_bytes:
            return rendered
        return _ensure_within_budget(
            header=header,
            required_lines=["- Update: Mission content updated"],
            optional_lines=[],
            max_bytes=max_payload_bytes,
        )

    if assets and isinstance(assets[0], dict):
        asset_delta = assets[0]
        op = _clean_text(asset_delta.get("op")).lower()
        update = "Asset removed" if op == "delete" else "Asset updated"
        asset_name = resolver.asset_name(
            asset_uid=asset_delta.get("asset_uid"),
            fallback_name=asset_delta.get("name"),
        )
        asset_type = _clip_text(asset_delta.get("asset_type"), 20)
        status = _clip_text(asset_delta.get("status"), 20)
        detail_suffix_parts = [item for item in (asset_type, status if op != "delete" else "") if item]
        detail_suffix = f" ({', '.join(detail_suffix_parts)})" if detail_suffix_parts else ""
        required_lines = [
            f"- Update: {update}",
            f"- Detail: {_clip_text(asset_name, 80)}{detail_suffix}",
        ]
        optional_lines: list[str] = []
        team_member_name = resolver.team_member_name_from_uid(
            mission_uid, asset_delta.get("team_member_uid")
        )
        if team_member_name:
            optional_lines.append(f"- Assigned: {_clip_text(team_member_name, 48)}")
        location = _clip_text(asset_delta.get("location"), 96)
        if location:
            optional_lines.append(f"- Location: {location}")
        return _ensure_within_budget(
            header=header,
            required_lines=required_lines,
            optional_lines=optional_lines,
            max_bytes=max_payload_bytes,
        )

    if tasks and isinstance(tasks[0], dict):
        task_delta = tasks[0]
        op = _clean_text(task_delta.get("op")).lower()
        checklist_uid = task_delta.get("checklist_uid")
        task_uid = task_delta.get("task_uid")
        task_label = resolver.task_label(checklist_uid, task_uid)
        required_lines = ["- Update: Mission content updated", "- Detail: Checklist task"]
        optional_lines: list[str] = []

        if op == "status_set":
            current_status = _status_label(task_delta.get("current_status"))
            previous_status = _status_label(task_delta.get("previous_status"))
            required_lines = [
                "- Update: Checklist task status changed",
                f"- Detail: {_clip_text(task_label, 80)}",
                f"- Status: {previous_status} -> {current_status}",
            ]
            if current_status in {"COMPLETE", "COMPLETE_LATE"}:
                completer = resolver.team_member_name_from_identity(
                    mission_uid,
                    task_delta.get("changed_by_team_member_rns_identity"),
                )
                required_lines.append(
                    f"- Completed by: {_clip_text(completer or 'Unknown team member', 48)}"
                )
        elif op == "cell_set":
            column_name = resolver.column_name(checklist_uid, task_delta.get("column_uid"))
            value = _clip_text(task_delta.get("value"), 100)
            required_lines = [
                "- Update: Checklist task updated",
                f"- Detail: {_clip_text(task_label, 80)}",
                f"- Field: {_clip_text(column_name, 48)} = {value or '(empty)'}",
            ]
        elif op == "row_style_set":
            required_lines = [
                "- Update: Checklist task formatting changed",
                f"- Detail: {_clip_text(task_label, 80)}",
            ]
            style_parts = []
            color = _clip_text(task_delta.get("row_background_color"), 16)
            if color:
                style_parts.append(f"color {color}")
            if task_delta.get("line_break_enabled") is not None:
                line_break = "on" if bool(task_delta.get("line_break_enabled")) else "off"
                style_parts.append(f"line-break {line_break}")
            if style_parts:
                optional_lines.append(f"- Style: {', '.join(style_parts)}")
        elif op == "row_added":
            required_lines = [
                "- Update: Checklist task added",
                f"- Detail: {_clip_text(task_label, 80)}",
            ]
            due = _clip_text(task_delta.get("due_dtg"), 32)
            if due:
                optional_lines.append(f"- Due: {due}")
        elif op == "row_deleted":
            required_lines = [
                "- Update: Checklist task removed",
                f"- Detail: {_clip_text(task_label, 80)}",
            ]
        elif op == "assignment_upsert":
            assignee = resolver.team_member_name_from_identity(
                mission_uid,
                task_delta.get("team_member_rns_identity"),
            )
            status = _status_label(task_delta.get("status"))
            required_lines = [
                "- Update: Assignment updated",
                f"- Detail: {_clip_text(task_label, 80)} -> {_clip_text(assignee or 'Unknown team member', 48)}",
                f"- Status: {status}",
            ]
            assets_value = task_delta.get("assets")
            if isinstance(assets_value, list) and assets_value:
                asset_labels = [
                    resolver.asset_name(asset_uid=item, fallback_name=None)
                    for item in assets_value[:3]
                ]
                optional_lines.append(
                    f"- Assets: {', '.join(_clip_text(name, 24) for name in asset_labels)}"
                )
                if len(assets_value) > 3:
                    optional_lines.append(f"- Assets total: {len(assets_value)}")
        elif op == "assignment_assets_set":
            required_lines = [
                "- Update: Assignment asset set replaced",
                f"- Detail: {_clip_text(task_label, 80)}",
            ]
            assets_value = task_delta.get("assets")
            if isinstance(assets_value, list) and assets_value:
                labels = [
                    resolver.asset_name(asset_uid=item, fallback_name=None)
                    for item in assets_value[:3]
                ]
                optional_lines.append(
                    f"- Assets: {', '.join(_clip_text(name, 24) for name in labels)}"
                )
                if len(assets_value) > 3:
                    optional_lines.append(f"- Assets total: {len(assets_value)}")
        elif op in {"assignment_asset_linked", "assignment_asset_unlinked"}:
            update = "Assignment asset linked" if op == "assignment_asset_linked" else "Assignment asset removed"
            required_lines = [
                f"- Update: {update}",
                f"- Detail: {_clip_text(task_label, 80)}",
            ]
            asset_name = resolver.asset_name(
                asset_uid=task_delta.get("asset_uid"),
                fallback_name=None,
            )
            required_lines.append(f"- Asset: {_clip_text(asset_name, 48)}")
        else:
            required_lines = [
                "- Update: Mission content updated",
                "- Detail: Additional details unavailable on this link",
            ]

        return _ensure_within_budget(
            header=header,
            required_lines=required_lines,
            optional_lines=optional_lines,
            max_bytes=max_payload_bytes,
        )

    change_type = _status_label(mission_change.get("change_type"))
    return _ensure_within_budget(
        header=header,
        required_lines=[
            "- Update: Mission content updated",
            f"- Detail: Change type {change_type}",
        ],
        optional_lines=[],
        max_bytes=max_payload_bytes,
    )
