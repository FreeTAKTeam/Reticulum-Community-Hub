"""Daemon run, worker, and shutdown helpers."""
# ruff: noqa: F403,F405

from __future__ import annotations

import time
from pathlib import Path

import LXMF
import RNS

import reticulum_telemetry_hub.lxmf_runtime  # noqa: F401
from reticulum_telemetry_hub.config.constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.announce_capabilities import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.delivery_defaults import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.propagation_selection import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_events import report_nonfatal_exception
from reticulum_telemetry_hub.reticulum_server.services import SERVICE_FACTORIES
from reticulum_telemetry_hub.reticulum_server.services import HubService
from reticulum_telemetry_hub.reticulum_server.runtime_constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_support import *  # noqa: F403


class RuntimeLifecycleMixin:
    """Daemon run, worker, and shutdown helpers."""

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
        announce_interval = max(1, int(self.announce_interval))
        RNS.log(
            f"Starting headless hub; announcing every {announce_interval}s",
            getattr(RNS, "LOG_INFO", 3),
        )
        self._refresh_announce_capabilities(log_startup=True)
        self._start_propagation_sync_worker()
        if daemon_mode:
            self.start_daemon_workers(services=services)
        self._announce_active_markers()
        while not self._shutdown:
            self._send_announce(reason="periodic")
            time.sleep(announce_interval)

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
            service = factory(self)
        except Exception as exc:  # pragma: no cover - defensive
            report_nonfatal_exception(
                getattr(self, "event_log", None),
                "daemon_service_error",
                f"Failed to initialize daemon service '{name}': {exc}",
                exc,
                metadata={
                    "service": name,
                    "operation": "init",
                },
                log_level=RNS.LOG_ERROR,
            )
            return None
        service.event_log = getattr(self, "event_log", None)
        return service

    def shutdown(self):
        if self._shutdown:
            return
        self._shutdown = True
        self._stop_propagation_sync_worker()
        self.stop_daemon_workers()
        if self._remove_mission_change_listener is not None:
            try:
                self._remove_mission_change_listener()
            finally:
                self._remove_mission_change_listener = None
        if self._remove_eam_status_listener is not None:
            try:
                self._remove_eam_status_listener()
            finally:
                self._remove_eam_status_listener = None
        if self._remove_topic_registry_change_listener is not None:
            try:
                self._remove_topic_registry_change_listener()
            finally:
                self._remove_topic_registry_change_listener = None
        if self._announce_handler is not None:
            self._announce_handler.close()
            self._announce_handler = None
        if self._rem_app_announce_handler is not None:
            self._rem_app_announce_handler.close()
            self._rem_app_announce_handler = None
        self._propagation_announce_handler = None
        if self.embedded_lxmd is not None:
            self.embedded_lxmd.stop()
            self.embedded_lxmd = None
        tak_runner = getattr(self, "_tak_async_runner", None)
        if tak_runner is not None:
            tak_runner.stop(timeout=1.0)
        self.telemetry_sampler = None


