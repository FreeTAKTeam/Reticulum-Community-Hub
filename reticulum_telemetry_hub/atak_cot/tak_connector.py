from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Mapping
from urllib.parse import urlparse
import json
import uuid

import RNS
from pytak.functions import tak_pong
from reticulum_telemetry_hub.atak_cot import Chat
from reticulum_telemetry_hub.atak_cot import ChatGroup
from reticulum_telemetry_hub.atak_cot import ChatHierarchy
from reticulum_telemetry_hub.atak_cot import ChatHierarchyContact
from reticulum_telemetry_hub.atak_cot import ChatHierarchyGroup
from reticulum_telemetry_hub.atak_cot import Contact
from reticulum_telemetry_hub.atak_cot import Detail
from reticulum_telemetry_hub.atak_cot import Event
from reticulum_telemetry_hub.atak_cot import Group
from reticulum_telemetry_hub.atak_cot import Link
from reticulum_telemetry_hub.atak_cot import Remarks
from reticulum_telemetry_hub.atak_cot import Status
from reticulum_telemetry_hub.atak_cot import Takv
from reticulum_telemetry_hub.atak_cot import Track
from reticulum_telemetry_hub.atak_cot import Uid
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
    EVENT_HOW = "h-g-i-g-o"
    CHAT_LINK_TYPE = "a-f-G-U-C-I"
    CHAT_EVENT_TYPE = "b-t-f"
    CHAT_EVENT_HOW = "h-g-i-g-o"
    TAKV_VERSION = "4.9.0.156"
    TAKV_PLATFORM = "WinTAK-CIV"
    TAKV_OS = "Microsoft Windows 11 Pro"
    TAKV_DEVICE = "LENOVO 20XW003LUS"
    GROUP_NAME = "Yellow"
    GROUP_ROLE = "Team Member"
    STATUS_BATTERY = 0.0

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
                "TAK connector skipped CoT send because no location is " "available",
                RNS.LOG_WARNING,
            )
            return False
        event_payload = json.dumps(event.to_dict())
        RNS.log(
            f"TAK connector sending event type {event.type} with payload: {event_payload}",
            RNS.LOG_INFO,
        )
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

        uid = self._uid_from_hash(snapshot.peer_hash)
        callsign = self._callsign_from_hash(snapshot.peer_hash)
        return self._build_event_from_snapshot(snapshot, uid=uid, callsign=callsign)

    def build_event_from_telemetry(
        self,
        telemetry: Mapping[str, Any],
        *,
        peer_hash: str | bytes | None,
        timestamp: datetime | None = None,
    ) -> Event | None:
        """Build a CoT event directly from telemetry payloads.

        Args:
            telemetry (Mapping[str, Any]): Human-readable telemetry payload as
                decoded by :class:`TelemetryController`.
            peer_hash (str | bytes | None): LXMF destination hash identifying
                the telemetry sender.
            timestamp (datetime | None): Optional timestamp associated with the
                payload.

        Returns:
            Event | None: A populated CoT event when a location sensor exists,
            otherwise ``None``.
        """

        snapshot = self._snapshot_from_telemetry(telemetry, timestamp)
        if snapshot is None:
            return None

        uid = self._uid_from_hash(peer_hash)
        callsign = self._callsign_from_hash(peer_hash)
        snapshot.peer_hash = peer_hash if peer_hash is not None else snapshot.peer_hash
        return self._build_event_from_snapshot(snapshot, uid=uid, callsign=callsign)

    async def send_telemetry_event(
        self,
        telemetry: Mapping[str, Any],
        *,
        peer_hash: str | bytes | None,
        timestamp: datetime | None = None,
    ) -> bool:
        """Send a CoT event derived from telemetry data.

        Args:
            telemetry (Mapping[str, Any]): Telemetry payload to convert.
            peer_hash (str | bytes | None): LXMF destination hash identifying
                the telemetry sender.
            timestamp (datetime | None): Optional timestamp associated with the
                payload.

        Returns:
            bool: ``True`` when an event is transmitted, ``False`` when
            location data is missing.
        """

        event = self.build_event_from_telemetry(
            telemetry, peer_hash=peer_hash, timestamp=timestamp
        )
        if event is None:
            RNS.log(
                "TAK connector skipped CoT send because telemetry lacked location data",
                RNS.LOG_WARNING,
            )
            return False

        event_payload = json.dumps(event.to_dict())
        RNS.log(
            f"TAK connector sending event type {event.type} with payload: {event_payload}",
            RNS.LOG_INFO,
        )
        await self._pytak_client.create_and_send_message(
            event, config=self._config_parser, parse_inbound=False
        )
        RNS.log("TAK connector dispatched telemetry CoT event", RNS.LOG_INFO)
        return True

    async def send_keepalive(self) -> bool:
        """Transmit a takPong CoT event to keep the TAK session alive.

        Returns:
            bool: ``True`` when the keepalive is dispatched.
        """

        RNS.log("TAK connector sending keepalive takPong", RNS.LOG_DEBUG)
        await self._pytak_client.create_and_send_message(
            tak_pong(), config=self._config_parser, parse_inbound=False
        )
        return True

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
        uid = f"GeoChat.{identifier}-chat-{timestamp_ms}-{uid_suffix}"

        chatroom = str(topic_id) if topic_id else "GeoChat"
        chat_group = ChatGroup(
            chatroom=chatroom,
            chat_id=chatroom,
            uid0=identifier,
            uid1="",
        )
        hierarchy_contact = ChatHierarchyContact(
            uid=identifier, name=sender_label or identifier
        )
        chat_hierarchy_group = ChatHierarchyGroup(
            uid=chatroom,
            name=chatroom,
            contacts=[hierarchy_contact],
        )
        hierarchy_root = ChatHierarchyGroup(
            uid="TeamGroups",
            name="Teams",
            groups=[chat_hierarchy_group],
        )
        hierarchy = ChatHierarchy(groups=[hierarchy_root])
        chat = Chat(
            id=chatroom,
            chatroom=chatroom,
            sender_callsign=sender_label or identifier,
            group_owner="false",
            chat_group=chat_group,
            hierarchy=hierarchy,
        )
        link = Link(
            uid=identifier,
            type=self.CHAT_LINK_TYPE,
            relation="p-p",
        )

        remarks = Remarks(
            text=content.strip(),
            source=f"BAO.F.{sender_label}.{identifier}",
            source_id=identifier,
            to=chatroom,
            time=_utc_iso(start_time),
        )

        detail = Detail(
            chat=chat,
            links=[link],
            remarks=remarks,
        )

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
        event_payload = json.dumps(event.to_dict())
        RNS.log(
            f"TAK connector sending event type {event.type} with payload: {event_payload}",
            RNS.LOG_INFO,
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

    def _cot_endpoint(self) -> str | None:
        """Return the contact endpoint derived from the configured COT URL."""

        parsed = urlparse(self._config.cot_url)
        if not parsed.scheme or not parsed.hostname:
            return None
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.hostname}{port}:{parsed.scheme}"

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

    def _build_event_from_snapshot(
        self, snapshot: LocationSnapshot, *, uid: str, callsign: str
    ) -> Event:
        """Return a CoT event populated from a location snapshot.

        Args:
            snapshot (LocationSnapshot): Position and movement metadata.
            uid (str): UID assigned to the CoT event.
            callsign (str): Callsign used for the contact detail.

        Returns:
            Event: A populated CoT event ready for serialization.
        """

        now = datetime.utcnow()
        stale_delta = max(self._config.poll_interval_seconds, 1.0)
        stale = now + timedelta(seconds=stale_delta * 2)

        contact = Contact(callsign=callsign, endpoint=self._cot_endpoint())
        group = Group(name=self.GROUP_NAME, role=self.GROUP_ROLE)
        track = Track(course=snapshot.bearing, speed=snapshot.speed)
        takv = Takv(
            version=self.TAKV_VERSION,
            platform=self.TAKV_PLATFORM,
            os=self.TAKV_OS,
            device=self.TAKV_DEVICE,
        )
        detail = Detail(
            contact=contact,
            group=group,
            track=track,
            takv=takv,
            uid=Uid(droid=callsign),
            status=Status(battery=self.STATUS_BATTERY),
        )

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

    def _snapshot_from_telemetry(
        self, telemetry: Mapping[str, Any], timestamp: datetime | None
    ) -> LocationSnapshot | None:
        """Convert a telemetry payload into a location snapshot.

        Args:
            telemetry (Mapping[str, Any]): Human-readable telemetry payload.
            timestamp (datetime | None): Optional timestamp to use when sensor
                timestamps are absent.

        Returns:
            LocationSnapshot | None: Snapshot when location data exists.
        """

        location = telemetry.get("location")
        if not isinstance(location, Mapping):
            return None

        latitude = self._coerce_float(location.get("latitude"))
        longitude = self._coerce_float(location.get("longitude"))
        if latitude is None or longitude is None:
            return None

        altitude = self._coerce_float(location.get("altitude"), default=0.0)
        speed = self._coerce_float(location.get("speed"), default=0.0)
        bearing = self._coerce_float(location.get("bearing"), default=0.0)
        accuracy = self._coerce_float(location.get("accuracy"), default=0.0)

        updated_at = self._coerce_datetime(location.get("last_update_iso"))
        if updated_at is None:
            updated_at = self._coerce_datetime(location.get("last_update_timestamp"))
        if updated_at is None:
            updated_at = timestamp or datetime.utcnow()

        return LocationSnapshot(
            latitude=latitude,
            longitude=longitude,
            altitude=altitude or 0.0,
            speed=speed or 0.0,
            bearing=bearing or 0.0,
            accuracy=accuracy or 0.0,
            updated_at=updated_at,
        )

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
        except Exception:
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
