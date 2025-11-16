from datetime import datetime
from pathlib import Path
import string
from typing import Optional

import LXMF
import RNS
from msgpack import packb, unpackb
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance import Base
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor import (
    Sensor,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.telemeter import (
    Telemeter,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.lxmf_propagation import (
    LXMFPropagation,
)

from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_mapping import (
    sid_mapping,
)
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_enum import (
    SID_ACCELERATION,
    SID_AMBIENT_LIGHT,
    SID_ANGULAR_VELOCITY,
    SID_BATTERY,
    SID_CONNECTION_MAP,
    SID_CUSTOM,
    SID_FUEL,
    SID_GRAVITY,
    SID_HUMIDITY,
    SID_INFORMATION,
    SID_LOCATION,
    SID_LXMF_PROPAGATION,
    SID_MAGNETIC_FIELD,
    SID_NVM,
    SID_PHYSICAL_LINK,
    SID_POWER_CONSUMPTION,
    SID_POWER_PRODUCTION,
    SID_PRESSURE,
    SID_PROCESSOR,
    SID_PROXIMITY,
    SID_RAM,
    SID_RECEIVED,
    SID_RNS_TRANSPORT,
    SID_TANK,
    SID_TEMPERATURE,
    SID_TIME,
)
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, joinedload, sessionmaker


class TelemetryController:
    """This class is responsible for managing the telemetry data."""

    TELEMETRY_REQUEST = 1
    SID_HUMAN_NAMES = {
        SID_TIME: "time",
        SID_LOCATION: "location",
        SID_PRESSURE: "pressure",
        SID_BATTERY: "battery",
        SID_PHYSICAL_LINK: "physical_link",
        SID_ACCELERATION: "acceleration",
        SID_TEMPERATURE: "temperature",
        SID_HUMIDITY: "humidity",
        SID_MAGNETIC_FIELD: "magnetic_field",
        SID_AMBIENT_LIGHT: "ambient_light",
        SID_GRAVITY: "gravity",
        SID_ANGULAR_VELOCITY: "angular_velocity",
        SID_PROXIMITY: "proximity",
        SID_INFORMATION: "information",
        SID_RECEIVED: "received",
        SID_POWER_CONSUMPTION: "power_consumption",
        SID_POWER_PRODUCTION: "power_production",
        SID_PROCESSOR: "processor",
        SID_RAM: "ram",
        SID_NVM: "nvm",
        SID_TANK: "tank",
        SID_FUEL: "fuel",
        SID_LXMF_PROPAGATION: "lxmf_propagation",
        SID_RNS_TRANSPORT: "rns_transport",
        SID_CONNECTION_MAP: "connection_map",
        SID_CUSTOM: "custom",
    }

    def __init__(
        self,
        *,
        engine: Engine | None = None,
        db_path: str | Path | None = None,
    ) -> None:
        if engine is not None and db_path is not None:
            raise ValueError("Provide either 'engine' or 'db_path', not both")

        if engine is None:
            db_location = Path(db_path) if db_path is not None else Path("telemetry.db")
            engine = create_engine(f"sqlite:///{db_location}")

        self._engine = engine
        Base.metadata.create_all(self._engine)
        self._session_cls = sessionmaker(bind=self._engine, expire_on_commit=False)

    def _load_telemetry(
        self,
        session: Session,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> list[Telemeter]:
        query = session.query(Telemeter)
        if start_time:
            query = query.filter(Telemeter.time >= start_time)
        if end_time:
            query = query.filter(Telemeter.time <= end_time)
        query = query.order_by(Telemeter.time.desc())
        tels = query.options(
            joinedload(Telemeter.sensors),
            joinedload(Telemeter.sensors.of_type(LXMFPropagation)).joinedload(
                LXMFPropagation.peers
            ),
        ).all()
        return tels

    def get_telemetry(
        self, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None
    ) -> list[Telemeter]:
        """Get the telemetry data."""
        with self._session_cls() as ses:
            return self._load_telemetry(ses, start_time, end_time)

    def save_telemetry(
        self, telemetry_data: dict, peer_dest, timestamp: Optional[datetime] = None
    ) -> None:
        """Save the telemetry data."""
        tel = self._deserialize_telemeter(telemetry_data, peer_dest)
        if timestamp is not None:
            tel.time = timestamp
        with self._session_cls() as ses:
            ses.add(tel)
            ses.commit()

    def handle_message(self, message: LXMF.LXMessage) -> bool:
        """Handle the incoming message."""
        handled = False
        if LXMF.FIELD_TELEMETRY in message.fields:
            tel_data: dict = unpackb(
                message.fields[LXMF.FIELD_TELEMETRY], strict_map_key=False
            )
            readable = self._humanize_telemetry(tel_data)
            RNS.log(f"Telemetry received from {RNS.hexrep(message.source_hash, False)}")
            RNS.log(f"Telemetry decoded: {readable}")
            self.save_telemetry(tel_data, RNS.hexrep(message.source_hash, False))
            handled = True
        if LXMF.FIELD_TELEMETRY_STREAM in message.fields:
            tels_data = unpackb(
                message.fields[LXMF.FIELD_TELEMETRY_STREAM], strict_map_key=False
            )
            for tel_data in tels_data:
                tel_entry = list(tel_data)
                peer_hash = tel_entry.pop(0)
                peer_dest = RNS.hexrep(peer_hash, False)
                timestamp = None
                if tel_entry:
                    raw_timestamp = tel_entry.pop(0)
                    if raw_timestamp is not None:
                        timestamp = datetime.fromtimestamp(raw_timestamp)
                payload = tel_entry.pop(0) if tel_entry else None
                if not payload:
                    RNS.log("Telemetry payload missing; skipping entry")
                    continue
                readable = self._humanize_telemetry(payload)
                RNS.log(f"Telemetry stream from {peer_dest} at {timestamp}: {readable}")
                self.save_telemetry(payload, peer_dest, timestamp)
            handled = True

        return handled

    def handle_command(self, command: dict, message: LXMF.LXMessage, my_lxm_dest) -> Optional[LXMF.LXMessage]:
        """Handle the incoming command."""
        if TelemetryController.TELEMETRY_REQUEST in command:
            request_value = command[TelemetryController.TELEMETRY_REQUEST]

            # Sideband (and compatible clients) send telemetry requests either as a
            # standalone timestamp or as ``[timestamp, collector_flag]``.  The
            # hub currently ignores the optional collector flag, but we still
            # need to unpack the timestamp so ``datetime.fromtimestamp`` doesn't
            # receive a list and raise ``TypeError``.
            if isinstance(request_value, (list, tuple)):
                if not request_value:
                    return None
                timebase_raw = request_value[0]
            else:
                timebase_raw = request_value

            if not isinstance(timebase_raw, (int, float)):
                raise TypeError(
                    "Telemetry request timestamp must be numeric; "
                    f"received {type(timebase_raw)!r}"
                )

            timebase = int(timebase_raw)
            with self._session_cls() as ses:
                timebase_dt = datetime.fromtimestamp(timebase)
                teles = self._load_telemetry(ses, start_time=timebase_dt)
                # Return one snapshot per peer using the most recent entry.
                teles = self._latest_by_peer(teles)
                packed_tels = []
                dest = RNS.Destination(
                    message.source.identity,
                    RNS.Destination.OUT,
                    RNS.Destination.SINGLE,
                    "lxmf",
                    "delivery",
                )
                message = LXMF.LXMessage(
                        dest,
                        my_lxm_dest,
                        "Telemetry data",
                        desired_method=LXMF.LXMessage.DIRECT,
                    )
                for tel in tels:
                    peer_hash = self._peer_hash_bytes(tel)
                    if peer_hash is None:
                        continue
                    tel_data = self._serialize_telemeter(tel)
                    packed_tels.append(
                        [
                            peer_hash,
                            round(tel.time.timestamp()),
                            packb(tel_data),
                            ['account', b'\x00\x00\x00', b'\xff\xff\xff'],
                        ]
                    )
            message.fields[LXMF.FIELD_TELEMETRY_STREAM] = packb(
                packed_tels, use_bin_type=True
            )
            print("+--- Sending telemetry data---------------------------------")
            print(f"| Telemetry data: {packed_tels}")
            print(f"| Message: {message}")
            print("+------------------------------------------------------------")
            return message
        else:
            return None

    def _serialize_telemeter(self, telemeter: Telemeter) -> dict:
        """Serialize the telemeter data."""
        telemeter_data = {}
        for sensor in telemeter.sensors:
            sensor_data = sensor.pack()
            telemeter_data[sensor.sid] = sensor_data
        return telemeter_data

    def _deserialize_telemeter(self, tel_data, peer_dest: str = "") -> Telemeter:
        """Deserialize the telemeter data.

        The method accepts either already unpacked telemetry dictionaries or
        raw msgpack-encoded bytes. The optional ``peer_dest`` parameter is
        primarily used when storing data received from the network.
        """
        if isinstance(tel_data, (bytes, bytearray)):
            tel_data = unpackb(tel_data, strict_map_key=False)

        tel = Telemeter(peer_dest)
        # Iterate in the order defined by ``sid_mapping`` so tests relying on
        # specific sensor ordering remain stable.
        for sid in sid_mapping:
            if sid in tel_data:
                if tel_data[sid] is None:
                    RNS.log(f"Sensor data for {sid} is None")
                    continue
                sensor = sid_mapping[sid]()
                sensor.unpack(tel_data[sid])
                tel.sensors.append(sensor)
        return tel

    def _humanize_telemetry(self, tel_data: dict) -> dict:
        """Return a friendly dict mapping sensor names to decoded readings."""
        if isinstance(tel_data, (bytes, bytearray)):
            tel_data = unpackb(tel_data, strict_map_key=False)

        readable: dict[str, object] = {}
        for sid, payload in tel_data.items():
            name = self.SID_HUMAN_NAMES.get(sid, f"sid_{sid}")
            sensor_cls = sid_mapping.get(sid)
            if sensor_cls is None:
                readable[name] = payload
                continue
            sensor = sensor_cls()
            try:
                decoded = sensor.unpack(payload)
            except Exception as exc:  # pragma: no cover - defensive logging
                RNS.log(f"Failed decoding telemetry sensor {name}: {exc}")
                decoded = payload
            readable[name] = decoded
        return readable

    def _latest_by_peer(self, telemeters: list[Telemeter]) -> list[Telemeter]:
        """Return the most recent telemetry entry per peer."""
        latest: dict[str, Telemeter] = {}
        for tel in telemeters:
            # The list is already ordered newest->oldest, so first wins.
            if tel.peer_dest not in latest:
                latest[tel.peer_dest] = tel
        return list(latest.values())

    def _peer_hash_bytes(self, telemeter: Telemeter) -> Optional[bytes]:
        """Return the peer hash for ``telemeter`` as bytes or ``None`` on failure."""

        peer_dest = (telemeter.peer_dest or "").strip()
        if not peer_dest:
            RNS.log("Telemetry entry missing peer destination; skipping")
            return None

        normalized = "".join(ch for ch in peer_dest if ch in string.hexdigits)
        if len(normalized) % 2 != 0:
            RNS.log(
                f"Telemetry entry peer destination has odd length after normalization: {peer_dest!r}"
            )
            return None

        try:
            return bytes.fromhex(normalized)
        except ValueError as exc:
            RNS.log(
                f"Skipping telemetry entry with invalid peer destination {peer_dest!r}: {exc}"
            )
            return None
