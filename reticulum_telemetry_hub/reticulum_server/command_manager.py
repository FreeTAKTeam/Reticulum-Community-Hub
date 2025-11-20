# Command management for Reticulum Telemetry Hub
from __future__ import annotations

from typing import Any, Dict, List, Optional
import json
import re
import RNS
import LXMF

from reticulum_telemetry_hub.api.models import Client, Subscriber, Topic
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI

from .constants import PLUGIN_COMMAND
from .command_text import (
    build_help_text,
    format_subscriber_list,
    format_topic_list,
    topic_subscribe_hint,
)
from ..lxmf_telemetry.telemetry_controller import TelemetryController


class CommandManager:
    """Manage RTH command execution."""

    # Command names based on the API specification
    CMD_HELP = "Help"
    CMD_JOIN = "join"
    CMD_LEAVE = "leave"
    CMD_LIST_CLIENTS = "ListClients"
    CMD_RETRIEVE_TOPIC = "RetreiveTopic"
    CMD_CREATE_TOPIC = "CreateTopic"
    CMD_DELETE_TOPIC = "DeleteTopic"
    CMD_LIST_TOPIC = "ListTopic"
    CMD_PATCH_TOPIC = "PatchTopic"
    CMD_SUBSCRIBE_TOPIC = "SubscribeTopic"
    CMD_RETRIEVE_SUBSCRIBER = "RetreiveSubscriber"
    CMD_ADD_SUBSCRIBER = "AddSubscriber"
    CMD_CREATE_SUBSCRIBER = "CreateSubscriber"
    CMD_DELETE_SUBSCRIBER = "DeleteSubscriber"
    CMD_LIST_SUBSCRIBER = "ListSubscriber"
    CMD_PATCH_SUBSCRIBER = "PatchSubscriber"
    CMD_REMOVE_SUBSCRIBER = "RemoveSubscriber"
    CMD_GET_APP_INFO = "getAppInfo"

    def __init__(
        self,
        connections: dict,
        tel_controller: TelemetryController,
        my_lxmf_dest: RNS.Destination,
        api: ReticulumTelemetryHubAPI,
    ):
        self.connections = connections
        self.tel_controller = tel_controller
        self.my_lxmf_dest = my_lxmf_dest
        self.api = api
        self.pending_field_requests: Dict[str, Dict[str, Dict[str, Any]]] = {}

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
            msg = self.handle_command(normalized, message)
            if msg:
                if isinstance(msg, list):
                    responses.extend(msg)
                else:
                    responses.append(msg)
        return responses

    def _normalize_command(
        self, raw_command: Any, message: LXMF.LXMessage
    ) -> tuple[Optional[dict], Optional[LXMF.LXMessage]]:
        """Normalize incoming command payloads, including JSON-wrapped strings."""

        if isinstance(raw_command, str):
            try:
                parsed = json.loads(raw_command)
            except json.JSONDecodeError:
                error = self._reply(
                    message, f"Command payload is not valid JSON: {raw_command!r}"
                )
                return None, error
            if not isinstance(parsed, dict):
                return None, self._reply(
                    message, "Parsed command must be a JSON object"
                )
            return parsed, None
        if isinstance(raw_command, dict):
            if len(raw_command) == 1:
                key = next(iter(raw_command))
                if isinstance(key, (int, str)) and str(key).isdigit():
                    payload = raw_command[key]
                    if isinstance(payload, dict):
                        return payload, None
                    if isinstance(payload, str) and payload.lstrip().startswith("{"):
                        try:
                            parsed_payload = json.loads(payload)
                        except json.JSONDecodeError:
                            error = self._reply(
                                message,
                                f"Command payload is not valid JSON: {payload!r}",
                            )
                            return None, error
                        if not isinstance(parsed_payload, dict):
                            return None, self._reply(
                                message, "Parsed command must be a JSON object"
                            )
                        return parsed_payload, None
            return raw_command, None
        return None, self._reply(
            message, f"Unsupported command payload type: {type(raw_command).__name__}"
        )

    # ------------------------------------------------------------------
    # individual command processing
    # ------------------------------------------------------------------
    def handle_command(
        self, command: dict, message: LXMF.LXMessage
    ) -> Optional[LXMF.LXMessage]:
        command = self._merge_pending_fields(command, message)
        name = command.get(PLUGIN_COMMAND) or command.get("Command")
        if name is not None:
            if name == self.CMD_HELP:
                return self._handle_help(message)
            if name == self.CMD_JOIN:
                return self._handle_join(message)
            if name == self.CMD_LEAVE:
                return self._handle_leave(message)
            if name == self.CMD_LIST_CLIENTS:
                return self._handle_list_clients(message)
            if name == self.CMD_GET_APP_INFO:
                return self._handle_get_app_info(message)
            if name == self.CMD_LIST_TOPIC:
                return self._handle_list_topics(message)
            if name == self.CMD_CREATE_TOPIC:
                return self._handle_create_topic(command, message)
            if name == self.CMD_RETRIEVE_TOPIC:
                return self._handle_retrieve_topic(command, message)
            if name == self.CMD_DELETE_TOPIC:
                return self._handle_delete_topic(command, message)
            if name == self.CMD_PATCH_TOPIC:
                return self._handle_patch_topic(command, message)
            if name == self.CMD_SUBSCRIBE_TOPIC:
                return self._handle_subscribe_topic(command, message)
            if name == self.CMD_LIST_SUBSCRIBER:
                return self._handle_list_subscribers(message)
            if name == self.CMD_CREATE_SUBSCRIBER:
                return self._handle_create_subscriber(command, message)
            if name == self.CMD_ADD_SUBSCRIBER:
                return self._handle_create_subscriber(command, message)
            if name == self.CMD_RETRIEVE_SUBSCRIBER:
                return self._handle_retrieve_subscriber(command, message)
            if name in (self.CMD_DELETE_SUBSCRIBER, self.CMD_REMOVE_SUBSCRIBER):
                return self._handle_delete_subscriber(command, message)
            if name == self.CMD_PATCH_SUBSCRIBER:
                return self._handle_patch_subscriber(command, message)
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
        info = "ReticulumTelemetryHub"
        return self._reply(message, info)

    def _handle_list_topics(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        topics = self.api.list_topics()
        content_lines = format_topic_list(topics)
        content_lines.append(topic_subscribe_hint(self.CMD_SUBSCRIBE_TOPIC))
        return self._reply(message, "\n".join(content_lines))

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
        return self._reply(message, f"Subscribed: {payload}")

    def _handle_list_subscribers(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        subscribers = self.api.list_subscribers()
        lines = format_subscriber_list(subscribers)
        return self._reply(message, "\n".join(lines))

    def _handle_help(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        return self._reply(message, build_help_text(self))

    def _handle_unknown_command(
        self, name: str, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        help_text = build_help_text(self)
        payload = f"Unknown command '{name}'.\n{help_text}"
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
        subscriber = Subscriber.from_dict(command)
        if not subscriber.destination:
            subscriber.destination = self._identity_hex(message.source.identity)
        created = self.api.create_subscriber(subscriber)
        payload = json.dumps(created.to_dict(), sort_keys=True)
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
        return self._reply(message, f"Subscriber updated: {payload}")

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

    def _reply(self, message: LXMF.LXMessage, content: str) -> LXMF.LXMessage:
        dest = self._create_dest(message.source.identity)
        return LXMF.LXMessage(
            dest,
            self.my_lxmf_dest,
            content,
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
