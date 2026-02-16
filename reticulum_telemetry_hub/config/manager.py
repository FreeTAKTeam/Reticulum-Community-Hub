"""Helpers for reading and merging hub configuration files."""

from __future__ import annotations

import os
import string
from configparser import ConfigParser
from importlib import resources
from pathlib import Path
from datetime import datetime, timezone
from typing import Mapping, Optional

from dotenv import load_dotenv as load_env

from reticulum_telemetry_hub.config.constants import DEFAULT_STORAGE_PATH
from .models import (
    HubAppConfig,
    HubRuntimeConfig,
    LXMFRouterConfig,
    RNSInterfaceConfig,
    ReticulumConfig,
    TakConnectionConfig,
)


def _expand_user_path(value: Path | str) -> Path:
    """Expand user paths honoring HOME overrides on Windows."""
    value_str = str(value)
    if value_str.startswith("~"):
        home = os.environ.get("HOME")
        if home:
            tail = value_str[1:]
            if tail.startswith(("/", "\\")):
                tail = tail[1:]
            return Path(home) / tail
    return Path(value_str).expanduser()


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


class HubConfigurationManager:  # pylint: disable=too-many-instance-attributes
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
        self.storage_path = _expand_user_path(storage_path or DEFAULT_STORAGE_PATH)
        self.config_path = _expand_user_path(
            config_path or self.storage_path / "config.ini"
        )
        self._write_default_config_if_missing()
        self._config_parser = self._load_config_parser(self.config_path)
        self.runtime_config = self._load_runtime_config()

        reticulum_path_override = self.runtime_config.reticulum_config_path
        lxmf_path_override = self.runtime_config.lxmf_router_config_path

        self.reticulum_config_path = _expand_user_path(
            reticulum_config_path
            or reticulum_path_override
            or Path.home() / ".reticulum" / "config"
        )
        self.lxmf_router_config_path = _expand_user_path(
            lxmf_router_config_path
            or lxmf_path_override
            or Path.home() / ".lxmd" / "config"
        )
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
        self._tak_config = self._load_tak_config()
        self._config = self._load()
        return self._config

    @staticmethod
    def default_config_template_text() -> str:
        """Return the shipped config.ini template text."""

        return _load_default_config_template_text()

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

    def get_config_text(self) -> str:
        """Return the raw config.ini content when present."""

        if not self.config_path.exists():
            return ""
        return self.config_path.read_text(encoding="utf-8")

    def get_reticulum_config_text(self) -> str:
        """Return the raw Reticulum configuration content when present."""

        if not self.reticulum_config_path.exists():
            return ""
        return self.reticulum_config_path.read_text(encoding="utf-8")

    def validate_config_text(self, config_text: str) -> dict:
        """Validate a config.ini payload without applying it.

        Args:
            config_text (str): Raw ini contents to validate.

        Returns:
            dict: Validation result with ``valid`` and ``errors`` keys.
        """

        parser = ConfigParser()
        errors: list[str] = []
        try:
            parser.read_string(config_text)
        except Exception as exc:  # pragma: no cover - defensive parsing
            errors.append(str(exc))
        return {"valid": not errors, "errors": errors}

    def validate_reticulum_config_text(self, config_text: str) -> dict:
        """Validate a Reticulum configuration payload without applying it.

        Args:
            config_text (str): Raw ini contents to validate.

        Returns:
            dict: Validation result with ``valid`` and ``errors`` keys.
        """

        parser = ConfigParser()
        errors: list[str] = []
        try:
            parser.read_string(config_text)
        except Exception as exc:  # pragma: no cover - defensive parsing
            errors.append(str(exc))
        return {"valid": not errors, "errors": errors}

    def apply_config_text(self, config_text: str) -> dict:
        """Persist the provided config.ini content and keep a backup.

        Args:
            config_text (str): Raw ini content to persist.

        Returns:
            dict: Details about the persisted backup and target path.
        """

        validation = self.validate_config_text(config_text)
        if not validation.get("valid"):
            errors = validation.get("errors") or []
            details = "; ".join(str(error) for error in errors if error)
            message = "Invalid configuration payload"
            if details:
                message = f"{message}: {details}"
            raise ValueError(message)
        backup_path = self._backup_config()
        self.config_path.write_text(config_text, encoding="utf-8")
        return {
            "applied": True,
            "config_path": str(self.config_path),
            "backup_path": str(backup_path) if backup_path else None,
        }

    def apply_reticulum_config_text(self, config_text: str) -> dict:
        """Persist the provided Reticulum configuration content and keep a backup.

        Args:
            config_text (str): Raw ini content to persist.

        Returns:
            dict: Details about the persisted backup and target path.
        """

        validation = self.validate_reticulum_config_text(config_text)
        if not validation.get("valid"):
            errors = validation.get("errors") or []
            details = "; ".join(str(error) for error in errors if error)
            message = "Invalid Reticulum configuration payload"
            if details:
                message = f"{message}: {details}"
            raise ValueError(message)
        backup_path = self._backup_reticulum_config()
        self.reticulum_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.reticulum_config_path.write_text(config_text, encoding="utf-8")
        return {
            "applied": True,
            "config_path": str(self.reticulum_config_path),
            "backup_path": str(backup_path) if backup_path else None,
        }

    def rollback_config_text(self, backup_path: str | None = None) -> dict:
        """Restore the config.ini file from a backup.

        Args:
            backup_path (str | None): Optional backup path override.

        Returns:
            dict: Details about the restored backup.
        """

        target_backup = Path(backup_path) if backup_path else self._latest_backup()
        if target_backup is None or not target_backup.exists():
            return {"rolled_back": False, "error": "No backup available"}
        content = target_backup.read_text(encoding="utf-8")
        self.config_path.write_text(content, encoding="utf-8")
        return {"rolled_back": True, "backup_path": str(target_backup)}

    def rollback_reticulum_config_text(self, backup_path: str | None = None) -> dict:
        """Restore the Reticulum configuration file from a backup.

        Args:
            backup_path (str | None): Optional backup path override.

        Returns:
            dict: Details about the restored backup.
        """

        target_backup = (
            Path(backup_path) if backup_path else self._latest_reticulum_backup()
        )
        if target_backup is None or not target_backup.exists():
            return {"rolled_back": False, "error": "No backup available"}
        content = target_backup.read_text(encoding="utf-8")
        self.reticulum_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.reticulum_config_path.write_text(content, encoding="utf-8")
        return {"rolled_back": True, "backup_path": str(target_backup)}

    # ------------------------------------------------------------------ #
    # private helpers
    # ------------------------------------------------------------------ #
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

    def _load_config_parser(self, path: Path) -> ConfigParser:
        """Return a parser populated from ``config.ini`` when present."""

        parser = ConfigParser()
        if path.exists():
            parser.read(path)
        return parser

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

        gps_section = self._get_section("gpsd")
        gps_host = gps_section.get("host", defaults.gpsd_host)
        gps_port = self._coerce_int(gps_section.get("port"), defaults.gpsd_port)

        file_section = self._get_section("files")
        image_section = self._get_section("images")

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
            file_storage_path=file_storage_path,
            image_storage_path=image_storage_path,
        )

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

    def _load_reticulum_config(self, path: Path) -> ReticulumConfig:
        """Parse the Reticulum configuration file."""
        parser = ConfigParser()
        if path.exists():
            parser.read(path)

        # Use values from config.ini when present; fall back to external files.
        file_ret_section = (
            dict(parser["reticulum"]) if parser.has_section("reticulum") else {}
        )
        cfg_ret_section = dict(self._get_section("reticulum"))
        ret_section = {**file_ret_section, **cfg_ret_section}

        file_iface_section = dict(self._find_interface_section(parser))
        cfg_iface_section = {}
        for name in ("interfaces", "interface", "tcp_interface"):
            if self._config_parser.has_section(name):
                cfg_iface_section = dict(self._config_parser[name])
                break
        interface_section = {**file_iface_section, **cfg_iface_section}

        enable_transport = self._get_bool(ret_section, "enable_transport", True)
        share_instance = self._get_bool(ret_section, "share_instance", True)

        listen_port = self._coerce_int(interface_section.get("listen_port"), 4242)
        interface = RNSInterfaceConfig(
            listen_ip=interface_section.get("listen_ip", "0.0.0.0"),
            listen_port=listen_port,
            interface_enabled=self._get_bool(
                interface_section, "interface_enabled", True
            ),
            interface_type=interface_section.get("type", "TCPServerInterface"),
        )
        return ReticulumConfig(
            path=path,
            enable_transport=enable_transport,
            share_instance=share_instance,
            tcp_interface=interface,
        )

    def _load_lxmf_config(self, path: Path) -> LXMFRouterConfig:
        """Parse the LXMF router configuration file."""
        parser = ConfigParser()
        if path.exists():
            parser.read(path)

        file_prop_section = (
            dict(parser["propagation"]) if parser.has_section("propagation") else {}
        )
        cfg_prop_section = dict(self._get_section("propagation"))
        propagation_section = {**file_prop_section, **cfg_prop_section}

        file_lxmf_section = dict(parser["lxmf"]) if parser.has_section("lxmf") else {}
        cfg_lxmf_section = dict(self._get_section("lxmf"))
        lxmf_section = {**file_lxmf_section, **cfg_lxmf_section}

        enable_node_value = propagation_section.get("enable_node")
        if enable_node_value is None:
            enable_node_value = propagation_section.get("propagation_node")
        if enable_node_value is None:
            enable_node_value = lxmf_section.get("enable_node")
        if enable_node_value is None:
            enable_node_value = lxmf_section.get("propagation_node")
        enable_node = self._get_bool(
            {"enable_node": enable_node_value}, "enable_node", True
        )
        announce_interval = self._coerce_int(
            propagation_section.get("announce_interval"), 10
        )
        display_name = lxmf_section.get("display_name", "RTH_router")
        startup_mode_value = propagation_section.get("startup_mode")
        if startup_mode_value is None:
            startup_mode_value = propagation_section.get("propagation_start_mode")
        startup_mode = self._normalize_propagation_start_mode(startup_mode_value)

        startup_prune_enabled_value = propagation_section.get("startup_prune_enabled")
        if startup_prune_enabled_value is None:
            startup_prune_enabled_value = propagation_section.get(
                "propagation_startup_prune_enabled"
            )
        startup_prune_enabled = self._get_bool(
            {"startup_prune_enabled": startup_prune_enabled_value},
            "startup_prune_enabled",
            False,
        )

        startup_max_messages = self._coerce_optional_positive_int(
            propagation_section.get("startup_max_messages")
            or propagation_section.get("propagation_startup_max_messages")
        )
        startup_max_age_days = self._coerce_optional_positive_int(
            propagation_section.get("startup_max_age_days")
            or propagation_section.get("propagation_startup_max_age_days")
        )

        return LXMFRouterConfig(
            path=path,
            enable_node=enable_node,
            announce_interval_minutes=announce_interval,
            display_name=display_name,
            propagation_start_mode=startup_mode,
            propagation_startup_prune_enabled=startup_prune_enabled,
            propagation_startup_max_messages=startup_max_messages,
            propagation_startup_max_age_days=startup_max_age_days,
        )

    @staticmethod
    def _coerce_int(value: str | None, default: int) -> int:
        """Return an integer from a string value or fallback."""

        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    @staticmethod
    def _coerce_optional_positive_int(value: str | None) -> int | None:
        """Return a positive integer or ``None`` when unset/invalid."""

        if value is None:
            return None
        compact = str(value).strip()
        if not compact:
            return None
        try:
            parsed = int(compact)
        except ValueError:
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _normalize_display_name(value: str | None) -> str | None:
        """Return a trimmed display name or ``None`` when empty."""

        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @staticmethod
    def _normalize_name_token(value: str | None, fallback: str = "unknown") -> str:
        """Return a sanitized token suitable for generated names."""

        if value is None:
            return fallback
        compact = str(value).strip()
        if not compact:
            return fallback
        normalized = "".join(
            ch if ch.isalnum() or ch in {".", "-", "_"} else "_" for ch in compact
        )
        normalized = normalized.strip("._-")
        return normalized or fallback

    @staticmethod
    def _normalize_destination_hash(
        value: bytes | bytearray | memoryview | str | None,
    ) -> str:
        """Return a lowercase destination-hash token for generated names."""

        if isinstance(value, (bytes, bytearray, memoryview)):
            return bytes(value).hex().lower()

        if isinstance(value, str):
            candidate = value.strip().lower()
            if candidate.startswith("0x"):
                candidate = candidate[2:]
            if candidate and all(ch in string.hexdigits for ch in candidate):
                return candidate

        return "unknown"

    @staticmethod
    def _coerce_float(value: str | None, default: float) -> float:
        """Return a float from a string value or fallback."""

        if value is None:
            return default
        try:
            return float(value)
        except ValueError:
            return default

    @staticmethod
    def _normalize_propagation_start_mode(value: str | None) -> str:
        """Return a supported propagation startup mode."""

        mode = (value or "background").strip().lower()
        return mode if mode in {"blocking", "background"} else "background"

    @staticmethod
    def _get_bool(section, key: str, default: bool) -> bool:
        """Interpret boolean-like strings from a config section."""
        value = section.get(key)
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _find_interface_section(parser: ConfigParser) -> dict:
        """Find the first TCP interface section in a configuration parser."""
        candidate_sections = [
            name
            for name in parser.sections()
            if name.lower().startswith("interfaces") or "tcp" in name.lower()
        ]
        if candidate_sections:
            return parser[candidate_sections[0]]
        return {}

    @staticmethod
    def _ensure_directory(path: Path) -> Path:
        """
        Guarantee that a directory exists.

        Args:
            path (Path): Directory to create when missing.

        Returns:
            Path: The original path for chaining.
        """

        path.mkdir(parents=True, exist_ok=True)
        return path

    def _load_app_metadata(self) -> tuple[str, str | None, str]:
        """Return human-readable application metadata from ``config.ini``.

        Returns:
            tuple[str, str | None, str]: Name, version, and description for the
            application, preferring the ``[app]`` section when present.
        """

        section = self._get_section("app")
        default_name = "ReticulumTelemetryHub"
        default_version = HubAppConfig._safe_get_version(default_name)  # pylint: disable=protected-access
        name = section.get("name") or section.get("app_name") or default_name
        version = (
            section.get("version")
            or section.get("app_version")
            or section.get("build")
            or default_version
        )
        description = (
            section.get("description")
            or section.get("app_description")
            or section.get("summary")
            or ""
        )
        return name, version, description

    def _load_tak_config(self) -> TakConnectionConfig:
        """Construct the TAK configuration using ``config.ini`` values."""

        defaults = TakConnectionConfig()
        # Prefer the new uppercase [TAK] section; fall back to legacy [tak].
        section = self._get_section("TAK") or self._get_section("tak")

        interval = self._coerce_float(
            section.get("poll_interval_seconds")
            or section.get("interval_seconds")
            or section.get("interval"),
            defaults.poll_interval_seconds,
        )

        keepalive_interval = self._coerce_float(
            section.get("keepalive_interval_seconds")
            or section.get("keepalive_interval")
            or section.get("keepalive"),
            defaults.keepalive_interval_seconds,
        )

        tak_proto = self._coerce_int(section.get("tak_proto"), defaults.tak_proto)
        fts_compat = self._coerce_int(section.get("fts_compat"), defaults.fts_compat)

        return TakConnectionConfig(
            cot_url=section.get("cot_url", defaults.cot_url),
            callsign=section.get("callsign", defaults.callsign),
            poll_interval_seconds=interval,
            keepalive_interval_seconds=keepalive_interval,
            tls_client_cert=section.get("tls_client_cert"),
            tls_client_key=section.get("tls_client_key"),
            tls_ca=section.get("tls_ca"),
            tls_insecure=self._get_bool(section, "tls_insecure", defaults.tls_insecure),
            tak_proto=tak_proto,
            fts_compat=fts_compat,
        )

    def _backup_config(self) -> Path | None:
        """Create a timestamped backup of config.ini when it exists."""

        if not self.config_path.exists():
            return None
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        backup_path = self.config_path.with_suffix(f".ini.bak.{timestamp}")
        content = self.config_path.read_text(encoding="utf-8")
        backup_path.write_text(content, encoding="utf-8")
        return backup_path

    def _latest_backup(self) -> Path | None:
        """Return the most recent config.ini backup file."""

        backups = sorted(self.config_path.parent.glob("config.ini.bak.*"))
        if not backups:
            return None
        return backups[-1]

    def _backup_reticulum_config(self) -> Path | None:
        """Create a timestamped backup of the Reticulum config when it exists."""

        if not self.reticulum_config_path.exists():
            return None
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        backup_path = Path(f"{self.reticulum_config_path}.bak.{timestamp}")
        content = self.reticulum_config_path.read_text(encoding="utf-8")
        backup_path.write_text(content, encoding="utf-8")
        return backup_path

    def _latest_reticulum_backup(self) -> Path | None:
        """Return the most recent Reticulum config backup file."""

        backups = sorted(
            self.reticulum_config_path.parent.glob(
                f"{self.reticulum_config_path.name}.bak.*"
            )
        )
        if not backups:
            return None
        return backups[-1]
