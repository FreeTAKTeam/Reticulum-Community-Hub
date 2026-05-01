"""Checklist core lifecycle methods."""
# ruff: noqa: F403,F405

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any


from reticulum_telemetry_hub.api.storage_models import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.enums import *  # noqa: F403
from reticulum_telemetry_hub.mission_domain.enums import normalize_enum_value
from reticulum_telemetry_hub.mission_domain.service_constants import _as_datetime
from reticulum_telemetry_hub.mission_domain.service_constants import _utcnow
from reticulum_telemetry_hub.mission_domain.service_constants import *  # noqa: F403


class ChecklistCoreMixin:
    """Checklist core lifecycle methods."""

    def _create_checklist(
        self,
        *,
        mode: str,
        sync_state: str,
        origin_type: str,
        name: str,
        description: str,
        start_time: datetime,
        created_by: str,
        mission_uid: str | None = None,
        template_uid: str | None = None,
        columns: list[dict[str, Any]] | None = None,
        checklist_uid: str | None = None,
    ) -> dict[str, Any]:
        mode = normalize_enum_value(
            mode,
            field_name="mode",
            allowed_values=enum_values(ChecklistMode),
            default=CHECKLIST_MODE_ONLINE,
        )
        sync_state = normalize_enum_value(
            sync_state,
            field_name="sync_state",
            allowed_values=enum_values(ChecklistSyncState),
            default=CHECKLIST_SYNC_LOCAL_ONLY,
        )
        origin_type = normalize_enum_value(
            origin_type,
            field_name="origin_type",
            allowed_values=enum_values(ChecklistOriginType),
            default=ChecklistOriginType.BLANK_TEMPLATE.value,
        )
        with self._session() as session:
            requested_checklist_uid = str(checklist_uid or "").strip()
            if requested_checklist_uid:
                existing = session.get(R3aktChecklistRecord, requested_checklist_uid)
                if existing is not None:
                    return self._serialize_checklist(session, existing)
            if mission_uid:
                self._ensure_mission_exists(session, str(mission_uid))
            if template_uid:
                template = session.get(R3aktChecklistTemplateRecord, template_uid)
                if template is None and not columns:
                    raise KeyError(f"Checklist template '{template_uid}' not found")
                if template is None:
                    cols = [self._normalize_column(item, order=index) for index, item in enumerate(columns or [], start=1)]
                    template_name = None
                else:
                    cols = [self._serialize_column(col) for col in self._template_columns(session, template_uid)]
                    template_name = template.template_name
            elif columns:
                cols = [self._normalize_column(item, order=index) for index, item in enumerate(columns, start=1)]
                template_name = None
            else:
                cols = self._default_columns()
                template_name = None
            self._validate_columns(cols)
            now = _utcnow()
            checklist_uid = requested_checklist_uid or uuid.uuid4().hex
            row = R3aktChecklistRecord(
                uid=checklist_uid,
                mission_uid=mission_uid,
                template_uid=template_uid,
                template_version=1 if template_uid else None,
                template_name=template_name,
                name=name,
                description=description,
                start_time=start_time,
                mode=mode,
                sync_state=sync_state,
                origin_type=origin_type,
                checklist_status=CHECKLIST_TASK_PENDING,
                progress_percent=0.0,
                pending_count=0,
                late_count=0,
                complete_count=0,
                created_at=now,
                created_by_team_member_rns_identity=created_by,
                updated_at=now,
                uploaded_at=None,
            )
            session.add(row)
            for col in cols:
                session.add(
                    R3aktChecklistColumnRecord(
                        column_uid=uuid.uuid4().hex,
                        checklist_uid=checklist_uid,
                        template_uid=None,
                        column_name=col["column_name"],
                        display_order=int(col["display_order"]),
                        column_type=col["column_type"],
                        column_editable=bool(col["column_editable"]),
                        background_color=col.get("background_color"),
                        text_color=col.get("text_color"),
                        is_removable=bool(col["is_removable"]),
                        system_key=col.get("system_key"),
                        created_at=now,
                        updated_at=now,
                    )
                )
            session.flush()
            self._recompute_checklist_status(session, row)
            data = self._serialize_checklist(session, row)
            self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.created", payload=data)
            self._record_snapshot(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, state=data)
            if mode == CHECKLIST_MODE_ONLINE and mission_uid:
                self._emit_auto_mission_change(
                    session,
                    mission_uid=mission_uid,
                    source_event_type="mission.checklist.created",
                    change_type=MissionChangeType.ADD_CONTENT.value,
                    delta=self._build_delta_envelope(
                        source_event_type="mission.checklist.created",
                        checklists=[data],
                    ),
                    team_member_rns_identity=created_by,
                )
            return data

    def list_active_checklists(self, *, search: str | None = None, sort_by: str | None = None) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(R3aktChecklistRecord)
            if search:
                query = query.filter(R3aktChecklistRecord.name.ilike(f"%{search}%"))
            if sort_by == "name_desc":
                query = query.order_by(R3aktChecklistRecord.name.desc())
            elif sort_by == "created_at_asc":
                query = query.order_by(R3aktChecklistRecord.created_at.asc())
            elif sort_by == "created_at_desc":
                query = query.order_by(R3aktChecklistRecord.created_at.desc())
            else:
                query = query.order_by(R3aktChecklistRecord.name.asc())
            return [self._serialize_checklist(session, row) for row in query.all()]

    def create_checklist_online(self, args: dict[str, Any]) -> dict[str, Any]:
        template_uid = str(args.get("template_uid") or "").strip()
        name = str(args.get("name") or "").strip()
        if not name:
            raise ValueError("name is required")
        raw_columns = args.get("columns")
        columns = list(raw_columns) if isinstance(raw_columns, list) else None
        if not template_uid and not columns:
            raise ValueError("template_uid is required")
        origin_type = str(args.get("origin_type") or "").strip()
        if not origin_type:
            origin_type = (
                ChecklistOriginType.RCH_TEMPLATE.value
                if template_uid
                else ChecklistOriginType.BLANK_TEMPLATE.value
            )
        return self._create_checklist(
            mode=CHECKLIST_MODE_ONLINE,
            sync_state=CHECKLIST_SYNC_SYNCED,
            origin_type=origin_type,
            name=name,
            description=str(args.get("description") or ""),
            start_time=_as_datetime(args.get("start_time"), default=_utcnow()) or _utcnow(),
            created_by=str(args.get("source_identity") or args.get("created_by_team_member_rns_identity") or "unknown"),
            mission_uid=args.get("mission_uid"),
            template_uid=template_uid,
            columns=columns,
            checklist_uid=args.get("checklist_uid"),
        )

    def create_checklist_offline(self, args: dict[str, Any]) -> dict[str, Any]:
        name = str(args.get("name") or "").strip()
        if not name:
            raise ValueError("name is required")
        raw_columns = args.get("columns")
        columns = list(raw_columns) if isinstance(raw_columns, list) else None
        requested_sync_state = args.get("sync_state")
        return self._create_checklist(
            mode=CHECKLIST_MODE_OFFLINE,
            sync_state=str(requested_sync_state or CHECKLIST_SYNC_LOCAL_ONLY),
            origin_type=str(
                args.get("origin_type") or ChecklistOriginType.BLANK_TEMPLATE.value
            ),
            name=name,
            description=str(args.get("description") or ""),
            start_time=_as_datetime(args.get("start_time"), default=_utcnow()) or _utcnow(),
            created_by=str(args.get("source_identity") or args.get("created_by_team_member_rns_identity") or "unknown"),
            mission_uid=args.get("mission_uid"),
            template_uid=args.get("template_uid"),
            columns=columns,
            checklist_uid=args.get("checklist_uid"),
        )

    def get_checklist(self, checklist_uid: str) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktChecklistRecord, checklist_uid)
            if row is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            return self._serialize_checklist(session, row)

    def update_checklist(self, checklist_uid: str, patch: dict[str, Any]) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktChecklistRecord, checklist_uid)
            if row is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")

            if patch.get("name") is not None:
                row.name = str(patch.get("name"))

            if patch.get("description") is not None:
                row.description = str(patch.get("description"))

            if "mission_uid" in patch or "mission_id" in patch:
                raw_mission_uid = patch.get("mission_uid")
                if raw_mission_uid is None and "mission_uid" not in patch:
                    raw_mission_uid = patch.get("mission_id")
                mission_uid = str(raw_mission_uid or "").strip() or None
                if mission_uid:
                    self._ensure_mission_exists(session, mission_uid)
                row.mission_uid = mission_uid

            if patch.get("mode") is not None:
                row.mode = normalize_enum_value(
                    patch.get("mode"),
                    field_name="mode",
                    allowed_values=enum_values(ChecklistMode),
                    default=row.mode or CHECKLIST_MODE_ONLINE,
                )

            if patch.get("sync_state") is not None:
                row.sync_state = normalize_enum_value(
                    patch.get("sync_state"),
                    field_name="sync_state",
                    allowed_values=enum_values(ChecklistSyncState),
                    default=row.sync_state or CHECKLIST_SYNC_LOCAL_ONLY,
                )

            if patch.get("origin_type") is not None:
                row.origin_type = normalize_enum_value(
                    patch.get("origin_type"),
                    field_name="origin_type",
                    allowed_values=enum_values(ChecklistOriginType),
                    default=row.origin_type or ChecklistOriginType.BLANK_TEMPLATE.value,
                )

            if patch.get("checklist_status") is not None:
                row.checklist_status = normalize_enum_value(
                    patch.get("checklist_status"),
                    field_name="checklist_status",
                    allowed_values=enum_values(ChecklistStatus),
                    default=row.checklist_status or ChecklistStatus.PENDING.value,
                )

            row.updated_at = _utcnow()
            session.flush()
            data = self._serialize_checklist(session, row)
            self._record_event(
                session,
                domain="checklist",
                aggregate_type="checklist",
                aggregate_uid=checklist_uid,
                event_type="checklist.updated",
                payload=data,
            )
            self._record_snapshot(
                session,
                domain="checklist",
                aggregate_type="checklist",
                aggregate_uid=checklist_uid,
                state=data,
            )
            return data

    def delete_checklist(self, checklist_uid: str) -> dict[str, Any]:
        with self._session() as session:
            checklist = session.get(R3aktChecklistRecord, checklist_uid)
            if checklist is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            data = self._serialize_checklist(session, checklist)
            task_uids = [
                str(task.task_uid)
                for task in session.query(R3aktChecklistTaskRecord.task_uid)
                .filter(R3aktChecklistTaskRecord.checklist_uid == checklist_uid)
                .all()
            ]
            if task_uids:
                session.query(R3aktChecklistCellRecord).filter(
                    R3aktChecklistCellRecord.task_uid.in_(task_uids)
                ).delete(synchronize_session=False)
                session.query(R3aktTaskSkillRequirementRecord).filter(
                    R3aktTaskSkillRequirementRecord.task_uid.in_(task_uids)
                ).delete(synchronize_session=False)
                session.query(R3aktMissionTaskAssignmentRecord).filter(
                    R3aktMissionTaskAssignmentRecord.task_uid.in_(task_uids)
                ).delete(synchronize_session=False)
            session.query(R3aktChecklistTaskRecord).filter(
                R3aktChecklistTaskRecord.checklist_uid == checklist_uid
            ).delete(synchronize_session=False)
            session.query(R3aktChecklistColumnRecord).filter(
                R3aktChecklistColumnRecord.checklist_uid == checklist_uid
            ).delete(synchronize_session=False)
            session.query(R3aktChecklistFeedPublicationRecord).filter(
                R3aktChecklistFeedPublicationRecord.checklist_uid == checklist_uid
            ).delete(synchronize_session=False)
            session.delete(checklist)
            self._record_event(
                session,
                domain="checklist",
                aggregate_type="checklist",
                aggregate_uid=checklist_uid,
                event_type="checklist.deleted",
                payload=data,
            )
            return data

    def join_checklist(self, checklist_uid: str, *, source_identity: str | None = None) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktChecklistRecord, checklist_uid)
            if row is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            data = self._serialize_checklist(session, row)
            self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.joined", payload={"checklist": data, "joined_by_team_member_rns_identity": source_identity})
            return data

    def mark_checklist_upload_pending(
        self, checklist_uid: str, *, source_identity: str | None = None
    ) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktChecklistRecord, checklist_uid)
            if row is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            row.sync_state = CHECKLIST_SYNC_UPLOAD_PENDING
            row.updated_at = _utcnow()
            session.flush()
            data = self._serialize_checklist(session, row)
            self._record_event(
                session,
                domain="checklist",
                aggregate_type="checklist",
                aggregate_uid=checklist_uid,
                event_type="checklist.upload.pending",
                payload={
                    "checklist": data,
                    "marked_by_team_member_rns_identity": source_identity,
                },
            )
            self._record_snapshot(
                session,
                domain="checklist",
                aggregate_type="checklist",
                aggregate_uid=checklist_uid,
                state=data,
            )
            return data

    def upload_checklist(self, checklist_uid: str, *, source_identity: str | None = None) -> dict[str, Any]:
        with self._session() as session:
            row = session.get(R3aktChecklistRecord, checklist_uid)
            if row is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            row.sync_state = CHECKLIST_SYNC_SYNCED
            row.uploaded_at = _utcnow()
            row.updated_at = _utcnow()
            session.flush()
            data = self._serialize_checklist(session, row)
            self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.uploaded", payload={"checklist": data, "uploaded_by_team_member_rns_identity": source_identity})
            self._record_snapshot(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, state=data)
            mission_uid = str(row.mission_uid or "").strip() or None
            self._emit_auto_mission_change(
                session,
                mission_uid=mission_uid,
                source_event_type="mission.checklist.uploaded",
                change_type=MissionChangeType.ADD_CONTENT.value,
                delta=self._build_delta_envelope(
                    source_event_type="mission.checklist.uploaded",
                    checklists=[data],
                ),
                team_member_rns_identity=source_identity,
            )
            return data

    def publish_checklist_feed(self, checklist_uid: str, mission_feed_uid: str, *, source_identity: str | None = None) -> dict[str, Any]:
        mission_feed_uid = str(mission_feed_uid or "").strip()
        if not mission_feed_uid:
            raise ValueError("mission_feed_uid is required")
        with self._session() as session:
            checklist = session.get(R3aktChecklistRecord, checklist_uid)
            if checklist is None:
                raise KeyError(f"Checklist '{checklist_uid}' not found")
            if checklist.mode == CHECKLIST_MODE_OFFLINE and checklist.sync_state != CHECKLIST_SYNC_SYNCED:
                raise ValueError("Offline checklists must be SYNCED before publication")
            pub = R3aktChecklistFeedPublicationRecord(
                publication_uid=uuid.uuid4().hex,
                checklist_uid=checklist_uid,
                mission_feed_uid=mission_feed_uid,
                published_at=_utcnow(),
                published_by_team_member_rns_identity=str(source_identity or "unknown"),
            )
            session.add(pub)
            session.flush()
            data = self._serialize_publication(pub)
            self._record_event(session, domain="checklist", aggregate_type="checklist", aggregate_uid=checklist_uid, event_type="checklist.feed.published", payload=data)
            return data
