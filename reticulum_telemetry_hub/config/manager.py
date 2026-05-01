"""Helpers for reading and merging hub configuration files."""

from __future__ import annotations

from configparser import ConfigParser
from importlib import resources
from pathlib import Path
from typing import Mapping, Optional

from dotenv import load_dotenv as load_env

from reticulum_telemetry_hub.config.constants import DEFAULT_STORAGE_PATH
from reticulum_telemetry_hub.config.manager_coercion import ConfigCoercionMixin
from reticulum_telemetry_hub.config.manager_editing import ConfigEditingMixin
from reticulum_telemetry_hub.config.manager_external import ExternalConfigMixin
from reticulum_telemetry_hub.config.manager_paths import _expand_user_path
from reticulum_telemetry_hub.config.manager_runtime import RuntimeConfigMixin
from .models import (
    HubAppConfig,
    TakConnectionConfig,
)

_WS_STATUS_FANOUT_MODES = {"event_only", "periodic", "event_plus_periodic"}

def _load_default_config_template_text() -> str:
    """Return the packaged default config template text when available."""

    try:
        template = resources.files("reticulum_telemetry_hub.config").joinpath(
            "default_config.ini"
        )
        return template.read_text(encoding="utf-8")
    except (
        FileNotFoundError,
        ModuleNotFoundError,
        OSError,
        AttributeError,
    ):
        return ""


def _load_default_lxmf_router_template_text() -> str:
    """Return the packaged LXMF router template text when available."""

    try:
        template = resources.files("reticulum_telemetry_hub.config").joinpath(
            "default_lxmf_router_config.ini"
        )
        return template.read_text(encoding="utf-8")
    except (
        FileNotFoundError,
        ModuleNotFoundError,
        OSError,
        AttributeError,
    ):
        return ""


class HubConfigurationManager(  # pylint: disable=too-many-instance-attributes
    ConfigEditingMixin,
    RuntimeConfigMixin,
    ExternalConfigMixin,
    ConfigCoercionMixin,
):
    """Load hub related configuration files and expose them as Python objects."""

    def __init__(
        self,
        storage_path: Optional[Path] = None,
        config_path: Optional[Path] = None,
        reticulum_config_path: Optional[Path] = None,
        lxmf_router_config_path: Optional[Path] = None,
    ) -> None:
        """Load configuration files and prepare helpers.

        Args:
            storage_path (Optional[Path]): Root path for hub storage.
            reticulum_config_path (Optional[Path]): Override path to the
                Reticulum configuration file.
            lxmf_router_config_path (Optional[Path]): Override path to the
                LXMF router configuration file.
        """
        load_env()
        self._reticulum_config_override = (
            _expand_user_path(reticulum_config_path)
            if reticulum_config_path is not None
            else None
        )
        self._lxmf_router_config_override = (
            _expand_user_path(lxmf_router_config_path)
            if lxmf_router_config_path is not None
            else None
        )
        self.storage_path = _expand_user_path(storage_path or DEFAULT_STORAGE_PATH)
        self.config_path = _expand_user_path(
            config_path or self.storage_path / "config.ini"
        )
        self._write_default_config_if_missing()
        self._config_parser = self._load_config_parser(self.config_path)
        self.runtime_config = self._load_runtime_config()
        self._reload_external_config_paths()
        self._write_default_lxmf_router_config_if_missing()
        self._tak_config = self._load_tak_config()
        self._config = self._load()

    @property
    def config(self) -> HubAppConfig:
        """Return the aggregated hub configuration.

        Returns:
            HubAppConfig: Current configuration snapshot.
        """
        return self._config

    @property
    def tak_config(self) -> TakConnectionConfig:
        """Return the TAK connector configuration.

        Returns:
            TakConnectionConfig: Current TAK connection settings.
        """
        return self._tak_config

    @property
    def config_parser(self) -> ConfigParser:
        """Expose the raw ``ConfigParser`` loaded from disk."""

        return self._config_parser

    def reload(self) -> HubAppConfig:
        """Reload configuration files from disk and environment.

        Returns:
            HubAppConfig: Freshly parsed application configuration.
        """
        self._write_default_config_if_missing()
        self._config_parser = self._load_config_parser(self.config_path)
        self.runtime_config = self._load_runtime_config()
        self._reload_external_config_paths()
        self._write_default_lxmf_router_config_if_missing()
        self._tak_config = self._load_tak_config()
        self._config = self._load()
        return self._config

    @staticmethod
    def default_config_template_text() -> str:
        """Return the shipped config.ini template text."""

        return _load_default_config_template_text()

    @staticmethod
    def default_lxmf_router_template_text() -> str:
        """Return the shipped LXMF router template text."""

        return _load_default_lxmf_router_template_text()

    def reticulum_info_snapshot(self) -> dict:
        """Return a summary of Reticulum runtime configuration."""
        return self._config.to_reticulum_info_dict()

    def resolve_hub_display_name(
        self,
        *,
        override: str | None = None,
        destination_hash: bytes | bytearray | memoryview | str | None = None,
    ) -> str:
        """Resolve the hub name from override/config/default template.

        Args:
            override (str | None): Optional explicit name (for CLI overrides).
            destination_hash (bytes | bytearray | memoryview | str | None):
                Destination hash used by the generated fallback.

        Returns:
            str: Resolved hub display name.
        """

        explicit = self._normalize_display_name(override)
        if explicit is not None:
            return explicit

        configured = self._normalize_display_name(self.runtime_config.display_name)
        if configured is not None:
            return configured

        version = self._normalize_name_token(getattr(self._config, "app_version", None))
        dest_hash = self._normalize_destination_hash(destination_hash)
        return f"RCH_{version}_{dest_hash}"

    def _write_default_config_if_missing(self) -> None:
        """Create ``config.ini`` from the shipped template when absent."""

        if self.config_path.exists():
            return
        template_text = _load_default_config_template_text()
        if not template_text:
            return
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(template_text, encoding="utf-8")
        except OSError:
            # Reason: config.ini is optional and startup should proceed with built-in defaults.
            return

    def _write_default_lxmf_router_config_if_missing(self) -> None:
        """Create the default LXMF router config when the target file is absent."""

        if self.lxmf_router_config_path.exists():
            return
        template_text = _load_default_lxmf_router_template_text()
        if not template_text:
            return
        try:
            self.lxmf_router_config_path.parent.mkdir(parents=True, exist_ok=True)
            self.lxmf_router_config_path.write_text(template_text, encoding="utf-8")
        except OSError:
            # Reason: the dedicated LXMF config is optional and inline config.ini keys still work.
            return

    def _load_config_parser(self, path: Path) -> ConfigParser:
        """Return a parser populated from ``config.ini`` when present."""

        parser = ConfigParser()
        if path.exists():
            parser.read(path)
        return parser

    def _get_section(self, name: str) -> Mapping[str, str]:
        """Return a config section if it exists."""

        if self._config_parser.has_section(name):
            return self._config_parser[name]
        return {}

    def _load(self) -> HubAppConfig:
        """Assemble the high level hub configuration object."""
        reticulum = self._load_reticulum_config(self.reticulum_config_path)
        lxmf = self._load_lxmf_config(self.lxmf_router_config_path)
        app_name, app_version, app_description = self._load_app_metadata()
        storage_path = self.storage_path
        database_path = storage_path / "reticulum.db"
        hub_db_path = storage_path / "rth_api.sqlite"
        return HubAppConfig(
            storage_path=storage_path,
            database_path=database_path,
            hub_database_path=hub_db_path,
            file_storage_path=self.runtime_config.file_storage_path
            or storage_path
            / "files",
            image_storage_path=self.runtime_config.image_storage_path
            or storage_path
            / "images",
            runtime=self.runtime_config,
            reticulum=reticulum,
            lxmf_router=lxmf,
            app_name=app_name,
            app_version=app_version,
            app_description=app_description,
            tak_connection=self._tak_config,
        )

