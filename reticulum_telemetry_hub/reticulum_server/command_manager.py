# Command management for Reticulum Telemetry Hub
from __future__ import annotations

from typing import Any, List, Optional
import json
import RNS
import LXMF

from reticulum_telemetry_hub.api.models import Client, Subscriber, Topic
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI

from .constants import PLUGIN_COMMAND
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

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def handle_commands(self, commands: List[dict], message: LXMF.LXMessage) -> List[LXMF.LXMessage]:
        """Process a list of commands and return generated responses."""
        responses: List[LXMF.LXMessage] = []
        for cmd in commands:
            msg = self.handle_command(cmd, message)
            if msg:
                if isinstance(msg, list):
                    responses.extend(msg)
                else:
                    responses.append(msg)
        return responses

    # ------------------------------------------------------------------
    # individual command processing
    # ------------------------------------------------------------------
    def handle_command(self, command: dict, message: LXMF.LXMessage) -> Optional[LXMF.LXMessage]:
        if PLUGIN_COMMAND in command:
            name = command[PLUGIN_COMMAND]
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
        content_lines = self._format_topic_list(topics)
        content_lines.append(self._topic_subscribe_hint())
        return self._reply(message, "\n".join(content_lines))

    def _handle_create_topic(self, command: dict, message: LXMF.LXMessage) -> LXMF.LXMessage:
        topic = Topic.from_dict(command)
        if not topic.topic_name or not topic.topic_path:
            return self._reply(message, "TopicName and TopicPath are required")
        created = self.api.create_topic(topic)
        payload = json.dumps(created.to_dict(), sort_keys=True)
        return self._reply(message, f"Topic created: {payload}")

    def _handle_retrieve_topic(self, command: dict, message: LXMF.LXMessage) -> LXMF.LXMessage:
        topic_id = self._extract_topic_id(command)
        if not topic_id:
            return self._reply(message, "TopicID is required")
        try:
            topic = self.api.retrieve_topic(topic_id)
        except KeyError as exc:
            return self._reply(message, str(exc))
        payload = json.dumps(topic.to_dict(), sort_keys=True)
        return self._reply(message, payload)

    def _handle_delete_topic(self, command: dict, message: LXMF.LXMessage) -> LXMF.LXMessage:
        topic_id = self._extract_topic_id(command)
        if not topic_id:
            return self._reply(message, "TopicID is required")
        try:
            topic = self.api.delete_topic(topic_id)
        except KeyError as exc:
            return self._reply(message, str(exc))
        payload = json.dumps(topic.to_dict(), sort_keys=True)
        return self._reply(message, f"Topic deleted: {payload}")

    def _handle_patch_topic(self, command: dict, message: LXMF.LXMessage) -> LXMF.LXMessage:
        topic_id = self._extract_topic_id(command)
        if not topic_id:
            return self._reply(message, "TopicID is required")
        updates = {k: v for k, v in command.items() if k != PLUGIN_COMMAND}
        try:
            topic = self.api.patch_topic(topic_id, **updates)
        except KeyError as exc:
            return self._reply(message, str(exc))
        payload = json.dumps(topic.to_dict(), sort_keys=True)
        return self._reply(message, f"Topic updated: {payload}")

    def _handle_subscribe_topic(self, command: dict, message: LXMF.LXMessage) -> LXMF.LXMessage:
        topic_id = self._extract_topic_id(command)
        if not topic_id:
            return self._reply(message, "TopicID is required")
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
        lines = self._format_subscriber_list(subscribers)
        return self._reply(message, "\n".join(lines))

    def _handle_help(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        lines = [
            "Available commands:",
            "  Use the 'Command' field (numeric key 0 / PLUGIN_COMMAND) to choose an action.",
        ]
        for entry in self._command_reference():
            lines.append(f"- {entry['title']}: {entry['description']}")
            lines.append(f"  Example: {entry['example']}")
        telemetry_example = json.dumps(
            {str(TelemetryController.TELEMETRY_REQUEST): "<unix timestamp>"},
            sort_keys=True,
        )
        lines.append(
            "- TelemetryRequest: Request telemetry snapshots using numeric key 1 (TelemetryController.TELEMETRY_REQUEST)."
        )
        lines.append(
            f"  Example: {telemetry_example} (timestamp = earliest UNIX time to include)"
        )
        return self._reply(message, "\n".join(lines))

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
            return self._reply(message, "SubscriberID is required")
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
            return self._reply(message, "SubscriberID is required")
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
            return self._reply(message, "SubscriberID is required")
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

    @staticmethod
    def _format_topic_entry(index: int, topic: Topic) -> str:
        description = f" - {topic.topic_description}" if topic.topic_description else ""
        topic_id = topic.topic_id or "<unassigned>"
        return (
            f"{index}. {topic.topic_name} [{topic.topic_path}] (ID: {topic_id}){description}"
        )

    def _format_topic_list(self, topics: List[Topic]) -> List[str]:
        if not topics:
            return ["No topics registered yet."]
        return [self._format_topic_entry(idx, topic) for idx, topic in enumerate(topics, start=1)]

    def _topic_subscribe_hint(self) -> str:
        example = json.dumps(
            {"Command": self.CMD_SUBSCRIBE_TOPIC, "TopicID": "<TopicID>"},
            sort_keys=True,
        )
        return f"Send the command payload {example} to subscribe to a topic from the list above."

    @staticmethod
    def _format_subscriber_entry(index: int, subscriber: Subscriber) -> str:
        metadata = subscriber.metadata or {}
        metadata_str = json.dumps(metadata, sort_keys=True)
        topic_id = subscriber.topic_id or "<any>"
        subscriber_id = subscriber.subscriber_id or "<pending>"
        return (
            f"{index}. {subscriber.destination} subscribed to {topic_id} "
            f"(SubscriberID: {subscriber_id}) metadata={metadata_str}"
        )

    def _format_subscriber_list(self, subscribers: List[Subscriber]) -> List[str]:
        if not subscribers:
            return ["No subscribers registered yet."]
        return [
            self._format_subscriber_entry(idx, subscriber)
            for idx, subscriber in enumerate(subscribers, start=1)
        ]

    def _command_reference(self) -> List[dict]:
        def example(command: str, **fields: Any) -> str:
            payload = {"Command": command}
            payload.update(fields)
            return json.dumps(payload, sort_keys=True)

        return [
            {
                "title": self.CMD_JOIN,
                "description": "Register your LXMF destination with the hub to receive replies.",
                "example": example(self.CMD_JOIN),
            },
            {
                "title": self.CMD_LEAVE,
                "description": "Remove your destination from the hub's connection list.",
                "example": example(self.CMD_LEAVE),
            },
            {
                "title": self.CMD_LIST_CLIENTS,
                "description": "List LXMF destinations currently joined to the hub.",
                "example": example(self.CMD_LIST_CLIENTS),
            },
            {
                "title": self.CMD_GET_APP_INFO,
                "description": "Return the hub name so you can confirm connectivity.",
                "example": example(self.CMD_GET_APP_INFO),
            },
            {
                "title": self.CMD_LIST_TOPIC,
                "description": "Display every registered topic and its ID.",
                "example": example(self.CMD_LIST_TOPIC),
            },
            {
                "title": self.CMD_CREATE_TOPIC,
                "description": "Create a topic by providing a name and path.",
                "example": example(
                    self.CMD_CREATE_TOPIC,
                    TopicName="Weather",
                    TopicPath="environment/weather",
                ),
            },
            {
                "title": self.CMD_RETRIEVE_TOPIC,
                "description": "Fetch a specific topic by TopicID.",
                "example": example(self.CMD_RETRIEVE_TOPIC, TopicID="<TopicID>"),
            },
            {
                "title": self.CMD_DELETE_TOPIC,
                "description": "Delete a topic (and unsubscribe listeners).",
                "example": example(self.CMD_DELETE_TOPIC, TopicID="<TopicID>"),
            },
            {
                "title": self.CMD_PATCH_TOPIC,
                "description": "Update fields on a topic by TopicID.",
                "example": example(
                    self.CMD_PATCH_TOPIC,
                    TopicID="<TopicID>",
                    TopicDescription="New description",
                ),
            },
            {
                "title": self.CMD_SUBSCRIBE_TOPIC,
                "description": "Subscribe the sending destination to a topic.",
                "example": example(
                    self.CMD_SUBSCRIBE_TOPIC,
                    TopicID="<TopicID>",
                    Metadata={"tag": "field-station"},
                ),
            },
            {
                "title": self.CMD_LIST_SUBSCRIBER,
                "description": "List every subscriber registered with the hub.",
                "example": example(self.CMD_LIST_SUBSCRIBER),
            },
            {
                "title": f"{self.CMD_CREATE_SUBSCRIBER} / {self.CMD_ADD_SUBSCRIBER}",
                "description": "Create a subscriber entry for any destination.",
                "example": example(
                    self.CMD_CREATE_SUBSCRIBER,
                    Destination="<hex destination>",
                    TopicID="<TopicID>",
                ),
            },
            {
                "title": self.CMD_RETRIEVE_SUBSCRIBER,
                "description": "Fetch subscriber metadata by SubscriberID.",
                "example": example(
                    self.CMD_RETRIEVE_SUBSCRIBER,
                    SubscriberID="<SubscriberID>",
                ),
            },
            {
                "title": f"{self.CMD_DELETE_SUBSCRIBER} / {self.CMD_REMOVE_SUBSCRIBER}",
                "description": "Remove a subscriber mapping.",
                "example": example(
                    self.CMD_DELETE_SUBSCRIBER,
                    SubscriberID="<SubscriberID>",
                ),
            },
            {
                "title": self.CMD_PATCH_SUBSCRIBER,
                "description": "Update subscriber metadata by SubscriberID.",
                "example": example(
                    self.CMD_PATCH_SUBSCRIBER,
                    SubscriberID="<SubscriberID>",
                    Metadata={"tag": "updated"},
                ),
            },
        ]

