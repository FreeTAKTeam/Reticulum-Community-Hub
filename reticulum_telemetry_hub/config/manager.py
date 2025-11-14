from __future__ import annotations

from configparser import ConfigParser
from pathlib import Path
from typing import Optional

from .models import (
    HubAppConfig,
    LXMFRouterConfig,
    RNSInterfaceConfig,
    ReticulumConfig,
)


class HubConfigurationManager:
    """Load hub related configuration files and expose them as Python objects."""

    def __init__(
        self,
        storage_path: Optional[Path] = None,
        reticulum_config_path: Optional[Path] = None,
        lxmf_router_config_path: Optional[Path] = None,
    ) -> None:
        self.storage_path = Path(storage_path or "RTH_Store")
        self.reticulum_config_path = Path(
            reticulum_config_path or Path.home() / ".reticulum" / "config"
        )
        self.lxmf_router_config_path = Path(
            lxmf_router_config_path or Path.home() / ".lxmd" / "config"
        )
        self._config = self._load()

    @property
    def config(self) -> HubAppConfig:
        return self._config

    def reload(self) -> HubAppConfig:
        self._config = self._load()
        return self._config

    def reticulum_info_snapshot(self) -> dict:
        return self._config.to_reticulum_info_dict()

    # ------------------------------------------------------------------ #
    # private helpers
    # ------------------------------------------------------------------ #
    def _load(self) -> HubAppConfig:
        reticulum = self._load_reticulum_config(self.reticulum_config_path)
        lxmf = self._load_lxmf_config(self.lxmf_router_config_path)
        storage_path = self.storage_path
        database_path = storage_path / "reticulum.db"
        hub_db_path = storage_path / "rth_api.sqlite"
        return HubAppConfig(
            storage_path=storage_path,
            database_path=database_path,
            hub_database_path=hub_db_path,
            reticulum=reticulum,
            lxmf_router=lxmf,
        )

    def _load_reticulum_config(self, path: Path) -> ReticulumConfig:
        parser = ConfigParser()
        if path.exists():
            parser.read(path)
        ret_section = parser["reticulum"] if parser.has_section("reticulum") else {}
        enable_transport = self._get_bool(ret_section, "enable_transport", True)
        share_instance = self._get_bool(ret_section, "share_instance", True)

        interface_section = self._find_interface_section(parser)
        interface = RNSInterfaceConfig(
            listen_ip=interface_section.get("listen_ip", "0.0.0.0"),
            listen_port=int(interface_section.get("listen_port", 4242)),
            interface_enabled=self._get_bool(interface_section, "interface_enabled", True),
            interface_type=interface_section.get("type", "TCPServerInterface"),
        )
        return ReticulumConfig(
            path=path,
            enable_transport=enable_transport,
            share_instance=share_instance,
            tcp_interface=interface,
        )

    def _load_lxmf_config(self, path: Path) -> LXMFRouterConfig:
        parser = ConfigParser()
        if path.exists():
            parser.read(path)
        propagation_section = (
            parser["propagation"] if parser.has_section("propagation") else {}
        )
        lxmf_section = parser["lxmf"] if parser.has_section("lxmf") else {}
        enable_node = self._get_bool(propagation_section, "enable_node", True)
        announce_interval = int(propagation_section.get("announce_interval", 10))
        display_name = lxmf_section.get("display_name", "RTH_router")
        return LXMFRouterConfig(
            path=path,
            enable_node=enable_node,
            announce_interval_minutes=announce_interval,
            display_name=display_name,
        )

    @staticmethod
    def _get_bool(section, key: str, default: bool) -> bool:
        value = section.get(key)
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _find_interface_section(parser: ConfigParser) -> dict:
        candidate_sections = [
            name
            for name in parser.sections()
            if name.lower().startswith("interfaces")
            or "tcp" in name.lower()
        ]
        if candidate_sections:
            return parser[candidate_sections[0]]
        return {}
