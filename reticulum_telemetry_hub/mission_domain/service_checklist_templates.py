"""Checklist template methods."""
# ruff: noqa: F403,F405

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from reticulum_telemetry_hub.api.storage_models import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.enums import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.enums import normalize_enum_value
from reticulum_telemetry_hub.mission_domain.service_constants import *  # noqa: F403


class ChecklistTemplateMixin:
    """Checklist template methods."""

    def _default_columns(self) -> list[dict[str, Any]]:
        return [
            {
                "column_uid": uuid.uuid4().hex,
                "column_name": "Due",
                "display_order": 1,
                "column_type": "RELATIVE_TIME",
                "column_editable": False,
                "is_removable": False,
                "system_key": SYSTEM_COLUMN_KEY_DUE_RELATIVE_DTG,
                "background_color": None,
                "text_color": None,
            },
            {
                "column_uid": uuid.uuid4().hex,
                "column_name": "Task",
                "display_order": 2,
                "column_type": "SHORT_STRING",
                "column_editable": True,
                "is_removable": True,
                "system_key": None,
                "background_color": None,
                "text_color": None,
            },
        ]

    def _normalize_column(self, payload: dict[str, Any], *, order: int) -> dict[str, Any]:
        column_type = normalize_enum_value(
            payload.get("column_type"),
            field_name="column_type",
            allowed_values=enum_values(ChecklistColumnType),
            default=ChecklistColumnType.SHORT_STRING.value,
        )
        system_key = payload.get("system_key")
        if system_key is not None and str(system_key).strip():
            system_key = normalize_enum_value(
                system_key,
                field_name="system_key",
                allowed_values=enum_values(ChecklistSystemColumnKey),
                default=None,
            )
        else:
            system_key = None
        return {
            "column_uid": str(payload.get("column_uid") or payload.get("uid") or uuid.uuid4().hex),
            "column_name": str(payload.get("column_name") or payload.get("name") or "Column"),
            "display_order": int(payload.get("display_order") or order),
            "column_type": column_type,
            "column_editable": bool(payload.get("column_editable", True)),
            "is_removable": bool(payload.get("is_removable", True)),
            "system_key": system_key,
            "background_color": payload.get("background_color"),
            "text_color": payload.get("text_color"),
        }

    def _validate_columns(self, columns: list[dict[str, Any]]) -> None:
        if not columns:
            raise ValueError("columns are required")
        due = [c for c in columns if c.get("system_key") == SYSTEM_COLUMN_KEY_DUE_RELATIVE_DTG]
        if len(due) != 1:
            raise ValueError("Exactly one DUE_RELATIVE_DTG system column is required")
        due_col = due[0]
        if due_col.get("column_type") != "RELATIVE_TIME":
            raise ValueError("DUE_RELATIVE_DTG column must be RELATIVE_TIME")
        if bool(due_col.get("is_removable", True)):
            raise ValueError("DUE_RELATIVE_DTG column cannot be removable")

    @staticmethod
    def _serialize_column(row: R3aktChecklistColumnRecord) -> dict[str, Any]:
        return {
            "column_uid": row.column_uid,
            "column_name": row.column_name,
            "display_order": int(row.display_order or 0),
            "column_type": row.column_type,
            "column_editable": bool(row.column_editable),
            "background_color": row.background_color,
            "text_color": row.text_color,
            "is_removable": bool(row.is_removable),
            "system_key": row.system_key,
        }

    def _template_columns(self, session: Session, template_uid: str) -> list[R3aktChecklistColumnRecord]:
        return (
            session.query(R3aktChecklistColumnRecord)
            .filter(
                R3aktChecklistColumnRecord.template_uid == template_uid,
                R3aktChecklistColumnRecord.checklist_uid.is_(None),
            )
            .order_by(R3aktChecklistColumnRecord.display_order.asc())
            .all()
        )

    def _checklist_columns(self, session: Session, checklist_uid: str) -> list[R3aktChecklistColumnRecord]:
        return (
            session.query(R3aktChecklistColumnRecord)
            .filter(R3aktChecklistColumnRecord.checklist_uid == checklist_uid)
            .order_by(R3aktChecklistColumnRecord.display_order.asc())
            .all()
        )

    def _serialize_template(self, session: Session, row: R3aktChecklistTemplateRecord) -> dict[str, Any]:
        return {
            "uid": row.uid,
            "template_name": row.template_name,
            "description": row.description or "",
            "created_at": _dt(row.created_at),
            "created_by_team_member_rns_identity": row.created_by_team_member_rns_identity,
            "updated_at": _dt(row.updated_at),
            "source_template_uid": row.source_template_uid,
            "server_only": bool(row.server_only),
            "columns": [self._serialize_column(col) for col in self._template_columns(session, row.uid)],
        }

    def list_checklist_templates(self, *, search: str | None = None, sort_by: str | None = None) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(R3aktChecklistTemplateRecord)
            if search:
                query = query.filter(R3aktChecklistTemplateRecord.template_name.ilike(f"%{search}%"))
            if sort_by == "name_desc":
                query = query.order_by(R3aktChecklistTemplateRecord.template_name.desc())
            elif sort_by == "created_at_asc":
                query = query.order_by(R3aktChecklistTemplateRecord.created_at.asc())
            elif sort_by == "created_at_desc":
                query = query.order_by(R3aktChecklistTemplateRecord.created_at.desc())
            else:
                query = query.order_by(R3aktChecklistTemplateRecord.template_name.asc())
            return [self._serialize_template(session, row) for row in query.all()]

    def get_checklist_template(self, template_uid: str) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktChecklistTemplateRecord, template_uid)
            if row is None:
                raise KeyError(f"Checklist template '{template_uid}' not found")
            return self._serialize_template(session, row)

    def create_checklist_template(self, template: dict[str, Any]) -> dict[str, Any]:
        uid = str(template.get("uid") or uuid.uuid4().hex)
        now = _utcnow()
        cols = [self._normalize_column(item, order=index) for index, item in enumerate(template.get("columns") or self._default_columns(), start=1)]
        self._validate_columns(cols)
        with self._session() as session:
            row = R3aktChecklistTemplateRecord(
                uid=uid,
                template_name=str(template.get("template_name") or template.get("name") or "Template"),
                description=str(template.get("description") or ""),
                created_at=_as_datetime(template.get("created_at"), default=now) or now,
                created_by_team_member_rns_identity=str(template.get("created_by_team_member_rns_identity") or template.get("created_by") or "unknown"),
                updated_at=_as_datetime(template.get("updated_at"), default=now) or now,
                source_template_uid=template.get("source_template_uid"),
                server_only=bool(template.get("server_only", True)),
            )
            session.add(row)
            for col in cols:
                session.add(
                    R3aktChecklistColumnRecord(
                        column_uid=col["column_uid"],
                        checklist_uid=None,
                        template_uid=uid,
                        column_name=col["column_name"],
                        display_order=col["display_order"],
                        column_type=col["column_type"],
                        column_editable=col["column_editable"],
                        background_color=col["background_color"],
                        text_color=col["text_color"],
                        is_removable=col["is_removable"],
                        system_key=col["system_key"],
                        created_at=now,
                        updated_at=now,
                    )
                )
            session.flush()
            data = self._serialize_template(session, row)
            self._record_event(session, domain="checklist", aggregate_type="template", aggregate_uid=uid, event_type="checklist.template.created", payload=data)
            self._record_snapshot(session, domain="checklist", aggregate_type="template", aggregate_uid=uid, state=data)
            return data

    def update_checklist_template(self, template_uid: str, patch: dict[str, Any]) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktChecklistTemplateRecord, template_uid)
            if row is None:
                raise KeyError(f"Checklist template '{template_uid}' not found")
            if patch.get("template_name") is not None:
                row.template_name = str(patch.get("template_name"))
            if patch.get("description") is not None:
                row.description = str(patch.get("description"))
            if patch.get("source_template_uid") is not None:
                row.source_template_uid = patch.get("source_template_uid")
            if patch.get("columns") is not None:
                cols = [self._normalize_column(item, order=index) for index, item in enumerate(patch.get("columns") or [], start=1)]
                self._validate_columns(cols)
                session.query(R3aktChecklistColumnRecord).filter(
                    R3aktChecklistColumnRecord.template_uid == template_uid,
                    R3aktChecklistColumnRecord.checklist_uid.is_(None),
                ).delete(synchronize_session=False)
                now = _utcnow()
                for col in cols:
                    session.add(
                        R3aktChecklistColumnRecord(
                            column_uid=col["column_uid"], checklist_uid=None, template_uid=template_uid,
                            column_name=col["column_name"], display_order=col["display_order"], column_type=col["column_type"],
                            column_editable=col["column_editable"], background_color=col["background_color"], text_color=col["text_color"],
                            is_removable=col["is_removable"], system_key=col["system_key"], created_at=now, updated_at=now,
                        )
                    )
            row.updated_at = _utcnow()
            session.flush()
            data = self._serialize_template(session, row)
            self._record_event(session, domain="checklist", aggregate_type="template", aggregate_uid=template_uid, event_type="checklist.template.updated", payload=data)
            self._record_snapshot(session, domain="checklist", aggregate_type="template", aggregate_uid=template_uid, state=data)
            return data

    def clone_checklist_template(self, source_template_uid: str, *, template_name: str, description: str | None = None, created_by_team_member_rns_identity: str = "unknown") -> dict[str, Any]:
        with self._session() as session:
            source = session.get(R3aktChecklistTemplateRecord, source_template_uid)
            if source is None:
                raise KeyError(f"Checklist template '{source_template_uid}' not found")
            source_cols = []
            for col in self._template_columns(session, source_template_uid):
                serialized = self._serialize_column(col)
                # Template clones must allocate fresh column UIDs to satisfy
                # global primary-key uniqueness across templates/checklists.
                serialized["column_uid"] = uuid.uuid4().hex
                source_cols.append(serialized)
        return self.create_checklist_template(
            {
                "template_name": template_name,
                "description": description if description is not None else source.description,
                "source_template_uid": source_template_uid,
                "created_by_team_member_rns_identity": created_by_team_member_rns_identity,
                "columns": source_cols,
            }
        )

    def delete_checklist_template(self, template_uid: str) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktChecklistTemplateRecord, template_uid)
            if row is None:
                raise KeyError(f"Checklist template '{template_uid}' not found")
            data = self._serialize_template(session, row)
            session.query(R3aktChecklistColumnRecord).filter(
                R3aktChecklistColumnRecord.template_uid == template_uid,
                R3aktChecklistColumnRecord.checklist_uid.is_(None),
            ).delete(synchronize_session=False)
            session.delete(row)
            self._record_event(session, domain="checklist", aggregate_type="template", aggregate_uid=template_uid, event_type="checklist.template.deleted", payload=data)
            return data
    @staticmethod
    def _serialize_publication(row: R3aktChecklistFeedPublicationRecord) -> dict[str, Any]:
        return {
            "publication_uid": row.publication_uid,
            "checklist_uid": row.checklist_uid,
            "mission_feed_uid": row.mission_feed_uid,
            "published_at": _dt(row.published_at),
            "published_by_team_member_rns_identity": row.published_by_team_member_rns_identity,
        }

    def _serialize_checklist(self, session: Session, row: R3aktChecklistRecord) -> dict[str, Any]:
        columns = [self._serialize_column(col) for col in self._checklist_columns(session, row.uid)]
        tasks = (
            session.query(R3aktChecklistTaskRecord)
            .filter(R3aktChecklistTaskRecord.checklist_uid == row.uid)
            .order_by(R3aktChecklistTaskRecord.number.asc())
            .all()
        )
        task_ids = [task.task_uid for task in tasks]
        cells_by_task: dict[str, list[dict[str, Any]]] = {task_id: [] for task_id in task_ids}
        if task_ids:
            for cell in session.query(R3aktChecklistCellRecord).filter(R3aktChecklistCellRecord.task_uid.in_(task_ids)).all():
                cells_by_task.setdefault(cell.task_uid, []).append(
                    {
                        "cell_uid": cell.cell_uid,
                        "task_uid": cell.task_uid,
                        "column_uid": cell.column_uid,
                        "value": cell.value,
                        "updated_at": _dt(cell.updated_at),
                        "updated_by_team_member_rns_identity": cell.updated_by_team_member_rns_identity,
                    }
                )
        publications = (
            session.query(R3aktChecklistFeedPublicationRecord)
            .filter(R3aktChecklistFeedPublicationRecord.checklist_uid == row.uid)
            .order_by(R3aktChecklistFeedPublicationRecord.published_at.desc())
            .all()
        )
        return {
            "uid": row.uid,
            "mission_id": row.mission_uid,
            "template_uid": row.template_uid,
            "template_version": row.template_version,
            "template_name": row.template_name,
            "name": row.name,
            "description": row.description,
            "start_time": _dt(row.start_time),
            "mode": row.mode,
            "sync_state": row.sync_state,
            "origin_type": row.origin_type,
            "checklist_status": row.checklist_status,
            "created_at": _dt(row.created_at),
            "created_by_team_member_rns_identity": row.created_by_team_member_rns_identity,
            "updated_at": _dt(row.updated_at),
            "uploaded_at": _dt(row.uploaded_at),
            "progress_percent": float(row.progress_percent or 0.0),
            "counts": {
                "pending_count": int(row.pending_count or 0),
                "late_count": int(row.late_count or 0),
                "complete_count": int(row.complete_count or 0),
            },
            "columns": columns,
            "tasks": [
                {
                    "task_uid": task.task_uid,
                    "number": int(task.number or 0),
                    "user_status": task.user_status,
                    "task_status": task.task_status,
                    "is_late": bool(task.is_late),
                    "custom_status": task.custom_status,
                    "due_relative_minutes": task.due_relative_minutes,
                    "due_dtg": _dt(task.due_dtg),
                    "notes": task.notes,
                    "row_background_color": task.row_background_color,
                    "line_break_enabled": bool(task.line_break_enabled),
                    "completed_at": _dt(task.completed_at),
                    "completed_by_team_member_rns_identity": task.completed_by_team_member_rns_identity,
                    "legacy_value": task.legacy_value,
                    "cells": cells_by_task.get(task.task_uid, []),
                }
                for task in tasks
            ],
            "feed_publications": [self._serialize_publication(item) for item in publications],
        }

    def _derive_task_status(self, *, user_status: str, due_dtg: datetime | None, completed_at: datetime | None) -> tuple[str, bool]:
        due = _as_datetime(due_dtg)
        completed = _as_datetime(completed_at)
        if user_status == CHECKLIST_USER_COMPLETE:
            if due and completed and completed > due:
                return CHECKLIST_TASK_COMPLETE_LATE, True
            return CHECKLIST_TASK_COMPLETE, False
        if due and _utcnow() > due:
            return CHECKLIST_TASK_LATE, True
        return CHECKLIST_TASK_PENDING, False

    def _recompute_checklist_status(self, session: Session, checklist: R3aktChecklistRecord) -> None:
        tasks = (
            session.query(R3aktChecklistTaskRecord)
            .filter(R3aktChecklistTaskRecord.checklist_uid == checklist.uid)
            .order_by(R3aktChecklistTaskRecord.number.asc())
            .all()
        )
        pending = 0
        late = 0
        complete = 0
        has_complete_late = False
        for task in tasks:
            status, is_late = self._derive_task_status(user_status=str(task.user_status or CHECKLIST_USER_PENDING), due_dtg=task.due_dtg, completed_at=task.completed_at)
            task.task_status = status
            task.is_late = is_late
            if task.user_status == CHECKLIST_USER_COMPLETE:
                complete += 1
                if status == CHECKLIST_TASK_COMPLETE_LATE:
                    has_complete_late = True
            else:
                pending += 1
                if status == CHECKLIST_TASK_LATE:
                    late += 1
        total = len(tasks)
        checklist.pending_count = pending
        checklist.late_count = late
        checklist.complete_count = complete
        checklist.progress_percent = round((complete / total) * 100.0, 2) if total else 0.0
        if total == 0:
            checklist.checklist_status = CHECKLIST_TASK_PENDING
        elif pending == 0:
            checklist.checklist_status = CHECKLIST_TASK_COMPLETE_LATE if has_complete_late else CHECKLIST_TASK_COMPLETE
        elif late > 0:
            checklist.checklist_status = CHECKLIST_TASK_LATE
        else:
            checklist.checklist_status = CHECKLIST_TASK_PENDING
        checklist.updated_at = _utcnow()

