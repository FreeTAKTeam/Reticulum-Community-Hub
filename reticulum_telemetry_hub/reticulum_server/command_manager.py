# Command management for Reticulum Telemetry Hub
from __future__ import annotations

from typing import Any, Callable, Dict, List
import time
import RNS
import LXMF

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.config.manager import HubConfigurationManager
from reticulum_telemetry_hub.reticulum_server.command_manager_admin import CommandAdminMixin
from reticulum_telemetry_hub.reticulum_server.command_manager_dispatch import CommandDispatchMixin
from reticulum_telemetry_hub.reticulum_server.command_manager_parsing import CommandParsingMixin
from reticulum_telemetry_hub.reticulum_server.command_manager_prompts import CommandPromptMixin
from reticulum_telemetry_hub.reticulum_server.command_manager_reply import CommandReplyMixin
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog

from ..lxmf_telemetry.telemetry_controller import TelemetryController


class CommandManager(
    CommandParsingMixin,
    CommandDispatchMixin,
    CommandPromptMixin,
    CommandAdminMixin,
    CommandReplyMixin,
):
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
    _REPLY_CONTEXT_FIELDS = (LXMF.FIELD_THREAD, LXMF.FIELD_GROUP)
    _MAX_RESULT_TEXT_BYTES = 1024
    _EVENT_TYPE_REPLY = "rch.reply"
    _EVENT_TYPE_COMMAND_RESULT = "rch.command.result"

    def __init__(
        self,
        connections: dict,
        tel_controller: TelemetryController,
        my_lxmf_dest: RNS.Destination,
        api: ReticulumTelemetryHubAPI,
        *,
        config_manager: HubConfigurationManager | None = None,
        event_log: EventLog | None = None,
        destination_removed_callback: Callable[[str], None] | None = None,
    ):
        self.connections = connections
        self.tel_controller = tel_controller
        self.my_lxmf_dest = my_lxmf_dest
        self.api = api
        self.config_manager = config_manager
        self.event_log = event_log
        self._destination_removed_callback = destination_removed_callback
        self.pending_field_requests: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._command_aliases_cache: Dict[str, str] = {}
        self._start_time = time.time()

