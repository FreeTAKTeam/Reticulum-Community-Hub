"""LXMF command dispatch handlers."""

from __future__ import annotations

from functools import partial
from typing import Optional
import json

import LXMF
import RNS

from reticulum_telemetry_hub.api.models import Topic
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import TelemetryController
from reticulum_telemetry_hub.reticulum_server.command_text import build_examples_text
from reticulum_telemetry_hub.reticulum_server.command_text import build_help_text
from reticulum_telemetry_hub.reticulum_server.command_text import format_attachment_list
from reticulum_telemetry_hub.reticulum_server.command_text import format_subscriber_list
from reticulum_telemetry_hub.reticulum_server.command_text import format_topic_list
from reticulum_telemetry_hub.reticulum_server.command_text import topic_subscribe_hint
from reticulum_telemetry_hub.reticulum_server.constants import PLUGIN_COMMAND


class CommandDispatchMixin:
    """LXMF command dispatch handlers."""

    def handle_command(
        self, command: dict, message: LXMF.LXMessage
    ) -> Optional[LXMF.LXMessage]:
        command = self._merge_pending_fields(command, message)
        name = command.get(PLUGIN_COMMAND) or command.get("Command")
        name = self._normalize_command_name(name)
        telemetry_request_present = self._has_numeric_key(
            command, TelemetryController.TELEMETRY_REQUEST
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
                return self._finalize_command_response(
                    handler(), command_name=name, status="ok"
                )
            if telemetry_request_present and is_telemetry_command:
                telemetry_reply = self.tel_controller.handle_command(
                    command, message, self.my_lxmf_dest
                )
                return self._finalize_command_response(
                    telemetry_reply, command_name=name, status="ok"
                )
            return self._finalize_command_response(
                self._handle_unknown_command(name, message),
                command_name=name,
                status="unknown_command",
            )
        # Delegate to telemetry controller for telemetry related commands
        telemetry_reply = self.tel_controller.handle_command(
            command, message, self.my_lxmf_dest
        )
        return self._finalize_command_response(
            telemetry_reply, command_name="TelemetryRequest", status="ok"
        )

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
        identity_hex = self._identity_hex(dest.identity)
        self.api.join(identity_hex)
        RNS.log(f"Connection added: {message.source}")
        display_name, label = self._resolve_identity_label(identity_hex)
        self._record_event(
            "client_join",
            f"Client joined: {label}",
            metadata={"identity": identity_hex, "display_name": display_name},
        )
        return self._reply(message, "Connection established")

    def _handle_leave(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        dest = self._create_dest(message.source.identity)
        self.connections.pop(dest.identity.hash, None)
        identity_hex = self._identity_hex(dest.identity)
        callback = self._destination_removed_callback
        if callback is not None:
            callback(identity_hex)
        self.api.leave(identity_hex)
        RNS.log(f"Connection removed: {message.source}")
        display_name, label = self._resolve_identity_label(identity_hex)
        self._record_event(
            "client_leave",
            f"Client left: {label}",
            metadata={"identity": identity_hex, "display_name": display_name},
        )
        return self._reply(message, "Connection removed")

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
            "reticulum_destination": getattr(app_info, "reticulum_destination", None),
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
        return self._reply(
            message,
            build_help_text(self),
            fields={LXMF.FIELD_RENDERER: self._markdown_renderer_value()},
        )

    def _handle_examples(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        return self._reply(
            message,
            build_examples_text(self),
            fields={LXMF.FIELD_RENDERER: self._markdown_renderer_value()},
        )

    def _handle_unknown_command(
        self, name: str, message: LXMF.LXMessage
    ) -> LXMF.LXMessage:
        sender = self._identity_hex(message.source.identity)
        RNS.log(f"Unknown command '{name}' from {sender}", getattr(RNS, "LOG_ERROR", 1))
        help_text = build_help_text(self)
        payload = f"Unknown command\n\n{help_text}"
        return self._reply(message, payload)

