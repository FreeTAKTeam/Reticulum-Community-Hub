"""Configuration model for the embedded LXMD runtime."""

from __future__ import annotations

from dataclasses import dataclass

from reticulum_telemetry_hub.config.manager import HubConfigurationManager


@dataclass
class EmbeddedLxmdConfig:
    """Runtime configuration for the embedded LXMD service."""

    enable_propagation_node: bool
    peer_announce_at_start: bool
    peer_announce_interval_seconds: int | None
    node_announce_at_start: bool
    node_announce_interval_seconds: int | None
    auth_required: bool
    control_allowed_identities: tuple[str, ...]
    propagation_start_mode: str
    propagation_startup_prune_enabled: bool
    propagation_startup_max_messages: int | None
    propagation_startup_max_age_days: int | None

    @classmethod
    def from_manager(cls, manager: HubConfigurationManager) -> "EmbeddedLxmdConfig":
        lxmf_config = manager.config.lxmf_router
        peer_interval = lxmf_config.peer_announce_interval_minutes
        if peer_interval is not None:
            peer_interval = max(1, int(peer_interval) * 60)
        node_interval = lxmf_config.node_announce_interval_minutes
        if node_interval is not None:
            node_interval = max(1, int(node_interval) * 60)
        startup_mode = str(
            getattr(lxmf_config, "propagation_start_mode", "background")
        ).strip().lower()
        if startup_mode not in {"blocking", "background"}:
            startup_mode = "background"
        return cls(
            enable_propagation_node=lxmf_config.enable_node,
            peer_announce_at_start=bool(
                getattr(lxmf_config, "peer_announce_at_start", True)
            ),
            peer_announce_interval_seconds=peer_interval,
            node_announce_at_start=bool(
                getattr(lxmf_config, "node_announce_at_start", True)
            ),
            node_announce_interval_seconds=node_interval,
            auth_required=bool(getattr(lxmf_config, "auth_required", False)),
            control_allowed_identities=tuple(
                getattr(lxmf_config, "control_allowed_identities", ()) or ()
            ),
            propagation_start_mode=startup_mode,
            propagation_startup_prune_enabled=bool(
                getattr(lxmf_config, "propagation_startup_prune_enabled", False)
            ),
            propagation_startup_max_messages=getattr(
                lxmf_config, "propagation_startup_max_messages", None
            ),
            propagation_startup_max_age_days=getattr(
                lxmf_config, "propagation_startup_max_age_days", None
            ),
        )
