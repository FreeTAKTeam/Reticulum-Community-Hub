"""Command parsing and normalization helpers."""

from __future__ import annotations

from typing import Any
from typing import Dict
from typing import List
from typing import Optional
import json

import LXMF
import RNS

from reticulum_telemetry_hub.reticulum_server.constants import PLUGIN_COMMAND
from reticulum_telemetry_hub.reticulum_server.runtime_events import report_nonfatal_exception


class CommandParsingMixin:
    """Command parsing and normalization helpers."""

    def _all_command_names(self) -> List[str]:
        """Return the list of supported command names."""

        return [
            self.CMD_HELP,
            self.CMD_EXAMPLES,
            self.CMD_JOIN,
            self.CMD_LEAVE,
            self.CMD_LIST_CLIENTS,
            self.CMD_RETRIEVE_TOPIC,
            self.CMD_CREATE_TOPIC,
            self.CMD_DELETE_TOPIC,
            self.CMD_LIST_TOPIC,
            self.CMD_PATCH_TOPIC,
            self.CMD_SUBSCRIBE_TOPIC,
            self.CMD_RETRIEVE_SUBSCRIBER,
            self.CMD_ADD_SUBSCRIBER,
            self.CMD_CREATE_SUBSCRIBER,
            self.CMD_DELETE_SUBSCRIBER,
            self.CMD_REMOVE_SUBSCRIBER,
            self.CMD_LIST_SUBSCRIBER,
            self.CMD_PATCH_SUBSCRIBER,
            self.CMD_GET_APP_INFO,
            self.CMD_LIST_FILES,
            self.CMD_LIST_IMAGES,
            self.CMD_RETRIEVE_FILE,
            self.CMD_RETRIEVE_IMAGE,
            self.CMD_ASSOCIATE_TOPIC_ID,
            self.CMD_STATUS,
            self.CMD_LIST_EVENTS,
            self.CMD_BAN_IDENTITY,
            self.CMD_UNBAN_IDENTITY,
            self.CMD_BLACKHOLE_IDENTITY,
            self.CMD_LIST_IDENTITIES,
            self.CMD_GET_CONFIG,
            self.CMD_VALIDATE_CONFIG,
            self.CMD_APPLY_CONFIG,
            self.CMD_ROLLBACK_CONFIG,
            self.CMD_FLUSH_TELEMETRY,
            self.CMD_RELOAD_CONFIG,
            self.CMD_DUMP_ROUTING,
        ]

    def _command_alias_map(self) -> Dict[str, str]:
        """Return a mapping of lowercase aliases to canonical commands."""

        if self._command_aliases_cache:
            return self._command_aliases_cache
        for command_name in self._all_command_names():
            aliases = {
                command_name.lower(),
                self._lower_camel(command_name).lower(),
            }
            for alias in aliases:
                self._command_aliases_cache.setdefault(alias, command_name)
        self._command_aliases_cache.setdefault(
            "retrievesubscriber", self.CMD_RETRIEVE_SUBSCRIBER
        )
        self._command_aliases_cache.setdefault(
            "retreivesubscriber", self.CMD_RETRIEVE_SUBSCRIBER
        )
        return self._command_aliases_cache

    @staticmethod
    def _lower_camel(command_name: str) -> str:
        """Return the command name with a lowercase prefix."""

        if not command_name:
            return command_name
        return command_name[0].lower() + command_name[1:]

    def _normalize_command_name(self, name: Optional[str]) -> Optional[str]:
        """Normalize command names across casing variants."""

        if name is None:
            return None
        normalized = name.strip()
        if not normalized:
            return None
        alias_map = self._command_alias_map()
        return alias_map.get(normalized.lower(), normalized)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def handle_commands(
        self, commands: List[dict], message: LXMF.LXMessage
    ) -> List[LXMF.LXMessage]:
        """Process a list of commands and return generated responses."""

        responses: List[LXMF.LXMessage] = []
        for raw_command in commands:
            normalized, error_response = self._normalize_command(raw_command, message)
            if error_response is not None:
                responses.append(error_response)
                continue
            if normalized is None:
                continue
            try:
                msg = self.handle_command(normalized, message)
            except Exception as exc:  # pragma: no cover - defensive log
                command_name = normalized.get(PLUGIN_COMMAND) or normalized.get(
                    "Command"
                )
                resolved_name = str(command_name or "unknown")
                report_nonfatal_exception(
                    self.event_log,
                    "command_error",
                    f"Command '{resolved_name}' failed: {exc}",
                    exc,
                    metadata={"command": resolved_name},
                    log_level=getattr(RNS, "LOG_WARNING", 2),
                )
                msg = self._reply(
                    message, f"Command failed: {resolved_name}"
                )
            if msg:
                if isinstance(msg, list):
                    responses.extend(msg)
                else:
                    responses.append(msg)
        return responses

    def _normalize_command(
        self, raw_command: Any, message: LXMF.LXMessage
    ) -> tuple[Optional[dict], Optional[LXMF.LXMessage]]:
        """Normalize incoming command payloads, including JSON-wrapped strings.

        Args:
            raw_command (Any): The incoming payload from LXMF.
            message (LXMF.LXMessage): Source LXMF message for contextual replies.

        Returns:
            tuple[Optional[dict], Optional[LXMF.LXMessage]]: Normalized payload and
            optional error reply when parsing fails.
        """

        if isinstance(raw_command, str):
            raw_command, error_response = self._parse_json_object(raw_command, message)
            if error_response is not None:
                return None, error_response

        if isinstance(raw_command, (list, tuple)):
            raw_command = {index: value for index, value in enumerate(raw_command)}

        if isinstance(raw_command, dict):
            normalized, error_response = self._unwrap_sideband_payload(
                raw_command, message
            )
            if error_response is not None:
                return None, error_response
            normalized = self._apply_positional_payload(normalized)
            return normalized, None

        return None, self._reply(
            message, f"Unsupported command payload type: {type(raw_command).__name__}"
        )

    def _parse_json_object(
        self, payload: str, message: LXMF.LXMessage
    ) -> tuple[Optional[dict], Optional[LXMF.LXMessage]]:
        """Parse a JSON string and ensure it represents an object.

        Args:
            payload (str): Raw JSON string containing command data.
            message (LXMF.LXMessage): Source LXMF message for error replies.

        Returns:
            tuple[Optional[dict], Optional[LXMF.LXMessage]]: Parsed JSON
            object or an error response when parsing fails.
        """

        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            error = self._reply(
                message, f"Command payload is not valid JSON: {payload!r}"
            )
            return None, error
        if not isinstance(parsed, dict):
            return None, self._reply(message, "Parsed command must be a JSON object")
        return parsed, None

    def _unwrap_sideband_payload(
        self, payload: dict, message: LXMF.LXMessage
    ) -> tuple[dict, Optional[LXMF.LXMessage]]:
        """Remove Sideband numeric-key wrappers and parse nested JSON content.

        Args:
            payload (dict): Incoming command payload.
            message (LXMF.LXMessage): Source LXMF message for error replies.

        Returns:
            tuple[dict, Optional[LXMF.LXMessage]]: Normalized command payload and
            an optional error response when nested parsing fails.
        """

        if len(payload) == 1:
            key = next(iter(payload))
            if isinstance(key, (int, str)) and str(key).isdigit():
                inner_payload = payload[key]
                if isinstance(inner_payload, dict):
                    return inner_payload, None
                if isinstance(inner_payload, str) and inner_payload.lstrip().startswith(
                    "{"
                ):
                    parsed, error_response = self._parse_json_object(
                        inner_payload, message
                    )
                    if error_response is not None:
                        return payload, error_response
                    if parsed is not None:
                        return parsed, None
        return payload, None

    def _apply_positional_payload(self, payload: dict) -> dict:
        """Expand numeric-key payloads into named command dictionaries.

        Sideband can emit command payloads as ``{0: "CreateTopic", 1: "Weather"}``
        instead of JSON objects. This helper maps known positional arguments into
        the expected named fields so downstream handlers receive structured data.

        Args:
            payload (dict): Raw command payload.

        Returns:
            dict: Normalized payload including "Command" and PLUGIN_COMMAND keys
            when conversion succeeds; otherwise the original payload.
        """

        if PLUGIN_COMMAND in payload or "Command" in payload:
            has_named_fields = any(not self._is_numeric_key(key) for key in payload)
            if has_named_fields:
                return payload

        numeric_keys = {key for key in payload if self._is_numeric_key(key)}
        if not numeric_keys:
            return payload

        command_name_raw = payload.get(0) if 0 in payload else payload.get("0")
        if not isinstance(command_name_raw, str):
            return payload

        command_name = self._normalize_command_name(command_name_raw) or command_name_raw
        positional_fields = self._positional_fields_for_command(command_name)
        if not positional_fields:
            return payload

        normalized: dict = {PLUGIN_COMMAND: command_name, "Command": command_name}
        for index, field_name in enumerate(positional_fields, start=1):
            value = self._numeric_lookup(payload, index)
            if value is not None:
                normalized[field_name] = value

        for key, value in payload.items():
            if self._is_numeric_key(key):
                continue
            normalized[key] = value
        return normalized

    def _positional_fields_for_command(self, command_name: str) -> List[str]:
        """Return positional field hints for known commands.

        Args:
            command_name (str): Name of the incoming command.

        Returns:
            List[str]: Ordered field names expected for positional payloads.
        """

        return self.POSITIONAL_FIELDS.get(command_name, [])

    @staticmethod
    def _numeric_lookup(payload: dict, index: int) -> Any:
        """Fetch a value from digit-only keys in either int or str form.

        Args:
            payload (dict): Payload to search.
            index (int): Numeric index to look up.

        Returns:
            Any: The value bound to the numeric key when present.
        """

        if index in payload:
            return payload.get(index)
        index_key = str(index)
        if index_key in payload:
            return payload.get(index_key)
        for key in payload:
            if not CommandParsingMixin._is_numeric_key(key):
                continue
            try:
                if int(str(key)) == index:
                    return payload.get(key)
            except ValueError:
                continue
        return None

    @staticmethod
    def _has_numeric_key(payload: dict, index: int) -> bool:
        """Return True when the payload includes a matching numeric key.

        Args:
            payload (dict): Payload to search.
            index (int): Numeric index to look up.

        Returns:
            bool: True when the key exists in any numeric string form.
        """

        for key in payload:
            if not CommandParsingMixin._is_numeric_key(key):
                continue
            try:
                if int(str(key)) == index:
                    return True
            except ValueError:
                continue
        return False

    @staticmethod
    def _is_numeric_key(key: Any) -> bool:
        """Return True when the key is a digit-like identifier.

        Args:
            key (Any): Key to evaluate.

        Returns:
            bool: True when the key contains only digits.
        """

        try:
            return str(key).isdigit()
        except Exception:
            return False

    # ------------------------------------------------------------------
    # individual command processing
    # ------------------------------------------------------------------
