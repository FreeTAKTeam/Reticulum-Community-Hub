"""Render compact mission-delta markdown payloads for generic LXMF clients."""

from __future__ import annotations

from typing import Any

from reticulum_telemetry_hub.reticulum_server.mission_delta_resolver import (
    MissionDeltaNameResolver,
)
from reticulum_telemetry_hub.reticulum_server.mission_delta_text import (
    DEFAULT_MAX_MARKDOWN_BYTES,
)
from reticulum_telemetry_hub.reticulum_server.mission_delta_text import (
    bytes_len as _bytes_len,
)
from reticulum_telemetry_hub.reticulum_server.mission_delta_text import (
    clean_text as _clean_text,
)
from reticulum_telemetry_hub.reticulum_server.mission_delta_text import (
    clip_text as _clip_text,
)
from reticulum_telemetry_hub.reticulum_server.mission_delta_text import (
    status_label as _status_label,
)


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

    generic = _join_lines([header, "- Content: Mission content updated"])
    if _bytes_len(generic) <= target_bytes:
        return generic

    mission_name = _clip_text(header.replace("### Mission ", ""), max_chars=64)
    shortened_header = f"### Mission {mission_name}" if mission_name else "### Mission"
    shortened = _join_lines([shortened_header, "- Content: Mission content updated"])
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
    content = _clip_text(log_delta.get("content"), 180)
    fallback = _clip_text(log_delta.get("client_time"), 32) or "Mission log updated"
    required_lines = [f"- Log: {content or fallback}"]
    optional_lines: list[str] = []
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
        detail_suffix_parts = [
            item for item in (asset_type, status if op != "delete" else "") if item
        ]
        detail_suffix = (
            f" ({', '.join(detail_suffix_parts)})" if detail_suffix_parts else ""
        )
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
            update = (
                "Assignment asset linked"
                if op == "assignment_asset_linked"
                else "Assignment asset removed"
            )
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
    source_event_name = _clean_text(mission_change.get("name")).lower()
    notes = _clip_text(mission_change.get("notes"), 180)

    if source_event_name == "mission.log_entry.upserted":
        return _ensure_within_budget(
            header=header,
            required_lines=[f"- Log: {notes or 'Mission log updated'}"],
            optional_lines=[],
            max_bytes=max_payload_bytes,
        )

    if change_type == "ADD_CONTENT":
        return _ensure_within_budget(
            header=header,
            required_lines=[f"- Content: {notes or 'Mission content updated'}"],
            optional_lines=[],
            max_bytes=max_payload_bytes,
        )

    return _ensure_within_budget(
        header=header,
        required_lines=[f"- Change: {change_type}"],
        optional_lines=[],
        max_bytes=max_payload_bytes,
    )


__all__ = [
    "DEFAULT_MAX_MARKDOWN_BYTES",
    "MissionDeltaNameResolver",
    "render_mission_delta_markdown",
]
