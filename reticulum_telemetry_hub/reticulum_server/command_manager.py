# Command management for Reticulum Telemetry Hub
from __future__ import annotations

from typing import List, Optional
import RNS
import LXMF

from .constants import PLUGIN_COMMAND
from ..lxmf_telemetry.telemetry_controller import TelemetryController


class CommandManager:
    """Manage RTH command execution."""

    # Command names based on the API specification
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

    def __init__(self, connections: dict, tel_controller: TelemetryController, my_lxmf_dest: RNS.Destination):
        self.connections = connections
        self.tel_controller = tel_controller
        self.my_lxmf_dest = my_lxmf_dest

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
            if name == self.CMD_JOIN:
                return self._handle_join(message)
            if name == self.CMD_LEAVE:
                return self._handle_leave(message)
            if name == self.CMD_LIST_CLIENTS:
                return self._handle_list_clients(message)
            if name == self.CMD_GET_APP_INFO:
                return self._handle_get_app_info(message)
            # The remaining commands are currently placeholders
            # and can be implemented as needed.
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
        RNS.log(f"Connection removed: {message.source}")
        return LXMF.LXMessage(
            dest,
            self.my_lxmf_dest,
            "Connection removed",
            desired_method=LXMF.LXMessage.DIRECT,
        )

    def _handle_list_clients(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        dest = self._create_dest(message.source.identity)
        client_hashes = [RNS.prettyhexrep(h) for h in self.connections]
        return LXMF.LXMessage(
            dest,
            self.my_lxmf_dest,
            ",".join(client_hashes) or "",
            desired_method=LXMF.LXMessage.DIRECT,
        )

    def _handle_get_app_info(self, message: LXMF.LXMessage) -> LXMF.LXMessage:
        dest = self._create_dest(message.source.identity)
        info = "ReticulumTelemetryHub"
        return LXMF.LXMessage(dest, self.my_lxmf_dest, info, desired_method=LXMF.LXMessage.DIRECT)

