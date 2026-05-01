"""Runtime config parsing helpers."""

from __future__ import annotations

import logging

from reticulum_telemetry_hub.config.manager_paths import _expand_user_path
from reticulum_telemetry_hub.config.models import HubRuntimeConfig


class RuntimeConfigMixin:
    """Load runtime options from config.ini."""

    def _load_runtime_config(self) -> HubRuntimeConfig:  # pylint: disable=too-many-locals
        """Construct the runtime configuration from ``config.ini``."""

        defaults = HubRuntimeConfig()
        self._ensure_directory(self.storage_path)
        hub_section = self._get_section("hub")
        services_value = hub_section.get("services", "")
        services = tuple(
            part.strip() for part in services_value.split(",") if part.strip()
        )

        reticulum_path = hub_section.get("reticulum_config_path")
        lxmf_path = hub_section.get("lxmf_router_config_path")
        telemetry_filename = hub_section.get(
            "telemetry_filename", defaults.telemetry_filename
        )
        marker_announce_interval = self._coerce_int(
            hub_section.get("marker_announce_interval_minutes")
            or hub_section.get("marker_announce_interval"),
            defaults.marker_announce_interval_minutes,
        )
        event_retention_days = self._coerce_int(
            hub_section.get("event_retention_days"),
            defaults.event_retention_days,
        )
        ws_status_fanout_mode = self._normalize_status_fanout_mode(
            hub_section.get("ws_status_fanout_mode"),
            default=defaults.ws_status_fanout_mode,
        )
        ws_status_refresh_interval_seconds = self._coerce_min_float(
            hub_section.get("ws_status_refresh_interval_seconds"),
            default=defaults.ws_status_refresh_interval_seconds,
            minimum=2.0,
        )
        chat_attachment_max_bytes = self._coerce_optional_int_min(
            hub_section.get("chat_attachment_max_bytes"),
            minimum=1,
        )
        if chat_attachment_max_bytes is None:
            chat_attachment_max_bytes = defaults.chat_attachment_max_bytes

        gps_section = self._get_section("gpsd")
        gps_host = gps_section.get("host", defaults.gpsd_host)
        gps_port = self._coerce_int(gps_section.get("port"), defaults.gpsd_port)

        file_section = self._get_section("files")
        image_section = self._get_section("images")
        api_section = self._get_section("api")

        files_path_value = file_section.get("path") or file_section.get("directory")
        images_path_value = image_section.get("path") or image_section.get("directory")

        file_storage_path = _expand_user_path(
            files_path_value or (self.storage_path / "files")
        )
        image_storage_path = _expand_user_path(
            images_path_value or (self.storage_path / "images")
        )

        file_storage_path = self._ensure_directory(file_storage_path)
        image_storage_path = self._ensure_directory(image_storage_path)

        api_pagination_page_size = self._coerce_optional_int_min(
            api_section.get("pagination_default_page_size"),
            minimum=1,
        )
        if api_pagination_page_size is None:
            api_pagination_page_size = defaults.api_pagination_page_size
        api_pagination_max_page_size = self._coerce_optional_int_min(
            api_section.get("pagination_max_page_size"),
            minimum=1,
        )
        if api_pagination_max_page_size is None:
            api_pagination_max_page_size = defaults.api_pagination_max_page_size
        if api_pagination_max_page_size < api_pagination_page_size:
            logging.warning(
                "Configured API pagination max page size is below the default page size; using %s.",
                api_pagination_page_size,
            )
            api_pagination_max_page_size = api_pagination_page_size

        announce_section = (
            self._get_section("announce.capabilities")
            or self._get_section("announce_capabilities")
            or self._get_section("announce")
        )
        announce_enabled = self._get_bool(
            announce_section,
            "enabled",
            defaults.announce_capabilities_enabled,
        )
        announce_max_bytes = self._coerce_int(
            announce_section.get("max_bytes"),
            defaults.announce_capabilities_max_bytes,
        )
        announce_include_version = self._get_bool(
            announce_section,
            "include_version",
            defaults.announce_capabilities_include_version,
        )
        announce_include_timestamp = self._get_bool(
            announce_section,
            "include_timestamp",
            defaults.announce_capabilities_include_timestamp,
        )
        if "announce.capabilities.enabled" in hub_section:
            announce_enabled = self._get_bool(
                hub_section,
                "announce.capabilities.enabled",
                announce_enabled,
            )
        if "announce.capabilities.max_bytes" in hub_section:
            announce_max_bytes = self._coerce_int(
                hub_section.get("announce.capabilities.max_bytes"),
                announce_max_bytes,
            )
        if "announce.capabilities.include_version" in hub_section:
            announce_include_version = self._get_bool(
                hub_section,
                "announce.capabilities.include_version",
                announce_include_version,
            )
        if "announce.capabilities.include_timestamp" in hub_section:
            announce_include_timestamp = self._get_bool(
                hub_section,
                "announce.capabilities.include_timestamp",
                announce_include_timestamp,
            )
        if "announce_capabilities_enabled" in hub_section:
            announce_enabled = self._get_bool(
                hub_section,
                "announce_capabilities_enabled",
                announce_enabled,
            )
        if "announce_capabilities_max_bytes" in hub_section:
            announce_max_bytes = self._coerce_int(
                hub_section.get("announce_capabilities_max_bytes"),
                announce_max_bytes,
            )
        if "announce_capabilities_include_version" in hub_section:
            announce_include_version = self._get_bool(
                hub_section,
                "announce_capabilities_include_version",
                announce_include_version,
            )
        if "announce_capabilities_include_timestamp" in hub_section:
            announce_include_timestamp = self._get_bool(
                hub_section,
                "announce_capabilities_include_timestamp",
                announce_include_timestamp,
            )

        display_name = self._normalize_display_name(hub_section.get("display_name"))
        if display_name is None:
            display_name = defaults.display_name

        return HubRuntimeConfig(
            display_name=display_name,
            announce_interval=self._coerce_int(
                hub_section.get("announce_interval"), defaults.announce_interval
            ),
            marker_announce_interval_minutes=marker_announce_interval,
            announce_capabilities_enabled=announce_enabled,
            announce_capabilities_max_bytes=announce_max_bytes,
            announce_capabilities_include_version=announce_include_version,
            announce_capabilities_include_timestamp=announce_include_timestamp,
            hub_telemetry_interval=self._coerce_int(
                hub_section.get("hub_telemetry_interval"),
                defaults.hub_telemetry_interval,
            ),
            service_telemetry_interval=self._coerce_int(
                hub_section.get("service_telemetry_interval"),
                defaults.service_telemetry_interval,
            ),
            outbound_workers=max(
                1,
                self._coerce_int(
                    hub_section.get("outbound_workers"),
                    defaults.outbound_workers,
                ),
            ),
            log_level=hub_section.get("log_level", defaults.log_level).lower(),
            embedded_lxmd=self._get_bool(
                hub_section, "embedded_lxmd", defaults.embedded_lxmd
            ),
            default_services=services,
            gpsd_host=gps_host,
            gpsd_port=gps_port,
            reticulum_config_path=(
                _expand_user_path(reticulum_path) if reticulum_path else None
            ),
            lxmf_router_config_path=(
                _expand_user_path(lxmf_path) if lxmf_path else None
            ),
            telemetry_filename=telemetry_filename,
            event_retention_days=event_retention_days,
            ws_status_fanout_mode=ws_status_fanout_mode,
            ws_status_refresh_interval_seconds=ws_status_refresh_interval_seconds,
            chat_attachment_max_bytes=chat_attachment_max_bytes,
            file_storage_path=file_storage_path,
            image_storage_path=image_storage_path,
            api_pagination_page_size=api_pagination_page_size,
            api_pagination_max_page_size=api_pagination_max_page_size,
        )

