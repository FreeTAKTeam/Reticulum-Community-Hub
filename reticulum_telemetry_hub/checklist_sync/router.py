"""Checklist-sync command routing and response building."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
import uuid
from typing import Any
from typing import Callable

from pydantic import ValidationError

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.checklist_sync.capabilities import CHECKLIST_COMMAND_CAPABILITIES
from reticulum_telemetry_hub.mission_domain.service import MissionDomainService
from reticulum_telemetry_hub.mission_sync.router import MissionSyncResponse
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandAccepted
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandEnvelope
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandRejected
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandResult
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChecklistCommandError(Exception):
    """Error raised for checklist command execution failures."""

    def __init__(self, reason_code: str, reason: str) -> None:
        super().__init__(reason)
        self.reason_code = reason_code
        self.reason = reason


class ChecklistSyncRouter:
    """Route checklist-sync envelopes to domain operations."""

    def __init__(
        self,
        *,
        api: ReticulumTelemetryHubAPI,
        domain_service: MissionDomainService,
        event_log: EventLog | None,
        hub_identity_resolver: Callable[[], str | None],
        field_results: int,
        field_event: int,
        field_group: int,
    ) -> None:
        self._api = api
        self._domain = domain_service
        self._event_log = event_log
        self._hub_identity_resolver = hub_identity_resolver
        self._field_results = field_results
        self._field_event = field_event
        self._field_group = field_group

    def handle_commands(
        self,
        commands: list[dict[str, Any]],
        *,
        source_identity: str | None,
        group: object | None = None,
    ) -> list[MissionSyncResponse]:
        responses: list[MissionSyncResponse] = []
        for raw_command in commands:
            responses.extend(
                self._handle_single(raw_command, source_identity=source_identity, group=group)
            )
        return responses

    def _handle_single(
        self,
        raw_command: dict[str, Any],
        *,
        source_identity: str | None,
        group: object | None,
    ) -> list[MissionSyncResponse]:
        command_id = self._extract_command_id(raw_command)
        correlation_id = self._extract_correlation_id(raw_command)
        try:
            envelope = MissionCommandEnvelope.model_validate(raw_command)
        except ValidationError as exc:
            rejected = MissionCommandRejected(
                command_id=command_id,
                reason_code="invalid_payload",
                reason=str(exc),
                correlation_id=correlation_id,
            )
            return [self._response_from_results(rejected.model_dump(mode="json"), group=group)]

        envelope_source = str(envelope.source.rns_identity or "").strip().lower()
        if source_identity and envelope_source and envelope_source != source_identity.lower():
            rejected = MissionCommandRejected(
                command_id=envelope.command_id,
                reason_code="unauthorized",
                reason="Envelope source identity does not match transport sender",
                correlation_id=envelope.correlation_id,
            )
            return [self._response_from_results(rejected.model_dump(mode="json"), group=group)]

        required_capability = CHECKLIST_COMMAND_CAPABILITIES.get(envelope.command_type)
        if required_capability is None:
            rejected = MissionCommandRejected(
                command_id=envelope.command_id,
                reason_code="unknown_command",
                reason=f"Unsupported checklist command '{envelope.command_type}'",
                correlation_id=envelope.correlation_id,
            )
            return [self._response_from_results(rejected.model_dump(mode="json"), group=group)]

        if not source_identity:
            rejected = MissionCommandRejected(
                command_id=envelope.command_id,
                reason_code="unauthorized",
                reason="Source identity is required",
                correlation_id=envelope.correlation_id,
                required_capabilities=[required_capability],
            )
            return [self._response_from_results(rejected.model_dump(mode="json"), group=group)]

        capabilities = set(self._api.list_identity_capabilities(source_identity))
        if required_capability not in capabilities:
            rejected = MissionCommandRejected(
                command_id=envelope.command_id,
                reason_code="unauthorized",
                reason=f"Capability '{required_capability}' is required",
                correlation_id=envelope.correlation_id,
                required_capabilities=[required_capability],
            )
            self._record_event(
                "checklist_command_rejected",
                {
                    "command_id": envelope.command_id,
                    "command_type": envelope.command_type,
                    "reason_code": "unauthorized",
                    "identity": source_identity,
                },
            )
            return [self._response_from_results(rejected.model_dump(mode="json"), group=group)]

        accepted = MissionCommandAccepted(
            command_id=envelope.command_id,
            accepted_at=_utcnow(),
            correlation_id=envelope.correlation_id,
            by_identity=self._hub_identity_resolver(),
        )
        responses: list[MissionSyncResponse] = [
            self._response_from_results(accepted.model_dump(mode="json"), group=group)
        ]

        try:
            result_payload, event_type, event_payload = self._execute_command(
                envelope, source_identity=source_identity
            )
        except ChecklistCommandError as exc:
            rejected = MissionCommandRejected(
                command_id=envelope.command_id,
                reason_code=exc.reason_code,
                reason=exc.reason,
                correlation_id=envelope.correlation_id,
                required_capabilities=[required_capability],
            )
            responses.append(
                self._response_from_results(rejected.model_dump(mode="json"), group=group)
            )
            self._record_event(
                "checklist_command_rejected",
                {
                    "command_id": envelope.command_id,
                    "command_type": envelope.command_type,
                    "reason_code": exc.reason_code,
                    "reason": exc.reason,
                    "identity": source_identity,
                },
            )
            return responses

        result = MissionCommandResult(
            command_id=envelope.command_id,
            correlation_id=envelope.correlation_id,
            result=result_payload,
        )
        responses.append(
            self._response_from_results(
                result.model_dump(mode="json"),
                group=group,
                event=self._build_event_envelope(
                    event_type=event_type,
                    payload=event_payload,
                    source_identity=source_identity,
                    topics=envelope.topics,
                ),
            )
        )
        self._record_event(
            "checklist_command_processed",
            {
                "command_id": envelope.command_id,
                "command_type": envelope.command_type,
                "identity": source_identity,
                "event_type": event_type,
            },
        )
        return responses

    def _execute_command(
        self, envelope: MissionCommandEnvelope, *, source_identity: str
    ) -> tuple[dict[str, Any], str, dict[str, Any]]:
        args = dict(envelope.args or {})
        ctype = envelope.command_type
        try:
            if ctype == "checklist.template.list":
                payload = {
                    "templates": self._domain.list_checklist_templates(
                        search=args.get("search"), sort_by=args.get("sort_by")
                    )
                }
                return payload, "checklist.template.updated", payload
            if ctype == "checklist.template.create":
                template = args.get("template")
                if not isinstance(template, dict):
                    raise ChecklistCommandError("invalid_payload", "template is required")
                payload = self._domain.create_checklist_template(template)
                return payload, "checklist.template.created", payload
            if ctype == "checklist.template.update":
                template_uid = str(args.get("template_uid") or "").strip()
                patch = args.get("patch")
                if not template_uid or not isinstance(patch, dict):
                    raise ChecklistCommandError("invalid_payload", "template_uid and patch are required")
                payload = self._domain.update_checklist_template(template_uid, patch)
                return payload, "checklist.template.updated", payload
            if ctype == "checklist.template.clone":
                source_uid = str(args.get("source_template_uid") or "").strip()
                name = str(args.get("template_name") or "").strip()
                if not source_uid or not name:
                    raise ChecklistCommandError("invalid_payload", "source_template_uid and template_name are required")
                payload = self._domain.clone_checklist_template(
                    source_uid,
                    template_name=name,
                    description=args.get("description"),
                    created_by_team_member_rns_identity=source_identity,
                )
                return payload, "checklist.template.created", payload
            if ctype == "checklist.template.delete":
                template_uid = str(args.get("template_uid") or "").strip()
                if not template_uid:
                    raise ChecklistCommandError("invalid_payload", "template_uid is required")
                payload = self._domain.delete_checklist_template(template_uid)
                return payload, "checklist.template.deleted", payload
            if ctype == "checklist.list.active":
                payload = {
                    "checklists": self._domain.list_active_checklists(
                        search=args.get("search"), sort_by=args.get("sort_by")
                    )
                }
                return payload, "checklist.progress.changed", payload
            if ctype == "checklist.create.online":
                payload = self._domain.create_checklist_online(
                    {
                        **args,
                        "source_identity": source_identity,
                    }
                )
                return payload, "checklist.created", payload
            if ctype == "checklist.create.offline":
                payload = self._domain.create_checklist_offline(
                    {
                        **args,
                        "source_identity": source_identity,
                    }
                )
                return payload, "checklist.created", payload
            if ctype == "checklist.import.csv":
                payload = self._domain.import_checklist_csv(
                    {
                        **args,
                        "source_identity": source_identity,
                    }
                )
                return payload, "checklist.imported.csv", payload
            if ctype == "checklist.join":
                checklist_uid = str(args.get("checklist_uid") or "").strip()
                if not checklist_uid:
                    raise ChecklistCommandError("invalid_payload", "checklist_uid is required")
                payload = self._domain.join_checklist(checklist_uid, source_identity=source_identity)
                return payload, "checklist.joined", payload
            if ctype == "checklist.get":
                checklist_uid = str(args.get("checklist_uid") or "").strip()
                if not checklist_uid:
                    raise ChecklistCommandError("invalid_payload", "checklist_uid is required")
                payload = self._domain.get_checklist(checklist_uid)
                return payload, "checklist.progress.changed", payload
            if ctype == "checklist.upload":
                checklist_uid = str(args.get("checklist_uid") or "").strip()
                if not checklist_uid:
                    raise ChecklistCommandError("invalid_payload", "checklist_uid is required")
                payload = self._domain.upload_checklist(checklist_uid, source_identity=source_identity)
                return payload, "checklist.uploaded", payload
            if ctype == "checklist.feed.publish":
                checklist_uid = str(args.get("checklist_uid") or "").strip()
                mission_feed_uid = str(args.get("mission_feed_uid") or "").strip()
                if not checklist_uid or not mission_feed_uid:
                    raise ChecklistCommandError("invalid_payload", "checklist_uid and mission_feed_uid are required")
                payload = self._domain.publish_checklist_feed(
                    checklist_uid,
                    mission_feed_uid,
                    source_identity=source_identity,
                )
                return payload, "checklist.feed.published", payload
            if ctype == "checklist.task.status.set":
                checklist_uid = str(args.get("checklist_uid") or "").strip()
                task_uid = str(args.get("task_uid") or "").strip()
                if not checklist_uid or not task_uid:
                    raise ChecklistCommandError("invalid_payload", "checklist_uid and task_uid are required")
                payload = self._domain.set_checklist_task_status(checklist_uid, task_uid, args)
                return payload, "checklist.task.status.changed", payload
            if ctype == "checklist.task.row.add":
                checklist_uid = str(args.get("checklist_uid") or "").strip()
                if not checklist_uid:
                    raise ChecklistCommandError("invalid_payload", "checklist_uid is required")
                payload = self._domain.add_checklist_task_row(checklist_uid, args)
                return payload, "checklist.progress.changed", payload
            if ctype == "checklist.task.row.delete":
                checklist_uid = str(args.get("checklist_uid") or "").strip()
                task_uid = str(args.get("task_uid") or "").strip()
                if not checklist_uid or not task_uid:
                    raise ChecklistCommandError("invalid_payload", "checklist_uid and task_uid are required")
                payload = self._domain.delete_checklist_task_row(checklist_uid, task_uid)
                return payload, "checklist.progress.changed", payload
            if ctype == "checklist.task.row.style.set":
                checklist_uid = str(args.get("checklist_uid") or "").strip()
                task_uid = str(args.get("task_uid") or "").strip()
                if not checklist_uid or not task_uid:
                    raise ChecklistCommandError("invalid_payload", "checklist_uid and task_uid are required")
                payload = self._domain.set_checklist_task_row_style(checklist_uid, task_uid, args)
                return payload, "checklist.progress.changed", payload
            if ctype == "checklist.task.cell.set":
                checklist_uid = str(args.get("checklist_uid") or "").strip()
                task_uid = str(args.get("task_uid") or "").strip()
                column_uid = str(args.get("column_uid") or "").strip()
                if not checklist_uid or not task_uid or not column_uid:
                    raise ChecklistCommandError("invalid_payload", "checklist_uid, task_uid and column_uid are required")
                payload = self._domain.set_checklist_task_cell(checklist_uid, task_uid, column_uid, args)
                return payload, "checklist.progress.changed", payload
        except KeyError as exc:
            raise ChecklistCommandError("invalid_payload", str(exc)) from exc
        except ValueError as exc:
            raise ChecklistCommandError("invalid_payload", str(exc)) from exc

        raise ChecklistCommandError(
            "unknown_command",
            f"Unsupported checklist command '{ctype}'",
        )

    def _response_from_results(
        self,
        results_payload: dict[str, Any],
        *,
        group: object | None,
        event: dict[str, Any] | None = None,
    ) -> MissionSyncResponse:
        fields: dict[int | str, object] = {self._field_results: results_payload}
        if group is not None:
            fields[self._field_group] = group
        if event is not None:
            fields[self._field_event] = event
        return MissionSyncResponse(content="checklist-sync", fields=fields)

    def _build_event_envelope(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
        source_identity: str,
        topics: list[str] | None,
    ) -> dict[str, Any]:
        return {
            "event_id": uuid.uuid4().hex,
            "source": {"rns_identity": source_identity},
            "timestamp": _utcnow().isoformat(),
            "event_type": event_type,
            "topics": list(topics or []),
            "payload": payload,
        }

    @staticmethod
    def _extract_command_id(raw_command: dict[str, Any]) -> str:
        command_id = raw_command.get("command_id")
        if isinstance(command_id, str) and command_id.strip():
            return command_id
        return uuid.uuid4().hex

    @staticmethod
    def _extract_correlation_id(raw_command: dict[str, Any]) -> str | None:
        value = raw_command.get("correlation_id")
        if isinstance(value, str) and value.strip():
            return value
        return None

    def _record_event(self, event_type: str, metadata: dict[str, Any]) -> None:
        if self._event_log is None:
            return
        self._event_log.add_event(event_type, event_type.replace("_", " "), metadata=metadata)
