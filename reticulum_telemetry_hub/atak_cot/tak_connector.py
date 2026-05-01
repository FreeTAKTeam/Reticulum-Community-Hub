"""Utilities for building and transmitting ATAK Cursor-on-Target events."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

import RNS
from reticulum_telemetry_hub.atak_cot.tak_connector_chat import TakChatMixin
from reticulum_telemetry_hub.atak_cot.tak_connector_location import TakLocationMixin
from reticulum_telemetry_hub.atak_cot.tak_connector_models import LocationSnapshot
from reticulum_telemetry_hub.config.models import TakConnectionConfig
from reticulum_telemetry_hub.lxmf_telemetry.telemeter_manager import (
    TelemeterManager,
)
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)

if TYPE_CHECKING:
    from reticulum_telemetry_hub.atak_cot.pytak_client import PytakClient

__all__ = [
    "LocationSnapshot",
    "TakConnector",
]


class TakConnector(TakLocationMixin, TakChatMixin):  # pylint: disable=too-many-instance-attributes
    """Build and transmit CoT events describing the hub's location."""

    EVENT_TYPE = "a-f-G-U-C"
    EVENT_HOW = "h-g-i-g-o"
    CHAT_LINK_TYPE = "a-f-G-U-C-I"
    CHAT_EVENT_TYPE = "b-t-f"
    CHAT_EVENT_HOW = "h-g-i-g-o"
    TAKV_VERSION = "0.44.0"
    TAKV_PLATFORM = "RetTAK"
    TAKV_OS = "ubuntu"
    TAKV_DEVICE = "not your business"
    GROUP_NAME = "Yellow"
    GROUP_ROLE = "Team Member"
    STATUS_BATTERY = 0.0

    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        config: TakConnectionConfig | None = None,
        pytak_client: PytakClient | None = None,
        telemeter_manager: TelemeterManager | None = None,
        telemetry_controller: TelemetryController | None = None,
        identity_lookup: Callable[[str | bytes | None], str] | None = None,
    ) -> None:
        """Initialize the connector with optional collaborators.

        Args:
            config (TakConnectionConfig | None): Connection parameters for
                PyTAK. Defaults to a new :class:`TakConnectionConfig` when
                omitted.
            pytak_client (PytakClient | None): Client used to create and send
                messages. A default client is created when not provided.
            telemeter_manager (TelemeterManager | None): Manager that exposes
                live sensor data.
            telemetry_controller (TelemetryController | None): Controller used
                for fallback location lookups.
            identity_lookup (Callable[[str | bytes | None], str] | None):
                Optional lookup used to resolve destination hashes into human
                readable labels.
        """

        self._config = config or TakConnectionConfig()
        if pytak_client is None:
            from reticulum_telemetry_hub.atak_cot.pytak_client import PytakClient

            pytak_client = PytakClient(self._config.to_config_parser())
        self._pytak_client = pytak_client
        self._config_parser = self._config.to_config_parser()
        self._telemeter_manager = telemeter_manager
        self._telemetry_controller = telemetry_controller
        self._identity_lookup = identity_lookup

    @property
    def config(self) -> TakConnectionConfig:
        """Return the current TAK connection configuration.

        Returns:
            TakConnectionConfig: Active configuration for outbound CoT events.
        """

        return self._config

    async def send_keepalive(self) -> bool:
        """Transmit a takPong CoT event to keep the TAK session alive.

        Returns:
            bool: ``True`` when the keepalive is dispatched.
        """

        from pytak.functions import tak_pong

        RNS.log("TAK connector sending keepalive takPong", RNS.LOG_DEBUG)
        await self._pytak_client.create_and_send_message(
            tak_pong(), config=self._config_parser, parse_inbound=False
        )
        return True

    async def send_ping(self) -> bool:
        """Send a TAK hello/ping keepalive event."""

        from pytak import hello_event

        RNS.log("TAK connector sending ping", RNS.LOG_DEBUG)
        await self._pytak_client.create_and_send_message(
            hello_event(), config=self._config_parser, parse_inbound=False
        )
        return True

    def _uid_from_hash(self, peer_hash: str | bytes | None) -> str:
        """Return a CoT UID derived from an LXMF destination hash."""

        normalized = self._normalize_hash(peer_hash)
        return normalized or self._config.callsign

    def _callsign_from_hash(self, peer_hash: str | bytes | None) -> str:
        """Return a callsign preferring identity labels when available."""

        label = self._label_from_identity(peer_hash)
        if label:
            return label
        normalized = self._normalize_hash(peer_hash)
        return normalized or self._config.callsign

    def _identifier_from_hash(self, peer_hash: str | bytes | None) -> str:
        """Return a short identifier suitable for chat UIDs."""

        label = self._label_from_identity(peer_hash)
        if label:
            return label
        normalized = self._normalize_hash(peer_hash) or self._config.callsign
        if len(normalized) > 12:
            return normalized[-12:]
        return normalized

    def _normalize_hash(self, peer_hash: str | bytes | None) -> str:
        """Normalize LXMF destination hashes for use in UIDs."""

        if peer_hash is None:
            return ""
        if isinstance(peer_hash, (bytes, bytearray)):
            normalized = peer_hash.hex()
        else:
            normalized = str(peer_hash).strip()
        normalized = normalized.replace(":", "")
        return normalized

    def _label_from_identity(self, peer_hash: str | bytes | None) -> str | None:
        """Return a display label for ``peer_hash`` when a lookup is available.

        Args:
            peer_hash (str | bytes | None): Destination hash supplied by the
                telemetry source.

        Returns:
            str | None: A human-friendly label if the lookup yields one.
        """

        if self._identity_lookup is None:
            return None
        if peer_hash is None:
            return None
        try:
            label = self._identity_lookup(peer_hash)
        except Exception:  # pylint: disable=broad-exception-caught
            return None
        if label is None:
            return None
        cleaned = str(label).strip()
        return cleaned or None

    def _coerce_float(
        self, value: Any, *, default: float | None = None
    ) -> float | None:
        """Safely cast a value to ``float`` when possible."""

        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _coerce_datetime(self, value: Any) -> datetime | None:
        """Parse ISO or timestamp inputs into :class:`datetime` objects."""

        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value))
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None
