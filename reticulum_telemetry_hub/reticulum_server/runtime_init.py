"""Reticulum telemetry hub initialization."""
# ruff: noqa: F403,F405

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable
from typing import cast

import LXMF
import RNS

from reticulum_telemetry_hub.api.marker_identity import derive_marker_identity_key
from reticulum_telemetry_hub.api.marker_service import MarkerService
from reticulum_telemetry_hub.api.marker_storage import MarkerStorage
from reticulum_telemetry_hub.api.zone_service import ZoneService
from reticulum_telemetry_hub.api.zone_storage import ZoneStorage
from reticulum_telemetry_hub.checklist_sync import ChecklistSyncRouter
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.config.manager import HubConfigurationManager
from reticulum_telemetry_hub.embedded_lxmd import EmbeddedLxmd
import reticulum_telemetry_hub.lxmf_runtime  # noqa: F401
from reticulum_telemetry_hub.config.constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.announce_capabilities import *  # noqa: F403
from reticulum_telemetry_hub.atak_cot.tak_connector import TakConnector
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import TelemetryController
from reticulum_telemetry_hub.lxmf_telemetry.sampler import TelemetrySampler
from reticulum_telemetry_hub.lxmf_telemetry.telemeter_manager import TelemeterManager
from reticulum_telemetry_hub.mission_domain import EmergencyActionMessageService
from reticulum_telemetry_hub.mission_domain import MissionDomainService
from reticulum_telemetry_hub.mission_sync import MissionSyncRouter
from reticulum_telemetry_hub.reticulum_server.delivery_defaults import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.delivery_service import DeliveryService
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog
from reticulum_telemetry_hub.reticulum_server.event_log import resolve_event_log_path
from reticulum_telemetry_hub.reticulum_server.message_events import MessageEventEmitter
from reticulum_telemetry_hub.reticulum_server.message_router import MessageRouter
from reticulum_telemetry_hub.reticulum_server.delivery_policy import OutboundDeliveryPolicy
from reticulum_telemetry_hub.reticulum_server.internal_adapter import ReticulumInternalAdapter
from reticulum_telemetry_hub.reticulum_server.marker_objects import MarkerObjectManager
from reticulum_telemetry_hub.reticulum_server.rem_command_router import RemCommandRouter
from reticulum_telemetry_hub.reticulum_server.outbound_queue import OutboundMessageQueue
from reticulum_telemetry_hub.reticulum_server.propagation_selection import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_metrics_store import RuntimeMetricsStore
from reticulum_telemetry_hub.reticulum_server.command_manager import CommandManager
from reticulum_telemetry_hub.reticulum_server.runtime_constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_support import *  # noqa: F403

class RuntimeInitMixin:
    """Reticulum telemetry hub initialization."""

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
        outbound_delivery_receipt_timeout: float = DEFAULT_OUTBOUND_DELIVERY_RECEIPT_TIMEOUT,
        outbound_backoff: float = DEFAULT_OUTBOUND_BACKOFF,
        outbound_max_attempts: int = DEFAULT_OUTBOUND_MAX_ATTEMPTS,
        outbound_fanout_soft_max_recipients: int = DEFAULT_OUTBOUND_FANOUT_SOFT_MAX_RECIPIENTS,
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
            outbound_delivery_receipt_timeout (float): Seconds to wait for an
                LXMF delivery/failure callback before retrying or failing.
            outbound_backoff (float): Base number of seconds to wait between retry attempts.
            outbound_max_attempts (int): Number of attempts before an outbound message is dropped.
            outbound_fanout_soft_max_recipients (int): Soft cap for fan-out recipients per send tick.
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
        self.outbound_delivery_receipt_timeout = outbound_delivery_receipt_timeout
        self.outbound_backoff = outbound_backoff
        self.outbound_max_attempts = outbound_max_attempts
        self.outbound_fanout_soft_max_recipients = max(outbound_fanout_soft_max_recipients, 0)
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
        self.runtime_metrics = RuntimeMetricsStore()
        self.outbound_delivery_policy = OutboundDeliveryPolicy(self)
        self.tel_controller = TelemetryController(
            db_path=telemetry_db_path,
            event_log=self.event_log,
        )
        self._message_listeners: list[Callable[[dict[str, object]], None]] = []
        self.message_events = MessageEventEmitter(self)
        self.delivery_service = DeliveryService(self)
        self.message_router = MessageRouter(self)
        self.embedded_lxmd: EmbeddedLxmd | None = None
        self.telemetry_sampler: TelemetrySampler | None = None
        self.telemeter_manager: TelemeterManager | None = None
        self._shutdown = False
        self.connections: dict[bytes, RNS.Destination] = {}
        self._destination_cache: dict[str, RNS.Destination] = {}
        self._destination_cache_lock = threading.Lock()
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
        self.rem_command_router = None
        self.checklist_sync_router = None
        self.mission_domain_service = None
        self.emergency_action_message_service = None
        self._remove_mission_change_listener: Callable[[], None] | None = None
        self._remove_eam_status_listener: Callable[[], None] | None = None
        self._remove_topic_registry_change_listener: Callable[[], None] | None = None
        self._announce_handler: AnnounceHandler | None = None
        self._rem_app_announce_handler: AnnounceHandler | None = None
        self._propagation_node_registry = PropagationNodeRegistry()
        self._propagation_announce_handler: PropagationNodeAnnounceHandler | None = None
        self._propagation_sync_lock = threading.Lock()
        self._propagation_sync_stop_event = threading.Event()
        self._propagation_sync_thread: threading.Thread | None = None
        self._tak_async_runner = _AsyncTaskRunner(name="rch-tak-async")
        self._outbound_transition_log_window_seconds = 1.0
        self._outbound_transition_log_last_emitted: dict[str, float] = {}
        self._outbound_transition_log_lock = threading.Lock()

        identity = self.load_or_generate_identity(self.identity_path)
        destination_hash = self._delivery_destination_hash(identity)
        self.display_name = self.config_manager.resolve_hub_display_name(
            override=display_name,
            destination_hash=destination_hash,
        )
        lxmf_router_config = self.config_manager.config.lxmf_router
        delivery_display_name = lxmf_router_config.display_name or self.display_name

        hub_type = type(self)
        if hub_type._shared_lxm_router is None:
            hub_type._shared_lxm_router = LXMF.LXMRouter(
                **self._lxmf_router_init_kwargs()
            )
        shared_router = hub_type._shared_lxm_router
        if shared_router is None:
            msg = "Shared LXMF router failed to initialize"
            raise RuntimeError(msg)

        self.lxm_router = cast(LXMF.LXMRouter, shared_router)
        self._apply_lxmf_router_runtime_config()

        self.my_lxmf_dest = self._invoke_router_hook(
            "register_delivery_identity",
            identity,
            display_name=delivery_display_name,
        )

        self.identities: dict[str, str] = {}

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
                event_log=self.event_log,
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
        self.emergency_action_message_service = EmergencyActionMessageService(hub_db_path)
        self.api.set_reticulum_destination(self._origin_rch_hex())
        self._backfill_identity_announces()
        self._load_persisted_clients()
        self._remove_topic_registry_change_listener = (
            self.api.register_topic_registry_change_listener(
                self._invalidate_topic_registry
            )
        )
        self._announce_handler = AnnounceHandler(
            self.identities,
            api=self.api,
            capability_callback=self._update_identity_capability_cache,
            presence_callback=self._mark_presence_evidence,
        )
        self._rem_app_announce_handler = AnnounceHandler(
            self.identities,
            api=self.api,
            capability_callback=self._update_identity_capability_cache,
            presence_callback=self._mark_presence_evidence,
            aspect_filter=REM_APP_NAME,
            decode_display_name=False,
        )
        self._propagation_announce_handler = PropagationNodeAnnounceHandler(
            self._propagation_node_registry
        )
        RNS.Transport.register_announce_handler(self._announce_handler)
        RNS.Transport.register_announce_handler(self._rem_app_announce_handler)
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
            outbound_queue=self._ensure_outbound_queue(),
            event_log=self.event_log,
        )

        self.command_manager = CommandManager(
            self.connections,
            self.tel_controller,
            self.my_lxmf_dest,
            self.api,
            config_manager=self.config_manager,
            event_log=self.event_log,
            destination_removed_callback=self._evict_cached_destination,
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
            emergency_action_message_service=self.emergency_action_message_service,
            event_log=self.event_log,
            hub_identity_resolver=self._origin_rch_hex,
            field_results=LXMF.FIELD_RESULTS,
            field_event=LXMF.FIELD_EVENT,
            field_group=LXMF.FIELD_GROUP,
        )
        self.rem_command_router = RemCommandRouter(
            api=self.api,
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
        self._topic_registry_dirty = True
        self._refresh_topic_registry()
        if self.mission_domain_service is not None:
            self._remove_mission_change_listener = (
                self.mission_domain_service.register_mission_change_listener(
                    self._fanout_mission_change_to_recipients
                )
            )
        if self.emergency_action_message_service is not None:
            self._remove_eam_status_listener = (
                self.emergency_action_message_service.register_status_listener(
                    self._handle_eam_status_update
                )
            )
        self._tak_async_runner.start()
        self._invoke_router_hook("register_delivery_callback", self.delivery_callback)
        init_elapsed = time.monotonic() - init_started
        RNS.log(
            f"Hub initialization completed in {init_elapsed:.2f}s",
            getattr(RNS, "LOG_NOTICE", 3),
        )

