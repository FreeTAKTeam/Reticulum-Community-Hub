"""Checklist task row methods."""
# ruff: noqa: F403,F405

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any


from reticulum_telemetry_hub.api.storage_models import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.enums import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.service_constants import *  # noqa: F403


class ChecklistTaskMixin:
    """Checklist task row methods."""

    def add_checklist_task_row(self, checklist_uid: str, args: dict[str, Any]) -> dict[str, Any]:
        with self._session() as session:
            checklist = session.get(R3aktChecklistRecord, checklist_uid)
            if checklist is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            mission_uid = str(checklist.mission_uid or "").strip() or None
            task_number = int(args.get("number") or 1)
            due_dtg = _as_datetime(args.get("due_dtg"))
            due_relative_minutes: int | None
            raw_due_relative = args.get("due_relative_minutes")
            if raw_due_relative is None:
                due_relative_minutes = (
                    task_number * CHECKLIST_DEFAULT_DUE_STEP_MINUTES
                    if due_dtg is None
                    else None
                )
            else:
                due_relative_minutes = int(raw_due_relative)
            if due_dtg is None and due_relative_minutes is not None:
                due_dtg = checklist.start_time + timedelta(minutes=due_relative_minutes)
            legacy_value_raw = args.get("legacy_value")
            legacy_value = None
            if legacy_value_raw is not None:
                legacy_value_text = str(legacy_value_raw).strip()
                legacy_value = legacy_value_text or None
            notes_raw = args.get("notes")
            notes = None
            if notes_raw is not None:
                notes_text = str(notes_raw).strip()
                notes = notes_text or None
            status, is_late = self._derive_task_status(user_status=CHECKLIST_USER_PENDING, due_dtg=due_dtg, completed_at=None)
            requested_task_uid = str(args.get("task_uid") or "").strip()
            if requested_task_uid:
                existing_task = session.get(R3aktChecklistTaskRecord, requested_task_uid)
                if existing_task is not None:
                    if existing_task.checklist_uid != checklist_uid:
                        raise KeyError(f"Checklist task '{requested_task_uid}' not found")
                    existing_task.number = task_number
                    existing_task.due_relative_minutes = due_relative_minutes
                    existing_task.due_dtg = due_dtg
                    existing_task.legacy_value = legacy_value
                    existing_task.notes = notes
                    existing_task.updated_at = _utcnow()
                    session.flush()
                    self._recompute_checklist_status(session, checklist)
                    data = self._serialize_checklist(session, checklist)
                    self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.progress.changed", payload=data)
                    return data
            task_uid = requested_task_uid or uuid.uuid4().hex
            task = R3aktChecklistTaskRecord(
                task_uid=task_uid,
                checklist_uid=checklist_uid,
                number=task_number,
                user_status=CHECKLIST_USER_PENDING,
                task_status=status,
                is_late=is_late,
                custom_status=None,
                due_relative_minutes=due_relative_minutes,
                due_dtg=due_dtg,
                notes=notes,
                row_background_color=None,
                line_break_enabled=False,
                completed_at=None,
                completed_by_team_member_rns_identity=None,
                legacy_value=legacy_value,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            session.add(task)
            for col in self._checklist_columns(session, checklist_uid):
                session.add(
                    R3aktChecklistCellRecord(
                        cell_uid=uuid.uuid4().hex,
                        task_uid=task_uid,
                        column_uid=col.column_uid,
                        value=None,
                        updated_at=_utcnow(),
                        updated_by_team_member_rns_identity=None,
                    )
                )
            session.flush()
            self._recompute_checklist_status(session, checklist)
            data = self._serialize_checklist(session, checklist)
            self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.progress.changed", payload=data)
            task_delta = {
                "op": "row_added",
                "mission_uid": mission_uid,
                "checklist_uid": checklist_uid,
                "task_uid": task_uid,
                "number": int(task.number or 0),
                "status": task.task_status,
                "user_status": task.user_status,
                "due_dtg": _dt(task.due_dtg),
                "due_relative_minutes": task.due_relative_minutes,
                "notes": task.notes,
                "legacy_value": task.legacy_value,
            }
            self._emit_auto_mission_change(
                session,
                mission_uid=mission_uid,
                source_event_type="mission.checklist.task.row.added",
                change_type=MissionChangeType.ADD_CONTENT.value,
                delta=self._build_delta_envelope(
                    source_event_type="mission.checklist.task.row.added",
                    tasks=[task_delta],
                ),
            )
            return data

    def delete_checklist_task_row(self, checklist_uid: str, task_uid: str) -> dict[str, Any]:
        with self._session() as session:
            checklist = session.get(R3aktChecklistRecord, checklist_uid)
            if checklist is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            mission_uid = str(checklist.mission_uid or "").strip() or None
            task = session.get(R3aktChecklistTaskRecord, task_uid)
            if task is None or task.checklist_uid != checklist_uid:
                raise KeyError(f"Checklist task '{task_uid}' not found")
            deleted_task_payload = {
                "op": "row_deleted",
                "mission_uid": mission_uid,
                "checklist_uid": checklist_uid,
                "task_uid": task_uid,
                "number": int(task.number or 0),
                "status": task.task_status,
                "user_status": task.user_status,
            }
            session.query(R3aktChecklistCellRecord).filter(R3aktChecklistCellRecord.task_uid == task_uid).delete(synchronize_session=False)
            session.delete(task)
            session.flush()
            self._recompute_checklist_status(session, checklist)
            data = self._serialize_checklist(session, checklist)
            self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.progress.changed", payload=data)
            self._emit_auto_mission_change(
                session,
                mission_uid=mission_uid,
                source_event_type="mission.checklist.task.row.deleted",
                change_type=MissionChangeType.REMOVE_CONTENT.value,
                delta=self._build_delta_envelope(
                    source_event_type="mission.checklist.task.row.deleted",
                    tasks=[deleted_task_payload],
                ),
            )
            return data

    def set_checklist_task_row_style(self, checklist_uid: str, task_uid: str, args: dict[str, Any]) -> dict[str, Any]:
        with self._session() as session:
            checklist = session.get(R3aktChecklistRecord, checklist_uid)
            if checklist is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            mission_uid = str(checklist.mission_uid or "").strip() or None
            task = session.get(R3aktChecklistTaskRecord, task_uid)
            if task is None or task.checklist_uid != checklist_uid:
                raise KeyError(f"Checklist task '{task_uid}' not found")
            if args.get("row_background_color") is not None:
                task.row_background_color = str(args.get("row_background_color"))
            if args.get("line_break_enabled") is not None:
                task.line_break_enabled = bool(args.get("line_break_enabled"))
            task.updated_at = _utcnow()
            session.flush()
            data = self._serialize_checklist(session, checklist)
            self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.progress.changed", payload=data)
            task_delta = {
                "op": "row_style_set",
                "mission_uid": mission_uid,
                "checklist_uid": checklist_uid,
                "task_uid": task_uid,
                "row_background_color": task.row_background_color,
                "line_break_enabled": bool(task.line_break_enabled),
            }
            self._emit_auto_mission_change(
                session,
                mission_uid=mission_uid,
                source_event_type="mission.checklist.task.row.style_set",
                change_type=MissionChangeType.ADD_CONTENT.value,
                delta=self._build_delta_envelope(
                    source_event_type="mission.checklist.task.row.style_set",
                    tasks=[task_delta],
                ),
            )
            return data

    def set_checklist_task_cell(self, checklist_uid: str, task_uid: str, column_uid: str, args: dict[str, Any]) -> dict[str, Any]:
        with self._session() as session:
            checklist = session.get(R3aktChecklistRecord, checklist_uid)
            if checklist is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            mission_uid = str(checklist.mission_uid or "").strip() or None
            task = session.get(R3aktChecklistTaskRecord, task_uid)
            if task is None or task.checklist_uid != checklist_uid:
                raise KeyError(f"Checklist task '{task_uid}' not found")
            column = session.get(R3aktChecklistColumnRecord, column_uid)
            if column is None or column.checklist_uid != checklist_uid:
                raise KeyError(f"Checklist column '{column_uid}' not found")
            cell = (
                session.query(R3aktChecklistCellRecord)
                .filter(R3aktChecklistCellRecord.task_uid == task_uid, R3aktChecklistCellRecord.column_uid == column_uid)
                .first()
            )
            if cell is None:
                cell = R3aktChecklistCellRecord(cell_uid=uuid.uuid4().hex, task_uid=task_uid, column_uid=column_uid, value=None, updated_at=_utcnow(), updated_by_team_member_rns_identity=None)
                session.add(cell)
            cell.value = None if args.get("value") is None else str(args.get("value"))
            cell.updated_at = _utcnow()
            if args.get("updated_by_team_member_rns_identity") is not None:
                cell.updated_by_team_member_rns_identity = str(args.get("updated_by_team_member_rns_identity"))
            session.flush()
            data = self._serialize_checklist(session, checklist)
            self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.progress.changed", payload=data)
            task_delta = {
                "op": "cell_set",
                "mission_uid": mission_uid,
                "checklist_uid": checklist_uid,
                "task_uid": task_uid,
                "column_uid": column_uid,
                "value": cell.value,
                "updated_by_team_member_rns_identity": cell.updated_by_team_member_rns_identity,
                "updated_at": _dt(cell.updated_at),
            }
            self._emit_auto_mission_change(
                session,
                mission_uid=mission_uid,
                source_event_type="mission.checklist.task.cell_set",
                change_type=MissionChangeType.ADD_CONTENT.value,
                delta=self._build_delta_envelope(
                    source_event_type="mission.checklist.task.cell_set",
                    tasks=[task_delta],
                ),
                team_member_rns_identity=cell.updated_by_team_member_rns_identity,
            )
            return data

    def set_checklist_task_status(self, checklist_uid: str, task_uid: str, args: dict[str, Any]) -> dict[str, Any]:
        user_status = str(args.get("user_status") or "").strip().upper()
        if user_status not in {CHECKLIST_USER_PENDING, CHECKLIST_USER_COMPLETE}:
            raise ValueError("user_status must be PENDING or COMPLETE")
        changed_by = args.get("changed_by_team_member_rns_identity")
        with self._session() as session:
            checklist = session.get(R3aktChecklistRecord, checklist_uid)
            if checklist is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            mission_uid = str(checklist.mission_uid or "").strip() or None
            task = session.get(R3aktChecklistTaskRecord, task_uid)
            if task is None or task.checklist_uid != checklist_uid:
                raise KeyError(f"Checklist task '{task_uid}' not found")
            prev = task.task_status
            task.user_status = user_status
            now = _utcnow()
            if user_status == CHECKLIST_USER_COMPLETE:
                task.completed_at = task.completed_at or now
                if changed_by:
                    task.completed_by_team_member_rns_identity = str(changed_by)
            else:
                task.completed_at = None
                task.completed_by_team_member_rns_identity = None
            task.task_status, task.is_late = self._derive_task_status(user_status=task.user_status, due_dtg=task.due_dtg, completed_at=task.completed_at)
            task.updated_at = now
            session.flush()
            self._recompute_checklist_status(session, checklist)
            data = self._serialize_checklist(session, checklist)
            delta = {
                "checklist_uid": checklist_uid,
                "task_uid": task_uid,
                "previous_status": prev,
                "current_status": task.task_status,
                "changed_by_team_member_rns_identity": changed_by,
                "changed_at": now.isoformat(),
            }
            self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.task.status.changed", payload=delta)
            if task.task_status in {CHECKLIST_TASK_LATE, CHECKLIST_TASK_COMPLETE_LATE}:
                self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.task.marked.late", payload=delta)
            self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.progress.changed", payload=data)
            self._record_snapshot(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, state=data)
            task_delta = {
                "op": "status_set",
                "mission_uid": mission_uid,
                "checklist_uid": checklist_uid,
                "task_uid": task_uid,
                "previous_status": prev,
                "current_status": task.task_status,
                "user_status": task.user_status,
                "changed_by_team_member_rns_identity": changed_by,
                "changed_at": _dt(now),
                "completed_at": _dt(task.completed_at),
                "due_dtg": _dt(task.due_dtg),
            }
            self._emit_auto_mission_change(
                session,
                mission_uid=mission_uid,
                source_event_type="mission.checklist.task.status_set",
                change_type=MissionChangeType.ADD_CONTENT.value,
                delta=self._build_delta_envelope(
                    source_event_type="mission.checklist.task.status_set",
                    tasks=[task_delta],
                ),
                team_member_rns_identity=(
                    str(changed_by).strip() if changed_by is not None else None
                ),
            )
            return data
