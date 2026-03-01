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
import queue
import re
import string
import time
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from typing import Callable
from typing import cast

import LXMF
import RNS
import RNS.vendor.umsgpack as msgpack

from reticulum_telemetry_hub.api.models import ChatMessage
from reticulum_telemetry_hub.api.models import FileAttachment
from reticulum_telemetry_hub.api.models import Marker
from reticulum_telemetry_hub.api.marker_identity import derive_marker_identity_key
from reticulum_telemetry_hub.api.marker_service import MarkerService
from reticulum_telemetry_hub.api.marker_storage import MarkerStorage
from reticulum_telemetry_hub.api.zone_service import ZoneService
from reticulum_telemetry_hub.api.zone_storage import ZoneStorage
from reticulum_telemetry_hub.checklist_sync import ChecklistSyncRouter
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.config.manager import HubConfigurationManager
from reticulum_telemetry_hub.config.manager import _expand_user_path
from reticulum_telemetry_hub.config.models import HubAppConfig
from reticulum_telemetry_hub.embedded_lxmd import EmbeddedLxmd
from reticulum_telemetry_hub.lxmf_daemon.LXMF import display_name_from_app_data
from reticulum_telemetry_hub.lxmf_runtime import apply_lxmf_runtime_patches
from reticulum_telemetry_hub.reticulum_server.appearance import apply_icon_appearance
from reticulum_telemetry_hub.reticulum_server.announce_capabilities import (
    AnnounceCapabilitiesConfig,
    CapabilityEncodingResult,
    append_capabilities_to_announce_app_data,
    build_capability_payload,
    decode_inbound_capability_payload,
    encode_capability_payload,
    normalize_capability_list,
    select_capability_encoder,
)
from reticulum_telemetry_hub.atak_cot.tak_connector import TakConnector
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)

apply_lxmf_runtime_patches()
from reticulum_telemetry_hub.lxmf_telemetry.sampler import TelemetrySampler
from reticulum_telemetry_hub.lxmf_telemetry.telemeter_manager import TelemeterManager
from reticulum_telemetry_hub.reticulum_server.services import (
    SERVICE_FACTORIES,
    HubService,
)
from reticulum_telemetry_hub.reticulum_server.constants import PLUGIN_COMMAND
from reticulum_telemetry_hub.reticulum_server.outbound_queue import (
    OutboundPayload,
    OutboundMessageQueue,
)
from reticulum_telemetry_hub.reticulum_server.propagation_selection import (
    PropagationNodeAnnounceHandler,
)
from reticulum_telemetry_hub.reticulum_server.propagation_selection import (
    PropagationNodeCandidate,
)
from reticulum_telemetry_hub.reticulum_server.propagation_selection import (
    PropagationNodeRegistry,
)
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog
from reticulum_telemetry_hub.reticulum_server.event_log import resolve_event_log_path
from reticulum_telemetry_hub.reticulum_server.internal_adapter import LxmfInbound
from reticulum_telemetry_hub.reticulum_server.internal_adapter import ReticulumInternalAdapter
from reticulum_telemetry_hub.reticulum_server.marker_objects import MarkerObjectManager
from reticulum_telemetry_hub.reticulum_server.mission_delta_markdown import (
    MissionDeltaNameResolver,
    render_mission_delta_markdown,
)
from reticulum_telemetry_hub.mission_domain import MissionDomainService
from reticulum_telemetry_hub.mission_sync import MissionSyncRouter
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
R3AKT_CUSTOM_TYPE_IDENTIFIER = "r3akt.mission.change.v1"
R3AKT_CUSTOM_META_VERSION = "1.0"
R3AKT_CUSTOM_TYPE_FIELD = int(getattr(LXMF, "FIELD_CUSTOM_TYPE", 0xFB))
R3AKT_CUSTOM_DATA_FIELD = int(getattr(LXMF, "FIELD_CUSTOM_DATA", 0xFC))
R3AKT_CUSTOM_META_FIELD = int(getattr(LXMF, "FIELD_CUSTOM_META", 0xFD))
MARKDOWN_RENDERER_FIELD = int(getattr(LXMF, "FIELD_RENDERER", 0x0F))
MARKDOWN_RENDERER_VALUE = int(getattr(LXMF, "RENDERER_MARKDOWN", 0x02))
ESCAPED_COMMAND_PREFIX = "\\\\\\"
DEFAULT_OUTBOUND_QUEUE_SIZE = 64
DEFAULT_OUTBOUND_WORKERS = 2
DEFAULT_OUTBOUND_SEND_TIMEOUT = 5.0
DEFAULT_OUTBOUND_BACKOFF = 0.5
DEFAULT_OUTBOUND_MAX_ATTEMPTS = 3
IDENTITY_CAPABILITY_CACHE_TTL_SECONDS = 6 * 60 * 60


def _resolve_interval(value: int | None, fallback: int) -> int:
    """Return the positive interval derived from CLI/config values."""

    if value is not None:
        return max(0, int(value))

    return max(0, int(fallback))


def _resolve_reticulum_config_dir(
    config_manager: HubConfigurationManager | None,
) -> str | None:
    """Return the Reticulum config directory inferred from manager settings."""

    if config_manager is None:
        return None

    config_path = getattr(config_manager, "reticulum_config_path", None)
    if config_path is None:
        return None

    resolved_path = _expand_user_path(config_path)
    if resolved_path.exists():
        target_dir = resolved_path if resolved_path.is_dir() else resolved_path.parent
        return str(target_dir)

    # For non-existing values, treat ".../config" as file path shorthand.
    if resolved_path.name.lower() == "config":
        return str(resolved_path.parent)

    return str(resolved_path)


def _build_reticulum_init_kwargs(
    *,
    loglevel: int,
    config_manager: HubConfigurationManager | None,
) -> dict[str, object]:
    """Build kwargs passed to ``RNS.Reticulum``."""

    kwargs: dict[str, object] = {"loglevel": loglevel}
    config_dir = _resolve_reticulum_config_dir(config_manager)
    if config_dir:
        kwargs["configdir"] = config_dir
    return kwargs


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

    _DEFAULT_PERSIST_QUEUE_SIZE = 1024
    _DROP_LOG_INTERVAL = 100

    def __init__(
        self,
        identities: dict[str, str],
        api: ReticulumTelemetryHubAPI | None = None,
        *,
        persist_queue_size: int = _DEFAULT_PERSIST_QUEUE_SIZE,
        capability_callback: Callable[[str, set[str]], None] | None = None,
    ):
        self.aspect_filter = APP_NAME
        self.identities = identities
        self._api = api
        self._capability_callback = capability_callback
        self._persist_queue: queue.Queue[tuple[str, str | None, str | None]] = queue.Queue(
            maxsize=max(1, int(persist_queue_size))
        )
        self._persist_stop_event = threading.Event()
        self._persist_worker: threading.Thread | None = None
        self._persist_worker_lock = threading.Lock()
        self._dropped_persist_count = 0

    def close(self, *, timeout: float = 2.0) -> None:
        """Stop the background persistence worker."""

        worker = self._persist_worker
        if worker is None:
            return
        self._persist_stop_event.set()
        worker.join(timeout=timeout)
        self._persist_worker = None

    def _ensure_persist_worker(self) -> None:
        """Start the background persistence worker once."""

        worker = self._persist_worker
        if worker is not None and worker.is_alive():
            return
        with self._persist_worker_lock:
            worker = self._persist_worker
            if worker is not None and worker.is_alive():
                return
            self._persist_stop_event.clear()
            self._persist_worker = threading.Thread(
                target=self._persist_worker_loop,
                daemon=True,
            )
            self._persist_worker.start()

    def _persist_worker_loop(self) -> None:
        """Persist announce metadata from the bounded queue."""

        while True:
            if self._persist_stop_event.is_set() and self._persist_queue.empty():
                return
            try:
                destination_hash, display_name, source_interface = self._persist_queue.get(
                    timeout=0.2
                )
            except queue.Empty:
                continue

            try:
                api = self._api
                if api is None:
                    continue
                api.record_identity_announce(
                    destination_hash,
                    display_name=display_name,
                    source_interface=source_interface,
                )
            except Exception as exc:  # pragma: no cover - defensive log
                RNS.log(
                    f"Failed to persist announce metadata for {destination_hash}: {exc}",
                    getattr(RNS, "LOG_WARNING", 2),
                )
            finally:
                self._persist_queue.task_done()

    def received_announce(self, destination_hash, announced_identity, app_data):
        # RNS.log("\t+--- LXMF Announcement -----------------------------------------")
        # RNS.log(f"\t| Source hash            : {RNS.prettyhexrep(destination_hash)}")
        # RNS.log(f"\t| Announced identity     : {announced_identity}")
        # RNS.log(f"\t| App data               : {app_data}")
        # RNS.log("\t+---------------------------------------------------------------")
        label = self._decode_app_data(app_data)
        capabilities = self._decode_capabilities(app_data)
        destination_key = self._normalize_hash(destination_hash)
        identity_key = self._normalize_hash(announced_identity)
        hash_keys = [key for key in (destination_key, identity_key) if key]
        if label:
            for key in hash_keys:
                self.identities[key] = label
        if capabilities:
            callback = self._capability_callback
            if callback is not None:
                for key in hash_keys:
                    callback(key, set(capabilities))
        if destination_key:
            self._persist_announce_async(
                destination_key,
                label,
                source_interface="destination",
            )
        if identity_key and identity_key != destination_key:
            self._persist_announce_async(
                identity_key,
                label,
                source_interface="identity",
            )

    @staticmethod
    def _normalize_hash(value) -> str | None:
        if value is None:
            return None
        if isinstance(value, (bytes, bytearray, memoryview)):
            return bytes(value).hex().lower()
        hash_value = getattr(value, "hash", None)
        if isinstance(hash_value, (bytes, bytearray, memoryview)):
            return bytes(hash_value).hex().lower()
        if isinstance(value, str):
            candidate = value.strip().lower()
            if candidate and all(ch in string.hexdigits for ch in candidate):
                return candidate
        return None

    @staticmethod
    def _decode_app_data(app_data) -> str | None:
        if app_data is None:
            return None

        if isinstance(app_data, (bytes, bytearray)):
            try:
                display_name = display_name_from_app_data(bytes(app_data))
            except Exception:
                display_name = None

            if display_name:
                display_name = display_name.strip()
                return display_name or None

        return None

    @staticmethod
    def _decode_capabilities(app_data) -> set[str]:
        if not isinstance(app_data, (bytes, bytearray, memoryview)):
            return set()
        try:
            decoded = msgpack.unpackb(bytes(app_data), raw=False)
        except Exception:
            return set()
        if not isinstance(decoded, list) or len(decoded) < 3:
            return set()
        payload = decode_inbound_capability_payload(decoded[2])
        if not isinstance(payload, dict):
            return set()
        raw_caps = payload.get("caps")
        if not isinstance(raw_caps, list):
            return set()
        normalized: set[str] = set()
        for item in raw_caps:
            text = str(item or "").strip().lower()
            if text:
                normalized.add(text)
        return normalized

    def _persist_announce_async(
        self,
        destination_hash: str,
        display_name: str | None,
        *,
        source_interface: str | None = None,
    ) -> None:
        """Persist announce metadata on a background thread.

        Args:
            destination_hash (str): Identity or destination hash to store.
            display_name (str | None): Optional announce display name.
            source_interface (str | None): Tag describing the announce hash type.
        """

        api = self._api
        if api is None:
            return
        self._ensure_persist_worker()

        try:
            self._persist_queue.put_nowait(
                (destination_hash, display_name, source_interface)
            )
        except queue.Full:
            self._dropped_persist_count += 1
            dropped_count = self._dropped_persist_count
            if dropped_count == 1 or dropped_count % self._DROP_LOG_INTERVAL == 0:
                RNS.log(
                    (
                        "Announce persistence queue is full; dropping metadata event "
                        f"#{dropped_count} for {destination_hash}"
                    ),
                    getattr(RNS, "LOG_WARNING", 2),
                )


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
    marker_service: MarkerService | None
    zone_service: ZoneService | None
    marker_manager: MarkerObjectManager | None
    command_manager: CommandManager | None
    mission_sync_router: MissionSyncRouter | None
    checklist_sync_router: ChecklistSyncRouter | None
    mission_domain_service: MissionDomainService | None
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

    @staticmethod
    def _delivery_destination_hash(identity) -> str | None:
        """Return the local LXMF delivery destination hash for ``identity``."""

        if identity is None:
            return None
        try:
            destination_hash = RNS.Destination.hash_from_name_and_identity(
                APP_NAME, identity
            )
        except Exception:  # pragma: no cover - defensive
            return None
        if isinstance(destination_hash, (bytes, bytearray, memoryview)):
            return bytes(destination_hash).hex().lower()
        return None

    def __init__(
        self,
        display_name: str | None,
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
            display_name (str | None): Optional label announced with the LXMF destination.
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
        init_started = time.monotonic()
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
        self.config_manager: HubConfigurationManager | None = config_manager
        if self.config_manager is None:
            self.config_manager = HubConfigurationManager(
                storage_path=self.storage_path, config_path=config_path
            )

        # Reuse an existing Reticulum instance when running in-process tests
        # to avoid triggering the single-instance guard in the RNS library.
        existing_reticulum = RNS.Reticulum.get_instance()
        if existing_reticulum is not None:
            self.ret = existing_reticulum
            RNS.loglevel = self.loglevel
        else:
            self.ret = RNS.Reticulum(
                **_build_reticulum_init_kwargs(
                    loglevel=self.loglevel,
                    config_manager=self.config_manager,
                )
            )
            RNS.loglevel = self.loglevel

        telemetry_db_path = self.storage_path / "telemetry.db"
        event_log_path = resolve_event_log_path(self.storage_path)
        self.event_log = EventLog(event_path=event_log_path)
        self.tel_controller = TelemetryController(
            db_path=telemetry_db_path,
            event_log=self.event_log,
        )
        self._message_listeners: list[Callable[[dict[str, object]], None]] = []
        self.embedded_lxmd: EmbeddedLxmd | None = None
        self.telemetry_sampler: TelemetrySampler | None = None
        self.telemeter_manager: TelemeterManager | None = None
        self._shutdown = False
        self.connections: dict[bytes, RNS.Destination] = {}
        self._daemon_started = False
        self._active_services = {}
        self._outbound_queue: OutboundMessageQueue | None = None
        self._announce_capabilities_state: CapabilityEncodingResult | None = None
        self._announce_capabilities_encoder = select_capability_encoder()
        self._announce_capabilities_enabled = True
        self._announce_capabilities_lock = threading.Lock()
        self._announce_capabilities_logged = False
        self._identity_capability_cache: dict[str, tuple[set[str], float]] = {}
        self._mission_change_fanout_cache: dict[str, float] = {}
        self.command_manager = None
        self.mission_sync_router = None
        self.checklist_sync_router = None
        self.mission_domain_service = None
        self._remove_mission_change_listener: Callable[[], None] | None = None
        self._announce_handler: AnnounceHandler | None = None
        self._propagation_node_registry = PropagationNodeRegistry()
        self._propagation_announce_handler: PropagationNodeAnnounceHandler | None = None

        identity = self.load_or_generate_identity(self.identity_path)
        destination_hash = self._delivery_destination_hash(identity)
        self.display_name = self.config_manager.resolve_hub_display_name(
            override=display_name,
            destination_hash=destination_hash,
        )

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
            "register_delivery_identity", identity, display_name=self.display_name
        )

        self.identities: dict[str, str] = {}

        self._invoke_router_hook("set_message_storage_limit", megabytes=5)

        hub_db_path = self.config_manager.config.hub_database_path
        marker_identity_key = derive_marker_identity_key(identity)
        self.marker_service = MarkerService(
            MarkerStorage(hub_db_path),
            identity_key_provider=lambda: marker_identity_key,
        )
        self.zone_service = ZoneService(ZoneStorage(hub_db_path))
        runtime_config = self.config_manager.runtime_config
        marker_interval_minutes = getattr(
            runtime_config, "marker_announce_interval_minutes", 15
        )
        self.marker_manager = MarkerObjectManager(
            origin_rch_provider=self._origin_rch_hex,
            event_log=self.event_log,
            telemetry_recorder=self.tel_controller.save_telemetry,
            identity_key_provider=lambda: marker_identity_key,
            announce_interval_seconds=max(int(marker_interval_minutes) * 60, 60),
        )
        try:
            self.marker_service.migrate_markers(origin_rch=self._origin_rch_hex())
        except ValueError as exc:
            RNS.log(
                f"Skipping marker migration: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )

        self.embedded_lxmd = None
        if embedded:
            self.embedded_lxmd = EmbeddedLxmd(
                router=self.lxm_router,
                destination=self.my_lxmf_dest,
                config_manager=self.config_manager,
                telemetry_controller=self.tel_controller,
            )
            embedded_started = time.monotonic()
            self.embedded_lxmd.start()
            embedded_elapsed = time.monotonic() - embedded_started
            RNS.log(
                f"Embedded LXMF startup hook returned in {embedded_elapsed:.2f}s",
                getattr(RNS, "LOG_NOTICE", 3),
            )

        self.api = ReticulumTelemetryHubAPI(
            config_manager=self.config_manager,
            on_config_reload=self._handle_config_reload,
        )
        event_retention_days = getattr(runtime_config, "event_retention_days", 90)
        self.mission_domain_service = MissionDomainService(
            hub_db_path,
            event_retention_days=event_retention_days,
        )
        self.api.set_reticulum_destination(self._origin_rch_hex())
        self._backfill_identity_announces()
        self._load_persisted_clients()
        self._announce_handler = AnnounceHandler(
            self.identities,
            api=self.api,
            capability_callback=self._update_identity_capability_cache,
        )
        self._propagation_announce_handler = PropagationNodeAnnounceHandler(
            self._propagation_node_registry
        )
        RNS.Transport.register_announce_handler(self._announce_handler)
        RNS.Transport.register_announce_handler(self._propagation_announce_handler)
        self.tel_controller.set_api(self.api)
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
            config_manager=self.config_manager,
            event_log=self.event_log,
        )
        self.mission_sync_router = MissionSyncRouter(
            api=self.api,
            send_message=lambda content, topic_id, destination: self.send_message(
                content,
                topic=topic_id,
                destination=destination,
            ),
            marker_service=self.marker_service,
            zone_service=self.zone_service,
            domain_service=self.mission_domain_service,
            event_log=self.event_log,
            hub_identity_resolver=self._origin_rch_hex,
            field_results=LXMF.FIELD_RESULTS,
            field_event=LXMF.FIELD_EVENT,
            field_group=LXMF.FIELD_GROUP,
        )
        self.checklist_sync_router = ChecklistSyncRouter(
            api=self.api,
            domain_service=self.mission_domain_service,
            event_log=self.event_log,
            hub_identity_resolver=self._origin_rch_hex,
            field_results=LXMF.FIELD_RESULTS,
            field_event=LXMF.FIELD_EVENT,
            field_group=LXMF.FIELD_GROUP,
        )
        self.internal_adapter = ReticulumInternalAdapter(send_message=self.send_message)
        self.topic_subscribers: dict[str, set[str]] = {}
        self._topic_registry_last_refresh: float = 0.0
        self._refresh_topic_registry()
        if self.mission_domain_service is not None:
            self._remove_mission_change_listener = (
                self.mission_domain_service.register_mission_change_listener(
                    self._fanout_mission_change_to_recipients
                )
            )
        self._invoke_router_hook("register_delivery_callback", self.delivery_callback)
        init_elapsed = time.monotonic() - init_started
        RNS.log(
            f"Hub initialization completed in {init_elapsed:.2f}s",
            getattr(RNS, "LOG_NOTICE", 3),
        )

    def command_handler(self, commands: list, message: LXMF.LXMessage) -> list[LXMF.LXMessage]:
        """Handles commands received from the client and returns responses.

        Args:
            commands (list): List of commands received from the client
            message (LXMF.LXMessage): LXMF message object

        Returns:
            list[LXMF.LXMessage]: Responses generated for the commands.
        """
        manager = getattr(self, "command_manager", None)
        if manager is None:
            RNS.log(
                "Command manager unavailable; dropping command payload.",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return []

        mission_commands: list[dict[str, Any]] = []
        checklist_commands: list[dict[str, Any]] = []
        legacy_commands: list[Any] = []
        for command in commands:
            if not isinstance(command, dict):
                legacy_commands.append(command)
                continue
            command_type = command.get("command_type")
            if isinstance(command_type, str) and command_type.strip():
                if command_type.startswith("checklist."):
                    checklist_commands.append(command)
                else:
                    mission_commands.append(command)
            else:
                legacy_commands.append(command)

        responses: list[LXMF.LXMessage] = []
        source_identity = self._message_source_hex(message)
        message_fields = message.fields if isinstance(message.fields, dict) else {}
        group = message_fields.get(LXMF.FIELD_GROUP)

        mission_router = getattr(self, "mission_sync_router", None)
        if mission_commands and mission_router is not None:
            mission_replies = mission_router.handle_commands(
                mission_commands,
                source_identity=source_identity,
                group=group,
            )
            responses.extend(
                [
                    response
                    for response in (
                        self._mission_sync_response_to_lxmf(message, entry)
                        for entry in mission_replies
                    )
                    if response is not None
                ]
            )

        checklist_router = getattr(self, "checklist_sync_router", None)
        if checklist_commands and checklist_router is not None:
            checklist_replies = checklist_router.handle_commands(
                checklist_commands,
                source_identity=source_identity,
                group=group,
            )
            responses.extend(
                [
                    response
                    for response in (
                        self._mission_sync_response_to_lxmf(message, entry)
                        for entry in checklist_replies
                    )
                    if response is not None
                ]
            )

        if legacy_commands:
            responses.extend(manager.handle_commands(legacy_commands, message))

        if self._commands_affect_subscribers(legacy_commands) or self._mission_commands_affect_subscribers(
            mission_commands
        ):
            self._refresh_topic_registry()
        return responses

    def _mission_sync_response_to_lxmf(
        self, message: LXMF.LXMessage, response
    ) -> LXMF.LXMessage | None:
        """Convert a mission/checklist sync response to a reply LXMF message."""

        if self.my_lxmf_dest is None:
            return None
        destination = None
        command_manager = getattr(self, "command_manager", None)
        try:
            if command_manager is not None and hasattr(command_manager, "_create_dest"):
                destination = command_manager._create_dest(  # pylint: disable=protected-access
                    message.source.identity
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
            except Exception:
                return None
        response_fields = response.fields if isinstance(response.fields, dict) else {}
        outbound_fields = self._augment_r3akt_custom_fields(response_fields)
        merged_fields = self._merge_standard_fields(
            source_fields=message.fields,
            extra_fields=outbound_fields,
        )
        return LXMF.LXMessage(
            destination,
            self.my_lxmf_dest,
            str(response.content or ""),
            fields=apply_icon_appearance(merged_fields or {}),
            desired_method=LXMF.LXMessage.DIRECT,
        )

    @staticmethod
    def _extract_mission_uid_from_response_fields(
        fields: dict[int | str, object] | None,
    ) -> str | None:
        if not isinstance(fields, dict):
            return None
        event_field = fields.get(LXMF.FIELD_EVENT)
        if not isinstance(event_field, dict):
            return None
        event_type = str(event_field.get("event_type") or "").strip()
        payload = event_field.get("payload")
        if not isinstance(payload, dict):
            return None

        mission_uid = str(
            payload.get("mission_uid") or payload.get("mission_id") or ""
        ).strip()
        if mission_uid:
            return mission_uid

        if event_type.startswith("mission.registry.mission."):
            fallback_uid = str(payload.get("uid") or "").strip()
            if fallback_uid:
                return fallback_uid

        result_field = fields.get(LXMF.FIELD_RESULTS)
        if isinstance(result_field, dict):
            result_payload = result_field.get("result")
            if isinstance(result_payload, dict):
                mission_uid = str(
                    result_payload.get("mission_uid")
                    or result_payload.get("mission_id")
                    or ""
                ).strip()
                if mission_uid:
                    return mission_uid
                if event_type.startswith("mission.registry.mission."):
                    fallback_uid = str(result_payload.get("uid") or "").strip()
                    if fallback_uid:
                        return fallback_uid

        return None

    @staticmethod
    def _build_r3akt_custom_fields(
        *,
        mission_uid: str,
        event_envelope: dict[str, object],
    ) -> dict[int | str, object]:
        event_type = str(event_envelope.get("event_type") or "").strip()
        return {
            R3AKT_CUSTOM_TYPE_FIELD: R3AKT_CUSTOM_TYPE_IDENTIFIER,
            R3AKT_CUSTOM_DATA_FIELD: {
                "mission_uid": mission_uid,
                "event": event_envelope,
            },
            R3AKT_CUSTOM_META_FIELD: {
                "version": R3AKT_CUSTOM_META_VERSION,
                "event_type": event_type,
                "mission_uid": mission_uid,
                "encoding": "json",
                "source": "rch",
            },
        }

    def _augment_r3akt_custom_fields(
        self,
        fields: dict[int | str, object],
    ) -> dict[int | str, object]:
        merged = dict(fields or {})
        mission_uid = self._extract_mission_uid_from_response_fields(merged)
        event_field = merged.get(LXMF.FIELD_EVENT)
        if not mission_uid or not isinstance(event_field, dict):
            return merged
        merged.update(
            self._build_r3akt_custom_fields(
                mission_uid=mission_uid,
                event_envelope=event_field,
            )
        )
        return merged

    def _update_identity_capability_cache(
        self, identity: str, capabilities: set[str]
    ) -> None:
        normalized_identity = str(identity or "").strip().lower()
        if not normalized_identity:
            return
        normalized_caps = {
            str(value or "").strip().lower() for value in capabilities if value
        }
        if not normalized_caps:
            return
        expires_at = time.time() + IDENTITY_CAPABILITY_CACHE_TTL_SECONDS
        self._identity_capability_cache[normalized_identity] = (
            normalized_caps,
            expires_at,
        )

    def _identity_capabilities(self, identity: str) -> set[str]:
        normalized_identity = str(identity or "").strip().lower()
        if not normalized_identity:
            return set()

        cached = self._identity_capability_cache.get(normalized_identity)
        now = time.time()
        if cached is not None:
            values, expires_at = cached
            if now < float(expires_at):
                return set(values)

        api = getattr(self, "api", None)
        if api is None:
            return set()
        try:
            grants = api.list_identity_capabilities(normalized_identity)
        except Exception:
            return set()
        normalized = {
            str(value or "").strip().lower() for value in grants if value
        }
        self._identity_capability_cache[normalized_identity] = (
            normalized,
            now + IDENTITY_CAPABILITY_CACHE_TTL_SECONDS,
        )
        return normalized

    def _identity_supports_r3akt(self, identity: str) -> bool:
        capabilities = self._identity_capabilities(identity)
        return "r3akt" in capabilities

    def _prune_mission_change_fanout_cache(self) -> None:
        now = time.time()
        stale = [
            uid
            for uid, expires_at in self._mission_change_fanout_cache.items()
            if now >= float(expires_at)
        ]
        for uid in stale:
            self._mission_change_fanout_cache.pop(uid, None)

    def _mark_mission_change_fanned_out(self, mission_change_uid: str) -> None:
        uid = str(mission_change_uid or "").strip()
        if not uid:
            return
        self._prune_mission_change_fanout_cache()
        self._mission_change_fanout_cache[uid] = time.time() + 24 * 60 * 60

    def _has_mission_change_been_fanned_out(self, mission_change_uid: str) -> bool:
        uid = str(mission_change_uid or "").strip()
        if not uid:
            return False
        self._prune_mission_change_fanout_cache()
        expires_at = self._mission_change_fanout_cache.get(uid)
        if expires_at is None:
            return False
        return time.time() < float(expires_at)

    @staticmethod
    def _build_mission_change_event_field(
        *,
        mission_uid: str,
        mission_change_uid: str,
        change_type: str | None,
    ) -> dict[str, object]:
        return {
            "event_type": "mission.registry.mission_change.upserted",
            "payload": {
                "mission_uid": mission_uid,
                "mission_change_uid": mission_change_uid,
                "change_type": change_type,
            },
        }

    @staticmethod
    def _build_r3akt_delta_custom_fields(
        *,
        mission_uid: str,
        mission_change: dict[str, Any],
        delta: dict[str, Any],
    ) -> dict[int | str, object]:
        return {
            R3AKT_CUSTOM_TYPE_FIELD: R3AKT_CUSTOM_TYPE_IDENTIFIER,
            R3AKT_CUSTOM_DATA_FIELD: {
                "mission_uid": mission_uid,
                "mission_change": mission_change,
                "delta": delta,
            },
            R3AKT_CUSTOM_META_FIELD: {
                "version": R3AKT_CUSTOM_META_VERSION,
                "event_type": "mission.registry.mission_change.upserted",
                "mission_uid": mission_uid,
                "encoding": "json",
                "source": "rch",
            },
        }

    def _fanout_mission_change_to_recipients(
        self, mission_change: dict[str, Any]
    ) -> None:
        if not isinstance(mission_change, dict):
            return
        mission_uid = str(
            mission_change.get("mission_uid")
            or mission_change.get("mission_id")
            or ""
        ).strip()
        mission_change_uid = str(mission_change.get("uid") or "").strip()
        if not mission_uid or not mission_change_uid:
            return
        if self._has_mission_change_been_fanned_out(mission_change_uid):
            return

        domain = getattr(self, "mission_domain_service", None)
        if domain is None:
            return
        try:
            destinations = domain.list_mission_team_member_identities(mission_uid)
        except (KeyError, ValueError):
            return
        if not destinations:
            return
        deduped_destinations = [
            value
            for value in dict.fromkeys(
                str(identity or "").strip().lower() for identity in destinations if identity
            )
            if value
        ]
        if not deduped_destinations:
            return

        delta = mission_change.get("delta")
        delta_payload = dict(delta) if isinstance(delta, dict) else {}
        resolver = MissionDeltaNameResolver(domain)
        base_event_fields = {
            LXMF.FIELD_EVENT: self._build_mission_change_event_field(
                mission_uid=mission_uid,
                mission_change_uid=mission_change_uid,
                change_type=mission_change.get("change_type"),
            )
        }

        markdown_body = render_mission_delta_markdown(
            mission_uid=mission_uid,
            mission_change=mission_change,
            delta=delta_payload,
            resolver=resolver,
        )
        concise_body = (
            f"r3akt mission delta {mission_uid} {mission_change_uid}".strip()
        )
        for destination in deduped_destinations:
            if self._identity_supports_r3akt(destination):
                custom_fields = self._build_r3akt_delta_custom_fields(
                    mission_uid=mission_uid,
                    mission_change=mission_change,
                    delta=delta_payload,
                )
                merged_fields = self._merge_standard_fields(
                    source_fields=None,
                    extra_fields={**base_event_fields, **custom_fields},
                )
                self.send_message(
                    concise_body,
                    destination=destination,
                    fields=merged_fields,
                )
                continue

            merged_fields = self._merge_standard_fields(
                source_fields=None,
                extra_fields={
                    **base_event_fields,
                    MARKDOWN_RENDERER_FIELD: MARKDOWN_RENDERER_VALUE,
                },
            )
            self.send_message(
                markdown_body,
                destination=destination,
                fields=merged_fields,
            )

        self._mark_mission_change_fanned_out(mission_change_uid)

    def _fanout_mission_team_events(
        self,
        mission_replies: list[Any],
        *,
        source_fields: dict | None,
    ) -> None:
        if not mission_replies:
            return
        domain = getattr(self, "mission_domain_service", None)
        if domain is None:
            return
        for reply in mission_replies:
            fields = getattr(reply, "fields", None)
            if not isinstance(fields, dict):
                continue
            event_field = fields.get(LXMF.FIELD_EVENT)
            if not isinstance(event_field, dict):
                continue
            mission_uid = self._extract_mission_uid_from_response_fields(fields)
            if not mission_uid:
                continue
            try:
                destinations = domain.list_mission_team_member_identities(mission_uid)
            except (KeyError, ValueError):
                continue
            if not destinations:
                continue
            extra_fields = self._augment_r3akt_custom_fields(fields)
            outbound_fields = self._merge_standard_fields(
                source_fields=source_fields,
                extra_fields=extra_fields,
            )
            payload_text = f"r3akt mission event {event_field.get('event_type') or ''}".strip()
            for destination in destinations:
                if not destination:
                    continue
                self.send_message(
                    payload_text,
                    destination=destination,
                    fields=outbound_fields,
                )

    def register_message_listener(
        self, listener: Callable[[dict[str, object]], None]
    ) -> Callable[[], None]:
        """Register a callback invoked for inbound LXMF messages."""

        self._message_listeners.append(listener)

        def _remove_listener() -> None:
            """Remove a previously registered message listener."""

            if listener in self._message_listeners:
                self._message_listeners.remove(listener)

        return _remove_listener

    def _notify_message_listeners(self, entry: dict[str, object]) -> None:
        """Dispatch an inbound message entry to registered listeners."""

        listeners = list(getattr(self, "_message_listeners", []))
        for listener in listeners:
            try:
                listener(entry)
            except Exception as exc:  # pragma: no cover - defensive logging
                RNS.log(
                    f"Message listener raised an exception: {exc}",
                    getattr(RNS, "LOG_WARNING", 2),
                )

    def _record_message_event(
        self,
        *,
        content: str,
        source_label: str,
        source_hash: str | None,
        topic_id: str | None,
        timestamp: datetime,
        direction: str,
        state: str,
        destination: str | None,
        attachments: list[FileAttachment],
        message_id: str | None = None,
    ) -> None:
        """Emit a message event for northbound consumers."""

        scope = "topic" if topic_id else "dm"
        if direction == "outbound" and not destination and not topic_id:
            scope = "broadcast"
        api = getattr(self, "api", None)
        has_chat_support = api is not None and all(
            hasattr(api, name) for name in ("record_chat_message", "chat_attachment_from_file")
        )
        attachment_payloads = []
        if has_chat_support:
            attachment_payloads = [
                api.chat_attachment_from_file(item).to_dict()
                for item in attachments
            ]
            chat_message = ChatMessage(
                message_id=message_id,
                direction=direction,
                scope=scope,
                state=state,
                content=content,
                source=source_hash or source_label,
                destination=destination,
                topic_id=topic_id,
                attachments=[
                    api.chat_attachment_from_file(item) for item in attachments
                ],
                created_at=timestamp,
                updated_at=timestamp,
            )
            stored = api.record_chat_message(chat_message)
            entry = stored.to_dict()
            entry["SourceHash"] = source_hash or ""
            entry["SourceLabel"] = source_label
            entry["Timestamp"] = timestamp.isoformat()
            entry["Attachments"] = attachment_payloads
            self._notify_message_listeners(entry)
        else:
            entry = {
                "MessageID": message_id,
                "Direction": direction,
                "Scope": scope,
                "State": state,
                "Content": content,
                "Source": source_hash or source_label,
                "Destination": destination,
                "TopicID": topic_id,
                "Attachments": attachment_payloads,
                "CreatedAt": timestamp.isoformat(),
                "UpdatedAt": timestamp.isoformat(),
                "SourceHash": source_hash or "",
                "SourceLabel": source_label,
                "Timestamp": timestamp.isoformat(),
            }
            self._notify_message_listeners(entry)
        event_log = getattr(self, "event_log", None)
        if event_log is not None:
            event_log.add_event(
                "message_received" if direction == "inbound" else "message_sent",
                (
                    f"Message received from {source_label}"
                    if direction == "inbound"
                    else "Message sent from hub"
                ),
                metadata=entry,
            )

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
            adapter_commands: list[dict] = []
            sender_joined = False
            attachment_replies: list[LXMF.LXMessage] = []
            stored_attachments: list[FileAttachment] = []
            # Handle the commands
            command_replies: list[LXMF.LXMessage] = []
            if message.signature_validated:
                commands: list[dict] | None = None
                escape_error: str | None = None
                if LXMF.FIELD_COMMANDS in message.fields:
                    command_payload_present = True
                    commands = message.fields[LXMF.FIELD_COMMANDS]
                else:
                    escape_commands, escape_detected, escape_error = (
                        self._parse_escape_prefixed_commands(message)
                    )
                    if escape_detected:
                        command_payload_present = True
                    if escape_commands:
                        commands = escape_commands

                topic_id = self._extract_attachment_topic_id(commands)
                (
                    attachment_replies,
                    stored_attachments,
                ) = self._persist_attachments_from_fields(message, topic_id=topic_id)
                if escape_error:
                    error_reply = self._reply_message(
                        message, f"Command error: {escape_error}"
                    )
                    if error_reply is not None:
                        attachment_replies.append(error_reply)

                if commands:
                    command_replies = self.command_handler(commands, message) or []
                    adapter_commands = list(commands)

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
                self._reply_with_help(message)
                return

            adapter = getattr(self, "internal_adapter", None)
            if adapter is not None and message.signature_validated:
                try:
                    inbound = LxmfInbound(
                        message_id=self._message_id_hex(message),
                        source_id=self._message_source_hex(message),
                        topic_id=self._extract_target_topic(message.fields),
                        text=self._message_text(message),
                        fields=message.fields or {},
                        commands=adapter_commands,
                    )
                    adapter.handle_inbound(inbound)
                except Exception as exc:  # pragma: no cover - defensive logging
                    RNS.log(
                        f"Internal adapter failed to process inbound message: {exc}",
                        getattr(RNS, "LOG_WARNING", 2),
                    )

            # Skip if the message content is empty and no attachments were stored.
            if (message.content is None or message.content == b"") and not stored_attachments:
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
            try:
                message_time = datetime.fromtimestamp(
                    getattr(message, "timestamp", time.time()),
                    tz=timezone.utc,
                ).replace(tzinfo=None)
            except Exception:
                message_time = _utcnow()

            self._record_message_event(
                content=content_text,
                source_label=source_label,
                source_hash=self._message_source_hex(message),
                topic_id=topic_id,
                timestamp=message_time,
                direction="inbound",
                state="delivered",
                destination=None,
                attachments=stored_attachments,
                message_id=self._message_id_hex(message),
            )

            tak_connector = getattr(self, "tak_connector", None)
            if tak_connector is not None and content_text:
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

            # Broadcast the message to all connected clients.
            msg = self._format_chat_broadcast_text(
                source_label=source_label,
                content_text=content_text,
                topic_id=topic_id,
            )
            source_hex = self._message_source_hex(message)
            exclude = {source_hex} if source_hex else None
            relay_fields = self._merge_standard_fields(
                source_fields=message.fields,
                extra_fields={
                    LXMF.FIELD_EVENT: self._build_event_field(
                        event_type="rch.message.relay",
                        direction="inbound",
                        topic_id=topic_id,
                        source_hash=source_hex,
                    )
                },
            )
            self.send_message(msg, topic=topic_id, exclude=exclude, fields=relay_fields)
        except Exception as e:
            RNS.log(f"Error: {e}")

    def send_message(
        self,
        message: str,
        *,
        topic: str | None = None,
        destination: str | None = None,
        exclude: set[str] | None = None,
        fields: dict | None = None,
        sender: RNS.Destination | None = None,
        chat_message_id: str | None = None,
    ) -> bool:
        """Sends a message to connected clients.

        Args:
            message (str): Text to broadcast.
            topic (str | None): Topic filter limiting recipients.
            destination (str | None): Optional destination hash for a targeted send.
            exclude (set[str] | None): Optional set of lowercase destination
                hashes that should not receive the broadcast.
            fields (dict | None): Optional LXMF message fields.
            sender (RNS.Destination | None): Optional sender identity override.
            chat_message_id (str | None): Optional persisted chat message ID
                used to track delivery acknowledgements.
        """

        queue = self._ensure_outbound_queue()
        if queue is None:
            RNS.log(
                "Outbound queue unavailable; dropping message broadcast request.",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return False

        available = (
            list(self.connections.values())
            if hasattr(self.connections, "values")
            else list(self.connections)
        )
        excluded = {value.lower() for value in exclude if value} if exclude else set()
        normalized_destination = destination.lower() if destination else None
        if topic:
            subscriber_hex = self._subscribers_for_topic(topic)
            available = [
                connection
                for connection in available
                if self._connection_hex(connection) in subscriber_hex
            ]
        enqueued_any = False
        for connection in available:
            connection_hex = self._connection_hex(connection)
            if normalized_destination and connection_hex != normalized_destination:
                continue
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
                fields,
                sender=sender,
                chat_message_id=chat_message_id,
            )
            if enqueued:
                enqueued_any = True
            if not enqueued:
                RNS.log(
                    (
                        "Failed to enqueue outbound LXMF message for"
                        f" {connection_hex or 'unknown destination'}"
                    ),
                    getattr(RNS, "LOG_WARNING", 2),
                )
        return enqueued_any

    def dispatch_northbound_message(
        self,
        message: str,
        topic_id: str | None = None,
        destination: str | None = None,
        fields: dict | None = None,
    ) -> ChatMessage | None:
        """Dispatch a message originating from the northbound interface."""

        api = getattr(self, "api", None)
        attachments: list[FileAttachment] = []
        scope = "broadcast"
        if destination:
            scope = "dm"
        elif topic_id:
            scope = "topic"
        if isinstance(fields, dict):
            raw_attachments = fields.get("attachments")
            if isinstance(raw_attachments, list):
                attachments = [item for item in raw_attachments if isinstance(item, FileAttachment)]
            override_scope = fields.get("scope")
            if isinstance(override_scope, str) and override_scope.strip():
                scope = override_scope.strip()
        outbound_message = message
        if topic_id and message:
            topic_path = self._resolve_topic_path(topic_id)
            if self._has_sender_prefix(message):
                outbound_message = f"{topic_path}: {message}"
            else:
                outbound_message = self._format_chat_broadcast_text(
                    source_label=self._hub_sender_label(),
                    content_text=message,
                    topic_id=topic_id,
                )
        queued = None
        now = _utcnow()
        if api is not None:
            queued = api.record_chat_message(
                ChatMessage(
                    direction="outbound",
                    scope=scope,
                    state="queued",
                    content=outbound_message,
                    source=None,
                    destination=destination,
                    topic_id=topic_id,
                    attachments=[api.chat_attachment_from_file(item) for item in attachments],
                    created_at=now,
                    updated_at=now,
                )
            )
            self._notify_message_listeners(queued.to_dict())
            if getattr(self, "event_log", None) is not None:
                self.event_log.add_event(
                    "message_queued",
                    "Message queued for delivery",
                    metadata=queued.to_dict(),
                )
        lxmf_fields = None
        if attachments:
            try:
                lxmf_fields = self._build_lxmf_attachment_fields(attachments)
            except Exception as exc:  # pragma: no cover - defensive log
                RNS.log(
                    f"Failed to build attachment fields: {exc}",
                    getattr(RNS, "LOG_WARNING", 2),
                )
        lxmf_fields = self._merge_standard_fields(
            source_fields=fields,
            extra_fields=lxmf_fields,
        )
        if lxmf_fields is None:
            lxmf_fields = {}
        if LXMF.FIELD_EVENT not in lxmf_fields:
            lxmf_fields[LXMF.FIELD_EVENT] = self._build_event_field(
                event_type="rch.message.outbound",
                direction="outbound",
                topic_id=topic_id,
                destination=destination,
            )
        sent = self.send_message(
            outbound_message,
            topic=topic_id,
            destination=destination,
            fields=lxmf_fields,
            chat_message_id=queued.message_id if queued is not None else None,
        )
        if api is not None and queued is not None:
            updated = api.update_chat_message_state(
                queued.message_id or "", "sent" if sent else "failed"
            )
            if updated is not None:
                self._notify_message_listeners(updated.to_dict())
                if getattr(self, "event_log", None) is not None:
                    self.event_log.add_event(
                        "message_sent" if sent else "message_failed",
                        "Message sent" if sent else "Message failed",
                        metadata=updated.to_dict(),
                    )
                return updated
            return queued
        return None

    def _handle_outbound_delivery_receipt(
        self,
        message: LXMF.LXMessage,
        payload: OutboundPayload,
    ) -> None:
        """Persist and broadcast outbound delivery acknowledgements."""

        destination = payload.destination_hex or self._message_destination_hex(message)
        is_propagated = payload.delivery_mode == "propagated"
        entry = self._update_outbound_chat_state(
            message=message,
            payload=payload,
            state="sent" if is_propagated else "delivered",
            destination=destination,
        )
        entry = self._augment_outbound_delivery_metadata(entry, payload)
        event_log = getattr(self, "event_log", None)
        if event_log is None:
            return
        destination_label = self._lookup_identity_label(destination) if destination else "unknown"
        if is_propagated:
            if payload.local_propagation_fallback:
                event_log.add_event(
                    "message_propagated",
                    f"Message stored for local propagation to {destination_label}",
                    metadata=entry,
                )
                return
            node_label = self._resolve_propagation_node_label(payload)
            event_log.add_event(
                "message_propagated",
                f"Message accepted for propagation to {destination_label} via {node_label}",
                metadata=entry,
            )
            return
        event_log.add_event(
            "message_delivered",
            f"Message delivered to {destination_label}",
            metadata=entry,
        )

    def _handle_outbound_delivery_failure(
        self,
        message: LXMF.LXMessage,
        payload: OutboundPayload,
    ) -> None:
        """Persist and broadcast outbound delivery failures."""

        destination = payload.destination_hex or self._message_destination_hex(message)
        entry = self._update_outbound_chat_state(
            message=message,
            payload=payload,
            state="failed",
            destination=destination,
        )
        entry = self._augment_outbound_delivery_metadata(entry, payload)
        event_log = getattr(self, "event_log", None)
        if event_log is None:
            return
        destination_label = self._lookup_identity_label(destination) if destination else "unknown"
        event_log.add_event(
            "message_delivery_failed",
            f"Message delivery failed for {destination_label}",
            metadata=entry,
        )

    def _augment_outbound_delivery_metadata(
        self,
        entry: dict[str, object],
        payload: OutboundPayload,
    ) -> dict[str, object]:
        """Add retry and propagation metadata to outbound event entries."""

        augmented = dict(entry)
        if payload.attempts > 0:
            augmented["direct_attempts"] = payload.attempts
        if payload.delivery_mode != "propagated":
            return augmented
        augmented["fallback_reason"] = "direct_delivery_failed"
        augmented["delivery_method"] = (
            "local_propagation_store"
            if payload.local_propagation_fallback
            else "propagated"
        )
        if payload.propagation_node_hex:
            augmented["propagation_node"] = payload.propagation_node_hex
        return augmented

    def _build_outbound_attempt_metadata(
        self,
        payload: OutboundPayload,
    ) -> dict[str, object]:
        """Build event metadata for retry and fallback transitions."""

        timestamp = _utcnow().isoformat()
        topic_id = self._extract_target_topic(payload.fields)
        scope = "topic" if topic_id else "dm"
        if not payload.destination_hex and not topic_id:
            scope = "broadcast"
        entry: dict[str, object] = {
            "MessageID": payload.chat_message_id,
            "Direction": "outbound",
            "Scope": scope,
            "State": "sent",
            "Content": payload.message_text,
            "Source": self._origin_rch_hex() or self._hub_sender_label(),
            "Destination": payload.destination_hex,
            "TopicID": topic_id,
            "Attachments": [],
            "CreatedAt": timestamp,
            "UpdatedAt": timestamp,
            "SourceHash": self._origin_rch_hex(),
            "SourceLabel": self._hub_sender_label(),
            "Timestamp": timestamp,
        }
        return self._augment_outbound_delivery_metadata(entry, payload)

    def _resolve_propagation_node_label(self, payload: OutboundPayload) -> str:
        """Return the most useful label for the selected propagation node."""

        if payload.local_propagation_fallback:
            return self._hub_sender_label()
        if payload.propagation_node_hex:
            return self._lookup_identity_label(payload.propagation_node_hex)
        return "unknown"

    def _select_best_propagation_node(self) -> PropagationNodeCandidate | None:
        """Return the current best remote propagation node and activate it."""

        registry = getattr(self, "_propagation_node_registry", None)
        if registry is None:
            return None
        return registry.best_candidate()

    def _handle_outbound_retry_scheduled(self, payload: OutboundPayload) -> None:
        """Record a direct-delivery retry event."""

        event_log = getattr(self, "event_log", None)
        if event_log is None:
            return
        destination_label = (
            self._lookup_identity_label(payload.destination_hex)
            if payload.destination_hex
            else "unknown"
        )
        event_log.add_event(
            "message_delivery_retrying",
            f"Retrying message delivery to {destination_label}",
            metadata=self._build_outbound_attempt_metadata(payload),
        )

    def _handle_outbound_propagation_fallback(self, payload: OutboundPayload) -> None:
        """Record that direct delivery exhausted and propagation fallback is in use."""

        event_log = getattr(self, "event_log", None)
        if event_log is None:
            return
        destination_label = (
            self._lookup_identity_label(payload.destination_hex)
            if payload.destination_hex
            else "unknown"
        )
        if payload.local_propagation_fallback:
            message = f"Direct delivery exhausted; stored message for local propagation to {destination_label}"
        else:
            node_label = self._resolve_propagation_node_label(payload)
            message = (
                "Direct delivery exhausted; queued message for propagation to"
                f" {destination_label} via {node_label}"
            )
        event_log.add_event(
            "message_propagation_queued",
            message,
            metadata=self._build_outbound_attempt_metadata(payload),
        )

    def _update_outbound_chat_state(
        self,
        *,
        message: LXMF.LXMessage,
        payload: OutboundPayload,
        state: str,
        destination: str | None,
    ) -> dict[str, object]:
        """Return metadata for outbound delivery state transitions."""

        timestamp = _utcnow()
        source_hash = self._origin_rch_hex()
        source_label = self._hub_sender_label()
        topic_id = self._extract_target_topic(getattr(message, "fields", None))
        chat_message_id = payload.chat_message_id
        api = getattr(self, "api", None)

        if api is not None and chat_message_id and hasattr(api, "update_chat_message_state"):
            try:
                updated = api.update_chat_message_state(chat_message_id, state)
            except Exception as exc:  # pragma: no cover - defensive log
                RNS.log(
                    f"Failed to update chat message state for '{chat_message_id}': {exc}",
                    getattr(RNS, "LOG_WARNING", 2),
                )
            else:
                if updated is not None:
                    entry = updated.to_dict()
                    entry["SourceHash"] = source_hash
                    entry["SourceLabel"] = source_label
                    entry["Timestamp"] = timestamp.isoformat()
                    self._notify_message_listeners(entry)
                    return entry

        scope = "topic" if topic_id else "dm"
        if not destination and not topic_id:
            scope = "broadcast"
        return {
            "MessageID": chat_message_id or self._message_id_hex(message),
            "Direction": "outbound",
            "Scope": scope,
            "State": state,
            "Content": payload.message_text,
            "Source": source_hash or source_label,
            "Destination": destination,
            "TopicID": topic_id,
            "Attachments": [],
            "CreatedAt": timestamp.isoformat(),
            "UpdatedAt": timestamp.isoformat(),
            "SourceHash": source_hash,
            "SourceLabel": source_label,
            "Timestamp": timestamp.isoformat(),
        }

    def dispatch_marker_event(self, marker: Marker, event_type: str) -> bool:
        """Dispatch marker announcements and telemetry events.

        Args:
            marker (Marker): Marker metadata to dispatch.
            event_type (str): Marker event type string.

        Returns:
            bool: True when the telemetry payload is recorded.
        """

        manager = getattr(self, "marker_manager", None)
        if manager is None:
            RNS.log("Marker manager unavailable; dropping marker event.")
            return False
        if event_type in {"marker.created", "marker.updated"}:
            manager.announce_marker(marker)
        return manager.dispatch_marker_telemetry(marker, event_type)

    def _handle_config_reload(self, _config: "HubAppConfig") -> None:
        """Handle configuration reloads by recomputing capabilities.

        Args:
            _config (HubAppConfig): Updated configuration snapshot.
        """

        self._refresh_announce_capabilities(trigger_announce=True)

    def _announce_capabilities_settings(self) -> AnnounceCapabilitiesConfig:
        """Return announce capability settings from runtime config.

        Returns:
            AnnounceCapabilitiesConfig: Capability announce settings.
        """

        config_manager = self.config_manager or HubConfigurationManager(
            storage_path=self.storage_path
        )
        runtime = config_manager.runtime_config
        return AnnounceCapabilitiesConfig(
            enabled=bool(
                getattr(runtime, "announce_capabilities_enabled", True)
            ),
            max_bytes=int(
                getattr(runtime, "announce_capabilities_max_bytes", 256)
            ),
            include_version=bool(
                getattr(runtime, "announce_capabilities_include_version", True)
            ),
            include_timestamp=bool(
                getattr(runtime, "announce_capabilities_include_timestamp", False)
            ),
        )

    def _derive_announce_capabilities(self) -> list[str]:
        """Derive capability identifiers from configuration and runtime state.

        Returns:
            list[str]: Capability identifiers to advertise.
        """

        caps: list[str] = []
        if (
            getattr(self, "command_manager", None) is not None
            and getattr(self, "api", None) is not None
        ):
            caps.append("topic_broker")
            caps.append("group_chat")
        if getattr(self, "tel_controller", None) is not None:
            caps.append("telemetry_relay")
        if getattr(self, "api", None) is not None:
            caps.append("attachments")
        if getattr(self, "tak_connector", None) is not None:
            caps.append("tak_bridge")
        return normalize_capability_list(caps)

    def _resolve_rch_version(
        self, settings: AnnounceCapabilitiesConfig
    ) -> str | None:
        """Return the RCH version string when configured.

        Args:
            settings (AnnounceCapabilitiesConfig): Capability settings.

        Returns:
            str | None: Version string when enabled, otherwise ``None``.
        """

        if not settings.include_version:
            return None
        config_manager = self.config_manager
        if config_manager is None:
            return None
        version = getattr(config_manager.config, "app_version", None)
        if not version:
            return None
        return str(version)

    def _refresh_announce_capabilities(
        self,
        *,
        trigger_announce: bool = False,
        log_startup: bool = False,
    ) -> None:
        """Recompute the announce capability payload.

        Args:
            trigger_announce (bool): When True, send an announce if changed.
            log_startup (bool): When True, emit the startup capabilities log.
        """

        settings = self._announce_capabilities_settings()
        if not settings.enabled:
            with self._announce_capabilities_lock:
                self._announce_capabilities_state = None
                self._announce_capabilities_enabled = False
            if log_startup and not self._announce_capabilities_logged:
                RNS.log(
                    "Announce capabilities disabled",
                    getattr(RNS, "LOG_INFO", 3),
                )
                self._announce_capabilities_logged = True
            return

        payload = build_capability_payload(
            rch_version=self._resolve_rch_version(settings),
            caps=self._derive_announce_capabilities(),
            roles=None,
            include_timestamp=settings.include_timestamp,
        )
        result = encode_capability_payload(
            payload,
            encoder=self._announce_capabilities_encoder,
            max_bytes=settings.max_bytes,
        )
        with self._announce_capabilities_lock:
            previous = self._announce_capabilities_state
            changed = previous is None or previous.encoded != result.encoded
            self._announce_capabilities_state = result
            self._announce_capabilities_enabled = True

        if result.truncated and (
            previous is None or not previous.truncated or changed
        ):
            RNS.log(
                "Announce capabilities truncated to fit max bytes",
                getattr(RNS, "LOG_WARNING", 2),
            )

        if log_startup and not self._announce_capabilities_logged:
            caps = result.payload.get("caps", [])
            RNS.log(
                f"Announce capabilities: {caps} ({result.encoded_size_bytes} bytes)",
                getattr(RNS, "LOG_INFO", 3),
            )
            self._announce_capabilities_logged = True

        if changed and trigger_announce:
            self._send_announce(recompute_capabilities=False, reason="capabilities")

    def _build_announce_app_data(self) -> bytes | None:
        """Return announce app-data with optional capabilities appended.

        Returns:
            bytes | None: Encoded announce app-data.
        """

        destination = getattr(self, "my_lxmf_dest", None)
        if destination is None:
            return None
        base_app_data = None
        try:
            base_app_data = self._invoke_router_hook(
                "get_announce_app_data", destination.hash
            )
        except Exception as exc:  # pragma: no cover - defensive
            RNS.log(
                f"Failed to build base announce app data: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )

        if not self._announce_capabilities_enabled:
            return base_app_data

        state = self._announce_capabilities_state
        if state is None:
            return base_app_data
        try:
            return append_capabilities_to_announce_app_data(
                base_app_data,
                state.encoded,
            )
        except Exception as exc:  # pragma: no cover - defensive
            RNS.log(
                f"Failed to append announce capabilities: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return base_app_data

    def announce_capabilities_snapshot(self) -> dict[str, object]:
        """Return the current announced capability payload.

        Returns:
            dict[str, object]: Capability snapshot payload and encoded size.
        """

        if (
            self._announce_capabilities_state is None
            and self._announce_capabilities_enabled
        ):
            self._refresh_announce_capabilities()
        with self._announce_capabilities_lock:
            state = self._announce_capabilities_state
            enabled = self._announce_capabilities_enabled
        if not enabled or state is None:
            return {"capabilities": None, "encoded_size_bytes": 0}
        return {
            "capabilities": state.payload,
            "encoded_size_bytes": state.encoded_size_bytes,
        }

    def _announce_propagation_aspect(self, *, reason: str = "") -> None:
        """Announce the propagation destination when the node is active.

        Args:
            reason (str): Optional log label for diagnostics.
        """

        router = getattr(self, "lxm_router", None)
        if router is None:
            return
        if not bool(getattr(router, "propagation_node", False)):
            return

        try:
            self._invoke_router_hook("announce_propagation_node")
            message = "LXMF propagation announced"
            if reason:
                message = f"{message} ({reason})"
            RNS.log(
                message,
                getattr(RNS, "LOG_DEBUG", self.loglevel),
            )
        except Exception as exc:  # pragma: no cover - defensive
            RNS.log(
                f"Propagation announce failed: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )

    def _send_announce(
        self, *, recompute_capabilities: bool = True, reason: str = "manual"
    ) -> bool:
        """Send a Reticulum announce with optional capabilities.

        Args:
            recompute_capabilities (bool): Whether to recompute capabilities.
            reason (str): Log label for the announce reason.

        Returns:
            bool: True when the announce is dispatched.
        """

        destination = getattr(self, "my_lxmf_dest", None)
        if destination is None:
            RNS.log(
                "Announce skipped; no LXMF destination available.",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return False
        if recompute_capabilities:
            self._refresh_announce_capabilities()
        app_data = None
        if self._announce_capabilities_enabled:
            app_data = self._build_announce_app_data()
        try:
            if app_data is None:
                destination.announce()
            else:
                destination.announce(app_data=app_data)
            message = "LXMF identity announced"
            if reason:
                message = f"{message} ({reason})"
            RNS.log(
                message,
                getattr(RNS, "LOG_DEBUG", self.loglevel),
            )
            self._announce_propagation_aspect(reason=reason)
            self._announce_active_markers()
            return True
        except Exception as exc:  # pragma: no cover - defensive
            RNS.log(
                f"Announce failed: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return False

    def send_announce(self) -> bool:
        """Send an immediate Reticulum announce.

        Returns:
            bool: True when the announce was dispatched.
        """

        return self._send_announce(reason="manual")

    def get_propagation_startup_status(self) -> dict[str, object]:
        """Return the embedded propagation startup state."""

        embedded = self.embedded_lxmd
        if embedded is None:
            return {
                "enabled": False,
                "start_mode": "external",
                "state": "unmanaged",
                "ready": False,
                "last_error": None,
                "index_duration_seconds": None,
                "startup_prune": None,
            }
        status = embedded.propagation_startup_status()
        return cast(dict[str, object], status)

    def _announce_active_markers(self) -> None:
        """Announce non-expired marker objects on schedule."""

        manager = getattr(self, "marker_manager", None)
        service = getattr(self, "marker_service", None)
        if manager is None or service is None:
            return
        try:
            markers = service.list_markers()
        except Exception as exc:  # pragma: no cover - defensive logging
            RNS.log(
                f"Failed to list markers for announce: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return
        manager.announce_active_markers(markers)

    def _origin_rch_hex(self) -> str:
        """Return the local collector identity hash as lowercase hex."""

        destination = getattr(self, "my_lxmf_dest", None)
        identity_hash = getattr(destination, "hash", None)
        if isinstance(identity_hash, (bytes, bytearray, memoryview)):
            return bytes(identity_hash).hex()
        return ""

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
                delivery_receipt_callback=self._handle_outbound_delivery_receipt,
                delivery_failure_callback=self._handle_outbound_delivery_failure,
                propagation_selector=self._select_best_propagation_node,
                retry_scheduled_callback=self._handle_outbound_retry_scheduled,
                propagation_fallback_callback=self._handle_outbound_propagation_fallback,
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
            hash_key = source_hash.hex().lower()
            pretty = RNS.prettyhexrep(source_hash)
        elif source_hash:
            hash_key = str(source_hash).lower()
            pretty = hash_key
        else:
            return "unknown"
        label = self.identities.get(hash_key)
        if not label:
            api = getattr(self, "api", None)
            if api is not None and hasattr(api, "resolve_identity_display_name"):
                try:
                    label = api.resolve_identity_display_name(hash_key)
                except Exception as exc:  # pragma: no cover - defensive log
                    RNS.log(
                        f"Failed to resolve announce display name for {hash_key}: {exc}",
                        getattr(RNS, "LOG_WARNING", 2),
                    )
                if label:
                    self.identities[hash_key] = label
        return label or pretty

    def _backfill_identity_announces(self) -> None:
        api = getattr(self, "api", None)
        storage = getattr(api, "_storage", None)
        if storage is None:
            return
        try:
            records = storage.list_identity_announces()
        except Exception as exc:  # pragma: no cover - defensive log
            RNS.log(
                f"Failed to load announce records for backfill: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return

        if not records:
            return

        existing = {record.destination_hash.lower() for record in records}
        created = 0
        for record in records:
            if not record.display_name:
                continue
            try:
                destination_bytes = bytes.fromhex(record.destination_hash)
            except ValueError:
                continue
            identity = RNS.Identity.recall(destination_bytes)
            if identity is None:
                continue
            identity_hash = identity.hash.hex().lower()
            if identity_hash in existing:
                continue
            try:
                api.record_identity_announce(
                    identity_hash,
                    display_name=record.display_name,
                    source_interface="identity",
                )
            except Exception as exc:  # pragma: no cover - defensive log
                RNS.log(
                    (
                        "Failed to backfill announce metadata for "
                        f"{identity_hash}: {exc}"
                    ),
                    getattr(RNS, "LOG_WARNING", 2),
                )
                continue
            existing.add(identity_hash)
            created += 1

        if created:
            RNS.log(
                f"Backfilled {created} identity announce records for display names.",
                getattr(RNS, "LOG_INFO", 3),
            )

    def _load_persisted_clients(self) -> None:
        api = getattr(self, "api", None)
        if api is None:
            return
        try:
            clients = api.list_clients()
        except Exception as exc:  # pragma: no cover - defensive log
            RNS.log(
                f"Failed to load persisted clients: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return

        loaded = 0
        for client in clients:
            identity = getattr(client, "identity", None)
            if not identity:
                continue
            try:
                identity_hash = bytes.fromhex(identity)
            except ValueError:
                continue
            if identity_hash in self.connections:
                continue
            try:
                recalled = RNS.Identity.recall(identity_hash, from_identity_hash=True)
            except Exception:
                recalled = None
            if recalled is None:
                continue
            try:
                dest = RNS.Destination(
                    recalled,
                    RNS.Destination.OUT,
                    RNS.Destination.SINGLE,
                    "lxmf",
                    "delivery",
                )
            except Exception:
                continue
            self.connections[dest.identity.hash] = dest
            loaded += 1

        if loaded:
            RNS.log(
                f"Loaded {loaded} persisted clients into the connection cache.",
                getattr(RNS, "LOG_INFO", 3),
            )

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

    @staticmethod
    def _relay_standard_fields(fields: dict | None) -> dict | None:
        """Return relay-safe standard LXMF metadata fields.

        The hub forwards threading and group metadata so downstream clients keep
        conversation context when messages are relayed.
        """

        if not isinstance(fields, dict):
            return None
        relayed: dict = {}
        for key in (LXMF.FIELD_THREAD, LXMF.FIELD_GROUP):
            value = fields.get(key)
            if value is not None:
                relayed[key] = value
        return relayed or None

    @classmethod
    def _merge_standard_fields(
        cls,
        *,
        source_fields: dict | None,
        extra_fields: dict | None,
    ) -> dict | None:
        """Merge relay-safe standard fields with explicit outbound fields."""

        merged: dict = {}
        relayed = cls._relay_standard_fields(source_fields)
        if relayed:
            merged.update(relayed)
        if isinstance(extra_fields, dict):
            merged.update(extra_fields)
        return merged or None

    @staticmethod
    def _build_event_field(
        *,
        event_type: str,
        direction: str | None = None,
        topic_id: str | None = None,
        source_hash: str | None = None,
        destination: str | None = None,
    ) -> dict[str, object]:
        """Return a structured event payload for FIELD_EVENT."""

        payload: dict[str, object] = {
            "event_type": event_type,
            "ts": int(time.time()),
            "source": "rch",
        }
        if direction:
            payload["direction"] = direction
        if topic_id:
            payload["topic_id"] = topic_id
        if source_hash:
            payload["source_hash"] = source_hash
        if destination:
            payload["destination"] = destination
        return payload

    def _format_chat_broadcast_text(
        self,
        *,
        source_label: str,
        content_text: str,
        topic_id: str | None,
    ) -> str:
        """Build the relayed chat text for topic and non-topic messages."""

        if not topic_id:
            return f"{source_label} > {content_text}"

        topic_path = self._resolve_topic_path(topic_id)
        return f"{topic_path}: {source_label} > {content_text}"

    def _hub_sender_label(self) -> str:
        """Return the sender label used for hub-originated chat messages."""

        display_name = getattr(self, "display_name", None)
        if isinstance(display_name, str):
            normalized = display_name.strip()
            if normalized:
                return normalized
        return "Hub"

    @staticmethod
    def _has_sender_prefix(content_text: str) -> bool:
        """Return True when ``content_text`` already contains ``User > Text``."""

        if not isinstance(content_text, str):
            return False
        separator = " > "
        left, marker, right = content_text.partition(separator)
        if marker != separator:
            return False
        return bool(left.strip() and right.strip())

    def _resolve_topic_path(self, topic_id: str) -> str:
        """Return the topic path for ``topic_id`` when available."""

        fallback = str(topic_id)
        api = getattr(self, "api", None)
        if api is None:
            return fallback

        resolver = getattr(api, "retrieve_topic", None)
        if not callable(resolver):
            return fallback

        try:
            topic = resolver(topic_id)
        except Exception:
            return fallback

        topic_path = getattr(topic, "topic_path", None)
        if isinstance(topic_path, str):
            normalized = topic_path.strip()
            if normalized:
                return normalized
        return fallback

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
    def _mission_commands_affect_subscribers(commands: list[dict] | None) -> bool:
        """Return True when mission-sync commands modify subscriber mappings."""

        if not commands:
            return False
        for command in commands:
            if not isinstance(command, dict):
                continue
            command_type = command.get("command_type")
            if command_type == "topic.subscribe":
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

    @staticmethod
    def _message_destination_hex(message: LXMF.LXMessage) -> str | None:
        destination_hash = getattr(message, "destination_hash", None)
        if isinstance(destination_hash, (bytes, bytearray, memoryview)) and destination_hash:
            return bytes(destination_hash).hex().lower()
        if isinstance(destination_hash, str) and destination_hash:
            return destination_hash.lower()
        return None

    @staticmethod
    def _message_id_hex(message: LXMF.LXMessage) -> str | None:
        message_id = getattr(message, "message_id", None) or getattr(message, "hash", None)
        if isinstance(message_id, (bytes, bytearray)) and message_id:
            return message_id.hex().lower()
        if isinstance(message_id, str) and message_id:
            return message_id.lower()
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

        identities = getattr(self, "identities", {}) or {}
        if isinstance(identities, dict) and sender_hex.lower() in {
            str(key).lower() for key in identities
        }:
            return True

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

        self._reply_with_command_handler(
            message, "_handle_get_app_info", "app info reply"
        )

    def _reply_with_help(self, message: LXMF.LXMessage) -> None:
        """Send a help reply to the given message source.

        Args:
            message (LXMF.LXMessage): Message requiring a help reply.
        """

        self._reply_with_command_handler(message, "_handle_help", "help reply")

    def _reply_with_command_handler(
        self,
        message: LXMF.LXMessage,
        handler_name: str,
        response_label: str,
    ) -> None:
        """Reply using a command manager handler when available."""

        command_manager = getattr(self, "command_manager", None)
        router = getattr(self, "lxm_router", None)
        if command_manager is None or router is None:
            return
        handler = getattr(command_manager, handler_name, None)
        if handler is None:
            return
        try:
            response = handler(message)
        except Exception as exc:  # pragma: no cover - defensive log
            RNS.log(
                f"Unable to build {response_label}: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return
        try:
            router.handle_outbound(response)
        except Exception as exc:  # pragma: no cover - defensive log
            RNS.log(
                f"Unable to send {response_label}: {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )

    def _persist_attachments_from_fields(
        self, message: LXMF.LXMessage, *, topic_id: str | None = None
    ) -> tuple[list[LXMF.LXMessage], list[FileAttachment]]:
        """
        Persist file and image attachments from LXMF fields.

        Args:
            message (LXMF.LXMessage): Incoming LXMF message that may include
                ``FIELD_FILE_ATTACHMENTS`` or ``FIELD_IMAGE`` entries.

        Returns:
            tuple[list[LXMF.LXMessage], list[FileAttachment]]: Replies acknowledging
                stored attachments and the stored attachment records.
        """

        if not message.fields:
            return [], []
        stored_files, file_errors = self._store_attachment_payloads(
            message.fields.get(LXMF.FIELD_FILE_ATTACHMENTS),
            category="file",
            default_prefix="file",
            topic_id=topic_id,
        )
        stored_images, image_errors = self._store_attachment_payloads(
            message.fields.get(LXMF.FIELD_IMAGE),
            category="image",
            default_prefix="image",
            topic_id=topic_id,
        )
        stored_attachments = stored_files + stored_images
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
        return acknowledgements, stored_attachments

    def _store_attachment_payloads(
        self, payload, *, category: str, default_prefix: str, topic_id: str | None = None
    ) -> tuple[list[FileAttachment], list[str]]:
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
        stored: list[FileAttachment] = []
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
                topic_id=topic_id,
            )
            if stored_entry is not None:
                stored.append(stored_entry)
        return stored, errors

    def _attachment_payload(self, attachment: FileAttachment) -> list:
        """Return an LXMF-compatible attachment payload list."""

        file_path = Path(attachment.path)
        data = file_path.read_bytes()
        if attachment.media_type:
            return [attachment.name, data, attachment.media_type]
        return [attachment.name, data]

    def _build_lxmf_attachment_fields(
        self, attachments: list[FileAttachment]
    ) -> dict | None:
        """Build LXMF fields for outbound attachments."""

        if not attachments:
            return None
        file_payloads: list[list] = []
        image_payloads: list[list] = []
        for attachment in attachments:
            payload = self._attachment_payload(attachment)
            category = (attachment.category or "").lower()
            if category == "image":
                image_payloads.append(payload)
                file_payloads.append(payload)
            else:
                file_payloads.append(payload)
        fields: dict = {}
        if file_payloads:
            fields[LXMF.FIELD_FILE_ATTACHMENTS] = file_payloads
        if image_payloads:
            fields[LXMF.FIELD_IMAGE] = image_payloads
        return fields

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
        if isinstance(payload, (list, tuple)):
            if self._is_single_attachment_sequence(payload):
                entries = [payload]
        else:
            entries = [payload]
        normalized: list[dict] = []
        for index, entry in enumerate(entries):
            parsed = self._parse_attachment_entry(
                entry, category=category, default_prefix=default_prefix, index=index
            )
            if parsed is not None:
                normalized.append(parsed)
        return normalized

    @staticmethod
    def _is_single_attachment_sequence(payload: list | tuple) -> bool:
        """Return True when a sequence most likely represents one attachment entry."""

        if not payload:
            return False
        if all(isinstance(item, int) for item in payload):
            return True
        first = payload[0]
        if isinstance(first, (dict, list, tuple)):
            return False
        if any(
            ReticulumTelemetryHub._is_binary_attachment_candidate(item)
            for item in payload
        ):
            return True
        if len(payload) == 1:
            return True
        if len(payload) <= 3 and isinstance(first, str):
            return True
        return False

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
        extension_hint = None
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
            parsed = self._parse_sequence_attachment_entry(entry)
            if parsed:
                data = parsed.get("data")
                media_type = parsed.get("media_type")
                name = parsed.get("name")
                extension_hint = parsed.get("extension_hint")

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
        if not data:
            reason = "Empty attachment data"
            attachment_name = name or f"{category}-{index + 1}"
            RNS.log(
                f"Ignoring empty attachment payload (category={category}).",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return {"error": f"{reason}: {attachment_name}"}
        if not media_type and category == "image":
            media_type = self._infer_image_media_type(data)
        if not media_type and category == "image" and extension_hint:
            media_type = self._guess_image_media_type_from_extension(extension_hint)
        generated_name = None
        if category == "image" and not name and extension_hint:
            generated_name = self._image_name_from_extension(extension_hint)
        safe_name = self._sanitize_attachment_name(
            name
            or generated_name
            or self._default_attachment_name(default_prefix, index, media_type)
        )
        if media_type and not Path(safe_name).suffix:
            extension = self._guess_media_type_extension(media_type)
            if extension:
                safe_name = f"{safe_name}{extension}"
        media_type = media_type or self._guess_media_type(safe_name, category)
        return {"data": data, "name": safe_name, "media_type": media_type}

    def _parse_sequence_attachment_entry(self, entry: list | tuple) -> dict:
        """Parse list/tuple attachment formats into name/data/media_type parts."""

        if not entry:
            return {}

        if all(isinstance(item, int) for item in entry):
            return {"data": list(entry), "name": None, "media_type": None}

        data_index = None
        for index, item in enumerate(entry):
            if self._is_binary_attachment_candidate(item):
                data_index = index
                break

        if data_index is None:
            data_index = 1 if len(entry) >= 2 else 0

        data = entry[data_index]

        string_tokens: list[tuple[int, str]] = []
        for index, item in enumerate(entry):
            if index == data_index or not isinstance(item, str):
                continue
            token = item.strip()
            if token:
                string_tokens.append((index, token))

        media_type = None
        for _, token in string_tokens:
            if self._looks_like_media_type(token):
                media_type = token
                break

        name = self._select_attachment_name_token(
            string_tokens, media_type=media_type
        )
        extension_hint = self._extract_extension_hint_from_tokens(string_tokens)

        return {
            "data": data,
            "name": name,
            "media_type": media_type,
            "extension_hint": extension_hint,
        }

    @staticmethod
    def _is_binary_attachment_candidate(value) -> bool:
        """Return True for values that are likely raw attachment bytes."""

        if isinstance(value, (bytes, bytearray, memoryview)):
            return True
        return isinstance(value, (list, tuple)) and bool(value) and all(
            isinstance(item, int) for item in value
        )

    @staticmethod
    def _looks_like_media_type(value: str) -> bool:
        """Return True when a token resembles a MIME media type."""

        return bool(
            re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*",
                value,
            )
        )

    @staticmethod
    def _looks_like_extension_label(value: str) -> bool:
        """Return True when a token looks like an extension-only label."""

        token = value.strip().lstrip(".").lower()
        return token in {
            "jpg",
            "jpeg",
            "png",
            "gif",
            "bmp",
            "webp",
            "tif",
            "tiff",
            "heic",
            "heif",
        }

    @staticmethod
    def _looks_like_filename_token(value: str) -> bool:
        """Return True when a token is likely an actual filename."""

        candidate = Path(value).name
        if not candidate:
            return False
        if any(separator in value for separator in ("/", "\\")):
            return True
        if Path(candidate).suffix:
            return True
        return False

    def _select_attachment_name_token(
        self,
        string_tokens: list[tuple[int, str]],
        *,
        media_type: str | None,
    ) -> str | None:
        """Pick the most likely filename token from string values."""

        if not string_tokens:
            return None
        non_media_tokens = [
            token for _, token in string_tokens if not media_type or token != media_type
        ]
        if not non_media_tokens:
            return None

        for token in non_media_tokens:
            if self._looks_like_filename_token(token):
                return token

        for token in non_media_tokens:
            if not self._looks_like_extension_label(token):
                return token

        return None

    def _extract_extension_hint_from_tokens(
        self, string_tokens: list[tuple[int, str]]
    ) -> str | None:
        """Return an image extension hint from string tokens when present."""

        if not string_tokens:
            return None
        for _, token in string_tokens:
            normalized = self._normalize_extension_token(token)
            if normalized:
                return normalized
        return None

    @staticmethod
    def _normalize_extension_token(value: str) -> str | None:
        """Normalize a token into an extension string without a leading dot."""

        token = value.strip().lower()
        if not token:
            return None
        if "/" in token and ReticulumTelemetryHub._looks_like_media_type(token):
            guessed = ReticulumTelemetryHub._guess_media_type_extension(token)
            if guessed:
                token = guessed.lstrip(".").lower()
        token = token.lstrip(".")
        if not token:
            return None
        if re.fullmatch(r"[a-z0-9]{2,8}", token):
            return token
        return None

    @staticmethod
    def _image_name_from_extension(extension: str) -> str:
        """Build timestamped image name from an extension hint."""

        timestamp = datetime.now().strftime("Image_%Y_%m_%d_%H_%M_%S")
        return f"{timestamp}.{extension}"

    @staticmethod
    def _guess_image_media_type_from_extension(extension: str) -> str | None:
        """Return an image media type from a file extension."""

        normalized = extension.strip().lstrip(".").lower()
        if not normalized:
            return None
        guessed, _ = mimetypes.guess_type(f"image.{normalized}")
        if guessed:
            return guessed
        fallback = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "bmp": "image/bmp",
            "webp": "image/webp",
        }
        return fallback.get(normalized)

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
        if guessed:
            return guessed
        fallback = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/bmp": ".bmp",
            "image/webp": ".webp",
        }
        guessed = fallback.get(media_type.lower(), "")
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
        topic_id: str | None,
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
                    target_path,
                    name=target_path.name,
                    media_type=media_type,
                    topic_id=topic_id,
                )
            return api.store_file(
                target_path,
                name=target_path.name,
                media_type=media_type,
                topic_id=topic_id,
            )
        except Exception as exc:  # pragma: no cover - defensive log
            RNS.log(
                f"Failed to persist {category} attachment '{name}': {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return None

    def _extract_attachment_topic_id(self, commands: list[dict] | None) -> str | None:
        """Return the TopicID from an AssociateTopicID command if provided."""

        if not commands:
            return None
        command_manager = getattr(self, "command_manager", None)
        normalizer = (
            getattr(command_manager, "_normalize_command_name", None)
            if command_manager is not None
            else None
        )
        for command in commands:
            if not isinstance(command, dict):
                continue
            name = command.get(PLUGIN_COMMAND) or command.get("Command")
            if not name:
                continue
            normalized = normalizer(name) if callable(normalizer) else name
            if normalized == CommandManager.CMD_ASSOCIATE_TOPIC_ID:
                topic_id = CommandManager._extract_topic_id(command)
                if topic_id:
                    return str(topic_id)
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
        response_fields = self._merge_standard_fields(
            source_fields=message.fields,
            extra_fields=fields,
        )
        if response_fields is None:
            response_fields = {}
        if LXMF.FIELD_EVENT not in response_fields:
            response_fields[LXMF.FIELD_EVENT] = self._build_event_field(
                event_type="rch.reply",
                direction="outbound",
                topic_id=self._extract_target_topic(message.fields),
            )
        return LXMF.LXMessage(
            destination,
            self.my_lxmf_dest,
            content,
            fields=apply_icon_appearance(response_fields),
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
        self._refresh_announce_capabilities(log_startup=True)
        if daemon_mode:
            self.start_daemon_workers(services=services)
        self._announce_active_markers()
        while not self._shutdown:
            self._send_announce(reason="periodic")
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
        self._refresh_announce_capabilities(trigger_announce=True)

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
            self._refresh_announce_capabilities(trigger_announce=True)

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
        if self._remove_mission_change_listener is not None:
            try:
                self._remove_mission_change_listener()
            finally:
                self._remove_mission_change_listener = None
        if self._announce_handler is not None:
            self._announce_handler.close()
            self._announce_handler = None
        self._propagation_announce_handler = None
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

    display_name = args.display_name
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
