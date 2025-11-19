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
import os
import time
from pathlib import Path

import LXMF
import RNS

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.config.manager import HubConfigurationManager
from reticulum_telemetry_hub.embedded_lxmd import EmbeddedLxmd
from reticulum_telemetry_hub.lxmf_daemon.LXMF import display_name_from_app_data
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
from .command_manager import CommandManager

# Constants
STORAGE_PATH = "RTH_Store"  # Path to store temporary files
IDENTITY_PATH = os.path.join(STORAGE_PATH, "identity")  # Path to store identity file
APP_NAME = LXMF.APP_NAME + ".delivery"  # Application name for LXMF
DEFAULT_ANNOUNCE_INTERVAL = 60
DEFAULT_HUB_TELEMETRY_INTERVAL = 600
DEFAULT_SERVICE_TELEMETRY_INTERVAL = 900
DEFAULT_LOG_LEVEL = getattr(RNS, "LOG_DEBUG", getattr(RNS, "LOG_INFO", 3))
LOG_LEVELS = {
    "error": getattr(RNS, "LOG_ERROR", 1),
    "warning": getattr(RNS, "LOG_WARNING", 2),
    "info": getattr(RNS, "LOG_INFO", 3),
    "debug": getattr(RNS, "LOG_DEBUG", DEFAULT_LOG_LEVEL),
}
ENV_HUB_TELEMETRY_INTERVAL = "RTH_HUB_TELEMETRY_INTERVAL"
ENV_SERVICE_TELEMETRY_INTERVAL = "RTH_SERVICE_TELEMETRY_INTERVAL"
TOPIC_REGISTRY_TTL_SECONDS = 5


def _resolve_interval(value: int | None, env_var: str, default: int) -> int:
    """Return the positive interval derived from CLI/env values."""

    if value is not None:
        return max(0, int(value))

    env_value = os.getenv(env_var)
    if env_value is not None:
        try:
            return max(0, int(env_value))
        except ValueError:
            RNS.log(
                f"Invalid telemetry interval set via {env_var}: {env_value!r}",
                RNS.LOG_WARNING,
            )
    return default


class AnnounceHandler:
    """Track simple metadata about peers announcing on the Reticulum bus."""

    def __init__(self, identities: dict[str, str]):
        self.aspect_filter = APP_NAME
        self.identities = identities

    def received_announce(self, destination_hash, announced_identity, app_data):
        RNS.log("\t+--- LXMF Announcement -----------------------------------------")
        RNS.log(f"\t| Source hash            : {RNS.prettyhexrep(destination_hash)}")
        RNS.log(f"\t| Announced identity     : {announced_identity}")
        RNS.log(f"\t| App data               : {app_data}")
        RNS.log("\t+---------------------------------------------------------------")
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
            display_name = display_name_from_app_data(app_data)
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
    _active_services: dict[str, HubService]

    TELEMETRY_PLACEHOLDERS = {"telemetry data", "telemetry update"}

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
    ):
        # Normalize paths early so downstream helpers can rely on Path objects.
        self.storage_path = Path(storage_path)
        self.identity_path = Path(identity_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.identity_path.parent.mkdir(parents=True, exist_ok=True)
        self.announce_interval = announce_interval
        self.hub_telemetry_interval = hub_telemetry_interval
        self.service_telemetry_interval = service_telemetry_interval
        self.loglevel = loglevel

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
        self.config_manager: HubConfigurationManager | None = None
        self.embedded_lxmd: EmbeddedLxmd | None = None
        self.telemetry_sampler: TelemetrySampler | None = None
        self.telemeter_manager: TelemeterManager | None = None
        self._shutdown = False
        self.connections: dict[bytes, RNS.Destination] = {}
        self._daemon_started = False
        self._active_services = {}

        identity = self.load_or_generate_identity(self.identity_path)

        if ReticulumTelemetryHub._shared_lxm_router is None:
            ReticulumTelemetryHub._shared_lxm_router = LXMF.LXMRouter(
                storagepath=str(self.storage_path)
            )
        self.lxm_router = ReticulumTelemetryHub._shared_lxm_router

        self.my_lxmf_dest = self.lxm_router.register_delivery_identity(
            identity, display_name=display_name
        )

        self.identities: dict[str, str] = {}

        self.lxm_router.set_message_storage_limit(megabytes=5)
        self.lxm_router.register_delivery_callback(self.delivery_callback)
        RNS.Transport.register_announce_handler(AnnounceHandler(self.identities))

        api_config_manager: HubConfigurationManager | None = None

        if embedded:
            self.config_manager = HubConfigurationManager(
                storage_path=self.storage_path
            )
            api_config_manager = self.config_manager
            self.embedded_lxmd = EmbeddedLxmd(
                router=self.lxm_router,
                destination=self.my_lxmf_dest,
                config_manager=self.config_manager,
                telemetry_controller=self.tel_controller,
            )
            self.embedded_lxmd.start()
        else:
            self.config_manager = None
            api_config_manager = HubConfigurationManager(storage_path=self.storage_path)
            self.embedded_lxmd = None

        self.api = ReticulumTelemetryHubAPI(config_manager=api_config_manager)
        self.telemeter_manager = TelemeterManager(config_manager=self.config_manager)
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

    def command_handler(self, commands: list, message: LXMF.LXMessage):
        """Handles commands received from the client and sends responses back.

        Args:
            commands (list): List of commands received from the client
            message (LXMF.LXMessage): LXMF message object
        """
        for response in self.command_manager.handle_commands(commands, message):
            self.lxm_router.handle_outbound(response)
        if self._commands_affect_subscribers(commands):
            self._refresh_topic_registry()

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

            # Handle the commands
            if message.signature_validated and LXMF.FIELD_COMMANDS in message.fields:
                self.command_handler(message.fields[LXMF.FIELD_COMMANDS], message)

            telemetry_handled = self.tel_controller.handle_message(message)
            if telemetry_handled:
                RNS.log("Telemetry data saved")

            # Skip if the message content is empty
            if message.content is None or message.content == b"":
                return

            if self._is_telemetry_only(message, telemetry_handled):
                return

            # Broadcast the message to all connected clients
            source = message.get_source()
            source_hash = getattr(source, "hash", None) or message.source_hash
            source_label = self._lookup_identity_label(source_hash)
            msg = f"{source_label} > {message.content_as_string()}"
            topic_id = self._extract_target_topic(message.fields)
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
            response = LXMF.LXMessage(
                connection,
                self.my_lxmf_dest,
                message,
                desired_method=LXMF.LXMessage.DIRECT,
            )
            if hasattr(connection, "identity") and hasattr(connection.identity, "hash"):
                response.destination_hash = connection.identity.hash
            self.lxm_router.handle_outbound(response)

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
        if not self._daemon_started:
            return

        for key, service in list(self._active_services.items()):
            try:
                service.stop()
            finally:
                # Ensure the registry is cleared even if ``stop`` raises.
                self._active_services.pop(key, None)

        if self.telemetry_sampler is not None:
            self.telemetry_sampler.stop()

        self._daemon_started = False

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
        "-s", "--storage_dir", help="Storage directory path", default=STORAGE_PATH
    )
    ap.add_argument("--display_name", help="Display name for the server", default="RTH")
    ap.add_argument(
        "--announce-interval",
        type=int,
        default=DEFAULT_ANNOUNCE_INTERVAL,
        help="Seconds between announcement broadcasts",
    )
    ap.add_argument(
        "--hub-telemetry-interval",
        type=int,
        default=None,
        help=(
            "Seconds between local telemetry snapshots. Overrides "
            f"{ENV_HUB_TELEMETRY_INTERVAL}"
        ),
    )
    ap.add_argument(
        "--service-telemetry-interval",
        type=int,
        default=None,
        help=(
            "Seconds between remote telemetry collector polls. Overrides "
            f"{ENV_SERVICE_TELEMETRY_INTERVAL}"
        ),
    )
    ap.add_argument(
        "--log-level",
        choices=list(LOG_LEVELS.keys()),
        default="debug",
        help="Log level to emit RNS traffic to stdout",
    )
    ap.add_argument(
        "--embedded",
        "--embedded-lxmd",
        dest="embedded",
        action="store_true",
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

    # Use the provided storage directory (or default) for both storage and identity paths
    storage_path = args.storage_dir
    identity_path = os.path.join(storage_path, "identity")

    if args.storage_dir:
        storage_path = args.storage_dir
        # store the identity in the user supplied directory rather than the
        # default STORAGE_PATH. Previously `STORAGE_PATH` was used here which
        # ignored the command line argument and always wrote the identity file
        # to the default location.
        identity_path = os.path.join(storage_path, "identity")

    hub_interval = _resolve_interval(
        args.hub_telemetry_interval,
        ENV_HUB_TELEMETRY_INTERVAL,
        DEFAULT_HUB_TELEMETRY_INTERVAL,
    )
    service_interval = _resolve_interval(
        args.service_telemetry_interval,
        ENV_SERVICE_TELEMETRY_INTERVAL,
        DEFAULT_SERVICE_TELEMETRY_INTERVAL,
    )

    reticulum_server = ReticulumTelemetryHub(
        args.display_name,
        storage_path,
        identity_path,
        embedded=args.embedded,
        announce_interval=args.announce_interval,
        loglevel=LOG_LEVELS[args.log_level],
        hub_telemetry_interval=hub_interval,
        service_telemetry_interval=service_interval,
    )

    try:
        reticulum_server.run(daemon_mode=args.daemon, services=args.services)
    except KeyboardInterrupt:
        RNS.log("Received interrupt, shutting down", RNS.LOG_INFO)
    finally:
        reticulum_server.shutdown()
