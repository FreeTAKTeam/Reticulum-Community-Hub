"""Reticulum Telemetry Hub API service operations."""

from __future__ import annotations

import string
from typing import Callable
from typing import Optional

from reticulum_telemetry_hub.config import HubConfigurationManager
from reticulum_telemetry_hub.config.models import HubAppConfig

from .filesystem import FileSystemAdapter
from .filesystem import LocalFileSystemAdapter
from .models import FileAttachment
from .models import ReticulumInfo
from .rem_registry_service import RemRegistryService
from .rights_service import SubjectAwareRightsService
from .service_attachments import ApiAttachmentChatMixin
from .service_clients import ApiClientRightsMixin
from .service_config_status import ApiConfigStatusMixin
from .service_identity_admin import ApiIdentityAdminMixin
from .service_topics import ApiTopicSubscriberMixin
from .storage import HubStorage

__all__ = [
    "FileAttachment",
    "ReticulumTelemetryHubAPI",
]


class ReticulumTelemetryHubAPI(  # pylint: disable=too-many-public-methods
    ApiClientRightsMixin,
    ApiAttachmentChatMixin,
    ApiTopicSubscriberMixin,
    ApiConfigStatusMixin,
    ApiIdentityAdminMixin,
):
    """Persistence-backed implementation of the ReticulumTelemetryHub API."""

    def __init__(
        self,
        config_manager: Optional[HubConfigurationManager] = None,
        storage: Optional[HubStorage] = None,
        on_config_reload: Optional[Callable[[HubAppConfig], None]] = None,
        filesystem: Optional[FileSystemAdapter] = None,
    ) -> None:
        """Initialize the API service with configuration and storage providers.

        Args:
            config_manager (Optional[HubConfigurationManager]): Manager
                supplying hub configuration. When omitted, a default manager
                loads the hub configuration and database path.
            storage (Optional[HubStorage]): Persistence provider for clients,
                topics, and subscribers. Defaults to storage built with the
                configuration's database path.
            filesystem (Optional[FileSystemAdapter]): Filesystem adapter used
                for file operations. Defaults to a local pathlib-backed
                implementation.

        """
        self._config_manager = config_manager or HubConfigurationManager()
        hub_db_path = self._config_manager.config.hub_database_path
        self._storage = storage or HubStorage(hub_db_path)
        self._filesystem = filesystem or LocalFileSystemAdapter()
        self._rights_storage = HubStorage(hub_db_path)
        self._rights = SubjectAwareRightsService(self._rights_storage)
        self._rem_registry = RemRegistryService(self._storage)
        self._file_category = "file"
        self._image_category = "image"
        self._on_config_reload = on_config_reload
        self._reticulum_destination: str | None = None
        self._topic_registry_change_listeners: list[Callable[[], None]] = []

    @property
    def rights(self) -> SubjectAwareRightsService:
        """Return the subject-aware rights service."""

        return self._rights

    def set_reticulum_destination(self, destination: str | None) -> None:
        """Set the Reticulum destination hash for app info responses.

        Args:
            destination (str | None): Hex-encoded destination hash. Provide
                ``None`` or whitespace to clear the value.

        Raises:
            ValueError: If ``destination`` is not a valid hex string.
        """

        if destination is None:
            self._reticulum_destination = None
            return

        cleaned = destination.strip()
        if not cleaned:
            self._reticulum_destination = None
            return

        if not all(char in string.hexdigits for char in cleaned):
            raise ValueError("destination must be a hex string")
        if len(cleaned) % 2 != 0:
            raise ValueError("destination must contain an even number of hex characters")

        self._reticulum_destination = cleaned.lower()

    def _build_reticulum_info(self, info_dict: dict) -> ReticulumInfo:
        """Return a ReticulumInfo model enriched with runtime data.

        Args:
            info_dict (dict): Base info payload from configuration.

        Returns:
            ReticulumInfo: Info snapshot including runtime destination data.
        """

        payload = dict(info_dict)
        payload["hub_display_name"] = self._config_manager.resolve_hub_display_name(
            destination_hash=self._reticulum_destination
        )
        payload["reticulum_destination"] = self._reticulum_destination
        return ReticulumInfo(**payload)

    def register_topic_registry_change_listener(
        self, listener: Callable[[], None]
    ) -> Callable[[], None]:
        """Register a callback invoked after topic/subscriber writes."""

        self._topic_registry_change_listeners.append(listener)

        def _remove_listener() -> None:
            if listener in self._topic_registry_change_listeners:
                self._topic_registry_change_listeners.remove(listener)

        return _remove_listener

    def _notify_topic_registry_change(self) -> None:
        """Notify listeners that topic subscriber mappings changed."""

        for listener in list(self._topic_registry_change_listeners):
            try:
                listener()
            except Exception:
                continue

    def _notify_config_reload(self, config: HubAppConfig) -> None:
        """Invoke the config reload callback when configured.

        Args:
            config (HubAppConfig): Updated configuration snapshot.
        """

        if self._on_config_reload is None:
            return
        self._on_config_reload(config)

    # ------------------------------------------------------------------ #
    # RTH operations
    # ------------------------------------------------------------------ #
