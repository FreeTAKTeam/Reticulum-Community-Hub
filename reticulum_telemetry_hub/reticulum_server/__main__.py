"""
Reticulum Telemetry Hub (RTH)
================================

This module provides the CLI entry point that launches the Reticulum Telemetry
Hub process. The hub brings together several components:

* ``TelemetryController`` persists telemetry streams and handles inbound command
  requests arriving over LXMF.
* ``CommandManager`` implements the Reticulum plugin command vocabulary
  (join/leave/telemetry etc.) and publishes the appropriate LXMF responses.
* ``AnnounceHandler`` subscribes to Reticulum announcements so the hub can keep
  a lightweight directory of peers.
* ``ReticulumTelemetryHub`` wires the Reticulum stack, LXMF router and local
  identity together, runs headlessly, and relays messages between connected
  peers.

Running the script directly allows operators to:

* Generate or load a persistent Reticulum identity stored under ``STORAGE_PATH``.
* Announce the LXMF delivery destination on a fixed interval (headless only).
* Inspect/log inbound messages and fan them out to connected peers.

Use ``python -m reticulum_telemetry_hub.reticulum_server`` to start the hub.
Command line arguments let you override the storage path, choose a display name,
or run in headless mode for unattended deployments.
"""

import argparse
import asyncio
import base64
import binascii
import json
import mimetypes
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from typing import Callable
from typing import cast

import LXMF
import RNS

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.config.manager import HubConfigurationManager
from reticulum_telemetry_hub.config.manager import _expand_user_path
from reticulum_telemetry_hub.embedded_lxmd import EmbeddedLxmd
from reticulum_telemetry_hub.lxmf_daemon.LXMF import display_name_from_app_data
from reticulum_telemetry_hub.atak_cot.tak_connector import TakConnector
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.lxmf_telemetry.sampler import TelemetrySampler
from reticulum_telemetry_hub.lxmf_telemetry.telemeter_manager import TelemeterManager
from reticulum_telemetry_hub.reticulum_server.services import (
    SERVICE_FACTORIES,
    HubService,
)
from reticulum_telemetry_hub.reticulum_server.constants import PLUGIN_COMMAND
from reticulum_telemetry_hub.reticulum_server.outbound_queue import (
    OutboundMessageQueue,
)
from .command_manager import CommandManager
from reticulum_telemetry_hub.config.constants import (
    DEFAULT_ANNOUNCE_INTERVAL,
    DEFAULT_HUB_TELEMETRY_INTERVAL,
    DEFAULT_LOG_LEVEL_NAME,
    DEFAULT_SERVICE_TELEMETRY_INTERVAL,
    DEFAULT_STORAGE_PATH,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Constants
STORAGE_PATH = DEFAULT_STORAGE_PATH  # Path to store temporary files
APP_NAME = LXMF.APP_NAME + ".delivery"  # Application name for LXMF
DEFAULT_LOG_LEVEL = getattr(RNS, "LOG_DEBUG", getattr(RNS, "LOG_INFO", 3))
LOG_LEVELS = {
    "error": getattr(RNS, "LOG_ERROR", 1),
    "warning": getattr(RNS, "LOG_WARNING", 2),
    "info": getattr(RNS, "LOG_INFO", 3),
    "debug": getattr(RNS, "LOG_DEBUG", DEFAULT_LOG_LEVEL),
}
TOPIC_REGISTRY_TTL_SECONDS = 5
ESCAPED_COMMAND_PREFIX = "\\\\\\"
DEFAULT_OUTBOUND_QUEUE_SIZE = 64
DEFAULT_OUTBOUND_WORKERS = 2
DEFAULT_OUTBOUND_SEND_TIMEOUT = 5.0
DEFAULT_OUTBOUND_BACKOFF = 0.5
DEFAULT_OUTBOUND_MAX_ATTEMPTS = 3


def _resolve_interval(value: int | None, fallback: int) -> int:
    """Return the positive interval derived from CLI/config values."""

    if value is not None:
        return max(0, int(value))

    return max(0, int(fallback))


def _dispatch_coroutine(coroutine) -> None:
    """Execute ``coroutine`` on the active event loop or create one if needed.

    Args:
        coroutine: Awaitable object to schedule or run synchronously.
    """

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coroutine)
        return

    loop.create_task(coroutine)


class AnnounceHandler:
    """Track simple metadata about peers announcing on the Reticulum bus."""

    def __init__(self, identities: dict[str, str]):
        self.aspect_filter = APP_NAME
        self.identities = identities

    def received_announce(self, destination_hash, announced_identity, app_data):
        # RNS.log("\t+--- LXMF Announcement -----------------------------------------")
        # RNS.log(f"\t| Source hash            : {RNS.prettyhexrep(destination_hash)}")
        # RNS.log(f"\t| Announced identity     : {announced_identity}")
        # RNS.log(f"\t| App data               : {app_data}")
        # RNS.log("\t+---------------------------------------------------------------")
        label = self._decode_app_data(app_data)
        hash_key = (
            destination_hash.hex()
            if isinstance(destination_hash, (bytes, bytearray))
            else str(destination_hash)
        )
        self.identities[hash_key] = label

    @staticmethod
    def _decode_app_data(app_data) -> str:
        if app_data is None:
            return "unknown"

        if isinstance(app_data, bytes):
            try:
                display_name = display_name_from_app_data(app_data)
            except Exception:
                display_name = None

            if display_name is not None:
                return display_name.strip()

            try:
                return app_data.decode("utf-8").strip()
            except UnicodeDecodeError:
                return app_data.hex()

        return str(app_data)


class ReticulumTelemetryHub:
    """Runtime container that glues Reticulum, LXMF and telemetry services.

    The hub owns the Reticulum stack, LXMF router, telemetry persistence layer
    and connection bookkeeping. It runs headlessly and periodically announces
    its delivery identity.
    """

    lxm_router: LXMF.LXMRouter
    connections: dict[bytes, RNS.Destination]
    identities: dict[str, str]
    my_lxmf_dest: RNS.Destination | None
    ret: RNS.Reticulum
    storage_path: Path
    identity_path: Path
    tel_controller: TelemetryController
    config_manager: HubConfigurationManager | None
    embedded_lxmd: EmbeddedLxmd | None
    _shared_lxm_router: LXMF.LXMRouter | None = None
    telemetry_sampler: TelemetrySampler | None
    telemeter_manager: TelemeterManager | None
    tak_connector: TakConnector | None
    _active_services: dict[str, HubService]

    TELEMETRY_PLACEHOLDERS = {"telemetry data", "telemetry update"}

    @staticmethod
    def _get_router_callable(
        router: LXMF.LXMRouter, attribute: str
    ) -> Callable[..., Any]:
        """
        Return a callable attribute from the LXMF router.

        Args:
            router (LXMF.LXMRouter): Router exposing LXMF hooks.
            attribute (str): Name of the required callable attribute.

        Returns:
            Callable[..., Any]: Router hook matching ``attribute``.

        Raises:
            AttributeError: When the attribute is missing or not callable.
        """

        hook = getattr(router, attribute, None)
        if not callable(hook):
            msg = f"LXMF router is missing required callable '{attribute}'"
            raise AttributeError(msg)
        return cast(Callable[..., Any], hook)

    def _invoke_router_hook(self, attribute: str, *args: Any, **kwargs: Any) -> Any:
        """
        Invoke a callable hook on the LXMF router.

        Args:
            attribute (str): Name of the callable attribute to invoke.
            *args: Positional arguments forwarded to the callable.
            **kwargs: Keyword arguments forwarded to the callable.

        Returns:
            Any: Response from the invoked callable.
        """

        router_callable = self._get_router_callable(self.lxm_router, attribute)
        return router_callable(*args, **kwargs)

    def __init__(
        self,
        display_name: str,
        storage_path: Path,
        identity_path: Path,
        *,
        embedded: bool = False,
        announce_interval: int = DEFAULT_ANNOUNCE_INTERVAL,
        loglevel: int = DEFAULT_LOG_LEVEL,
        hub_telemetry_interval: float | None = DEFAULT_HUB_TELEMETRY_INTERVAL,
        service_telemetry_interval: float | None = DEFAULT_SERVICE_TELEMETRY_INTERVAL,
        config_manager: HubConfigurationManager | None = None,
        config_path: Path | None = None,
        outbound_queue_size: int = DEFAULT_OUTBOUND_QUEUE_SIZE,
        outbound_workers: int = DEFAULT_OUTBOUND_WORKERS,
        outbound_send_timeout: float = DEFAULT_OUTBOUND_SEND_TIMEOUT,
        outbound_backoff: float = DEFAULT_OUTBOUND_BACKOFF,
        outbound_max_attempts: int = DEFAULT_OUTBOUND_MAX_ATTEMPTS,
    ):
        """Initialize the telemetry hub runtime container.

        Args:
            display_name (str): Label announced with the LXMF destination.
            storage_path (Path): Directory containing hub storage files.
            identity_path (Path): Path to the persisted LXMF identity.
            embedded (bool): Whether to run the LXMF router threads in-process.
            announce_interval (int): Seconds between LXMF announces.
            loglevel (int): RNS log level to emit.
            hub_telemetry_interval (float | None): Interval for local telemetry sampling.
            service_telemetry_interval (float | None): Interval for remote service sampling.
            config_manager (HubConfigurationManager | None): Optional preloaded configuration manager.
            config_path (Path | None): Path to ``config.ini`` when creating a manager internally.
            outbound_queue_size (int): Maximum queued outbound LXMF payloads before applying backpressure.
            outbound_workers (int): Number of outbound worker threads to spin up.
            outbound_send_timeout (float): Seconds to wait before timing out a send attempt.
            outbound_backoff (float): Base number of seconds to wait between retry attempts.
            outbound_max_attempts (int): Number of attempts before an outbound message is dropped.
        """
        # Normalize paths early so downstream helpers can rely on Path objects.
        self.storage_path = Path(storage_path)
        self.identity_path = Path(identity_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.identity_path.parent.mkdir(parents=True, exist_ok=True)
        self.announce_interval = announce_interval
        self.hub_telemetry_interval = hub_telemetry_interval
        self.service_telemetry_interval = service_telemetry_interval
        self.loglevel = loglevel
        self.outbound_queue_size = outbound_queue_size
        self.outbound_workers = outbound_workers
        self.outbound_send_timeout = outbound_send_timeout
        self.outbound_backoff = outbound_backoff
        self.outbound_max_attempts = outbound_max_attempts

        # Reuse an existing Reticulum instance when running in-process tests
        # to avoid triggering the single-instance guard in the RNS library.
        existing_reticulum = RNS.Reticulum.get_instance()
        if existing_reticulum is not None:
            self.ret = existing_reticulum
            RNS.loglevel = self.loglevel
        else:
            self.ret = RNS.Reticulum(loglevel=self.loglevel)
            RNS.loglevel = self.loglevel

        telemetry_db_path = self.storage_path / "telemetry.db"
        self.tel_controller = TelemetryController(db_path=telemetry_db_path)
        self.config_manager: HubConfigurationManager | None = config_manager
        self.embedded_lxmd: EmbeddedLxmd | None = None
        self.telemetry_sampler: TelemetrySampler | None = None
        self.telemeter_manager: TelemeterManager | None = None
        self._shutdown = False
        self.connections: dict[bytes, RNS.Destination] = {}
        self._daemon_started = False
        self._active_services = {}
        self._outbound_queue: OutboundMessageQueue | None = None

        identity = self.load_or_generate_identity(self.identity_path)

        if ReticulumTelemetryHub._shared_lxm_router is None:
            ReticulumTelemetryHub._shared_lxm_router = LXMF.LXMRouter(
                storagepath=str(self.storage_path)
            )
        shared_router = ReticulumTelemetryHub._shared_lxm_router
        if shared_router is None:
            msg = "Shared LXMF router failed to initialize"
            raise RuntimeError(msg)

        self.lxm_router = cast(LXMF.LXMRouter, shared_router)

        self.my_lxmf_dest = self._invoke_router_hook(
            "register_delivery_identity", identity, display_name=display_name
        )

        self.identities: dict[str, str] = {}

        self._invoke_router_hook("set_message_storage_limit", megabytes=5)
        self._invoke_router_hook("register_delivery_callback", self.delivery_callback)
        RNS.Transport.register_announce_handler(AnnounceHandler(self.identities))

        if self.config_manager is None:
            self.config_manager = HubConfigurationManager(
                storage_path=self.storage_path, config_path=config_path
            )

        self.embedded_lxmd = None
        if embedded:
            self.embedded_lxmd = EmbeddedLxmd(
                router=self.lxm_router,
                destination=self.my_lxmf_dest,
                config_manager=self.config_manager,
                telemetry_controller=self.tel_controller,
            )
            self.embedded_lxmd.start()

        self.api = ReticulumTelemetryHubAPI(config_manager=self.config_manager)
        self.telemeter_manager = TelemeterManager(config_manager=self.config_manager)
        tak_config_manager = self.config_manager
        self.tak_connector = TakConnector(
            config=tak_config_manager.tak_config if tak_config_manager else None,
            telemeter_manager=self.telemeter_manager,
            telemetry_controller=self.tel_controller,
            identity_lookup=self._lookup_identity_label,
        )
        self.tel_controller.register_listener(self._handle_telemetry_for_tak)
        self.telemetry_sampler = TelemetrySampler(
            self.tel_controller,
            self.lxm_router,
            self.my_lxmf_dest,
            connections=self.connections,
            hub_interval=hub_telemetry_interval,
            service_interval=service_telemetry_interval,
            telemeter_manager=self.telemeter_manager,
        )

        self.command_manager = CommandManager(
            self.connections,
            self.tel_controller,
            self.my_lxmf_dest,
            self.api,
        )
        self.topic_subscribers: dict[str, set[str]] = {}
        self._topic_registry_last_refresh: float = 0.0
        self._refresh_topic_registry()

    def command_handler(self, commands: list, message: LXMF.LXMessage) -> list[LXMF.LXMessage]:
        """Handles commands received from the client and returns responses.

        Args:
            commands (list): List of commands received from the client
            message (LXMF.LXMessage): LXMF message object

        Returns:
            list[LXMF.LXMessage]: Responses generated for the commands.
        """
        responses = self.command_manager.handle_commands(commands, message)
        if self._commands_affect_subscribers(commands):
            self._refresh_topic_registry()
        return responses

    def _parse_escape_prefixed_commands(
        self, message: LXMF.LXMessage
    ) -> tuple[list[dict] | None, bool, str | None]:
        """Parse a command list from an escape-prefixed message body.

        The `Commands` LXMF field may be unavailable in some clients, so the
        hub accepts a leading ``\\\\\\`` prefix in the message content and
        treats the remainder as a command payload.

        Args:
            message (LXMF.LXMessage): LXMF message object.

        Returns:
            tuple[list[dict] | None, bool, str | None]: Normalized command list,
                an empty list when the payload is malformed, or ``None`` when no
                escape prefix is present, paired with a boolean indicating whether
                the escape prefix was detected and an optional error message.
        """

        if LXMF.FIELD_COMMANDS in message.fields:
            return None, False, None

        if message.content is None or message.content == b"":
            return None, False, None

        try:
            content_text = message.content_as_string()
        except Exception as exc:
            RNS.log(
                f"Unable to decode message content for escape-prefixed commands: {exc}",
                RNS.LOG_WARNING,
            )
            return [], False, "Unable to decode message content."

        if not content_text.startswith(ESCAPED_COMMAND_PREFIX):
            return None, False, None

        # Reason: the prefix signals that the body should be treated as a command
        # payload even when the `Commands` field is unavailable.
        body = content_text[len(ESCAPED_COMMAND_PREFIX) :].strip()
        if not body:
            RNS.log(
                "Ignored escape-prefixed command payload with no body.",
                RNS.LOG_WARNING,
            )
            return [], True, "Command payload is empty."

        if body.startswith("\\[") or body.startswith("\\{"):
            body = body[1:]

        parsed_payload = None
        if body.startswith("{") or body.startswith("["):
            try:
                parsed_payload = json.loads(body)
            except json.JSONDecodeError as exc:
                RNS.log(
                    f"Failed to parse escape-prefixed JSON payload: {exc}",
                    RNS.LOG_WARNING,
                )
                return [], True, "Command payload is not valid JSON."

        if parsed_payload is None:
            return [{"Command": body}], True, None

        if isinstance(parsed_payload, dict):
            return [parsed_payload], True, None

        if isinstance(parsed_payload, list):
            if not parsed_payload:
                RNS.log(
                    "Ignored escape-prefixed command list with no entries.",
                    RNS.LOG_WARNING,
                )
                return [], True, "Command payload list is empty."

            if not all(isinstance(item, dict) for item in parsed_payload):
                RNS.log(
                    "Escape-prefixed JSON must be an object or list of objects.",
                    RNS.LOG_WARNING,
                )
                return [], True, "Command payload must be a JSON object or list of objects."

            return parsed_payload, True, None

        RNS.log(
            "Escape-prefixed payload must decode to a JSON object or list of objects.",
            RNS.LOG_WARNING,
        )
        return [], True, "Command payload must be a JSON object or list of objects."

    def delivery_callback(self, message: LXMF.LXMessage):
        """Callback function to handle incoming messages.

        Args:
            message (LXMF.LXMessage): LXMF message object
        """
        try:
            # Format the timestamp of the message
            time_string = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(message.timestamp)
            )
            signature_string = "Signature is invalid, reason undetermined"

            # Determine the signature validation status
            if message.signature_validated:
                signature_string = "Validated"
            elif message.unverified_reason == LXMF.LXMessage.SIGNATURE_INVALID:
                signature_string = "Invalid signature"
                return
            elif message.unverified_reason == LXMF.LXMessage.SOURCE_UNKNOWN:
                signature_string = "Cannot verify, source is unknown"
                return

            # Log the delivery details
            self.log_delivery_details(message, time_string, signature_string)

            command_payload_present = False
            sender_joined = False
            attachment_replies: list[LXMF.LXMessage] = []
            # Handle the commands
            command_replies: list[LXMF.LXMessage] = []
            if message.signature_validated:
                attachment_replies = self._persist_attachments_from_fields(message)
                if LXMF.FIELD_COMMANDS in message.fields:
                    command_payload_present = True
                    command_replies = (
                        self.command_handler(message.fields[LXMF.FIELD_COMMANDS], message)
                        or []
                    )
                else:
                    escape_commands, escape_detected, escape_error = (
                        self._parse_escape_prefixed_commands(message)
                    )
                    if escape_detected:
                        command_payload_present = True
                    if escape_error:
                        error_reply = self._reply_message(
                            message, f"Command error: {escape_error}"
                        )
                        if error_reply is not None:
                            attachment_replies.append(error_reply)
                    if escape_commands:
                        command_replies = self.command_handler(escape_commands, message) or []

            responses = attachment_replies + command_replies
            text_only_replies: list[LXMF.LXMessage] = []
            for response in command_replies:
                response_fields = getattr(response, "fields", None) or {}
                if isinstance(response_fields, dict) and any(
                    key in response_fields
                    for key in (LXMF.FIELD_FILE_ATTACHMENTS, LXMF.FIELD_IMAGE)
                ):
                    text_only = self._reply_message(
                        message, response.content_as_string(), fields={}
                    )
                    if text_only is not None:
                        text_only_replies.append(text_only)

            responses.extend(text_only_replies)
            for response in responses:
                try:
                    self.lxm_router.handle_outbound(response)
                except Exception as exc:  # pragma: no cover - defensive log
                    has_attachment = False
                    response_fields = getattr(response, "fields", None) or {}
                    if isinstance(response_fields, dict):
                        has_attachment = any(
                            key in response_fields
                            for key in (LXMF.FIELD_FILE_ATTACHMENTS, LXMF.FIELD_IMAGE)
                        )
                    RNS.log(
                        f"Failed to send response: {exc}",
                        getattr(RNS, "LOG_WARNING", 2),
                    )
                    if has_attachment:
                        fallback = self._reply_message(
                            message,
                            "Failed to send attachment response; the file may be too large.",
                        )
                        if fallback is None:
                            continue
                        try:
                            self.lxm_router.handle_outbound(fallback)
                        except Exception as retry_exc:  # pragma: no cover - defensive log
                            RNS.log(
                                f"Failed to send fallback response: {retry_exc}",
                                getattr(RNS, "LOG_WARNING", 2),
                            )
            if responses:
                command_payload_present = True

            sender_joined = self._sender_is_joined(message)
            telemetry_handled = self.tel_controller.handle_message(message)
            if telemetry_handled:
                RNS.log("Telemetry data saved")

            if not sender_joined:
                self._reply_with_app_info(message)

            # Skip if the message content is empty
            if message.content is None or message.content == b"":
                return

            if self._is_telemetry_only(message, telemetry_handled):
                return

            if command_payload_present:
                return

            source = message.get_source()
            source_hash = getattr(source, "hash", None) or message.source_hash
            source_label = self._lookup_identity_label(source_hash)
            topic_id = self._extract_target_topic(message.fields)
            content_text = self._message_text(message)

            tak_connector = getattr(self, "tak_connector", None)
            if tak_connector is not None and content_text:
                try:
                    message_time = datetime.fromtimestamp(
                        getattr(message, "timestamp", time.time()),
                        tz=timezone.utc,
                    ).replace(tzinfo=None)
                except Exception:
                    message_time = _utcnow()
                try:
                    asyncio.run(
                        tak_connector.send_chat_event(
                            content=content_text,
                            sender_label=source_label,
                            topic_id=topic_id,
                            source_hash=source_hash,
                            timestamp=message_time,
                        )
                    )
                except Exception as exc:  # pragma: no cover - defensive log
                    RNS.log(
                        f"Failed to send CoT chat event: {exc}",
                        getattr(RNS, "LOG_WARNING", 2),
                    )

            # Broadcast the message to all connected clients
            msg = f"{source_label} > {content_text}"
            source_hex = self._message_source_hex(message)
            exclude = {source_hex} if source_hex else None
            self.send_message(msg, topic=topic_id, exclude=exclude)
        except Exception as e:
            RNS.log(f"Error: {e}")

    def send_message(
        self,
        message: str,
        *,
        topic: str | None = None,
        exclude: set[str] | None = None,
    ):
        """Sends a message to connected clients.

        Args:
            message (str): Text to broadcast.
            topic (str | None): Topic filter limiting recipients.
            exclude (set[str] | None): Optional set of lowercase destination
                hashes that should not receive the broadcast.
        """

        queue = self._ensure_outbound_queue()
        if queue is None:
            RNS.log(
                "Outbound queue unavailable; dropping message broadcast request.",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return

        available = (
            list(self.connections.values())
            if hasattr(self.connections, "values")
            else list(self.connections)
        )
        excluded = {value.lower() for value in exclude if value} if exclude else set()
        if topic:
            subscriber_hex = self._subscribers_for_topic(topic)
            available = [
                connection
                for connection in available
                if self._connection_hex(connection) in subscriber_hex
            ]
        for connection in available:
            connection_hex = self._connection_hex(connection)
            if excluded and connection_hex and connection_hex in excluded:
                continue
            identity = getattr(connection, "identity", None)
            destination_hash = getattr(identity, "hash", None)
            enqueued = queue.queue_message(
                connection,
                message,
                (
                    destination_hash
                    if isinstance(destination_hash, (bytes, bytearray))
                    else None
                ),
                connection_hex,
            )
            if not enqueued:
                RNS.log(
                    (
                        "Failed to enqueue outbound LXMF message for"
                        f" {connection_hex or 'unknown destination'}"
                    ),
                    getattr(RNS, "LOG_WARNING", 2),
                )

    def _ensure_outbound_queue(self) -> OutboundMessageQueue | None:
        """
        Initialize and start the outbound worker queue.

        Returns:
            OutboundMessageQueue | None: Active outbound queue instance when available.
        """

        if self.my_lxmf_dest is None:
            return None

        if not hasattr(self, "_outbound_queue"):
            self._outbound_queue = None

        if self._outbound_queue is None:
            self._outbound_queue = OutboundMessageQueue(
                self.lxm_router,
                self.my_lxmf_dest,
                queue_size=getattr(
                    self, "outbound_queue_size", DEFAULT_OUTBOUND_QUEUE_SIZE
                )
                or DEFAULT_OUTBOUND_QUEUE_SIZE,
                worker_count=getattr(self, "outbound_workers", DEFAULT_OUTBOUND_WORKERS)
                or DEFAULT_OUTBOUND_WORKERS,
                send_timeout=getattr(
                    self, "outbound_send_timeout", DEFAULT_OUTBOUND_SEND_TIMEOUT
                )
                or DEFAULT_OUTBOUND_SEND_TIMEOUT,
                backoff_seconds=getattr(
                    self, "outbound_backoff", DEFAULT_OUTBOUND_BACKOFF
                )
                or DEFAULT_OUTBOUND_BACKOFF,
                max_attempts=getattr(
                    self, "outbound_max_attempts", DEFAULT_OUTBOUND_MAX_ATTEMPTS
                )
                or DEFAULT_OUTBOUND_MAX_ATTEMPTS,
            )
        self._outbound_queue.start()
        return self._outbound_queue

    def wait_for_outbound_flush(self, timeout: float = 1.0) -> bool:
        """
        Wait until outbound messages clear the queue.

        Args:
            timeout (float): Seconds to wait before giving up.

        Returns:
            bool: ``True`` when the queue drained before the timeout elapsed.
        """

        queue = getattr(self, "_outbound_queue", None)
        if queue is None:
            return True
        return queue.wait_for_flush(timeout=timeout)

    @property
    def outbound_queue(self) -> OutboundMessageQueue | None:
        """Return the active outbound queue instance for diagnostics/testing."""

        return self._outbound_queue

    def log_delivery_details(self, message, time_string, signature_string):
        RNS.log("\t+--- LXMF Delivery ---------------------------------------------")
        RNS.log(f"\t| Source hash            : {RNS.prettyhexrep(message.source_hash)}")
        RNS.log(f"\t| Source instance        : {message.get_source()}")
        RNS.log(
            f"\t| Destination hash       : {RNS.prettyhexrep(message.destination_hash)}"
        )
        # RNS.log(f"\t| Destination identity   : {message.source_identity}")
        RNS.log(f"\t| Destination instance   : {message.get_destination()}")
        RNS.log(f"\t| Transport Encryption   : {message.transport_encryption}")
        RNS.log(f"\t| Timestamp              : {time_string}")
        RNS.log(f"\t| Title                  : {message.title_as_string()}")
        RNS.log(f"\t| Content                : {message.content_as_string()}")
        RNS.log(f"\t| Fields                 : {message.fields}")
        RNS.log(f"\t| Message signature      : {signature_string}")
        RNS.log("\t+---------------------------------------------------------------")

    def _lookup_identity_label(self, source_hash) -> str:
        if isinstance(source_hash, (bytes, bytearray)):
            hash_key = source_hash.hex()
            pretty = RNS.prettyhexrep(source_hash)
        elif source_hash:
            hash_key = str(source_hash)
            pretty = hash_key
        else:
            return "unknown"
        return self.identities.get(hash_key, pretty)

    def _handle_telemetry_for_tak(
        self,
        telemetry: dict,
        peer_hash: str | bytes | None,
        timestamp: datetime | None,
    ) -> None:
        """Convert telemetry payloads into CoT events for TAK consumers."""

        tak_connector = getattr(self, "tak_connector", None)
        if tak_connector is None:
            return
        try:
            _dispatch_coroutine(
                tak_connector.send_telemetry_event(
                    telemetry,
                    peer_hash=peer_hash,
                    timestamp=timestamp,
                )
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            RNS.log(
                f"Failed to send telemetry CoT event: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )

    def _extract_target_topic(self, fields) -> str | None:
        if not isinstance(fields, dict):
            return None
        for key in ("TopicID", "topic_id", "topic", "Topic"):
            topic_id = fields.get(key)
            if topic_id:
                return str(topic_id)
        commands = fields.get(LXMF.FIELD_COMMANDS)
        if isinstance(commands, list):
            for command in commands:
                if not isinstance(command, dict):
                    continue
                for key in ("TopicID", "topic_id", "topic", "Topic"):
                    topic_id = command.get(key)
                    if topic_id:
                        return str(topic_id)
        return None

    def _refresh_topic_registry(self) -> None:
        self._topic_registry_last_refresh = time.monotonic()
        if not self.api:
            return
        try:
            subscribers = self.api.list_subscribers()
        except Exception as exc:  # pragma: no cover - defensive logging
            RNS.log(
                f"Failed to refresh topic registry: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )
            self.topic_subscribers = {}
            return
        registry: dict[str, set[str]] = {}
        for subscriber in subscribers:
            topic_id = getattr(subscriber, "topic_id", None)
            destination = getattr(subscriber, "destination", "")
            if not topic_id or not destination:
                continue
            registry.setdefault(topic_id, set()).add(destination.lower())
        self.topic_subscribers = registry
        self._topic_registry_last_refresh = time.monotonic()

    def _subscribers_for_topic(self, topic_id: str) -> set[str]:
        if not topic_id:
            return set()
        if not hasattr(self, "_topic_registry_last_refresh"):
            self._topic_registry_last_refresh = time.monotonic()
        now = time.monotonic()
        last_refresh = getattr(self, "_topic_registry_last_refresh", 0.0)
        is_stale = (now - last_refresh) >= TOPIC_REGISTRY_TTL_SECONDS
        if is_stale or topic_id not in self.topic_subscribers:
            if self.api:
                self._refresh_topic_registry()
            else:
                self._topic_registry_last_refresh = now
        return self.topic_subscribers.get(topic_id, set())

    def _commands_affect_subscribers(self, commands: list[dict] | None) -> bool:
        """Return True when commands modify subscriber mappings."""

        if not commands:
            return False

        subscriber_commands = {
            CommandManager.CMD_SUBSCRIBE_TOPIC,
            CommandManager.CMD_CREATE_SUBSCRIBER,
            CommandManager.CMD_ADD_SUBSCRIBER,
            CommandManager.CMD_DELETE_SUBSCRIBER,
            CommandManager.CMD_REMOVE_SUBSCRIBER,
            CommandManager.CMD_PATCH_SUBSCRIBER,
        }

        for command in commands:
            if not isinstance(command, dict):
                continue
            name = command.get(PLUGIN_COMMAND) or command.get("Command")
            if name in subscriber_commands:
                return True

        return False

    @staticmethod
    def _connection_hex(connection: RNS.Destination) -> str | None:
        identity = getattr(connection, "identity", None)
        hash_bytes = getattr(identity, "hash", None)
        if isinstance(hash_bytes, (bytes, bytearray)) and hash_bytes:
            return hash_bytes.hex().lower()
        return None

    def _message_source_hex(self, message: LXMF.LXMessage) -> str | None:
        source = message.get_source()
        if source is not None:
            identity = getattr(source, "identity", None)
            hash_bytes = getattr(identity, "hash", None)
            if isinstance(hash_bytes, (bytes, bytearray)) and hash_bytes:
                return hash_bytes.hex().lower()
        source_hash = getattr(message, "source_hash", None)
        if isinstance(source_hash, (bytes, bytearray)) and source_hash:
            return source_hash.hex().lower()
        return None

    def _sender_is_joined(self, message: LXMF.LXMessage) -> bool:
        """Return True when the message sender has previously joined.

        Args:
            message (LXMF.LXMessage): Incoming LXMF message.

        Returns:
            bool: ``True`` if the sender exists in the connection cache or the
            persisted client registry.
        """

        connections = getattr(self, "connections", {}) or {}
        source = None
        try:
            source = message.get_source()
        except Exception:
            source = None
        identity = getattr(source, "identity", None)
        hash_bytes = getattr(identity, "hash", None)
        if isinstance(hash_bytes, (bytes, bytearray)) and hash_bytes:
            if hash_bytes in connections:
                return True

        sender_hex = self._message_source_hex(message)
        if not sender_hex:
            return False
        api = getattr(self, "api", None)
        if api is None:
            return False
        try:
            if hasattr(api, "has_client"):
                return bool(api.has_client(sender_hex))
            if hasattr(api, "list_clients"):
                lower_hex = sender_hex.lower()
                return any(
                    getattr(client, "identity", "").lower() == lower_hex
                    for client in api.list_clients()
                )
        except Exception as exc:  # pragma: no cover - defensive log
            RNS.log(
                f"Failed to determine join status for {sender_hex}: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )
        return False

    def _reply_with_app_info(self, message: LXMF.LXMessage) -> None:
        """Send an application info reply to the given message source.

        Args:
            message (LXMF.LXMessage): Message requiring an informational reply.
        """

        command_manager = getattr(self, "command_manager", None)
        router = getattr(self, "lxm_router", None)
        if command_manager is None or router is None:
            return
        handler = getattr(command_manager, "_handle_get_app_info", None)
        if handler is None:
            return
        try:
            response = handler(message)
        except Exception as exc:  # pragma: no cover - defensive log
            RNS.log(
                f"Unable to build app info reply: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return
        try:
            router.handle_outbound(response)
        except Exception as exc:  # pragma: no cover - defensive log
            RNS.log(
                f"Unable to send app info reply: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )

    def _persist_attachments_from_fields(
        self, message: LXMF.LXMessage
    ) -> list[LXMF.LXMessage]:
        """
        Persist file and image attachments from LXMF fields.

        Args:
            message (LXMF.LXMessage): Incoming LXMF message that may include
                ``FIELD_FILE_ATTACHMENTS`` or ``FIELD_IMAGE`` entries.

        Returns:
            list[LXMF.LXMessage]: Replies acknowledging stored attachments.
        """

        if not message.fields:
            return []
        stored_files, file_errors = self._store_attachment_payloads(
            message.fields.get(LXMF.FIELD_FILE_ATTACHMENTS),
            category="file",
            default_prefix="file",
        )
        stored_images, image_errors = self._store_attachment_payloads(
            message.fields.get(LXMF.FIELD_IMAGE),
            category="image",
            default_prefix="image",
        )
        attachment_errors = file_errors + image_errors
        acknowledgements: list[LXMF.LXMessage] = []
        if stored_files:
            reply = self._build_attachment_reply(
                message, stored_files, heading="Stored files:"
            )
            if reply:
                acknowledgements.append(reply)
        if stored_images:
            reply = self._build_attachment_reply(
                message, stored_images, heading="Stored images:"
            )
            if reply:
                acknowledgements.append(reply)
        if attachment_errors:
            reply = self._build_attachment_error_reply(
                message, attachment_errors, heading="Attachment errors:"
            )
            if reply:
                acknowledgements.append(reply)
        return acknowledgements

    def _store_attachment_payloads(
        self, payload, *, category: str, default_prefix: str
    ) -> tuple[list, list[str]]:
        """
        Normalize and store incoming attachments.

        Args:
            payload: Raw LXMF field payload (bytes, dict, or list).
            category (str): Attachment category ("file" or "image").
            default_prefix (str): Filename prefix when no name is supplied.

        Returns:
            tuple[list, list[str]]: Stored attachment records from the API and
                any errors encountered while parsing.
        """

        if payload in (None, {}, []):
            return [], []
        api = getattr(self, "api", None)
        base_path = self._attachment_base_path(category)
        if api is None or base_path is None:
            return [], []
        entries = self._normalize_attachment_payloads(
            payload, category=category, default_prefix=default_prefix
        )
        stored = []
        errors: list[str] = []
        for entry in entries:
            if entry.get("error"):
                errors.append(entry["error"])
                continue
            stored_entry = self._write_and_record_attachment(
                data=entry["data"],
                name=entry["name"],
                media_type=entry.get("media_type"),
                category=category,
                base_path=base_path,
            )
            if stored_entry is not None:
                stored.append(stored_entry)
        return stored, errors

    def _normalize_attachment_payloads(
        self, payload, *, category: str, default_prefix: str
    ) -> list[dict]:
        """
        Convert the raw LXMF payload into attachment dictionaries.

        Args:
            payload: Raw LXMF field value.
            category (str): Attachment category ("file" or "image").
            default_prefix (str): Prefix for generated filenames.

        Returns:
            list[dict]: Normalized payload entries.
        """

        entries = payload
        if not isinstance(payload, (list, tuple)):
            entries = [payload]
        normalized: list[dict] = []
        for index, entry in enumerate(entries):
            parsed = self._parse_attachment_entry(
                entry, category=category, default_prefix=default_prefix, index=index
            )
            if parsed is not None:
                normalized.append(parsed)
        return normalized

    def _parse_attachment_entry(
        self, entry, *, category: str, default_prefix: str, index: int
    ) -> dict | None:
        """
        Extract attachment data, name, and media type from an entry.

        Args:
            entry: Raw attachment value (dict, bytes, or string).
            category (str): Attachment category ("file" or "image").
            default_prefix (str): Prefix for generated filenames.
            index (int): Entry index for uniqueness.

        Returns:
            dict | None: Parsed attachment info when data is available.
        """

        data = None
        media_type = None
        name = None
        if isinstance(entry, dict):
            data = self._first_present_value(
                entry, ["data", "bytes", "content", "blob"]
            )
            media_type = self._first_present_value(
                entry, ["media_type", "mime", "mime_type", "type"]
            )
            name = self._first_present_value(
                entry, ["name", "filename", "file_name", "title"]
            )
        elif isinstance(entry, (bytes, bytearray, memoryview)):
            data = bytes(entry)
        elif isinstance(entry, str):
            data = entry
        elif isinstance(entry, (list, tuple)):
            if len(entry) >= 2:
                name = entry[0] if isinstance(entry[0], str) else name
                data = entry[1]
                if len(entry) >= 3 and isinstance(entry[2], str):
                    media_type = entry[2]
            elif entry:
                data = entry[0]

        if data is None:
            reason = "Missing attachment data"
            attachment_name = name or f"{category}-{index + 1}"
            RNS.log(
                f"Ignoring attachment without data (category={category}).",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return {"error": f"{reason}: {attachment_name}"}

        if isinstance(media_type, str):
            media_type = media_type.strip() or None
        data = self._coerce_attachment_data(data, media_type=media_type)
        if data is None:
            reason = "Unsupported attachment data format"
            attachment_name = name or f"{category}-{index + 1}"
            RNS.log(
                f"Ignoring attachment with unsupported data format (category={category}).",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return {"error": f"{reason}: {attachment_name}"}
        if not media_type and category == "image":
            media_type = self._infer_image_media_type(data)
        safe_name = self._sanitize_attachment_name(
            name or self._default_attachment_name(default_prefix, index, media_type)
        )
        if media_type and not Path(safe_name).suffix:
            extension = self._guess_media_type_extension(media_type)
            if extension:
                safe_name = f"{safe_name}{extension}"
        media_type = media_type or self._guess_media_type(safe_name, category)
        return {"data": data, "name": safe_name, "media_type": media_type}

    @staticmethod
    def _sanitize_attachment_name(name: str) -> str:
        """Return a filename-safe attachment name."""

        candidate = Path(name).name or "attachment"
        return candidate

    def _default_attachment_name(
        self, prefix: str, index: int, media_type: str | None
    ) -> str:
        """Return a unique attachment name using the prefix and media type."""

        suffix = ""
        guessed = self._guess_media_type_extension(media_type)
        if guessed:
            suffix = guessed
        unique_id = uuid.uuid4().hex[:8]
        return f"{prefix}-{int(time.time())}-{index}-{unique_id}{suffix}"

    @staticmethod
    def _guess_media_type(name: str, category: str) -> str | None:
        """Guess the media type from the name or category."""

        guessed, _ = mimetypes.guess_type(name)
        if guessed:
            return guessed
        if category == "image":
            return "image/octet-stream"
        return "application/octet-stream"

    @staticmethod
    def _infer_image_media_type(data: bytes) -> str | None:
        """Infer an image media type from raw bytes.

        Args:
            data (bytes): Raw image bytes.

        Returns:
            str | None: MIME type when recognized, otherwise ``None``.
        """

        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if data.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        if data.startswith(b"BM"):
            return "image/bmp"
        if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            return "image/webp"
        return None

    @staticmethod
    def _guess_media_type_extension(media_type: str | None) -> str:
        """Guess a file extension from the supplied media type."""

        if not media_type:
            return ""
        guessed = mimetypes.guess_extension(media_type) or ""
        return guessed

    @staticmethod
    def _first_present_value(entry: dict, keys: list[str]):
        """Return the first key value present in a dictionary.

        Args:
            entry (dict): Attachment metadata map.
            keys (list[str]): Keys to check in order.

        Returns:
            Any: The first matching value or ``None`` when absent.
        """

        lower_lookup = {}
        for key in entry:
            if isinstance(key, str):
                lower_lookup.setdefault(key.lower(), key)
        for key in keys:
            if key in entry:
                return entry.get(key)
            lookup_key = lower_lookup.get(key.lower())
            if lookup_key is not None:
                return entry.get(lookup_key)
        return None

    @staticmethod
    def _decode_base64_payload(payload: str) -> bytes | None:
        """Decode base64 content safely.

        Args:
            payload (str): Base64-encoded string.

        Returns:
            bytes | None: Decoded bytes or ``None`` if decoding fails.
        """

        compact = "".join(payload.split())
        try:
            return base64.b64decode(compact, validate=True)
        except (binascii.Error, ValueError):
            return None

    @staticmethod
    def _should_decode_base64(payload: str) -> bool:
        """Heuristically determine whether a string looks base64 encoded."""

        compact = "".join(payload.split())
        if compact.startswith("data:") and "base64," in compact:
            return True
        if any(marker in compact for marker in ("=", "+", "/")):
            return True
        if len(compact) >= 12 and len(compact) % 4 == 0:
            return bool(re.fullmatch(r"[A-Za-z0-9+/=]+", compact))
        return False

    def _coerce_attachment_data(
        self, data, *, media_type: str | None
    ) -> bytes | None:
        """Normalize attachment data into bytes.

        Args:
            data (Any): Raw attachment data.
            media_type (str | None): Attachment media type.

        Returns:
            bytes | None: Normalized bytes or ``None`` when unsupported.
        """

        if isinstance(data, (bytes, bytearray, memoryview)):
            return bytes(data)

        if isinstance(data, (list, tuple)):
            if all(isinstance(item, int) for item in data):
                try:
                    return bytes(data)
                except ValueError:
                    return None

        if isinstance(data, str):
            payload = data.strip()
            if not payload:
                return b""
            if payload.startswith("data:") and "base64," in payload:
                encoded = payload.split("base64,", 1)[1]
                decoded = self._decode_base64_payload(encoded)
                if decoded is not None:
                    return decoded
            # Reason: attachments may arrive as base64 when sent from JSON-only clients.
            if self._should_decode_base64(payload):
                decoded = self._decode_base64_payload(payload)
                if decoded is not None:
                    return decoded
            return payload.encode("utf-8")

        return None

    def _write_and_record_attachment(
        self,
        *,
        data: bytes,
        name: str,
        media_type: str | None,
        category: str,
        base_path: Path,
    ):
        """
        Write an attachment to disk and record it via the API.

        Args:
            data (bytes): Raw attachment data.
            name (str): Attachment filename.
            media_type (str | None): Optional MIME type.
            category (str): Attachment category ("file" or "image").
            base_path (Path): Directory to write the attachment.

        Returns:
            FileAttachment | None: Stored record or None on failure.
        """

        api = getattr(self, "api", None)
        if api is None:
            return None
        try:
            target_path = self._unique_path(base_path, name)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(data)
            if category == "image":
                return api.store_image(
                    target_path, name=target_path.name, media_type=media_type
                )
            return api.store_file(
                target_path, name=target_path.name, media_type=media_type
            )
        except Exception as exc:  # pragma: no cover - defensive log
            RNS.log(
                f"Failed to persist {category} attachment '{name}': {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return None

    @staticmethod
    def _unique_path(base_path: Path, name: str) -> Path:
        """Return a unique, non-existing path for the attachment."""

        candidate = base_path / name
        if not candidate.exists():
            return candidate
        index = 1
        stem = candidate.stem
        suffix = candidate.suffix
        while True:
            next_candidate = candidate.with_name(f"{stem}_{index}{suffix}")
            if not next_candidate.exists():
                return next_candidate
            index += 1

    def _attachment_base_path(self, category: str) -> Path | None:
        """Return the configured base path for the given category."""

        api = getattr(self, "api", None)
        if api is None:
            return None
        config_manager = getattr(api, "_config_manager", None)
        if config_manager is None:
            return None
        config = getattr(config_manager, "config", None)
        if config is None:
            return None
        if category == "image":
            return config.image_storage_path
        return config.file_storage_path

    def _build_attachment_reply(
        self, message: LXMF.LXMessage, attachments, *, heading: str
    ) -> LXMF.LXMessage | None:
        """Create an acknowledgement LXMF message for stored attachments."""

        lines = [heading]
        for index, attachment in enumerate(attachments, start=1):
            attachment_id = getattr(attachment, "file_id", None)
            name = getattr(attachment, "name", "<file>")
            id_text = attachment_id if attachment_id is not None else "<pending>"
            lines.append(f"{index}. {name} (ID: {id_text})")
        return self._reply_message(message, "\n".join(lines))

    def _build_attachment_error_reply(
        self, message: LXMF.LXMessage, errors: list[str], *, heading: str
    ) -> LXMF.LXMessage | None:
        """Create an acknowledgement LXMF message for attachment errors."""

        lines = [heading]
        for index, error in enumerate(errors, start=1):
            lines.append(f"{index}. {error}")
        return self._reply_message(message, "\n".join(lines))

    def _reply_message(
        self, message: LXMF.LXMessage, content: str, fields: dict | None = None
    ) -> LXMF.LXMessage | None:
        """Construct a reply LXMF message to the sender."""

        if self.my_lxmf_dest is None:
            return None
        destination = None
        try:
            command_manager = getattr(self, "command_manager", None)
            if command_manager is not None and hasattr(command_manager, "_create_dest"):
                destination = (
                    command_manager._create_dest(  # pylint: disable=protected-access
                        message.source.identity
                    )
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
            except Exception as exc:  # pragma: no cover - defensive log
                RNS.log(
                    f"Unable to build reply destination: {exc}",
                    getattr(RNS, "LOG_WARNING", 2),
                )
                return None
        return LXMF.LXMessage(
            destination,
            self.my_lxmf_dest,
            content,
            fields=fields or {},
            desired_method=LXMF.LXMessage.DIRECT,
        )

    def _is_telemetry_only(
        self, message: LXMF.LXMessage, telemetry_handled: bool
    ) -> bool:
        if not telemetry_handled:
            return False
        fields = message.fields or {}
        telemetry_keys = {LXMF.FIELD_TELEMETRY, LXMF.FIELD_TELEMETRY_STREAM}
        if not any(key in fields for key in telemetry_keys):
            return False
        for key, value in fields.items():
            if key in telemetry_keys:
                continue
            if value not in (None, "", b"", {}, [], ()):  # pragma: no cover - guard
                return False
        content_text = self._message_text(message)
        if not content_text:
            return True
        return content_text.lower() in self.TELEMETRY_PLACEHOLDERS

    @staticmethod
    def _message_text(message: LXMF.LXMessage) -> str:
        content = getattr(message, "content", None)
        if not content:
            return ""
        try:
            return message.content_as_string().strip()
        except Exception:  # pragma: no cover - defensive
            return ""

    def load_or_generate_identity(self, identity_path: Path):
        identity_path = Path(identity_path)
        if identity_path.exists():
            try:
                RNS.log("Loading existing identity")
                return RNS.Identity.from_file(str(identity_path))
            except Exception:
                RNS.log("Failed to load existing identity, generating new")
        else:
            RNS.log("Generating new identity")

        identity = RNS.Identity()  # Create a new identity
        identity_path.parent.mkdir(parents=True, exist_ok=True)
        identity.to_file(str(identity_path))  # Save the new identity to file
        return identity

    def run(
        self,
        *,
        daemon_mode: bool = False,
        services: list[str] | tuple[str, ...] | None = None,
    ):
        RNS.log(
            f"Starting headless hub; announcing every {self.announce_interval}s",
            getattr(RNS, "LOG_INFO", 3),
        )
        if daemon_mode:
            self.start_daemon_workers(services=services)
        while not self._shutdown:
            self.my_lxmf_dest.announce()
            RNS.log("LXMF identity announced", getattr(RNS, "LOG_DEBUG", self.loglevel))
            time.sleep(self.announce_interval)

    def start_daemon_workers(
        self, *, services: list[str] | tuple[str, ...] | None = None
    ) -> None:
        """Start background telemetry collectors and optional services."""

        if self._daemon_started:
            return

        self._ensure_outbound_queue()

        if self.telemetry_sampler is not None:
            self.telemetry_sampler.start()

        requested = list(services or [])
        for name in requested:
            service = self._create_service(name)
            if service is None:
                continue
            started = service.start()
            if started:
                self._active_services[name] = service

        self._daemon_started = True

    def stop_daemon_workers(self) -> None:
        if self._daemon_started:
            for key, service in list(self._active_services.items()):
                try:
                    service.stop()
                finally:
                    # Ensure the registry is cleared even if ``stop`` raises.
                    self._active_services.pop(key, None)

            if self.telemetry_sampler is not None:
                self.telemetry_sampler.stop()

            self._daemon_started = False

        if self._outbound_queue is not None:
            self.wait_for_outbound_flush(timeout=1.0)
            # Reason: ensure outbound thread exits cleanly between daemon runs.
            self._outbound_queue.stop()

    def _create_service(self, name: str) -> HubService | None:
        factory = SERVICE_FACTORIES.get(name)
        if factory is None:
            RNS.log(
                f"Unknown daemon service '{name}'; available services: {sorted(SERVICE_FACTORIES)}",
                RNS.LOG_WARNING,
            )
            return None
        try:
            return factory(self)
        except Exception as exc:  # pragma: no cover - defensive
            RNS.log(
                f"Failed to initialize daemon service '{name}': {exc}",
                RNS.LOG_ERROR,
            )
            return None

    def shutdown(self):
        if self._shutdown:
            return
        self._shutdown = True
        self.stop_daemon_workers()
        if self.embedded_lxmd is not None:
            self.embedded_lxmd.stop()
            self.embedded_lxmd = None
        self.telemetry_sampler = None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "-c",
        "--config",
        dest="config_path",
        help="Path to a unified config.ini file",
        default=None,
    )
    ap.add_argument("-s", "--storage_dir", help="Storage directory path", default=None)
    ap.add_argument("--display_name", help="Display name for the server", default=None)
    ap.add_argument(
        "--announce-interval",
        type=int,
        default=None,
        help="Seconds between announcement broadcasts",
    )
    ap.add_argument(
        "--hub-telemetry-interval",
        type=int,
        default=None,
        help="Seconds between local telemetry snapshots.",
    )
    ap.add_argument(
        "--service-telemetry-interval",
        type=int,
        default=None,
        help="Seconds between remote telemetry collector polls.",
    )
    ap.add_argument(
        "--log-level",
        choices=list(LOG_LEVELS.keys()),
        default=None,
        help="Log level to emit RNS traffic to stdout",
    )
    ap.add_argument(
        "--embedded",
        "--embedded-lxmd",
        dest="embedded",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Run the LXMF router/propagation threads in-process.",
    )
    ap.add_argument(
        "--daemon",
        dest="daemon",
        action="store_true",
        help="Start local telemetry collectors and optional services.",
    )
    ap.add_argument(
        "--service",
        dest="services",
        action="append",
        default=[],
        metavar="NAME",
        help=(
            "Enable an optional daemon service (e.g., gpsd). Repeat the flag for"
            " multiple services."
        ),
    )

    args = ap.parse_args()

    storage_path = _expand_user_path(args.storage_dir or STORAGE_PATH)
    identity_path = storage_path / "identity"
    config_path = (
        _expand_user_path(args.config_path)
        if args.config_path
        else storage_path / "config.ini"
    )

    config_manager = HubConfigurationManager(
        storage_path=storage_path, config_path=config_path
    )
    app_config = config_manager.config
    runtime_config = app_config.runtime

    display_name = args.display_name or runtime_config.display_name
    announce_interval = args.announce_interval or runtime_config.announce_interval
    hub_interval = _resolve_interval(
        args.hub_telemetry_interval,
        runtime_config.hub_telemetry_interval or DEFAULT_HUB_TELEMETRY_INTERVAL,
    )
    service_interval = _resolve_interval(
        args.service_telemetry_interval,
        runtime_config.service_telemetry_interval or DEFAULT_SERVICE_TELEMETRY_INTERVAL,
    )

    log_level_name = (
        args.log_level or runtime_config.log_level or DEFAULT_LOG_LEVEL_NAME
    ).lower()
    loglevel = LOG_LEVELS.get(log_level_name, DEFAULT_LOG_LEVEL)

    embedded = runtime_config.embedded_lxmd if args.embedded is None else args.embedded
    requested_services = list(runtime_config.default_services)
    requested_services.extend(args.services or [])
    services = list(dict.fromkeys(requested_services))

    reticulum_server = ReticulumTelemetryHub(
        display_name,
        storage_path,
        identity_path,
        embedded=embedded,
        announce_interval=announce_interval,
        loglevel=loglevel,
        hub_telemetry_interval=hub_interval,
        service_telemetry_interval=service_interval,
        config_manager=config_manager,
    )

    try:
        reticulum_server.run(daemon_mode=args.daemon, services=services)
    except KeyboardInterrupt:
        RNS.log("Received interrupt, shutting down", RNS.LOG_INFO)
    finally:
        reticulum_server.shutdown()
