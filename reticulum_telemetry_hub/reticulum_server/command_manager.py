# Command management for Reticulum Telemetry Hub
from __future__ import annotations

from functools import partial
from typing import Any, Dict, List, Optional
import json
from pathlib import Path
import re
import time
import RNS
import LXMF

from reticulum_telemetry_hub.api.models import Client, FileAttachment, Subscriber, Topic
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.config.manager import HubConfigurationManager
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog

from .constants import PLUGIN_COMMAND
from .command_text import (
    build_help_text,
    build_examples_text,
    format_attachment_list,
    format_subscriber_list,
    format_topic_list,
    topic_subscribe_hint,
)
from ..lxmf_telemetry.telemetry_controller import TelemetryController


class CommandManager:
    """Manage RTH command execution."""

    # Command names based on the API specification
    CMD_HELP = "Help"
    CMD_EXAMPLES = "Examples"
    CMD_JOIN = "join"
    CMD_LEAVE = "leave"
    CMD_LIST_CLIENTS = "ListClients"
    CMD_RETRIEVE_TOPIC = "RetrieveTopic"
    CMD_CREATE_TOPIC = "CreateTopic"
    CMD_DELETE_TOPIC = "DeleteTopic"
    CMD_LIST_TOPIC = "ListTopic"
    CMD_PATCH_TOPIC = "PatchTopic"
    CMD_SUBSCRIBE_TOPIC = "SubscribeTopic"
    CMD_RETRIEVE_SUBSCRIBER = "RetrieveSubscriber"
    CMD_ADD_SUBSCRIBER = "AddSubscriber"
    CMD_CREATE_SUBSCRIBER = "CreateSubscriber"
    CMD_DELETE_SUBSCRIBER = "DeleteSubscriber"
    CMD_LIST_SUBSCRIBER = "ListSubscriber"
    CMD_PATCH_SUBSCRIBER = "PatchSubscriber"
    CMD_REMOVE_SUBSCRIBER = "RemoveSubscriber"
    CMD_GET_APP_INFO = "getAppInfo"
    CMD_LIST_FILES = "ListFiles"
    CMD_LIST_IMAGES = "ListImages"
    CMD_RETRIEVE_FILE = "RetrieveFile"
    CMD_RETRIEVE_IMAGE = "RetrieveImage"
    CMD_ASSOCIATE_TOPIC_ID = "AssociateTopicID"
    CMD_STATUS = "GetStatus"
    CMD_LIST_EVENTS = "ListEvents"
    CMD_BAN_IDENTITY = "BanIdentity"
    CMD_UNBAN_IDENTITY = "UnbanIdentity"
    CMD_BLACKHOLE_IDENTITY = "BlackholeIdentity"
    CMD_LIST_IDENTITIES = "ListIdentities"
    CMD_GET_CONFIG = "GetConfig"
    CMD_VALIDATE_CONFIG = "ValidateConfig"
    CMD_APPLY_CONFIG = "ApplyConfig"
    CMD_ROLLBACK_CONFIG = "RollbackConfig"
    CMD_FLUSH_TELEMETRY = "FlushTelemetry"
    CMD_RELOAD_CONFIG = "ReloadConfig"
    CMD_DUMP_ROUTING = "DumpRouting"
    POSITIONAL_FIELDS: Dict[str, List[str]] = {
        CMD_CREATE_TOPIC: ["TopicName", "TopicPath"],
        CMD_RETRIEVE_TOPIC: ["TopicID"],
        CMD_DELETE_TOPIC: ["TopicID"],
        CMD_PATCH_TOPIC: ["TopicID", "TopicName", "TopicPath", "TopicDescription"],
        CMD_SUBSCRIBE_TOPIC: ["TopicID", "RejectTests"],
        CMD_CREATE_SUBSCRIBER: ["Destination", "TopicID"],
        CMD_ADD_SUBSCRIBER: ["Destination", "TopicID"],
        CMD_RETRIEVE_SUBSCRIBER: ["SubscriberID"],
        CMD_DELETE_SUBSCRIBER: ["SubscriberID"],
        CMD_REMOVE_SUBSCRIBER: ["SubscriberID"],
        CMD_PATCH_SUBSCRIBER: ["SubscriberID"],
        CMD_RETRIEVE_FILE: ["FileID"],
        CMD_RETRIEVE_IMAGE: ["FileID"],
        CMD_ASSOCIATE_TOPIC_ID: ["TopicID"],
    }

    def __init__(
        self,
        connections: dict,
        tel_controller: TelemetryController,
        my_lxmf_dest: RNS.Destination,
        api: ReticulumTelemetryHubAPI,
        *,
        config_manager: HubConfigurationManager | None = None,
        event_log: EventLog | None = None,
    ):
        self.connections = connections
        self.tel_controller = tel_controller
        self.my_lxmf_dest = my_lxmf_dest
        self.api = api
        self.config_manager = config_manager
        self.event_log = event_log
        self.pending_field_requests: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._command_aliases_cache: Dict[str, str] = {}
        self._start_time = time.time()

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
                RNS.log(
                    f"Command '{command_name}' failed: {exc}",
                    getattr(RNS, "LOG_WARNING", 2),
                )
                msg = self._reply(
                    message, f"Command failed: {command_name or 'unknown'}"
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
        return payload.get(str(index))

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
    def handle_command(
        self, command: dict, message: LXMF.LXMessage
    ) -> Optional[LXMF.LXMessage]:
        command = self._merge_pending_fields(command, message)
        name = command.get(PLUGIN_COMMAND) or command.get("Command")
        name = self._normalize_command_name(name)
        telemetry_request_present = (
            TelemetryController.TELEMETRY_REQUEST in command
            or str(TelemetryController.TELEMETRY_REQUEST) in command
        )
        is_telemetry_command = (
            isinstance(name, str) and name.strip().lower() == "telemetryrequest"
        )
        if name:
            command[PLUGIN_COMMAND] = name
            command["Command"] = name
        if name is not None:
            dispatch_map = {
                self.CMD_HELP: lambda: self._handle_help(message),
                self.CMD_EXAMPLES: lambda: self._handle_examples(message),
                self.CMD_JOIN: lambda: self._handle_join(message),
                self.CMD_LEAVE: lambda: self._handle_leave(message),
                self.CMD_LIST_CLIENTS: lambda: self._handle_list_clients(message),
                self.CMD_GET_APP_INFO: lambda: self._handle_get_app_info(message),
                self.CMD_LIST_TOPIC: lambda: self._handle_list_topics(message),
                self.CMD_LIST_FILES: lambda: self._handle_list_files(message),
                self.CMD_LIST_IMAGES: lambda: self._handle_list_images(message),
                self.CMD_CREATE_TOPIC: lambda: self._handle_create_topic(
                    command, message
                ),
                self.CMD_RETRIEVE_TOPIC: lambda: self._handle_retrieve_topic(
                    command, message
                ),
                self.CMD_DELETE_TOPIC: lambda: self._handle_delete_topic(
                    command, message
                ),
                self.CMD_PATCH_TOPIC: lambda: self._handle_patch_topic(
                    command, message
                ),
                self.CMD_SUBSCRIBE_TOPIC: lambda: self._handle_subscribe_topic(
                    command, message
                ),
                self.CMD_LIST_SUBSCRIBER: lambda: self._handle_list_subscribers(
                    message
                ),
                self.CMD_RETRIEVE_FILE: lambda: self._handle_retrieve_file(
                    command, message
                ),
                self.CMD_RETRIEVE_IMAGE: lambda: self._handle_retrieve_image(
                    command, message
                ),
                self.CMD_ASSOCIATE_TOPIC_ID: lambda: self._handle_associate_topic_id(
                    command, message
                ),
                self.CMD_CREATE_SUBSCRIBER: lambda: self._handle_create_subscriber(
                    command, message
                ),
                self.CMD_ADD_SUBSCRIBER: lambda: self._handle_create_subscriber(
                    command, message
                ),
                self.CMD_RETRIEVE_SUBSCRIBER: partial(
                    self._handle_retrieve_subscriber, command, message
                ),
                self.CMD_DELETE_SUBSCRIBER: lambda: self._handle_delete_subscriber(
                    command, message
                ),
                self.CMD_REMOVE_SUBSCRIBER: lambda: self._handle_delete_subscriber(
                    command, message
                ),
                self.CMD_PATCH_SUBSCRIBER: lambda: self._handle_patch_subscriber(
                    command, message
                ),
                self.CMD_STATUS: lambda: self._handle_status(message),
                self.CMD_LIST_EVENTS: lambda: self._handle_list_events(message),
                self.CMD_BAN_IDENTITY: lambda: self._handle_ban_identity(
                    command, message
                ),
                self.CMD_UNBAN_IDENTITY: lambda: self._handle_unban_identity(
                    command, message
                ),
                self.CMD_BLACKHOLE_IDENTITY: lambda: self._handle_blackhole_identity(
                    command, message
                ),
                self.CMD_LIST_IDENTITIES: lambda: self._handle_list_identities(message),
                self.CMD_GET_CONFIG: lambda: self._handle_get_config(message),
                self.CMD_VALIDATE_CONFIG: lambda: self._handle_validate_config(
                    command, message
                ),
                self.CMD_APPLY_CONFIG: lambda: self._handle_apply_config(
                    command, message
                ),
                self.CMD_ROLLBACK_CONFIG: lambda: self._handle_rollback_config(
                    command, message
                ),
                self.CMD_FLUSH_TELEMETRY: lambda: self._handle_flush_telemetry(message),
                self.CMD_RELOAD_CONFIG: lambda: self._handle_reload_config(message),
                self.CMD_DUMP_ROUTING: lambda: self._handle_dump_routing(message),
            }
            handler = dispatch_map.get(name)
            if handler is not None:
                return handler()
            if telemetry_request_present and is_telemetry_command:
                return self.tel_controller.handle_command(
                    command, message, self.my_lxmf_dest
                )
            return self._handle_unknown_command(name, message)
        # Delegate to telemetry controller for telemetry related commands
        return self.tel_controller.handle_command(command, message, self.my_lxmf_dest)

    # ------------------------------------------------------------------
    # command implementations
    # ------------------------------------------------------------------
    def _create_dest(self, identity: RNS.Identity) -> RNS.Destination:
        return RNS.Destination(
            identity,
            RNS.Destination.OUT,
            RNS.Destination.SINGLE,
            "lxmf",
            "delivery",
        )

    def _handle_join(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        dest = self._create_dest(message.source.identity)
        self.connections[dest.identity.hash] = dest
        self.api.join(self._identity_hex(dest.identity))
        RNS.log(f"Connection added: {message.source}")
        self._record_event(
            "client_join",
            f"Client joined: {self._identity_hex(dest.identity)}",
        )
        return LXMF.LXMessage(
            dest,
            self.my_lxmf_dest,
            "Connection established",
            desired_method=LXMF.LXMessage.DIRECT,
        )

    def _handle_leave(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        dest = self._create_dest(message.source.identity)
        self.connections.pop(dest.identity.hash, None)
        self.api.leave(self._identity_hex(dest.identity))
        RNS.log(f"Connection removed: {message.source}")
        self._record_event(
            "client_leave",
            f"Client left: {self._identity_hex(dest.identity)}",
        )
        return LXMF.LXMessage(
            dest,
            self.my_lxmf_dest,
            "Connection removed",
            desired_method=LXMF.LXMessage.DIRECT,
        )

    def _handle_list_clients(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        clients = self.api.list_clients()
        client_hashes = [self._format_client_entry(client) for client in clients]
        return self._reply(message, ",".join(client_hashes) or "")

    def _handle_get_app_info(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        app_info = self.api.get_app_info()
        payload = {
            "name": getattr(app_info, "app_name", ""),
            "version": getattr(app_info, "app_version", ""),
            "description": getattr(app_info, "app_description", ""),
        }
        return self._reply(message, json.dumps(payload, sort_keys=True))

    def _handle_list_topics(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        topics = self.api.list_topics()
        content_lines = format_topic_list(topics)
        content_lines.append(topic_subscribe_hint(self.CMD_SUBSCRIBE_TOPIC))
        return self._reply(message, "\n".join(content_lines))

    def _handle_list_files(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        files = self.api.list_files()
        lines = format_attachment_list(files, empty_text="No files stored yet.")
        return self._reply(message, "\n".join(lines))

    def _handle_list_images(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        images = self.api.list_images()
        lines = format_attachment_list(images, empty_text="No images stored yet.")
        return self._reply(message, "\n".join(lines))

    def _handle_associate_topic_id(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        topic_id = self._extract_topic_id(command)
        if not topic_id:
            return self._prompt_for_fields(
                self.CMD_ASSOCIATE_TOPIC_ID, ["TopicID"], message, command
            )
        payload = json.dumps({"TopicID": topic_id}, sort_keys=True)
        return self._reply(message, f"Attachment TopicID set: {payload}")

    def _handle_create_topic(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        missing = self._missing_fields(command, ["TopicName", "TopicPath"])
        if missing:
            return self._prompt_for_fields(
                self.CMD_CREATE_TOPIC, missing, message, command
            )
        topic = Topic.from_dict(command)
        created = self.api.create_topic(topic)
        payload = json.dumps(created.to_dict(), sort_keys=True)
        self._record_event("topic_created", f"Topic created: {created.topic_id}")
        return self._reply(message, f"Topic created: {payload}")

    def _handle_retrieve_topic(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        topic_id = self._extract_topic_id(command)
        if not topic_id:
            return self._prompt_for_fields(
                self.CMD_RETRIEVE_TOPIC, ["TopicID"], message, command
            )
        try:
            topic = self.api.retrieve_topic(topic_id)
        except KeyError as exc:
            return self._reply(message, str(exc))
        payload = json.dumps(topic.to_dict(), sort_keys=True)
        return self._reply(message, payload)

    def _handle_delete_topic(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        topic_id = self._extract_topic_id(command)
        if not topic_id:
            return self._prompt_for_fields(
                self.CMD_DELETE_TOPIC, ["TopicID"], message, command
            )
        try:
            topic = self.api.delete_topic(topic_id)
        except KeyError as exc:
            return self._reply(message, str(exc))
        payload = json.dumps(topic.to_dict(), sort_keys=True)
        self._record_event("topic_deleted", f"Topic deleted: {topic.topic_id}")
        return self._reply(message, f"Topic deleted: {payload}")

    def _handle_patch_topic(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        topic_id = self._extract_topic_id(command)
        if not topic_id:
            return self._prompt_for_fields(
                self.CMD_PATCH_TOPIC, ["TopicID"], message, command
            )
        updates = {k: v for k, v in command.items() if k != PLUGIN_COMMAND}
        try:
            topic = self.api.patch_topic(topic_id, **updates)
        except KeyError as exc:
            return self._reply(message, str(exc))
        payload = json.dumps(topic.to_dict(), sort_keys=True)
        self._record_event("topic_updated", f"Topic updated: {topic.topic_id}")
        return self._reply(message, f"Topic updated: {payload}")

    def _handle_subscribe_topic(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        topic_id = self._extract_topic_id(command)
        if not topic_id:
            return self._prompt_for_fields(
                self.CMD_SUBSCRIBE_TOPIC, ["TopicID"], message, command
            )
        destination = self._identity_hex(message.source.identity)
        reject_tests = None
        if "RejectTests" in command:
            reject_tests = command["RejectTests"]
        elif "reject_tests" in command:
            reject_tests = command["reject_tests"]
        metadata = command.get("Metadata") or command.get("metadata") or {}
        try:
            subscriber = self.api.subscribe_topic(
                topic_id,
                destination=destination,
                reject_tests=reject_tests,
                metadata=metadata,
            )
        except KeyError as exc:
            return self._reply(message, str(exc))
        payload = json.dumps(subscriber.to_dict(), sort_keys=True)
        self._record_event(
            "topic_subscribed",
            f"Destination subscribed to {topic_id}",
        )
        return self._reply(message, f"Subscribed: {payload}")

    def _handle_retrieve_file(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        file_id_value = self._extract_file_id(command)
        file_id = self._coerce_int_id(file_id_value)
        if file_id is None:
            if file_id_value is None:
                return self._prompt_for_fields(
                    self.CMD_RETRIEVE_FILE, ["FileID"], message, command
                )
            return self._reply(message, "FileID must be an integer")
        try:
            attachment = self.api.retrieve_file(file_id)
        except KeyError as exc:
            return self._reply(message, str(exc))
        try:
            fields = self._build_attachment_fields(attachment)
        except FileNotFoundError:
            return self._reply(
                message, f"File '{file_id}' not found on disk; remove and re-upload."
            )
        payload = json.dumps(attachment.to_dict(), sort_keys=True)
        return self._reply(message, f"File retrieved: {payload}", fields=fields)

    def _handle_retrieve_image(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        image_id_value = self._extract_file_id(command)
        image_id = self._coerce_int_id(image_id_value)
        if image_id is None:
            if image_id_value is None:
                return self._prompt_for_fields(
                    self.CMD_RETRIEVE_IMAGE, ["FileID"], message, command
                )
            return self._reply(message, "FileID must be an integer")
        try:
            attachment = self.api.retrieve_image(image_id)
        except KeyError as exc:
            return self._reply(message, str(exc))
        try:
            fields = self._build_attachment_fields(attachment)
        except FileNotFoundError:
            return self._reply(
                message, f"Image '{image_id}' not found on disk; remove and re-upload."
            )
        payload = json.dumps(attachment.to_dict(), sort_keys=True)
        return self._reply(message, f"Image retrieved: {payload}", fields=fields)

    def _handle_list_subscribers(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        subscribers = self.api.list_subscribers()
        lines = format_subscriber_list(subscribers)
        return self._reply(message, "\n".join(lines))

    def _handle_help(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        return self._reply(message, build_help_text(self))

    def _handle_examples(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        return self._reply(message, build_examples_text(self))

    def _handle_unknown_command(
        self, name: str, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        sender = self._identity_hex(message.source.identity)
        RNS.log(f"Unknown command '{name}' from {sender}", getattr(RNS, "LOG_ERROR", 1))
        help_text = build_help_text(self)
        payload = f"Unknown command\n\n{help_text}"
        return self._reply(message, payload)

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

    def _handle_create_subscriber(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        destination = self._field_value(command, "Destination")
        if not destination:
            command = dict(command)
            command["Destination"] = self._sender_key(message)
        missing = self._missing_fields(command, ["Destination"])
        if missing:
            return self._prompt_for_fields(
                self.CMD_CREATE_SUBSCRIBER, missing, message, command
            )
        subscriber = Subscriber.from_dict(command)
        try:
            created = self.api.create_subscriber(subscriber)
        except ValueError as exc:
            return self._reply(message, f"Subscriber creation failed: {exc}")
        payload = json.dumps(created.to_dict(), sort_keys=True)
        self._record_event(
            "subscriber_created",
            f"Subscriber created: {created.subscriber_id}",
        )
        return self._reply(message, f"Subscriber created: {payload}")

    def _handle_retrieve_subscriber(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        subscriber_id = self._extract_subscriber_id(command)
        if not subscriber_id:
            return self._prompt_for_fields(
                self.CMD_RETRIEVE_SUBSCRIBER, ["SubscriberID"], message, command
            )
        try:
            subscriber = self.api.retrieve_subscriber(subscriber_id)
        except KeyError as exc:
            return self._reply(message, str(exc))
        payload = json.dumps(subscriber.to_dict(), sort_keys=True)
        return self._reply(message, payload)

    def _handle_delete_subscriber(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        subscriber_id = self._extract_subscriber_id(command)
        if not subscriber_id:
            return self._prompt_for_fields(
                self.CMD_DELETE_SUBSCRIBER, ["SubscriberID"], message, command
            )
        try:
            subscriber = self.api.delete_subscriber(subscriber_id)
        except KeyError as exc:
            return self._reply(message, str(exc))
        payload = json.dumps(subscriber.to_dict(), sort_keys=True)
        self._record_event(
            "subscriber_deleted",
            f"Subscriber deleted: {subscriber.subscriber_id}",
        )
        return self._reply(message, f"Subscriber deleted: {payload}")

    def _handle_patch_subscriber(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        subscriber_id = self._extract_subscriber_id(command)
        if not subscriber_id:
            return self._prompt_for_fields(
                self.CMD_PATCH_SUBSCRIBER, ["SubscriberID"], message, command
            )
        updates = {k: v for k, v in command.items() if k != PLUGIN_COMMAND}
        try:
            subscriber = self.api.patch_subscriber(subscriber_id, **updates)
        except KeyError as exc:
            return self._reply(message, str(exc))
        payload = json.dumps(subscriber.to_dict(), sort_keys=True)
        self._record_event(
            "subscriber_updated",
            f"Subscriber updated: {subscriber.subscriber_id}",
        )
        return self._reply(message, f"Subscriber updated: {payload}")

    def _handle_status(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        """Return the dashboard status snapshot."""

        uptime_seconds = int(time.time() - self._start_time)
        status = {
            "uptime_seconds": uptime_seconds,
            "clients": len(self.connections),
            "topics": len(self.api.list_topics()),
            "subscribers": len(self.api.list_subscribers()),
            "files": len(self.api.list_files()),
            "images": len(self.api.list_images()),
            "telemetry": self.tel_controller.telemetry_stats(),
        }
        payload = json.dumps(status, sort_keys=True)
        return self._reply(message, payload)

    def _handle_list_events(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        """Return recent event entries for the dashboard."""

        events = []
        if self.event_log is not None:
            events = self.event_log.list_events(limit=50)
        payload = json.dumps(events, sort_keys=True)
        return self._reply(message, payload)

    def _handle_ban_identity(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        """Mark an identity as banned."""

        identity = self._extract_identity(command)
        if not identity:
            return self._prompt_for_fields(
                self.CMD_BAN_IDENTITY, ["Identity"], message, command
            )
        status = self.api.ban_identity(identity)
        payload = json.dumps(status.to_dict(), sort_keys=True)
        self._record_event("identity_banned", f"Identity banned: {identity}")
        return self._reply(message, payload)

    def _handle_unban_identity(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        """Remove a ban/blackhole from an identity."""

        identity = self._extract_identity(command)
        if not identity:
            return self._prompt_for_fields(
                self.CMD_UNBAN_IDENTITY, ["Identity"], message, command
            )
        status = self.api.unban_identity(identity)
        payload = json.dumps(status.to_dict(), sort_keys=True)
        self._record_event("identity_unbanned", f"Identity unbanned: {identity}")
        return self._reply(message, payload)

    def _handle_blackhole_identity(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        """Mark an identity as blackholed."""

        identity = self._extract_identity(command)
        if not identity:
            return self._prompt_for_fields(
                self.CMD_BLACKHOLE_IDENTITY, ["Identity"], message, command
            )
        status = self.api.blackhole_identity(identity)
        payload = json.dumps(status.to_dict(), sort_keys=True)
        self._record_event("identity_blackholed", f"Identity blackholed: {identity}")
        return self._reply(message, payload)

    def _handle_list_identities(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        """Return identity status entries for admin tools."""

        identities = self.api.list_identity_statuses()
        payload = json.dumps([entry.to_dict() for entry in identities], sort_keys=True)
        return self._reply(message, payload)

    def _handle_get_config(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        """Return the current config.ini content."""

        config_text = self.api.get_config_text()
        return self._reply(message, config_text)

    def _handle_validate_config(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        """Validate config content without applying changes."""

        config_text = command.get("ConfigText") or command.get("config_text")
        if not config_text:
            return self._prompt_for_fields(
                self.CMD_VALIDATE_CONFIG, ["ConfigText"], message, command
            )
        result = self.api.validate_config_text(str(config_text))
        payload = json.dumps(result, sort_keys=True)
        return self._reply(message, payload)

    def _handle_apply_config(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        """Apply a new config.ini payload."""

        config_text = command.get("ConfigText") or command.get("config_text")
        if not config_text:
            return self._prompt_for_fields(
                self.CMD_APPLY_CONFIG, ["ConfigText"], message, command
            )
        try:
            result = self.api.apply_config_text(str(config_text))
        except ValueError as exc:
            return self._reply(message, f"Config apply failed: {exc}")
        payload = json.dumps(result, sort_keys=True)
        self._record_event("config_applied", "Configuration updated")
        return self._reply(message, payload)

    def _handle_rollback_config(
        self, command: dict, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        """Rollback configuration using the latest backup."""

        backup_path = command.get("BackupPath") or command.get("backup_path")
        backup_value = str(backup_path) if backup_path else None
        result = self.api.rollback_config_text(backup_path=backup_value)
        payload = json.dumps(result, sort_keys=True)
        self._record_event("config_rollback", "Configuration rollback applied")
        return self._reply(message, payload)

    def _handle_flush_telemetry(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        """Clear stored telemetry records."""

        deleted = self.tel_controller.clear_telemetry()
        payload = json.dumps({"deleted": deleted}, sort_keys=True)
        self._record_event("telemetry_flushed", f"Telemetry flushed ({deleted} rows)")
        return self._reply(message, payload)

    def _handle_reload_config(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        """Reload configuration from disk."""

        config = self.api.reload_config()
        payload = json.dumps(config.to_dict(), sort_keys=True)
        self._record_event("config_reloaded", "Configuration reloaded")
        return self._reply(message, payload)

    def _handle_dump_routing(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        """Return a summary of connected destinations."""

        destinations = [
            self._identity_hex(dest.identity) for dest in self.connections.values()
        ]
        payload = json.dumps({"destinations": destinations}, sort_keys=True)
        return self._reply(message, payload)

    @staticmethod
    def _identity_hex(identity: RNS.Identity) -> str:
        hash_bytes = getattr(identity, "hash", b"") or b""
        return hash_bytes.hex()

    @staticmethod
    def _format_client_entry(client: Client) -> str:
        metadata = client.metadata or {}
        metadata_str = json.dumps(metadata, sort_keys=True)
        try:
            identity_bytes = bytes.fromhex(client.identity)
            identity_value = RNS.prettyhexrep(identity_bytes)
        except (ValueError, TypeError):
            identity_value = client.identity
        return f"{identity_value}|{metadata_str}"

    def _reply(
        self, message: LXMF.LXMessage, content: str, *, fields: Optional[dict] = None
    ) -> LXMF.LXMessage:
        dest = self._create_dest(message.source.identity)
        return LXMF.LXMessage(
            dest,
            self.my_lxmf_dest,
            content,
            fields=fields,
            desired_method=LXMF.LXMessage.DIRECT,
        )

    @staticmethod
    def _extract_topic_id(command: dict) -> Optional[str]:
        return (
            command.get("TopicID")
            or command.get("topic_id")
            or command.get("id")
            or command.get("ID")
        )

    @staticmethod
    def _extract_subscriber_id(command: dict) -> Optional[str]:
        return (
            command.get("SubscriberID")
            or command.get("subscriber_id")
            or command.get("id")
            or command.get("ID")
        )

    @staticmethod
    def _extract_file_id(command: dict) -> Optional[Any]:
        for field in ("FileID", "ImageID", "ID"):
            value = CommandManager._field_value(command, field)
            if value is not None:
                return value
        return None

    @staticmethod
    def _extract_identity(command: dict) -> Optional[str]:
        """Return identity hash from a command payload."""

        return (
            command.get("Identity")
            or command.get("identity")
            or command.get("Destination")
            or command.get("destination")
        )

    @staticmethod
    def _coerce_int_id(value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _attachment_payload(self, attachment: FileAttachment) -> list:
        """Build a list payload compatible with Sideband/MeshChat clients."""

        file_path = Path(attachment.path)
        data = file_path.read_bytes()
        if attachment.media_type:
            return [attachment.name, data, attachment.media_type]
        return [attachment.name, data]

    def _build_attachment_fields(self, attachment: FileAttachment) -> dict:
        """Return LXMF fields carrying attachment content."""

        payload = self._attachment_payload(attachment)
        category = (attachment.category or "").lower()
        if category == "image":
            return {
                LXMF.FIELD_IMAGE: payload,
                LXMF.FIELD_FILE_ATTACHMENTS: [payload],
            }
        return {LXMF.FIELD_FILE_ATTACHMENTS: [payload]}

    def _record_event(self, event_type: str, message: str) -> None:
        """Emit an event log entry when a log sink is configured."""

        if self.event_log is None:
            return
        self.event_log.add_event(event_type, message)
