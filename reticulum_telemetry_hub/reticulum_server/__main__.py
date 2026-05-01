"""
Reticulum Telemetry Hub (RTH)
--------------------------------

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
import subprocess
from pathlib import Path

import LXMF
import RNS

from reticulum_telemetry_hub.api.marker_service import MarkerService
from reticulum_telemetry_hub.api.zone_service import ZoneService
from reticulum_telemetry_hub.checklist_sync import ChecklistSyncRouter
from reticulum_telemetry_hub.config.manager import HubConfigurationManager
from reticulum_telemetry_hub.config.manager import _expand_user_path
from reticulum_telemetry_hub.embedded_lxmd import EmbeddedLxmd
import reticulum_telemetry_hub.lxmf_runtime  # noqa: F401
from reticulum_telemetry_hub.config.constants import (
    DEFAULT_ANNOUNCE_INTERVAL,
    DEFAULT_HUB_TELEMETRY_INTERVAL,
    DEFAULT_LOG_LEVEL_NAME,
    DEFAULT_SERVICE_TELEMETRY_INTERVAL,
)
from reticulum_telemetry_hub.atak_cot.tak_connector import TakConnector
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)
from reticulum_telemetry_hub.lxmf_telemetry.sampler import TelemetrySampler
from reticulum_telemetry_hub.lxmf_telemetry.telemeter_manager import TelemeterManager
from reticulum_telemetry_hub.mission_domain import EmergencyActionMessageService
from reticulum_telemetry_hub.mission_domain import MissionDomainService
from reticulum_telemetry_hub.mission_sync import MissionSyncRouter
from reticulum_telemetry_hub.reticulum_server.marker_objects import MarkerObjectManager
from reticulum_telemetry_hub.reticulum_server.delivery_service import DeliveryService
from reticulum_telemetry_hub.reticulum_server.message_events import MessageEventEmitter
from reticulum_telemetry_hub.reticulum_server.message_router import MessageRouter
from reticulum_telemetry_hub.reticulum_server.runtime_constants import APP_NAME
from reticulum_telemetry_hub.reticulum_server.runtime_constants import DEFAULT_LOG_LEVEL
from reticulum_telemetry_hub.reticulum_server.runtime_constants import ESCAPED_COMMAND_PREFIX
from reticulum_telemetry_hub.reticulum_server.runtime_constants import LOG_LEVELS
from reticulum_telemetry_hub.reticulum_server.runtime_constants import R3AKT_CUSTOM_DATA_FIELD
from reticulum_telemetry_hub.reticulum_server.runtime_constants import REM_APP_NAME
from reticulum_telemetry_hub.reticulum_server.runtime_constants import STORAGE_PATH
from reticulum_telemetry_hub.reticulum_server.services import (
    HubService,
)
from .command_manager import CommandManager


from reticulum_telemetry_hub.reticulum_server.runtime_support import AnnounceHandler
from reticulum_telemetry_hub.reticulum_server.runtime_support import _build_reticulum_init_kwargs
from reticulum_telemetry_hub.reticulum_server.runtime_support import _dispatch_coroutine
from reticulum_telemetry_hub.reticulum_server.runtime_support import _resolve_interval
from reticulum_telemetry_hub.reticulum_server.runtime_support import _resolve_reticulum_config_dir
from reticulum_telemetry_hub.reticulum_server.runtime_router import RuntimeRouterMixin
from reticulum_telemetry_hub.reticulum_server.runtime_init import RuntimeInitMixin
from reticulum_telemetry_hub.reticulum_server.runtime_commands import RuntimeCommandMixin
from reticulum_telemetry_hub.reticulum_server.runtime_lxmf_config import RuntimeLxmfConfigMixin
from reticulum_telemetry_hub.reticulum_server.runtime_r3akt import RuntimeR3aktMixin
from reticulum_telemetry_hub.reticulum_server.runtime_rem_fanout import RuntimeRemFanoutMixin
from reticulum_telemetry_hub.reticulum_server.runtime_services import RuntimeServiceMixin
from reticulum_telemetry_hub.reticulum_server.runtime_delivery import RuntimeDeliveryMixin
from reticulum_telemetry_hub.reticulum_server.runtime_send import RuntimeSendMixin
from reticulum_telemetry_hub.reticulum_server.runtime_outbound import RuntimeOutboundMixin
from reticulum_telemetry_hub.reticulum_server.runtime_propagation_sync import RuntimePropagationSyncMixin
from reticulum_telemetry_hub.reticulum_server.runtime_announce import RuntimeAnnounceMixin
from reticulum_telemetry_hub.reticulum_server.runtime_state import RuntimeStateMixin
from reticulum_telemetry_hub.reticulum_server.runtime_tak_fields import RuntimeTakFieldMixin
from reticulum_telemetry_hub.reticulum_server.runtime_replies import RuntimeReplyMixin
from reticulum_telemetry_hub.reticulum_server.runtime_attachment_parse import RuntimeAttachmentParseMixin
from reticulum_telemetry_hub.reticulum_server.runtime_attachment_store import RuntimeAttachmentStoreMixin
from reticulum_telemetry_hub.reticulum_server.runtime_lifecycle import RuntimeLifecycleMixin

__all__ = [
    "APP_NAME",
    "AnnounceHandler",
    "DeliveryService",
    "ESCAPED_COMMAND_PREFIX",
    "MessageEventEmitter",
    "MessageRouter",
    "R3AKT_CUSTOM_DATA_FIELD",
    "REM_APP_NAME",
    "ReticulumTelemetryHub",
    "_build_reticulum_init_kwargs",
    "_dispatch_coroutine",
    "_resolve_interval",
    "_resolve_reticulum_config_dir",
    "subprocess",
]


class ReticulumTelemetryHub(
    RuntimeRouterMixin,
    RuntimeInitMixin,
    RuntimeLxmfConfigMixin,
    RuntimeCommandMixin,
    RuntimeR3aktMixin,
    RuntimeRemFanoutMixin,
    RuntimeServiceMixin,
    RuntimeDeliveryMixin,
    RuntimeSendMixin,
    RuntimeOutboundMixin,
    RuntimeAnnounceMixin,
    RuntimePropagationSyncMixin,
    RuntimeStateMixin,
    RuntimeTakFieldMixin,
    RuntimeReplyMixin,
    RuntimeAttachmentParseMixin,
    RuntimeAttachmentStoreMixin,
    RuntimeLifecycleMixin,
):
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
    marker_service: MarkerService | None
    zone_service: ZoneService | None
    marker_manager: MarkerObjectManager | None
    command_manager: CommandManager | None
    mission_sync_router: MissionSyncRouter | None
    checklist_sync_router: ChecklistSyncRouter | None
    mission_domain_service: MissionDomainService | None
    emergency_action_message_service: EmergencyActionMessageService | None
    _active_services: dict[str, HubService]

    TELEMETRY_PLACEHOLDERS = {"telemetry data", "telemetry update"}

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

    display_name = args.display_name
    announce_interval = max(
        1,
        _resolve_interval(
            args.announce_interval,
            runtime_config.announce_interval or DEFAULT_ANNOUNCE_INTERVAL,
        ),
    )
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
