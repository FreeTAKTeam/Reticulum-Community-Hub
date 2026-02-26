"""Tests for generic mission-delta markdown rendering."""

from __future__ import annotations

from typing import Any

import pytest

from reticulum_telemetry_hub.reticulum_server.mission_delta_markdown import (
    MissionDeltaNameResolver,
    render_mission_delta_markdown,
)


class _FakeDomainService:
    """Test double for mission-domain lookups used by markdown rendering."""

    def __init__(self) -> None:
        self._missions: dict[str, dict[str, Any]] = {
            "mission-1": {"uid": "mission-1", "mission_name": "Mission Alpha"},
        }
        self._teams_by_mission: dict[str, list[dict[str, Any]]] = {
            "mission-1": [{"uid": "team-1", "team_name": "Ops"}],
        }
        self._members_by_team: dict[str, list[dict[str, Any]]] = {
            "team-1": [
                {
                    "uid": "member-1",
                    "rns_identity": "peer-a",
                    "display_name": "Alice",
                }
            ]
        }
        self._checklists: dict[str, dict[str, Any]] = {
            "checklist-1": {
                "uid": "checklist-1",
                "columns": [
                    {
                        "column_uid": "column-1",
                        "column_name": "Task",
                        "column_type": "SHORT_STRING",
                    }
                ],
                "tasks": [
                    {
                        "task_uid": "task-1",
                        "number": 1,
                        "legacy_value": "Inspect route",
                        "cells": [
                            {
                                "column_uid": "column-1",
                                "value": "Inspect route",
                            }
                        ],
                    }
                ],
            }
        }
        self._assets: dict[str, dict[str, Any]] = {
            "asset-1": {"asset_uid": "asset-1", "name": "Radio 1"}
        }

    def get_mission(self, mission_uid: str) -> dict[str, Any]:
        """Return mission payload by UID.

        Args:
            mission_uid: Mission UID.

        Returns:
            Mission payload.
        """

        return dict(self._missions.get(mission_uid, {}))

    def list_teams(self, mission_uid: str | None = None) -> list[dict[str, Any]]:
        """Return mission teams.

        Args:
            mission_uid: Mission UID.

        Returns:
            Team payloads.
        """

        if mission_uid is None:
            return []
        return list(self._teams_by_mission.get(mission_uid, []))

    def list_team_members(self, team_uid: str | None = None) -> list[dict[str, Any]]:
        """Return team-member payloads.

        Args:
            team_uid: Team UID.

        Returns:
            Team-member payloads.
        """

        if team_uid is None:
            return []
        return list(self._members_by_team.get(team_uid, []))

    def get_checklist(self, checklist_uid: str) -> dict[str, Any]:
        """Return checklist payload by UID.

        Args:
            checklist_uid: Checklist UID.

        Returns:
            Checklist payload.
        """

        return dict(self._checklists.get(checklist_uid, {}))

    def get_asset(self, asset_uid: str) -> dict[str, Any]:
        """Return asset payload by UID.

        Args:
            asset_uid: Asset UID.

        Returns:
            Asset payload.
        """

        return dict(self._assets.get(asset_uid, {}))


def test_render_log_delta_includes_client_time_and_content() -> None:
    """Render log updates with client-time context and content excerpt."""

    resolver = MissionDeltaNameResolver(_FakeDomainService())
    message = render_mission_delta_markdown(
        mission_uid="mission-1",
        mission_change={},
        delta={
            "logs": [
                {
                    "op": "upsert",
                    "client_time": "2026-02-26T10:00:00Z",
                    "content": "Patrol reached checkpoint 1",
                    "keywords": ["ops", "checkpoint"],
                }
            ]
        },
        resolver=resolver,
    )

    assert "### Mission Mission Alpha" in message
    assert '- Detail: "2026-02-26T10:00:00Z, Patrol reached checkpoint 1"' in message
    assert "- Tags: ops, checkpoint" in message


def test_render_completed_status_includes_task_status_and_completer_name() -> None:
    """Include task label, status transition, and completer name on completion."""

    resolver = MissionDeltaNameResolver(_FakeDomainService())
    message = render_mission_delta_markdown(
        mission_uid="mission-1",
        mission_change={},
        delta={
            "tasks": [
                {
                    "op": "status_set",
                    "checklist_uid": "checklist-1",
                    "task_uid": "task-1",
                    "previous_status": "PENDING",
                    "current_status": "COMPLETE",
                    "changed_by_team_member_rns_identity": "peer-a",
                }
            ]
        },
        resolver=resolver,
    )

    assert "### Mission Mission Alpha" in message
    assert "- Detail: Inspect route" in message
    assert "- Status: PENDING -> COMPLETE" in message
    assert "- Completed by: Alice" in message
    assert "task-1" not in message


def test_render_completed_status_uses_unknown_team_member_fallback() -> None:
    """Use the unknown-team-member fallback when completer cannot be resolved."""

    resolver = MissionDeltaNameResolver(_FakeDomainService())
    message = render_mission_delta_markdown(
        mission_uid="mission-1",
        mission_change={},
        delta={
            "tasks": [
                {
                    "op": "status_set",
                    "checklist_uid": "checklist-1",
                    "task_uid": "task-1",
                    "previous_status": "PENDING",
                    "current_status": "COMPLETE_LATE",
                    "changed_by_team_member_rns_identity": "missing-peer",
                }
            ]
        },
        resolver=resolver,
    )

    assert "- Completed by: Unknown team member" in message


def test_render_respects_max_byte_budget() -> None:
    """Enforce byte budget when rendering very long markdown content."""

    resolver = MissionDeltaNameResolver(_FakeDomainService())
    message = render_mission_delta_markdown(
        mission_uid="mission-1",
        mission_change={},
        delta={
            "logs": [
                {
                    "op": "upsert",
                    "client_time": "2026-02-26T10:00:00Z",
                    "content": "X" * 6000,
                    "keywords": ["a" * 400, "b" * 400, "c" * 400, "d" * 400],
                }
            ]
        },
        resolver=resolver,
        max_bytes=700,
    )

    assert len(message.encode("utf-8")) <= 700
    assert message.startswith("### Mission ")


@pytest.mark.parametrize(
    ("task_delta", "expected_line"),
    [
        (
            {
                "op": "row_added",
                "checklist_uid": "checklist-1",
                "task_uid": "task-1",
                "due_dtg": "2026-02-26T11:00:00Z",
            },
            "- Update: Checklist task added",
        ),
        (
            {
                "op": "row_deleted",
                "checklist_uid": "checklist-1",
                "task_uid": "task-1",
            },
            "- Update: Checklist task removed",
        ),
        (
            {
                "op": "row_style_set",
                "checklist_uid": "checklist-1",
                "task_uid": "task-1",
                "row_background_color": "#123456",
                "line_break_enabled": True,
            },
            "- Update: Checklist task formatting changed",
        ),
        (
            {
                "op": "cell_set",
                "checklist_uid": "checklist-1",
                "task_uid": "task-1",
                "column_uid": "column-1",
                "value": "Inspect route now",
            },
            "- Update: Checklist task updated",
        ),
        (
            {
                "op": "assignment_upsert",
                "checklist_uid": "checklist-1",
                "task_uid": "task-1",
                "team_member_rns_identity": "peer-a",
                "status": "PENDING",
                "assets": ["asset-1"],
            },
            "- Update: Assignment updated",
        ),
        (
            {
                "op": "assignment_assets_set",
                "checklist_uid": "checklist-1",
                "task_uid": "task-1",
                "assets": ["asset-1"],
            },
            "- Update: Assignment asset set replaced",
        ),
        (
            {
                "op": "assignment_asset_linked",
                "checklist_uid": "checklist-1",
                "task_uid": "task-1",
                "asset_uid": "asset-1",
            },
            "- Update: Assignment asset linked",
        ),
        (
            {
                "op": "assignment_asset_unlinked",
                "checklist_uid": "checklist-1",
                "task_uid": "task-1",
                "asset_uid": "asset-1",
            },
            "- Update: Assignment asset removed",
        ),
    ],
)
def test_render_supported_task_operations(task_delta: dict[str, Any], expected_line: str) -> None:
    """Render all supported task operations with stable operation wording."""

    resolver = MissionDeltaNameResolver(_FakeDomainService())
    message = render_mission_delta_markdown(
        mission_uid="mission-1",
        mission_change={},
        delta={"tasks": [task_delta]},
        resolver=resolver,
    )

    assert "### Mission Mission Alpha" in message
    assert expected_line in message
    assert "task-1" not in message


def test_render_supported_asset_operations() -> None:
    """Render both asset upsert and delete operation summaries."""

    resolver = MissionDeltaNameResolver(_FakeDomainService())
    upsert_message = render_mission_delta_markdown(
        mission_uid="mission-1",
        mission_change={},
        delta={
            "assets": [
                {
                    "op": "upsert",
                    "asset_uid": "asset-1",
                    "name": "Radio 1",
                    "asset_type": "COMM",
                    "status": "AVAILABLE",
                    "team_member_uid": "member-1",
                }
            ]
        },
        resolver=resolver,
    )
    delete_message = render_mission_delta_markdown(
        mission_uid="mission-1",
        mission_change={},
        delta={
            "assets": [
                {
                    "op": "delete",
                    "asset_uid": "asset-1",
                    "name": "Radio 1",
                    "asset_type": "COMM",
                }
            ]
        },
        resolver=resolver,
    )

    assert "- Update: Asset updated" in upsert_message
    assert "- Update: Asset removed" in delete_message


def test_render_unknown_operation_uses_generic_fallback() -> None:
    """Fallback to generic messaging for unknown operation tokens."""

    resolver = MissionDeltaNameResolver(_FakeDomainService())
    message = render_mission_delta_markdown(
        mission_uid="mission-1",
        mission_change={"change_type": "ADD_CONTENT"},
        delta={"tasks": [{"op": "unsupported_op"}]},
        resolver=resolver,
    )

    assert "- Update: Mission content updated" in message
    assert "- Detail: Additional details unavailable on this link" in message
