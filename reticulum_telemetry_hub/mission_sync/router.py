"""Mission-sync command routing and response building."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
import uuid
from typing import Any
from typing import Callable

from pydantic import ValidationError

from reticulum_telemetry_hub.api.marker_service import MarkerService
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.api.zone_service import ZoneService
from reticulum_telemetry_hub.mission_domain import EmergencyActionMessageService
from reticulum_telemetry_hub.mission_domain.service import MissionDomainService
from reticulum_telemetry_hub.mission_sync.capabilities import MISSION_COMMAND_CAPABILITIES
from reticulum_telemetry_hub.mission_sync.router_errors import MissionCommandError
from reticulum_telemetry_hub.mission_sync.router_execution import MissionCommandExecutionMixin
from reticulum_telemetry_hub.mission_sync.router_helpers import MissionRouterHelperMixin
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandAccepted
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandEnvelope
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandRejected
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandResult
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog


def _utcnow() -> datetime:
    """Return the current aware UTC timestamp."""

    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class MissionSyncResponse:
    """Normalized mission-sync response payload."""

    content: str
    fields: dict[int | str, object]


class MissionSyncRouter(MissionCommandExecutionMixin, MissionRouterHelperMixin):
    """Route mission-sync command envelopes to backend operations."""

    def __init__(
        self,
        *,
        api: ReticulumTelemetryHubAPI,
        send_message: Callable[[str, str | None, str | None], bool],
        marker_service: MarkerService | None,
        zone_service: ZoneService | None,
        domain_service: MissionDomainService | None,
        emergency_action_message_service: EmergencyActionMessageService | None,
        event_log: EventLog | None,
        hub_identity_resolver: Callable[[], str | None],
        field_results: int,
        field_event: int,
        field_group: int,
    ) -> None:
        self._api = api
        self._send_message = send_message
        self._marker_service = marker_service
        self._zone_service = zone_service
        self._domain = domain_service
        self._emergency_action_message_service = emergency_action_message_service
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
        """Handle mission-sync command payloads."""

        responses: list[MissionSyncResponse] = []
        for raw_command in commands:
            responses.extend(
                self._handle_single(
                    raw_command,
                    source_identity=source_identity,
                    group=group,
                )
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

        required_capability = MISSION_COMMAND_CAPABILITIES.get(envelope.command_type)
        if required_capability is None:
            rejected = MissionCommandRejected(
                command_id=envelope.command_id,
                reason_code="unknown_command",
                reason=f"Unsupported mission command '{envelope.command_type}'",
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

        mission_uids = self._candidate_mission_uids(
            envelope.command_type,
            dict(envelope.args or {}),
        )
        if not self._is_authorized_for_operation(
            source_identity,
            required_capability,
            mission_uids,
        ):
            rejected = MissionCommandRejected(
                command_id=envelope.command_id,
                reason_code="unauthorized",
                reason=f"Capability '{required_capability}' is required",
                correlation_id=envelope.correlation_id,
                required_capabilities=[required_capability],
            )
            self._record_event(
                "mission_command_rejected",
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
        except MissionCommandError as exc:
            rejected = MissionCommandRejected(
                command_id=envelope.command_id,
                reason_code=exc.reason_code,
                reason=exc.reason,
                correlation_id=envelope.correlation_id,
                required_capabilities=exc.required_capabilities,
            )
            responses.append(
                self._response_from_results(rejected.model_dump(mode="json"), group=group)
            )
            self._record_event(
                "mission_command_rejected",
                {
                    "command_id": envelope.command_id,
                    "command_type": envelope.command_type,
                    "reason_code": exc.reason_code,
                    "reason": exc.reason,
                    "identity": source_identity,
                },
            )
            return responses
        except Exception as exc:
            rejected = MissionCommandRejected(
                command_id=envelope.command_id,
                reason_code="internal_error",
                reason="Mission command failed unexpectedly",
                correlation_id=envelope.correlation_id,
            )
            responses.append(
                self._response_from_results(rejected.model_dump(mode="json"), group=group)
            )
            self._record_event(
                "mission_command_rejected",
                {
                    "command_id": envelope.command_id,
                    "command_type": envelope.command_type,
                    "reason_code": "internal_error",
                    "reason": "Mission command failed unexpectedly",
                    "identity": source_identity,
                    "exception_type": type(exc).__name__,
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
            "mission_command_processed",
            {
                "command_id": envelope.command_id,
                "command_type": envelope.command_type,
                "identity": source_identity,
                "event_type": event_type,
            },
        )
        return responses

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
        return MissionSyncResponse(content="mission-sync", fields=fields)

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

