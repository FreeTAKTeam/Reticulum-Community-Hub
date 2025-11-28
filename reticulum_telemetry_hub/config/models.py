from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from configparser import ConfigParser


@dataclass
class RNSInterfaceConfig:
    """Represents the minimal subset of the TCP server interface configuration."""

    listen_ip: str = "0.0.0.0"
    listen_port: int = 4242
    interface_enabled: bool = True
    interface_type: str = "TCPServerInterface"

    def to_dict(self) -> dict:
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
        return {
            "path": str(self.path),
            "enable_node": self.enable_node,
            "announce_interval_minutes": self.announce_interval_minutes,
            "display_name": self.display_name,
        }


@dataclass
class HubAppConfig:
    """Aggregated configuration for the telemetry hub runtime."""

    storage_path: Path
    database_path: Path
    hub_database_path: Path
    reticulum: ReticulumConfig
    lxmf_router: LXMFRouterConfig
    app_version: Optional[str] = None
    tak_connection: "TakConnectionConfig | None" = None

    def to_reticulum_info_dict(self) -> dict:
        """Return a dict compatible with the ReticulumInfo schema."""
        return {
            "is_transport_enabled": self.reticulum.enable_transport,
            "is_connected_to_shared_instance": self.reticulum.share_instance,
            "reticulum_config_path": str(self.reticulum.path),
            "database_path": str(self.database_path),
            "storage_path": str(self.storage_path),
            "rns_version": self._safe_get_version("RNS"),
            "lxmf_version": self._safe_get_version("LXMF"),
            "app_version": self.app_version
            or self._safe_get_version("ReticulumTelemetryHub"),
        }

    @staticmethod
    def _safe_get_version(distribution: str) -> str:
        try:
            from importlib.metadata import version
        except Exception:  # pragma: no cover - importlib metadata shouldn't fail
            return "unknown"
        try:
            return version(distribution)
        except Exception:
            return "unknown"


@dataclass
class TakConnectionConfig:
    """Settings that control TAK/CoT connectivity."""

    cot_url: str = "tcp://127.0.0.1:8087"
    callsign: str = "RTH"
    poll_interval_seconds: float = 30.0
    tls_client_cert: str | None = None
    tls_client_key: str | None = None
    tls_ca: str | None = None
    tls_insecure: bool = False

    def to_config_parser(self) -> ConfigParser:
        """Return a ConfigParser that PyTAK understands."""

        parser = ConfigParser()
        parser["fts"] = {
            "COT_URL": self.cot_url,
            "CALLSIGN": self.callsign,
            "SSL_CLIENT_CERT": self.tls_client_cert or "",
            "SSL_CLIENT_KEY": self.tls_client_key or "",
            "SSL_CLIENT_CAFILE": self.tls_ca or "",
            "SSL_VERIFY": "false" if self.tls_insecure else "true",
        }
        return parser

    def to_dict(self) -> dict:
        """Return a serialisable representation for debugging or logs."""

        return {
            "cot_url": self.cot_url,
            "callsign": self.callsign,
            "poll_interval_seconds": self.poll_interval_seconds,
            "tls_client_cert": self.tls_client_cert,
            "tls_client_key": self.tls_client_key,
            "tls_ca": self.tls_ca,
            "tls_insecure": self.tls_insecure,
        }
