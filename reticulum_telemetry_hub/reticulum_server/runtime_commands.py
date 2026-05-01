"""Inbound command and mission response helpers."""
# ruff: noqa: F403,F405

from __future__ import annotations

from typing import Any
from typing import Callable
from typing import cast

import LXMF
import RNS

import reticulum_telemetry_hub.lxmf_runtime  # noqa: F401
from reticulum_telemetry_hub.config.constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.appearance import apply_icon_appearance
from reticulum_telemetry_hub.reticulum_server.announce_capabilities import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.constants import PLUGIN_COMMAND
from reticulum_telemetry_hub.reticulum_server.delivery_defaults import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.propagation_selection import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.command_manager import CommandManager
from reticulum_telemetry_hub.reticulum_server.runtime_constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_support import *  # noqa: F403


class RuntimeCommandMixin:
    """Inbound command and mission response helpers."""

    def command_handler(self, commands: list, message: LXMF.LXMessage) -> list[LXMF.LXMessage]:
        """Handles commands received from the client and returns responses.

        Args:
            commands (list): List of commands received from the client
            message (LXMF.LXMessage): LXMF message object

        Returns:
            list[LXMF.LXMessage]: Responses generated for the commands.
        """
        manager = getattr(self, "command_manager", None)
        if manager is None:
            RNS.log(
                "Command manager unavailable; dropping command payload.",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return []

        mission_commands: list[dict[str, Any]] = []
        rem_commands: list[dict[str, Any]] = []
        checklist_commands: list[dict[str, Any]] = []
        legacy_commands: list[Any] = []
        for command in commands:
            if not isinstance(command, dict):
                legacy_commands.append(command)
                continue
            command_type = command.get("command_type")
            if isinstance(command_type, str) and command_type.strip():
                if command_type.startswith("rem."):
                    rem_commands.append(command)
                elif command_type.startswith("checklist."):
                    checklist_commands.append(command)
                else:
                    mission_commands.append(command)
            else:
                legacy_commands.append(command)

        responses: list[LXMF.LXMessage] = []
        source_identity = self._message_source_hex(message)
        message_fields = message.fields if isinstance(message.fields, dict) else {}
        group = message_fields.get(LXMF.FIELD_GROUP)

        rem_router = getattr(self, "rem_command_router", None)
        if rem_commands and rem_router is not None:
            rem_replies = rem_router.handle_commands(
                rem_commands,
                source_identity=source_identity,
                group=group,
            )
            responses.extend(
                [
                    response
                    for response in (
                        self._mission_sync_response_to_lxmf(message, entry)
                        for entry in rem_replies
                    )
                    if response is not None
                ]
            )

        mission_router = getattr(self, "mission_sync_router", None)
        if mission_commands and mission_router is not None:
            mission_replies = mission_router.handle_commands(
                mission_commands,
                source_identity=source_identity,
                group=group,
            )
            responses.extend(
                [
                    response
                    for response in (
                        self._mission_sync_response_to_lxmf(message, entry)
                        for entry in mission_replies
                    )
                    if response is not None
                ]
            )

        checklist_router = getattr(self, "checklist_sync_router", None)
        if checklist_commands and checklist_router is not None:
            checklist_replies = checklist_router.handle_commands(
                checklist_commands,
                source_identity=source_identity,
                group=group,
            )
            responses.extend(
                [
                    response
                    for response in (
                        self._mission_sync_response_to_lxmf(message, entry)
                        for entry in checklist_replies
                    )
                    if response is not None
                ]
            )

        if legacy_commands:
            responses.extend(manager.handle_commands(legacy_commands, message))

        if self._commands_affect_subscribers(
            legacy_commands
        ) or self._mission_commands_affect_subscribers(mission_commands):
            self._invalidate_topic_registry()
        return responses

    def _should_ignore_passive_command_payload(
        self,
        commands: list[dict] | None,
        message: LXMF.LXMessage,
    ) -> bool:
        """Return True for background numeric command payloads with no user text.

        Some clients emit machine-generated ``FIELD_COMMANDS`` updates that use the
        numeric plugin key ``0`` but do not actually represent user CLI commands.
        When those packets have no message body and the key-0 token is not a known
        command, treating them as CLI input only produces unsolicited help spam.
        """

        if not commands:
            return False
        content = getattr(message, "content", None)
        if content not in (None, b"", ""):
            return False
        fields = message.fields if isinstance(message.fields, dict) else {}
        has_non_command_signal = any(
            key != LXMF.FIELD_COMMANDS
            and value not in (None, "", b"", {}, [], ())
            for key, value in fields.items()
        )
        if not has_non_command_signal:
            return False

        manager = getattr(self, "command_manager", None)
        if not isinstance(manager, CommandManager):
            return False
        normalize_name_fn = cast(
            Callable[[str | None], str | None],
            manager._normalize_command_name,  # pylint: disable=protected-access
        )
        known_names = set(
            manager._all_command_names()  # pylint: disable=protected-access
        )

        for command in commands:
            if not isinstance(command, dict):
                return False
            command_type = command.get("command_type")
            if isinstance(command_type, str) and command_type.strip():
                return False
            if "Command" in command:
                return False
            raw_name = command.get(PLUGIN_COMMAND)
            if raw_name is None:
                raw_name = command.get(str(PLUGIN_COMMAND))
            if not isinstance(raw_name, str):
                return False
            normalized = normalize_name_fn(raw_name)
            if normalized is None:
                normalized = raw_name.strip() or None
            if normalized in known_names:
                return False
        return True

    def _mission_sync_response_to_lxmf(
        self, message: LXMF.LXMessage, response
    ) -> LXMF.LXMessage | None:
        """Convert a mission/checklist sync response to a reply LXMF message."""

        if self.my_lxmf_dest is None:
            return None
        destination = None
        command_manager = getattr(self, "command_manager", None)
        try:
            if command_manager is not None and hasattr(command_manager, "_create_dest"):
                destination = command_manager._create_dest(  # pylint: disable=protected-access
                    message.source.identity
                )
        except Exception:
            destination = None
        if destination is None:
            try:
                destination = RNS.Destination(
                    message.source.identity,
                    RNS.Destination.OUT,
                    RNS.Destination.SINGLE,
                    "lxmf",
                    "delivery",
                )
            except Exception:
                return None
        response_fields = response.fields if isinstance(response.fields, dict) else {}
        outbound_fields = self._augment_r3akt_custom_fields(response_fields)
        merged_fields = self._merge_standard_fields(
            source_fields=message.fields,
            extra_fields=outbound_fields,
        )
        return LXMF.LXMessage(
            destination,
            self.my_lxmf_dest,
            str(response.content or ""),
            fields=apply_icon_appearance(merged_fields or {}),
            desired_method=LXMF.LXMessage.DIRECT,
        )

    @staticmethod
    def _extract_mission_uid_from_response_fields(
        fields: dict[int | str, object] | None,
    ) -> str | None:
        if not isinstance(fields, dict):
            return None
        event_field = fields.get(LXMF.FIELD_EVENT)
        if not isinstance(event_field, dict):
            return None
        event_type = str(event_field.get("event_type") or "").strip()
        payload = event_field.get("payload")
        if not isinstance(payload, dict):
            return None

        mission_uid = str(
            payload.get("mission_uid") or payload.get("mission_id") or ""
        ).strip()
        if mission_uid:
            return mission_uid

        if event_type.startswith("mission.registry.mission."):
            fallback_uid = str(payload.get("uid") or "").strip()
            if fallback_uid:
                return fallback_uid

        result_field = fields.get(LXMF.FIELD_RESULTS)
        if isinstance(result_field, dict):
            result_payload = result_field.get("result")
            if isinstance(result_payload, dict):
                mission_uid = str(
                    result_payload.get("mission_uid")
                    or result_payload.get("mission_id")
                    or ""
                ).strip()
                if mission_uid:
                    return mission_uid
                if event_type.startswith("mission.registry.mission."):
                    fallback_uid = str(result_payload.get("uid") or "").strip()
                    if fallback_uid:
                        return fallback_uid

        return None
