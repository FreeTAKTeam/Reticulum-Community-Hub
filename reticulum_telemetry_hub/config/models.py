"""Data models representing configuration shapes for the hub."""

from __future__ import annotations

from configparser import ConfigParser
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Optional, Tuple

from reticulum_telemetry_hub.config.constants import (
    DEFAULT_ANNOUNCE_INTERVAL,
    DEFAULT_HUB_TELEMETRY_INTERVAL,
    DEFAULT_LOG_LEVEL_NAME,
    DEFAULT_SERVICE_TELEMETRY_INTERVAL,
)


@dataclass
class RNSInterfaceConfig:
    """Represents the minimal subset of the TCP server interface configuration."""

    listen_ip: str = "0.0.0.0"
    listen_port: int = 4242
    interface_enabled: bool = True
    interface_type: str = "TCPServerInterface"

    def to_dict(self) -> dict:
        """Serialise the TCP interface configuration.

        Returns:
            dict: Mapping consumable by Reticulum configuration writers.
        """

        return {
            "listen_ip": self.listen_ip,
            "listen_port": self.listen_port,
            "interface_enabled": self.interface_enabled,
            "type": self.interface_type,
        }


@dataclass
class ReticulumConfig:
    """Object view of the Reticulum configuration file."""

    path: Path
    enable_transport: bool = True
    share_instance: bool = True
    tcp_interface: RNSInterfaceConfig = field(default_factory=RNSInterfaceConfig)

    def to_dict(self) -> dict:
        """Serialise the Reticulum configuration values.

        Returns:
            dict: Flattened representation including nested interfaces.
        """

        data = {
            "path": str(self.path),
            "enable_transport": self.enable_transport,
            "share_instance": self.share_instance,
        }
        data["tcp_interface"] = self.tcp_interface.to_dict()
        return data


@dataclass
class LXMFRouterConfig:
    """Object view of the LXMF router/propagation configuration."""

    path: Path
    enable_node: bool = True
    announce_interval_minutes: int = 10
    display_name: str = "RTH_router"

    def to_dict(self) -> dict:
        """Serialise LXMF router configuration fields.

        Returns:
            dict: Mapping used by the embedded LXMF daemon.
        """

        return {
            "path": str(self.path),
            "enable_node": self.enable_node,
            "announce_interval_minutes": self.announce_interval_minutes,
            "display_name": self.display_name,
        }


@dataclass
class HubRuntimeConfig:  # pylint: disable=too-many-instance-attributes
    """Configuration values that guide the hub runtime defaults."""

    display_name: str = "RTH"
    announce_interval: int = DEFAULT_ANNOUNCE_INTERVAL
    hub_telemetry_interval: int = DEFAULT_HUB_TELEMETRY_INTERVAL
    service_telemetry_interval: int = DEFAULT_SERVICE_TELEMETRY_INTERVAL
    log_level: str = DEFAULT_LOG_LEVEL_NAME
    embedded_lxmd: bool = False
    default_services: Tuple[str, ...] = ()
    gpsd_host: str = "127.0.0.1"
    gpsd_port: int = 2947
    reticulum_config_path: Path | None = None
    lxmf_router_config_path: Path | None = None
    telemetry_filename: str = "telemetry.ini"
    file_storage_path: Path | None = None
    image_storage_path: Path | None = None


@dataclass
class HubAppConfig:  # pylint: disable=too-many-instance-attributes
    """Aggregated configuration for the telemetry hub runtime."""

    storage_path: Path
    database_path: Path
    hub_database_path: Path
    file_storage_path: Path
    image_storage_path: Path
    runtime: "HubRuntimeConfig"
    reticulum: ReticulumConfig
    lxmf_router: LXMFRouterConfig
    app_name: str = "ReticulumTelemetryHub"
    app_version: Optional[str] = None
    app_description: str = ""
    tak_connection: "TakConnectionConfig | None" = None

    def to_reticulum_info_dict(self) -> dict:
        """Return a dict compatible with the ReticulumInfo schema.

        Returns:
            dict: Snapshot of the Reticulum runtime configuration.
        """
        return {
            "is_transport_enabled": self.reticulum.enable_transport,
            "is_connected_to_shared_instance": self.reticulum.share_instance,
            "reticulum_config_path": str(self.reticulum.path),
            "database_path": str(self.database_path),
            "storage_path": str(self.storage_path),
            "file_storage_path": str(self.file_storage_path),
            "image_storage_path": str(self.image_storage_path),
            "rns_version": self._safe_get_version("RNS"),
            "lxmf_version": self._safe_get_version("LXMF"),
            "app_name": self.app_name or "ReticulumTelemetryHub",
            "app_version": self.app_version
            or self._safe_get_version("ReticulumTelemetryHub"),
            "app_description": self.app_description or "",
        }

    @staticmethod
    def _safe_get_version(distribution: str) -> str:
        try:
            return metadata.version(distribution)
        except metadata.PackageNotFoundError:
            return "unknown"
        # Reason: metadata providers may raise unexpected runtime errors in constrained environments.
        except Exception:  # pylint: disable=broad-exception-caught
            return "unknown"


@dataclass
class TakConnectionConfig:  # pylint: disable=too-many-instance-attributes
    """Settings that control TAK/CoT connectivity."""

    cot_url: str = "tcp://127.0.0.1:8087"
    callsign: str = "RTH"
    poll_interval_seconds: float = 30.0
    keepalive_interval_seconds: float = 60.0
    tls_client_cert: str | None = None
    tls_client_key: str | None = None
    tls_ca: str | None = None
    tls_insecure: bool = False
    tak_proto: int = 0
    fts_compat: int = 1

    def to_config_parser(self) -> ConfigParser:
        """Return a ConfigParser that PyTAK understands.

        Returns:
            ConfigParser: Parser configured with PyTAK-compatible values.
        """

        parser = ConfigParser()
        parser["fts"] = {
            "COT_URL": self.cot_url,
            "CALLSIGN": self.callsign,
            "SSL_CLIENT_CERT": self.tls_client_cert or "",
            "SSL_CLIENT_KEY": self.tls_client_key or "",
            "SSL_CLIENT_CAFILE": self.tls_ca or "",
            "SSL_VERIFY": "false" if self.tls_insecure else "true",
            "TAK_PROTO": str(self.tak_proto),
            "FTS_COMPAT": str(self.fts_compat),
        }
        return parser

    def to_dict(self) -> dict:
        """Return a serialisable representation for debugging or logs.

        Returns:
            dict: Copy of the connector settings for display purposes.
        """

        return {
            "cot_url": self.cot_url,
            "callsign": self.callsign,
            "poll_interval_seconds": self.poll_interval_seconds,
            "keepalive_interval_seconds": self.keepalive_interval_seconds,
            "tls_client_cert": self.tls_client_cert,
            "tls_client_key": self.tls_client_key,
            "tls_ca": self.tls_ca,
            "tls_insecure": self.tls_insecure,
            "tak_proto": self.tak_proto,
            "fts_compat": self.fts_compat,
        }
