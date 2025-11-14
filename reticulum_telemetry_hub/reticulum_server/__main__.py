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
  identity together, exposes an interactive/headless loop, and relays messages
  between connected peers.

Running the script directly allows operators to:

* Generate or load a persistent Reticulum identity stored under ``STORAGE_PATH``.
* Announce the LXMF delivery destination on demand or periodically (headless
  mode).
* Inspect/log inbound messages and fan them out to connected peers.
* Request telemetry snapshots from specific peers.

Use ``python -m reticulum_telemetry_hub.reticulum_server`` to start the hub.
Command line arguments let you override the storage path, choose a display name,
or run in headless mode for unattended deployments.
"""

import os
import time
import LXMF
import RNS
import argparse
from pathlib import Path
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from .command_manager import CommandManager

# Constants
STORAGE_PATH = "RTH_Store"  # Path to store temporary files
IDENTITY_PATH = os.path.join(STORAGE_PATH, "identity")  # Path to store identity file
APP_NAME = LXMF.APP_NAME + ".delivery"  # Application name for LXMF

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
        if isinstance(app_data, bytes):
            try:
                return app_data.decode("utf-8").strip()
            except UnicodeDecodeError:
                return app_data.hex()
        if app_data is None:
            return "unknown"
        return str(app_data)


class ReticulumTelemetryHub:
    """Runtime container that glues Reticulum, LXMF and telemetry services.

    The hub owns the Reticulum stack, LXMF router, telemetry persistence layer
    and connection bookkeeping. It can run interactively (prompt driven) or in
    headless mode where it periodically announces its delivery identity.
    """

    lxm_router: LXMF.LXMRouter
    connections: dict[bytes, RNS.Destination]
    identities: dict[str, str]
    my_lxmf_dest: RNS.Destination | None
    ret: RNS.Reticulum
    storage_path: Path
    identity_path: Path
    tel_controller: TelemetryController
    _shared_lxm_router: LXMF.LXMRouter | None = None

    def __init__(self, display_name: str, storage_path: Path, identity_path: Path):
        # Normalize paths early so downstream helpers can rely on Path objects.
        self.storage_path = Path(storage_path)
        self.identity_path = Path(identity_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.identity_path.parent.mkdir(parents=True, exist_ok=True)

        # Reuse an existing Reticulum instance when running in-process tests
        # to avoid triggering the single-instance guard in the RNS library.
        self.ret = RNS.Reticulum.get_instance() or RNS.Reticulum()
        self.tel_controller = TelemetryController()
        self.connections: dict[bytes, RNS.Destination] = {}

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

        self.command_manager = CommandManager(
            self.connections, self.tel_controller, self.my_lxmf_dest
        )

        self.lxm_router.set_message_storage_limit(megabytes=5)
        self.lxm_router.register_delivery_callback(self.delivery_callback)
        RNS.Transport.register_announce_handler(AnnounceHandler(self.identities))

    def command_handler(self, commands: list, message: LXMF.LXMessage):
        """Handles commands received from the client and sends responses back.

        Args:
            commands (list): List of commands received from the client
            message (LXMF.LXMessage): LXMF message object
        """
        for response in self.command_manager.handle_commands(commands, message):
            self.lxm_router.handle_outbound(response)

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

            # Handle telemetry data
            if self.tel_controller.handle_message(message):
                RNS.log("Telemetry data saved")

            # Skip if the message content is empty
            if message.content is None or message.content == b"":
                return

            # Broadcast the message to all connected clients
            source = message.get_source()
            source_hash = getattr(source, "hash", None) or message.source_hash
            source_label = self._lookup_identity_label(source_hash)
            msg = f"{source_label} > {message.content_as_string()}"
            self.send_message(msg)
        except Exception as e:
            RNS.log(f"Error: {e}")

    def send_message(self, message: str):
        """Sends a message to all connected clients.

        Args:
            message (str): Message to send
        """
        for connection in self.connections.values():
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

    def interactive_loop(self):
        # Periodically announce the LXMF identity
        while True:
            choice = input("Enter your choice (exit/announce/telemetry): ")

            if choice == "exit":
                break
            elif choice == "announce":
                self.my_lxmf_dest.announce()
            elif choice == "telemetry":
                connection_hash = input("Enter the connection hash: ")
                found = False
                normalized_hash = connection_hash.strip().lower().replace(":", "")
                for conn_hash, connection in self.connections.items():
                    if conn_hash.hex() == normalized_hash:
                        message = LXMF.LXMessage(
                            connection,
                            self.my_lxmf_dest,
                            "Requesting telemetry",
                            desired_method=LXMF.LXMessage.DIRECT,
                            fields={
                                LXMF.FIELD_COMMANDS: [
                                    {TelemetryController.TELEMETRY_REQUEST: 1000000000}
                                ]
                            },
                        )
                        if hasattr(connection, "identity") and hasattr(
                            connection.identity, "hash"
                        ):
                            message.destination_hash = connection.identity.hash
                        self.lxm_router.handle_outbound(message)
                        found = True
                        break
                if not found:
                    print("Connection not found")
    def headless_loop(self):
        while True:
            self.my_lxmf_dest.announce()
            time.sleep(60)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "-s", "--storage_dir", help="Storage directory path", default=STORAGE_PATH
    )
    ap.add_argument("--headless", action="store_true", help="Run in headless mode")
    ap.add_argument("--display_name", help="Display name for the server", default="RTH")

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


    reticulum_server = ReticulumTelemetryHub(
        args.display_name, storage_path, identity_path
    )

    if not args.headless:
        reticulum_server.interactive_loop()
    else:
        reticulum_server.headless_loop()
