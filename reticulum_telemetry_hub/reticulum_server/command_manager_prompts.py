"""Pending field prompt helpers."""

from __future__ import annotations

from typing import Any
from typing import Dict
from typing import List
import json
import re

import LXMF

from reticulum_telemetry_hub.reticulum_server.constants import PLUGIN_COMMAND


class CommandPromptMixin:
    """Pending field prompt helpers."""

    def _prompt_for_fields(
        self,
        command_name: str,
        missing_fields: List[str],
        message: LXMF.LXMessage,
        command: dict,
    ) -> LXMF.LXMessage:
        """Store pending requests and prompt the sender for missing fields."""

        sender_key = self._sender_key(message)
        self._register_pending_request(
            sender_key, command_name, missing_fields, command
        )
        example_payload = self._build_prompt_example(
            command_name, missing_fields, command
        )
        lines = [
            f"{command_name} is missing required fields: {', '.join(missing_fields)}.",
            "Reply with the missing fields in JSON format to continue.",
            f"Example: {example_payload}",
        ]
        return self._reply(message, "\n".join(lines))

    def _register_pending_request(
        self,
        sender_key: str,
        command_name: str,
        missing_fields: List[str],
        command: dict,
    ) -> None:
        """Persist partial command data while waiting for required fields."""

        stored_command = dict(command)
        requests_for_sender = self.pending_field_requests.setdefault(sender_key, {})
        requests_for_sender[command_name] = {
            "command": stored_command,
            "missing": list(missing_fields),
        }

    def _merge_pending_fields(self, command: dict, message: LXMF.LXMessage) -> dict:
        """Combine new command fragments with any pending prompt state."""

        sender_key = self._sender_key(message)
        pending_commands = self.pending_field_requests.get(sender_key)
        if not pending_commands:
            return command
        command_name = command.get(PLUGIN_COMMAND) or command.get("Command")
        if command_name is None:
            return command
        pending_entry = pending_commands.get(command_name)
        if pending_entry is None:
            return command
        merged_command = dict(pending_entry.get("command", {}))
        merged_command.update(command)
        merged_command.setdefault(PLUGIN_COMMAND, command_name)
        merged_command.setdefault("Command", command_name)
        remaining_missing = self._missing_fields(
            merged_command, pending_entry.get("missing", [])
        )
        if remaining_missing:
            pending_entry["missing"] = remaining_missing
            pending_entry["command"] = merged_command
        else:
            del pending_commands[command_name]
            if not pending_commands:
                self.pending_field_requests.pop(sender_key, None)
        return merged_command

    @staticmethod
    def _field_value(command: dict, field: str) -> Any:
        """Return a field value supporting common casing variants."""

        alternate_keys = {
            field,
            field.lower(),
            field.replace("ID", "id"),
            field.replace("ID", "_id"),
            field.replace("Name", "name"),
            field.replace("Name", "_name"),
            field.replace("Path", "path"),
            field.replace("Path", "_path"),
        }
        snake_key = re.sub(r"(?<!^)(?=[A-Z])", "_", field).lower()
        alternate_keys.add(snake_key)
        alternate_keys.add(snake_key.replace("_i_d", "_id"))
        lower_camel = field[:1].lower() + field[1:]
        alternate_keys.add(lower_camel)
        alternate_keys.add(field.replace("ID", "Id"))
        alternate_keys.add(lower_camel.replace("ID", "Id"))
        for key in alternate_keys:
            if key in command:
                return command.get(key)
        return command.get(field)

    def _missing_fields(self, command: dict, required_fields: List[str]) -> List[str]:
        """Identify which required fields are still empty."""

        missing: List[str] = []
        for field in required_fields:
            value = self._field_value(command, field)
            if value is None or value == "":
                missing.append(field)
        return missing

    def _build_prompt_example(
        self, command_name: str, missing_fields: List[str], command: dict
    ) -> str:
        """Construct a JSON example showing the missing fields."""

        template: Dict[str, Any] = {"Command": command_name}
        for key, value in command.items():
            if key in {PLUGIN_COMMAND, "Command"}:
                continue
            template[key] = value
        for field in missing_fields:
            if self._field_value(template, field) in {None, ""}:
                template[field] = f"<{field}>"
        return json.dumps(template, sort_keys=True)

    def _sender_key(self, message: LXMF.LXMessage) -> str:
        """Return the hex identity key representing the message sender."""

        return self._identity_hex(message.source.identity)

