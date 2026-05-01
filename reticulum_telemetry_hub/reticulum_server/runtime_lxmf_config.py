"""LXMF router configuration helpers."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any
from typing import Callable
from typing import cast

import LXMF
import RNS

from reticulum_telemetry_hub.reticulum_server.runtime_constants import APP_NAME
from reticulum_telemetry_hub.reticulum_server.runtime_events import report_nonfatal_exception


class RuntimeLxmfConfigMixin:
    """Apply configured LXMF router constructor and runtime settings."""

    @staticmethod
    def _get_router_callable(
        router: LXMF.LXMRouter, attribute: str
    ) -> Callable[..., Any]:
        """Return a callable attribute from the LXMF router."""

        hook = getattr(router, attribute, None)
        if not callable(hook):
            msg = f"LXMF router is missing required callable '{attribute}'"
            raise AttributeError(msg)
        return cast(Callable[..., Any], hook)

    def _invoke_router_hook(self, attribute: str, *args: Any, **kwargs: Any) -> Any:
        """Invoke a callable hook on the LXMF router."""

        router_callable = self._get_router_callable(self.lxm_router, attribute)
        return router_callable(*args, **kwargs)

    @staticmethod
    def _delivery_destination_hash(identity) -> str | None:
        """Return the local LXMF delivery destination hash for ``identity``."""

        if identity is None:
            return None
        try:
            destination_hash = RNS.Destination.hash_from_name_and_identity(
                APP_NAME, identity
            )
        except Exception:  # pragma: no cover - defensive
            return None
        if isinstance(destination_hash, (bytes, bytearray, memoryview)):
            return bytes(destination_hash).hex().lower()
        return None

    @staticmethod
    def _decode_lxmf_hash(value: str, *, field: str) -> bytes | None:
        """Convert a configured hex hash to bytes, logging-friendly on failure."""

        candidate = str(value).strip().lower()
        if not candidate:
            return None
        try:
            return bytes.fromhex(candidate)
        except ValueError:
            RNS.log(
                f"Ignoring invalid LXMF {field} hash '{value}'",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return None

    def _decode_lxmf_hashes(
        self,
        values: tuple[str, ...] | list[str],
        *,
        field: str,
    ) -> list[bytes]:
        """Convert configured hex hash lists to bytes while skipping invalid items."""

        decoded: list[bytes] = []
        for value in values:
            parsed = self._decode_lxmf_hash(value, field=field)
            if parsed is not None:
                decoded.append(parsed)
        return decoded

    def _load_lxmf_sidecar_hashes(self, filename: str, *, field: str) -> list[bytes]:
        """Load optional newline-delimited LXMF hashes from a config sidecar file."""

        config = getattr(getattr(self, "config_manager", None), "config", None)
        lxmf_config = getattr(config, "lxmf_router", None)
        config_path = getattr(lxmf_config, "path", None)
        if config_path is None:
            return []

        sidecar_path = Path(str(config_path)).parent / filename
        if not sidecar_path.is_file():
            return []

        try:
            entries = tuple(
                line.strip()
                for line in sidecar_path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            )
        except OSError as exc:  # pragma: no cover - defensive logging
            RNS.log(
                f"Failed to read LXMF sidecar file '{sidecar_path}': {exc}",
                getattr(RNS, "LOG_WARNING", 2),
            )
            return []

        return self._decode_lxmf_hashes(entries, field=field)

    def _lxmf_router_init_kwargs(self) -> dict[str, Any]:
        """Return constructor kwargs derived from the configured LXMF router settings."""

        lxmf_config = self.config_manager.config.lxmf_router
        init_kwargs: dict[str, Any] = {
            "storagepath": str(self.storage_path),
            "autopeer": lxmf_config.autopeer,
            "autopeer_maxdepth": lxmf_config.autopeer_maxdepth,
            "propagation_limit": lxmf_config.propagation_transfer_max_accepted_size_kb,
            "delivery_limit": lxmf_config.delivery_transfer_max_accepted_size_kb,
            "sync_limit": lxmf_config.propagation_sync_max_accepted_size_kb,
            "static_peers": self._decode_lxmf_hashes(
                lxmf_config.static_peers,
                field="static_peers",
            ),
            "max_peers": lxmf_config.max_peers,
            "from_static_only": lxmf_config.from_static_only,
            "name": lxmf_config.node_name,
        }
        optional_mappings = {
            "propagation_cost": lxmf_config.propagation_stamp_cost_target,
            "propagation_cost_flexibility": (
                lxmf_config.propagation_stamp_cost_flexibility
            ),
            "peering_cost": lxmf_config.peering_cost,
            "max_peering_cost": lxmf_config.remote_peering_cost_max,
        }
        for key, value in optional_mappings.items():
            if value is not None:
                init_kwargs[key] = value
        return init_kwargs

    def _apply_lxmf_router_runtime_config(self) -> None:
        """Apply post-construction LXMF settings that are not constructor args."""

        lxmf_config = self.config_manager.config.lxmf_router
        self._invoke_router_hook(
            "set_message_storage_limit",
            megabytes=lxmf_config.message_storage_limit_megabytes,
        )
        if lxmf_config.auth_required:
            self._invoke_router_hook("set_authentication", required=True)
        for identity_hash in self._load_lxmf_sidecar_hashes(
            "allowed",
            field="allowed",
        ):
            try:
                self._invoke_router_hook("allow", identity_hash)
            except Exception as exc:  # pragma: no cover - defensive logging
                report_nonfatal_exception(
                    getattr(self, "event_log", None),
                    "lxmf_runtime_error",
                    f"Failed to allow LXMF identity {identity_hash.hex()}: {exc}",
                    exc,
                    metadata={
                        "operation": "router_runtime_config",
                        "hook": "allow",
                        "identity_hash": identity_hash.hex(),
                    },
                    log_level=getattr(RNS, "LOG_WARNING", 2),
                )
        for destination_hash in self._decode_lxmf_hashes(
            lxmf_config.prioritised_lxmf_destinations,
            field="prioritise_destinations",
        ):
            try:
                self._invoke_router_hook("prioritise", destination_hash)
            except Exception as exc:  # pragma: no cover - defensive logging
                report_nonfatal_exception(
                    getattr(self, "event_log", None),
                    "lxmf_runtime_error",
                    f"Failed to prioritise LXMF destination {destination_hash.hex()}: {exc}",
                    exc,
                    metadata={
                        "operation": "router_runtime_config",
                        "hook": "prioritise",
                        "destination_hash": destination_hash.hex(),
                    },
                    log_level=getattr(RNS, "LOG_WARNING", 2),
                )
        for destination_hash in self._load_lxmf_sidecar_hashes(
            "ignored",
            field="ignored",
        ):
            try:
                self._invoke_router_hook("ignore_destination", destination_hash)
            except Exception as exc:  # pragma: no cover - defensive logging
                report_nonfatal_exception(
                    getattr(self, "event_log", None),
                    "lxmf_runtime_error",
                    f"Failed to ignore LXMF destination {destination_hash.hex()}: {exc}",
                    exc,
                    metadata={
                        "operation": "router_runtime_config",
                        "hook": "ignore_destination",
                        "destination_hash": destination_hash.hex(),
                    },
                    log_level=getattr(RNS, "LOG_WARNING", 2),
                )

    def _handle_lxmf_on_inbound(self, message: LXMF.LXMessage) -> None:
        """Run the configured inbound handler command after persisting the message."""

        config_manager = getattr(self, "config_manager", None)
        if config_manager is None:
            return
        config = getattr(config_manager, "config", None)
        lxmf_config = getattr(config, "lxmf_router", None)
        if lxmf_config is None:
            return

        command = getattr(lxmf_config, "on_inbound", None)
        if not command:
            return

        storage_path = getattr(self, "storage_path", None)
        if storage_path is None:
            return

        inbound_directory = Path(str(storage_path)) / "lxmf_inbound"
        inbound_directory.mkdir(parents=True, exist_ok=True)
        try:
            written_path = message.write_to_directory(str(inbound_directory))
        except Exception as exc:  # pragma: no cover - defensive logging
            report_nonfatal_exception(
                getattr(self, "event_log", None),
                "lxmf_runtime_error",
                f"Failed to persist inbound LXMF message for on_inbound: {exc}",
                exc,
                metadata={
                    "operation": "on_inbound_persist",
                    "command": command,
                    "directory": str(inbound_directory),
                },
                log_level=getattr(RNS, "LOG_WARNING", 2),
            )
            return

        main_module = sys.modules.get("reticulum_telemetry_hub.reticulum_server.__main__")
        subprocess_module = getattr(main_module, "subprocess", subprocess)
        try:
            subprocess_module.call(  # noqa: S603
                [
                    *shlex.split(command, posix=os.name != "nt"),
                    str(written_path),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            report_nonfatal_exception(
                getattr(self, "event_log", None),
                "lxmf_runtime_error",
                f"Failed to execute LXMF on_inbound command '{command}': {exc}",
                exc,
                metadata={
                    "operation": "on_inbound_execute",
                    "command": command,
                    "path": str(written_path),
                },
                log_level=getattr(RNS, "LOG_WARNING", 2),
            )
