"""Announce capability and propagation sync helpers."""
# ruff: noqa: F403,F405

from __future__ import annotations


import RNS

from reticulum_telemetry_hub.api.models import Marker
from reticulum_telemetry_hub.config.manager import HubConfigurationManager
from reticulum_telemetry_hub.config.models import HubAppConfig
import reticulum_telemetry_hub.lxmf_runtime  # noqa: F401
from reticulum_telemetry_hub.config.constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.announce_capabilities import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.delivery_defaults import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.propagation_selection import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_constants import *  # noqa: F403
from reticulum_telemetry_hub.reticulum_server.runtime_support import *  # noqa: F403


class RuntimeAnnounceMixin:
    """Announce capability and propagation sync helpers."""

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
        if (
            getattr(self, "mission_sync_router", None) is not None
            and getattr(self, "checklist_sync_router", None) is not None
        ):
            caps.append("r3akt")
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

