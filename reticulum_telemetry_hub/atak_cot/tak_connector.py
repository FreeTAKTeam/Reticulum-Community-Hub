from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable
import uuid

from reticulum_telemetry_hub.atak_cot import Contact
from reticulum_telemetry_hub.atak_cot import Detail
from reticulum_telemetry_hub.atak_cot import Event
from reticulum_telemetry_hub.atak_cot import Group
from reticulum_telemetry_hub.atak_cot.pytak_client import PytakClient
from reticulum_telemetry_hub.config.models import TakConnectionConfig
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors import (
    sensor_enum,
)
from reticulum_telemetry_hub.lxmf_telemetry.telemeter_manager import (
    TelemeterManager,
)
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_controller import (
    TelemetryController,
)

SID_LOCATION = sensor_enum.SID_LOCATION


@dataclass
class LocationSnapshot:
    """Represents the latest known position of the hub."""

    latitude: float
    longitude: float
    altitude: float
    speed: float
    bearing: float
    accuracy: float
    updated_at: datetime
    peer_hash: str | None = None


def _utc_iso(dt: datetime) -> str:
    """Format a ``datetime`` in UTC without microseconds.

    Args:
        dt (datetime): Datetime to normalise.

    Returns:
        str: ISO-8601 timestamp suffixed with ``Z``.
    """

    return dt.replace(microsecond=0).isoformat() + "Z"


class TakConnector:
    """Build and transmit CoT events describing the hub's location."""

    EVENT_TYPE = "a-f-G-U-C"
    EVENT_HOW = "m-g"
    CHAT_EVENT_TYPE = "b-t-f"
    CHAT_EVENT_HOW = "h-g-i-g-o"

    def __init__(
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
        self._pytak_client = pytak_client or PytakClient(
            self._config.to_config_parser()
        )
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

    async def send_latest_location(self) -> bool:
        """Send the most recent location snapshot if one is available.

        Returns:
            bool: ``True`` when a message was dispatched, ``False`` when no
            location was available.
        """

        event = self.build_event()
        if event is None:
            RNS.log(
                "TAK connector skipped CoT send because no location is available",
                RNS.LOG_WARNING,
            )
            return False
        await self._pytak_client.create_and_send_message(
            event, config=self._config_parser, parse_inbound=False
        )
        RNS.log("TAK connector dispatched latest CoT event", RNS.LOG_INFO)
        return True

    def build_event(self) -> Event | None:
        """Construct a CoT :class:`Event` from available telemetry.

        Returns:
            Event | None: Populated CoT event or ``None`` when no location
            snapshot exists.
        """

        snapshot = self._latest_location()
        if snapshot is None:
            return None

        now = datetime.utcnow()
        stale_delta = max(self._config.poll_interval_seconds, 1.0)
        stale = now + timedelta(seconds=stale_delta * 2)

        identifier = self._identifier_from_hash(snapshot.peer_hash)
        uid = identifier if identifier else self._config.callsign
        if identifier and identifier != self._config.callsign:
            uid = f"{self._config.callsign}-{identifier}"

        contact = Contact(callsign=identifier or self._config.callsign)
        detail = Detail(contact=contact)

        event_dict = {
            "version": "2.0",
            "uid": uid,
            "type": self.EVENT_TYPE,
            "how": self.EVENT_HOW,
            "time": _utc_iso(now),
            "start": _utc_iso(snapshot.updated_at),
            "stale": _utc_iso(stale),
            "point": {
                "lat": snapshot.latitude,
                "lon": snapshot.longitude,
                "hae": snapshot.altitude,
                "ce": snapshot.accuracy,
                "le": snapshot.accuracy,
            },
            "detail": detail.to_dict(),
        }
        return Event.from_dict(event_dict)

    def build_chat_event(
        self,
        *,
        content: str,
        sender_label: str,
        topic_id: str | None = None,
        source_hash: str | None = None,
        timestamp: datetime | None = None,
    ) -> Event:
        """Construct a CoT chat :class:`Event` for LXMF message content.

        Args:
            content (str): Plaintext chat body to relay.
            sender_label (str): Human-readable label for the sender.
            topic_id (str | None): Optional topic identifier for routing.
            source_hash (str | None): Optional sender hash used to derive the
                UID.
            timestamp (datetime | None): Time the LXMF message was created.

        Returns:
            Event: Populated CoT chat event ready for transmission.
        """

        if not content:
            raise ValueError("Chat content is required to build a CoT event.")

        now = datetime.utcnow()
        start_time = timestamp or now
        stale_delta = max(self._config.poll_interval_seconds, 1.0)
        stale = now + timedelta(seconds=stale_delta * 2)

        snapshot = self._latest_location()
        latitude = snapshot.latitude if snapshot else 0.0
        longitude = snapshot.longitude if snapshot else 0.0
        altitude = snapshot.altitude if snapshot else 0.0
        accuracy = snapshot.accuracy if snapshot else 0.0

        identifier = self._identifier_from_hash(source_hash)
        timestamp_ms = int(start_time.timestamp() * 1000)
        uid_suffix = uuid.uuid4().hex[:6]
        uid = f"{identifier}-chat-{timestamp_ms}-{uid_suffix}"
        contact = Contact(callsign=sender_label or identifier)
        group = Group(name=str(topic_id), role="topic") if topic_id else None

        remarks = content.strip()
        if topic_id:
            remarks = f"[topic:{topic_id}] {remarks}"

        detail = Detail(contact=contact, group=group, remarks=remarks)

        event_dict = {
            "version": "2.0",
            "uid": uid,
            "type": self.CHAT_EVENT_TYPE,
            "how": self.CHAT_EVENT_HOW,
            "time": _utc_iso(now),
            "start": _utc_iso(start_time),
            "stale": _utc_iso(stale),
            "point": {
                "lat": latitude,
                "lon": longitude,
                "hae": altitude,
                "ce": accuracy,
                "le": accuracy,
            },
            "detail": detail.to_dict(),
        }
        return Event.from_dict(event_dict)

    async def send_chat_event(
        self,
        *,
        content: str,
        sender_label: str,
        topic_id: str | None = None,
        source_hash: str | None = None,
        timestamp: datetime | None = None,
    ) -> bool:
        """Send a CoT chat event derived from LXMF payloads.

        Args:
            content (str): Plaintext chat body to relay.
            sender_label (str): Human-readable label for the sender.
            topic_id (str | None): Optional topic identifier for routing.
            source_hash (str | None): Optional sender hash used to derive the
                UID.
            timestamp (datetime | None): Time the LXMF message was created.

        Returns:
            bool: ``True`` when a message was dispatched.
        """

        event = self.build_chat_event(
            content=content,
            sender_label=sender_label,
            topic_id=topic_id,
            source_hash=source_hash,
            timestamp=timestamp,
        )
        await self._pytak_client.create_and_send_message(
            event, config=self._config_parser, parse_inbound=False
        )
        return True

    def _latest_location(self) -> LocationSnapshot | None:
        """Return the freshest location snapshot available.

        Returns:
            LocationSnapshot | None: Most recent location if available.
        """

        location = self._latest_location_from_manager()
        if location is not None:
            return location
        return self._latest_location_from_controller()

    def _latest_location_from_manager(self) -> LocationSnapshot | None:
        """Extract the latest location data from the telemeter manager.

        Returns:
            LocationSnapshot | None: Location snapshot when a location sensor
            exists.
        """

        if self._telemeter_manager is None:
            return None

        sensor = self._telemeter_manager.get_sensor("location")
        if sensor is None:
            return None

        latitude = getattr(sensor, "latitude", None)
        longitude = getattr(sensor, "longitude", None)
        if latitude is None or longitude is None:
            return None

        altitude = getattr(sensor, "altitude", 0.0) or 0.0
        speed = getattr(sensor, "speed", 0.0) or 0.0
        bearing = getattr(sensor, "bearing", 0.0) or 0.0
        accuracy = getattr(sensor, "accuracy", 0.0) or 0.0
        updated_at = getattr(sensor, "last_update", None) or datetime.utcnow()
        peer_hash = getattr(
            getattr(self._telemeter_manager, "telemeter", None),
            "peer_dest",
            None,
        )

        return LocationSnapshot(
            latitude=float(latitude),
            longitude=float(longitude),
            altitude=float(altitude),
            speed=float(speed),
            bearing=float(bearing),
            accuracy=float(accuracy),
            updated_at=updated_at,
            peer_hash=str(peer_hash) if peer_hash is not None else None,
        )

    def _latest_location_from_controller(self) -> LocationSnapshot | None:
        """Extract the latest location data from the telemetry controller.

        Returns:
            LocationSnapshot | None: Location snapshot derived from stored
            telemetry.
        """

        if self._telemetry_controller is None:
            return None

        telemetry = self._telemetry_controller.get_telemetry()
        if not telemetry:
            return None

        telemeter = telemetry[0]
        location_sensor = None
        for sensor in getattr(telemeter, "sensors", []):
            if getattr(sensor, "sid", None) == SID_LOCATION:
                location_sensor = sensor
                break

        if location_sensor is None:
            return None

        latitude = getattr(location_sensor, "latitude", None)
        longitude = getattr(location_sensor, "longitude", None)
        if latitude is None or longitude is None:
            return None

        altitude = getattr(location_sensor, "altitude", 0.0) or 0.0
        speed = getattr(location_sensor, "speed", 0.0) or 0.0
        bearing = getattr(location_sensor, "bearing", 0.0) or 0.0
        accuracy = getattr(location_sensor, "accuracy", 0.0) or 0.0
        updated_at = getattr(location_sensor, "last_update", None) or getattr(
            telemeter, "time", datetime.utcnow()
        )

        return LocationSnapshot(
            latitude=float(latitude),
            longitude=float(longitude),
            altitude=float(altitude),
            speed=float(speed),
            bearing=float(bearing),
            accuracy=float(accuracy),
            updated_at=updated_at,
            peer_hash=getattr(telemeter, "peer_dest", None),
        )

    def _identifier_from_hash(self, peer_hash: str | bytes | None) -> str:
        """Derive a readable identifier from a destination hash.

        Args:
            peer_hash (str | bytes | None): Destination hash extracted from the
                telemeter or controller.

        Returns:
            str: Callsign-compatible identifier.
        """

        label = self._label_from_identity(peer_hash)
        if label:
            return label
        if peer_hash is None:
            return self._config.callsign
        if isinstance(peer_hash, (bytes, bytearray)):
            normalized = peer_hash.hex()
        else:
            normalized = str(peer_hash).strip()
        normalized = normalized.replace(":", "") or self._config.callsign
        if len(normalized) > 12:
            normalized = normalized[-12:]
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
        except Exception:
            return None
        if label is None:
            return None
        cleaned = str(label).strip()
        return cleaned or None
