"""Reticulum and LXMF router config parsing helpers."""

from __future__ import annotations

from configparser import ConfigParser
import logging
from pathlib import Path

from reticulum_telemetry_hub.config.models import LXMFRouterConfig
from reticulum_telemetry_hub.config.models import RNSInterfaceConfig
from reticulum_telemetry_hub.config.models import ReticulumConfig

_LOGGER = logging.getLogger(__name__)


class ExternalConfigMixin:
    """Load Reticulum and LXMF router config objects."""

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
        node_announce_interval = self._coerce_optional_positive_int(
            propagation_section.get("announce_interval")
        )
        if node_announce_interval is None:
            node_announce_interval = 10

        peer_announce_interval = self._coerce_optional_positive_int(
            lxmf_section.get("announce_interval")
        )
        if peer_announce_interval is None:
            peer_announce_interval = node_announce_interval

        display_name = self._normalize_display_name(lxmf_section.get("display_name"))
        peer_announce_at_start = self._get_bool(
            {"announce_at_start": lxmf_section.get("announce_at_start")},
            "announce_at_start",
            True,
        )
        delivery_transfer_limit = self._coerce_min_float(
            lxmf_section.get("delivery_transfer_max_accepted_size"),
            default=1000.0,
            minimum=0.38,
        )
        on_inbound = self._normalize_optional_text(lxmf_section.get("on_inbound"))
        node_name = self._normalize_optional_text(propagation_section.get("node_name"))
        auth_required = self._get_bool(
            {"auth_required": propagation_section.get("auth_required")},
            "auth_required",
            False,
        )
        node_announce_at_start = self._get_bool(
            {"announce_at_start": propagation_section.get("announce_at_start")},
            "announce_at_start",
            True,
        )
        autopeer = self._get_bool(
            {"autopeer": propagation_section.get("autopeer")},
            "autopeer",
            True,
        )
        autopeer_maxdepth = self._coerce_optional_int_min(
            propagation_section.get("autopeer_maxdepth"),
            minimum=0,
        )
        if autopeer_maxdepth is None:
            autopeer_maxdepth = 6

        message_storage_limit = self._coerce_min_float(
            propagation_section.get("message_storage_limit"),
            default=5.0,
            minimum=0.005,
        )
        propagation_transfer_limit = self._coerce_min_float(
            propagation_section.get("propagation_transfer_max_accepted_size")
            or propagation_section.get("propagation_message_max_accepted_size"),
            default=256.0,
            minimum=0.38,
        )
        propagation_sync_limit = self._coerce_min_float(
            propagation_section.get("propagation_sync_max_accepted_size"),
            default=256.0 * 40,
            minimum=0.38,
        )
        propagation_sync_interval = self._coerce_optional_positive_int(
            propagation_section.get("propagation_sync_interval_minutes")
        )
        if propagation_sync_interval is None:
            propagation_sync_interval = 10
        propagation_stamp_cost_target = self._coerce_optional_positive_int(
            propagation_section.get("propagation_stamp_cost_target")
        )
        propagation_stamp_cost_flexibility = self._coerce_optional_int_min(
            propagation_section.get("propagation_stamp_cost_flexibility"),
            minimum=0,
        )
        peering_cost = self._coerce_optional_int_min(
            propagation_section.get("peering_cost"),
            minimum=0,
        )
        remote_peering_cost_max = self._coerce_optional_int_min(
            propagation_section.get("remote_peering_cost_max"),
            minimum=0,
        )
        prioritised_lxmf_destinations = self._coerce_csv_list(
            propagation_section.get("prioritise_destinations")
        )
        control_allowed_identities = self._coerce_csv_list(
            propagation_section.get("control_allowed")
        )
        static_peers = self._coerce_csv_list(propagation_section.get("static_peers"))
        max_peers = self._coerce_optional_int_min(
            propagation_section.get("max_peers"),
            minimum=0,
        )
        from_static_only = self._get_bool(
            {"from_static_only": propagation_section.get("from_static_only")},
            "from_static_only",
            False,
        )
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
            display_name=display_name,
            peer_announce_at_start=peer_announce_at_start,
            peer_announce_interval_minutes=peer_announce_interval,
            delivery_transfer_max_accepted_size_kb=delivery_transfer_limit,
            on_inbound=on_inbound,
            node_name=node_name,
            auth_required=auth_required,
            node_announce_at_start=node_announce_at_start,
            node_announce_interval_minutes=node_announce_interval,
            autopeer=autopeer,
            autopeer_maxdepth=autopeer_maxdepth,
            message_storage_limit_megabytes=message_storage_limit,
            propagation_transfer_max_accepted_size_kb=propagation_transfer_limit,
            propagation_sync_max_accepted_size_kb=propagation_sync_limit,
            propagation_sync_interval_minutes=propagation_sync_interval,
            propagation_stamp_cost_target=propagation_stamp_cost_target,
            propagation_stamp_cost_flexibility=propagation_stamp_cost_flexibility,
            peering_cost=peering_cost,
            remote_peering_cost_max=remote_peering_cost_max,
            prioritised_lxmf_destinations=prioritised_lxmf_destinations,
            control_allowed_identities=control_allowed_identities,
            static_peers=static_peers,
            max_peers=max_peers,
            from_static_only=from_static_only,
            propagation_start_mode=startup_mode,
            propagation_startup_prune_enabled=startup_prune_enabled,
            propagation_startup_max_messages=startup_max_messages,
            propagation_startup_max_age_days=startup_max_age_days,
        )
