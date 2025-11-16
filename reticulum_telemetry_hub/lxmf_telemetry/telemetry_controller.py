from datetime import datetime
from pathlib import Path
import string
from typing import Optional

import LXMF
import RNS
from msgpack import packb, unpackb
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance import Base
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor import Sensor
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.telemeter import Telemeter
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.lxmf_propagation import (
    LXMFPropagation,
)

from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor_mapping import sid_mapping
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session, joinedload


class TelemetryController:
    """This class is responsible for managing the telemetry data."""

    TELEMETRY_REQUEST = 1

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
            RNS.log(f"Telemetry data: {tel_data}")
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
                self.save_telemetry(payload, peer_dest, timestamp)
            handled = True

        return handled

    def handle_command(self, command: dict, message: LXMF.LXMessage, my_lxm_dest) -> Optional[LXMF.LXMessage]:
        """Handle the incoming command."""
        if TelemetryController.TELEMETRY_REQUEST in command:
            timebase = command[TelemetryController.TELEMETRY_REQUEST]
            with self._session_cls() as ses:
                tels = self._load_telemetry(
                    ses, start_time=datetime.fromtimestamp(timebase)
                )
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
