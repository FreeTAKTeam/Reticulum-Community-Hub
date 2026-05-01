"""Location CoT event helpers for the TAK connector."""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta
import json
from typing import Any
from typing import Mapping
from urllib.parse import urlparse

import RNS
from sqlalchemy.orm.exc import DetachedInstanceError

from reticulum_telemetry_hub.atak_cot import Contact
from reticulum_telemetry_hub.atak_cot import Detail
from reticulum_telemetry_hub.atak_cot import Event
from reticulum_telemetry_hub.atak_cot import Group
from reticulum_telemetry_hub.atak_cot import Status
from reticulum_telemetry_hub.atak_cot import Takv
from reticulum_telemetry_hub.atak_cot import Track
from reticulum_telemetry_hub.atak_cot import Uid
from reticulum_telemetry_hub.atak_cot.tak_connector_models import LocationSnapshot
from reticulum_telemetry_hub.atak_cot.tak_connector_models import utc_iso
from reticulum_telemetry_hub.atak_cot.tak_connector_models import utcnow
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors import (
    sensor_enum,
)

SID_LOCATION = sensor_enum.SID_LOCATION


class TakLocationMixin:
    """Build and send CoT location events."""

    async def send_latest_location(self) -> bool:
        """Send the most recent location snapshot if one is available."""

        snapshots = self._latest_location_snapshots()
        if not snapshots:
            RNS.log(
                "TAK connector skipped CoT send because no location is available",
                RNS.LOG_WARNING,
            )
            return False

        dispatched = False
        for snapshot in snapshots:
            uid = self._uid_from_hash(snapshot.peer_hash)
            callsign = self._callsign_from_hash(snapshot.peer_hash)
            event = self._build_event_from_snapshot(
                snapshot, uid=uid, callsign=callsign
            )
            event_size = len(json.dumps(event.to_dict()))
            RNS.log(
                f"TAK connector sending event type {event.type} ({event_size} bytes)",
                RNS.LOG_INFO,
            )
            await self._pytak_client.create_and_send_message(
                event, config=self._config_parser, parse_inbound=False
            )
            dispatched = True
        return dispatched

    def build_event(self) -> Event | None:
        """Construct a CoT :class:`Event` from available telemetry."""

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
        """Build a CoT event directly from telemetry payloads."""

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
        """Send a CoT event derived from telemetry data."""

        event = self.build_event_from_telemetry(
            telemetry, peer_hash=peer_hash, timestamp=timestamp
        )
        if event is None:
            RNS.log(
                "TAK connector skipped CoT send because telemetry lacked location data",
                RNS.LOG_WARNING,
            )
            return False

        event_size = len(json.dumps(event.to_dict()))
        RNS.log(
            f"TAK connector sending event type {event.type} ({event_size} bytes)",
            RNS.LOG_INFO,
        )
        await self._pytak_client.create_and_send_message(
            event, config=self._config_parser, parse_inbound=False
        )
        RNS.log("TAK connector dispatched telemetry CoT event", RNS.LOG_INFO)
        return True

    def _latest_location(self) -> LocationSnapshot | None:
        """Return the freshest location snapshot available."""

        snapshots = self._latest_location_snapshots()
        if not snapshots:
            return None
        return snapshots[0]

    def _latest_location_snapshots(self) -> list[LocationSnapshot]:
        """Return location snapshots for the latest telemetry per peer."""

        snapshots: list[LocationSnapshot] = []
        seen_hashes: set[str] = set()

        manager_snapshot = self._latest_location_from_manager()
        if manager_snapshot is not None:
            normalized = self._normalize_hash(manager_snapshot.peer_hash)
            seen_hashes.add(normalized)
            snapshots.append(manager_snapshot)

        controller_snapshots = self._latest_locations_from_controller(seen_hashes)
        snapshots.extend(controller_snapshots)

        snapshots.sort(key=lambda snapshot: snapshot.updated_at, reverse=True)
        return snapshots

    def _cot_endpoint(self) -> str | None:
        """Return the contact endpoint derived from the configured COT URL."""

        parsed = urlparse(self._config.cot_url)
        if not parsed.scheme or not parsed.hostname:
            return None
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.hostname}{port}:{parsed.scheme}"

    def _latest_locations_from_controller(
        self, seen_hashes: set[str]
    ) -> list[LocationSnapshot]:
        """Return unique snapshots derived from stored telemetry entries."""

        if self._telemetry_controller is None:
            return []

        telemetry_controller = self._telemetry_controller
        snapshots: list[LocationSnapshot] = []
        # pylint: disable=protected-access
        with telemetry_controller._session_cls() as session:  # type: ignore[attr-defined]
            telemetry = telemetry_controller._load_telemetry(session)
            for telemeter in telemetry:
                peer_hash = getattr(telemeter, "peer_dest", None)
                normalized_peer = self._normalize_hash(peer_hash)
                if normalized_peer in seen_hashes:
                    continue
                snapshot = self._snapshot_from_telemeter(telemeter)
                if snapshot is None:
                    continue
                snapshot.peer_hash = (
                    peer_hash if peer_hash is not None else snapshot.peer_hash
                )
                snapshots.append(snapshot)
                seen_hashes.add(normalized_peer)
        snapshots.sort(key=lambda snap: snap.updated_at, reverse=True)
        return snapshots

    def _latest_location_from_manager(self) -> LocationSnapshot | None:
        """Extract the latest location data from the telemeter manager."""

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
        updated_at = getattr(sensor, "last_update", None) or utcnow()
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
        """Extract the latest location data from the telemetry controller."""

        if self._telemetry_controller is None:
            return None

        telemetry = self._telemetry_controller.get_telemetry()
        if not telemetry:
            return None

        snapshot = self._snapshot_from_telemeter(telemetry[0])
        if snapshot is None:
            return None
        snapshot.peer_hash = getattr(telemetry[0], "peer_dest", None)
        return snapshot

    def _snapshot_from_telemeter(self, telemeter: Any) -> LocationSnapshot | None:
        """Convert a stored telemeter entry into a location snapshot."""

        location_sensor = None
        for sensor in getattr(telemeter, "sensors", []):
            if getattr(sensor, "sid", None) == SID_LOCATION:
                location_sensor = sensor
                break

        if location_sensor is None:
            return None

        try:
            latitude = getattr(location_sensor, "latitude", None)
            longitude = getattr(location_sensor, "longitude", None)
            altitude = getattr(location_sensor, "altitude", 0.0) or 0.0
            speed = getattr(location_sensor, "speed", 0.0) or 0.0
            bearing = getattr(location_sensor, "bearing", 0.0) or 0.0
            accuracy = getattr(location_sensor, "accuracy", 0.0) or 0.0
            updated_at = getattr(location_sensor, "last_update", None)
        except DetachedInstanceError:
            sensor_state = getattr(location_sensor, "__dict__", {}) or {}
            latitude = sensor_state.get("latitude")
            longitude = sensor_state.get("longitude")
            altitude = sensor_state.get("altitude", 0.0) or 0.0
            speed = sensor_state.get("speed", 0.0) or 0.0
            bearing = sensor_state.get("bearing", 0.0) or 0.0
            accuracy = sensor_state.get("accuracy", 0.0) or 0.0
            updated_at = sensor_state.get("last_update")

        if (latitude is None or longitude is None) and hasattr(
            location_sensor, "unpack"
        ):
            packed_payload = getattr(location_sensor, "data", None)
            if packed_payload is not None:
                try:
                    location_sensor.unpack(packed_payload)
                    latitude = getattr(location_sensor, "latitude", latitude)
                    longitude = getattr(location_sensor, "longitude", longitude)
                    altitude = getattr(location_sensor, "altitude", altitude)
                    speed = getattr(location_sensor, "speed", speed)
                    bearing = getattr(location_sensor, "bearing", bearing)
                    accuracy = getattr(location_sensor, "accuracy", accuracy)
                    updated_at = getattr(location_sensor, "last_update", updated_at)
                except Exception:  # pylint: disable=broad-exception-caught
                    return None

        if latitude is None or longitude is None:
            return None

        updated_at = updated_at or getattr(telemeter, "time", utcnow())

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
        """Return a CoT event populated from a location snapshot."""

        now = utcnow()
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
            "time": utc_iso(now),
            "start": utc_iso(snapshot.updated_at),
            "stale": utc_iso(stale),
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
        """Convert a telemetry payload into a location snapshot."""

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
            updated_at = timestamp or utcnow()

        return LocationSnapshot(
            latitude=latitude,
            longitude=longitude,
            altitude=altitude or 0.0,
            speed=speed or 0.0,
            bearing=bearing or 0.0,
            accuracy=accuracy or 0.0,
            updated_at=updated_at,
        )
