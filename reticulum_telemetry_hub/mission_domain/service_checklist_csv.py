"""Checklist CSV import methods."""
# ruff: noqa: F403,F405

from __future__ import annotations

import base64
import csv
from io import StringIO
from pathlib import Path
from typing import Any


from reticulum_telemetry_hub.api.storage_models import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.enums import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.service_constants import *  # noqa: F403


class ChecklistCsvMixin:
    """Checklist CSV import methods."""

    def import_checklist_csv(self, args: dict[str, Any]) -> dict[str, Any]:
        filename = str(args.get("csv_filename") or "checklist.csv")
        encoded = str(args.get("csv_base64") or "")
        if not encoded:
            raise ValueError("csv_base64 is required")
        try:
            decoded = base64.b64decode(encoded)
        except Exception as exc:
            raise ValueError("csv_base64 is invalid") from exc
        rows = [
            [str(cell).replace("\ufeff", "").strip() for cell in row]
            for row in csv.reader(StringIO(decoded.decode("utf-8", errors="ignore")))
        ]
        rows = [row for row in rows if any(cell for cell in row)]
        if len(rows) < 2:
            raise ValueError("CSV must include a header row and at least one task row")

        header_row = rows[0]
        task_rows = rows[1:]
        max_columns = max(len(header_row), *(len(row) for row in task_rows))
        if max_columns <= 0:
            raise ValueError("CSV header row is empty")

        headers = [
            (header_row[index] if index < len(header_row) else "").strip() or f"Column {index + 1}"
            for index in range(max_columns)
        ]

        def _normalize_header(value: str) -> str:
            return " ".join(value.lower().replace("_", " ").replace("-", " ").split())

        due_aliases = {"due", "due relative minutes", "due minutes"}
        due_header_index = next(
            (index for index, value in enumerate(headers) if _normalize_header(value) in due_aliases),
            None,
        )

        columns: list[dict[str, Any]] = []
        if due_header_index is None:
            columns.append(
                {
                    "column_name": "Due",
                    "column_type": "RELATIVE_TIME",
                    "column_editable": False,
                    "is_removable": False,
                    "system_key": SYSTEM_COLUMN_KEY_DUE_RELATIVE_DTG,
                }
            )
            for header in headers:
                columns.append(
                    {
                        "column_name": header,
                        "column_type": "SHORT_STRING",
                        "column_editable": True,
                        "is_removable": True,
                    }
                )
            header_display_orders: dict[int, int] = {index: index + 2 for index in range(len(headers))}
        else:
            for index, header in enumerate(headers):
                if index == due_header_index:
                    columns.append(
                        {
                            "column_name": header or "Due",
                            "column_type": "RELATIVE_TIME",
                            "column_editable": False,
                            "is_removable": False,
                            "system_key": SYSTEM_COLUMN_KEY_DUE_RELATIVE_DTG,
                        }
                    )
                else:
                    columns.append(
                        {
                            "column_name": header,
                            "column_type": "SHORT_STRING",
                            "column_editable": True,
                            "is_removable": True,
                        }
                    )
            header_display_orders = {index: index + 1 for index in range(len(headers))}

        checklist = self._create_checklist(
            mode=CHECKLIST_MODE_ONLINE,
            sync_state=CHECKLIST_SYNC_SYNCED,
            origin_type=ChecklistOriginType.CSV_IMPORT.value,
            name=Path(filename).stem or "Checklist CSV",
            description=f"Imported from {filename}",
            start_time=_utcnow(),
            created_by=str(
                args.get("source_identity")
                or args.get("created_by_team_member_rns_identity")
                or "unknown"
            ),
            mission_uid=args.get("mission_uid"),
            columns=columns,
        )
        checklist_uid = str(checklist["uid"])
        created_columns = {int(col.get("display_order") or 0): str(col.get("column_uid") or "") for col in checklist.get("columns") or []}
        header_column_uids: dict[int, str] = {}
        for header_index, order in header_display_orders.items():
            if due_header_index is not None and header_index == due_header_index:
                continue
            column_uid = created_columns.get(order, "")
            if column_uid:
                header_column_uids[header_index] = column_uid

        source_identity = str(args.get("source_identity") or "unknown")

        def _parse_due_minutes(value: str) -> int | None:
            text = str(value or "").strip()
            if not text:
                return None
            if text.startswith("+"):
                text = text[1:]
            negative = text.startswith("-")
            digits = text[1:] if negative else text
            if not digits.isdigit():
                return None
            return -int(digits) if negative else int(digits)

        for index, row in enumerate(task_rows, start=1):
            normalized_row = [(row[col_index] if col_index < len(row) else "").strip() for col_index in range(len(headers))]
            due_minutes = None
            if due_header_index is not None:
                due_value = normalized_row[due_header_index] if due_header_index < len(normalized_row) else ""
                due_minutes = _parse_due_minutes(due_value)

            row_value = next(
                (
                    value
                    for cell_index, value in enumerate(normalized_row)
                    if value and (due_header_index is None or cell_index != due_header_index)
                ),
                None,
            )

            updated = self.add_checklist_task_row(
                checklist_uid,
                {
                    "number": index,
                    "due_relative_minutes": due_minutes,
                    "legacy_value": row_value,
                },
            )
            task_uid = str(
                next(
                    (
                        task.get("task_uid")
                        for task in updated.get("tasks") or []
                        if int(task.get("number") or 0) == index
                    ),
                    "",
                )
            )
            if not task_uid:
                raise RuntimeError("Checklist import failed to create task row")

            for column_index, column_uid in header_column_uids.items():
                value = normalized_row[column_index] if column_index < len(normalized_row) else ""
                if not value:
                    continue
                self.set_checklist_task_cell(
                    checklist_uid,
                    task_uid,
                    column_uid,
                    {
                        "value": value,
                        "updated_by_team_member_rns_identity": source_identity,
                    },
                )

        with self._session() as session:
            entity = session.get(R3aktChecklistRecord, checklist_uid)
            if entity is None:
                raise RuntimeError("Checklist import failed")
            data = self._serialize_checklist(session, entity)
            self._record_event(
                session,
                domain="checklist",
                aggregate_type="checklist",
                aggregate_uid=entity.uid,
                event_type="checklist.imported.csv",
                payload=data,
            )
            self._record_snapshot(
                session,
                domain="checklist",
                aggregate_type="checklist",
                aggregate_uid=entity.uid,
                state=data,
            )
            return data

