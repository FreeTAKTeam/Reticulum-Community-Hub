"""Southbound REM mode and peer registry command routing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from typing import Any
from typing import Callable

from pydantic import ValidationError

from reticulum_telemetry_hub.api.rem_registry_service import REM_REQUIRED_CAPABILITIES
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandAccepted
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandEnvelope
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandRejected
from reticulum_telemetry_hub.mission_sync.schemas import MissionCommandResult
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog


def _utcnow() -> datetime:
    """Return the current aware UTC timestamp."""

    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class RemCommandResponse:
    """Normalized REM command reply payload."""

    content: str
    fields: dict[int | str, object]


class RemCommandRouter:
    """Route REM registry commands carried in ``FIELD_COMMANDS``."""

    def __init__(
        self,
        *,
        api: ReticulumTelemetryHubAPI,
        event_log: EventLog | None,
        hub_identity_resolver: Callable[[], str | None],
        field_results: int,
        field_event: int,
        field_group: int,
    ) -> None:
        self._api = api
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
    ) -> list[RemCommandResponse]:
        """Handle a batch of REM registry commands."""

        responses: list[RemCommandResponse] = []
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
    ) -> list[RemCommandResponse]:
        command_id = str(raw_command.get("command_id") or "").strip() or "unknown"
        correlation_id = raw_command.get("correlation_id")
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
        if not source_identity:
            rejected = MissionCommandRejected(
                command_id=envelope.command_id,
                reason_code="unauthorized",
                reason="Source identity is required",
                correlation_id=envelope.correlation_id,
            )
            return [self._response_from_results(rejected.model_dump(mode="json"), group=group)]
        if envelope.command_type not in {"rem.registry.mode.set", "rem.registry.peers.list"}:
            rejected = MissionCommandRejected(
                command_id=envelope.command_id,
                reason_code="unknown_command",
                reason=f"Unsupported REM command '{envelope.command_type}'",
                correlation_id=envelope.correlation_id,
            )
            return [self._response_from_results(rejected.model_dump(mode="json"), group=group)]
        announce_capabilities = set(
            self._api.list_identity_announce_capabilities(source_identity)
        )
        if not REM_REQUIRED_CAPABILITIES.issubset(announce_capabilities):
            rejected = MissionCommandRejected(
                command_id=envelope.command_id,
                reason_code="unauthorized",
                reason="REM announce capabilities are required",
                correlation_id=envelope.correlation_id,
            )
            return [self._response_from_results(rejected.model_dump(mode="json"), group=group)]

        accepted = MissionCommandAccepted(
            command_id=envelope.command_id,
            accepted_at=_utcnow(),
            correlation_id=envelope.correlation_id,
            by_identity=self._hub_identity_resolver(),
        )
        responses = [self._response_from_results(accepted.model_dump(mode="json"), group=group)]
        try:
            result_payload, event_type = self._execute_command(
                envelope.command_type,
                source_identity=source_identity,
                args=dict(envelope.args or {}),
            )
        except ValueError as exc:
            rejected = MissionCommandRejected(
                command_id=envelope.command_id,
                reason_code="invalid_payload",
                reason=str(exc),
                correlation_id=envelope.correlation_id,
            )
            responses.append(
                self._response_from_results(rejected.model_dump(mode="json"), group=group)
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
                event={
                    "event_type": event_type,
                    "payload": result_payload,
                    "source": {"rns_identity": self._hub_identity_resolver()},
                },
            )
        )
        if self._event_log is not None:
            self._event_log.add_event(
                "rem_command_processed",
                f"Processed {envelope.command_type}",
                metadata={
                    "command_id": envelope.command_id,
                    "command_type": envelope.command_type,
                    "identity": source_identity,
                },
            )
        return responses

    def _execute_command(
        self,
        command_type: str,
        *,
        source_identity: str,
        args: dict[str, Any],
    ) -> tuple[dict[str, Any], str]:
        if command_type == "rem.registry.mode.set":
            mode = str(args.get("mode") or "").strip()
            return (
                self._api.set_rem_mode(source_identity, mode),
                "rem.registry.mode.updated",
            )
        return (
            self._api.rem_peer_registry(),
            "rem.registry.peers.listed",
        )

    def _response_from_results(
        self,
        results_payload: dict[str, Any],
        *,
        group: object | None,
        event: dict[str, object] | None = None,
    ) -> RemCommandResponse:
        fields: dict[int | str, object] = {self._field_results: results_payload}
        if event is not None:
            fields[self._field_event] = event
        if group is not None:
            fields[self._field_group] = group
        return RemCommandResponse(content="", fields=fields)
