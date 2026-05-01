"""Runtime configuration helpers for northbound services."""

from __future__ import annotations

from reticulum_telemetry_hub.api.models import ReticulumInfo


class NorthboundConfigMixin:
    """Refresh northbound service settings derived from runtime config."""

    def refresh_runtime_config(self) -> None:
        """Refresh service settings derived from the active runtime config."""

        config_manager = getattr(self.api, "_config_manager", None)
        runtime_config = getattr(config_manager, "runtime_config", None)
        if runtime_config is None:
            return
        self.pagination_default_page_size = int(
            getattr(
                runtime_config,
                "api_pagination_page_size",
                self.pagination_default_page_size,
            )
        )
        self.pagination_max_page_size = int(
            getattr(
                runtime_config,
                "api_pagination_max_page_size",
                self.pagination_max_page_size,
            )
        )

    def reload_config(self) -> ReticulumInfo:
        """Reload configuration from disk."""

        info = self.api.reload_config()
        self.refresh_runtime_config()
        return info
