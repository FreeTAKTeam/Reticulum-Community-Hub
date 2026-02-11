from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import string
import time
from typing import Callable, Optional

from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog
from reticulum_telemetry_hub.reticulum_server.appearance import apply_icon_appearance
from reticulum_telemetry_hub.reticulum_server.appearance import (
    build_telemetry_icon_appearance_value,
)

import LXMF
import RNS
from msgpack import packb, unpackb
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance import Base
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
from sqlalchemy import func as sa_func
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, joinedload, sessionmaker
from sqlalchemy.pool import QueuePool


class TelemetryController:
    """This class is responsible for managing the telemetry data."""

    TELEMETRY_REQUEST = 1
    DEFAULT_STREAM_APPEARANCE = ["account", [0, 0, 0, 1], [1, 1, 1, 1]]
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

    _POOL_SIZE = 30
    _POOL_OVERFLOW = 60
    _CONNECT_TIMEOUT_SECONDS = 30
    _SESSION_RETRIES = 3
    _SESSION_BACKOFF = 0.1

    def __init__(
        self,
        *,
        engine: Engine | None = None,
        db_path: str | Path | None = None,
        api: ReticulumTelemetryHubAPI | None = None,
        event_log: EventLog | None = None,
    ) -> None:
        if engine is not None and db_path is not None:
            raise ValueError("Provide either 'engine' or 'db_path', not both")

        if engine is None:
            db_location = Path(db_path) if db_path is not None else Path("telemetry.db")
            engine = self._create_engine(db_location)

        self._engine = engine
        self._enable_wal_mode()
        Base.metadata.create_all(self._engine)
        self._session_cls = sessionmaker(bind=self._engine, expire_on_commit=False)
        self._telemetry_listener: (
            Callable[[dict, str | bytes | None, Optional[datetime]], None] | None
        ) = None
        self._api = api
        self._event_log = event_log
        self._ingest_count = 0
        self._last_ingest_at: datetime | None = None

    def set_api(self, api: ReticulumTelemetryHubAPI | None) -> None:
        """Attach an API service for topic-aware telemetry filtering."""

        self._api = api

    def set_event_log(self, event_log: EventLog | None) -> None:
        """Attach an event log for telemetry activity updates."""

        self._event_log = event_log

    def _create_engine(self, db_location: Path) -> Engine:
        return create_engine(
            f"sqlite:///{db_location}",
            connect_args={
                "check_same_thread": False,
                "timeout": self._CONNECT_TIMEOUT_SECONDS,
            },
            poolclass=QueuePool,
            pool_size=self._POOL_SIZE,
            max_overflow=self._POOL_OVERFLOW,
            pool_pre_ping=True,
        )

    def _enable_wal_mode(self) -> None:
        if self._engine.url.get_backend_name() != "sqlite":
            return
        try:
            with self._engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as conn:
                conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
        except OperationalError as exc:
            RNS.log(f"Failed enabling WAL mode: {exc}", RNS.LOG_WARNING)

    @contextmanager
    def _session_scope(self):
        """Yield a telemetry DB session that always closes."""

        session = self._acquire_session_with_retry()
        try:
            yield session
        finally:
            session.close()

    def _acquire_session_with_retry(self):
        """Return a database session, retrying on transient OperationalError."""

        last_exc: OperationalError | None = None
        for attempt in range(1, self._SESSION_RETRIES + 1):
            session = None
            try:
                session = self._session_cls()
                session.execute(text("SELECT 1"))
                return session
            except OperationalError as exc:
                last_exc = exc
                if session is not None:
                    session.close()
                RNS.log(
                    (
                        "SQLite session acquisition failed "
                        f"(attempt {attempt}/{self._SESSION_RETRIES}): {exc}"
                    ),
                    RNS.LOG_WARNING,
                )
                time.sleep(self._SESSION_BACKOFF * attempt)
        RNS.log(
            "Unable to obtain telemetry database session after retries",
            RNS.LOG_ERROR,
        )
        if last_exc:
            raise last_exc
        raise RuntimeError("Failed to acquire telemetry session")

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
        with self._session_scope() as ses:
            return self._load_telemetry(ses, start_time, end_time)

    def list_telemetry_entries(
        self, *, since: int, topic_id: str | None = None
    ) -> list[dict[str, object]]:
        """Return telemetry entries as JSON-friendly dictionaries.

        Args:
            since (int): Unix timestamp (seconds) for the earliest telemetry
                records to include.
            topic_id (str | None): Optional topic identifier for filtering.

        Returns:
            list[dict[str, object]]: Telemetry entries formatted for the
                northbound API.

        Raises:
            KeyError: If ``topic_id`` is provided but does not exist.
            ValueError: If topic filtering is requested without an API service.
        """

        timebase_dt = datetime.fromtimestamp(int(since))
        with self._session_scope() as ses:
            telemeters = self._load_telemetry(ses, start_time=timebase_dt)
            telemeters = self._latest_by_peer(telemeters)
            if topic_id:
                if self._api is None:
                    raise ValueError("Topic filtering requires an API service")
                subscribers = self._api.list_subscribers_for_topic(topic_id)
                allowed = {sub.destination for sub in subscribers}
                telemeters = [
                    telemeter
                    for telemeter in telemeters
                    if telemeter.peer_dest in allowed
                ]

            entries: list[dict[str, object]] = []
            for telemeter in telemeters:
                timestamp = int(telemeter.time.timestamp()) if telemeter.time else 0
                payload = self._serialize_telemeter(telemeter)
                readable_payload = self._humanize_telemetry(payload)
                display_name = None
                if self._api is not None and hasattr(
                    self._api, "resolve_identity_display_name"
                ):
                    try:
                        display_name = self._api.resolve_identity_display_name(
                            telemeter.peer_dest
                        )
                    except Exception:  # pragma: no cover - defensive
                        display_name = None
                entries.append(
                    {
                        "peer_destination": telemeter.peer_dest,
                        "timestamp": timestamp,
                        "telemetry": self._json_safe(readable_payload),
                        "display_name": display_name,
                        "identity_label": display_name,
                    }
                )
            return entries

    def register_listener(
        self,
        listener: Callable[[dict, str | bytes | None, Optional[datetime]], None],
    ) -> None:
        """Register a callback invoked when telemetry is ingested."""

        self._telemetry_listener = listener

    def save_telemetry(
        self,
        telemetry_data: dict | bytes,
        peer_dest,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Save the telemetry data."""
        tel = self._deserialize_telemeter(telemetry_data, peer_dest)

        payload = telemetry_data
        if isinstance(payload, (bytes, bytearray)):
            try:
                payload = unpackb(payload, strict_map_key=False)
            except Exception:  # pragma: no cover - defensive decoding
                payload = None

        has_sensor_timestamp = False
        if isinstance(payload, dict):
            time_value = payload.get(SID_TIME)
            has_sensor_timestamp = isinstance(time_value, (int, float))

        if not has_sensor_timestamp and timestamp is not None:
            tel.time = timestamp
        with self._session_scope() as ses:
            ses.add(tel)
            ses.commit()
        self._record_ingest(tel)

    def record_telemetry(
        self,
        telemetry_data: dict | bytes,
        peer_dest: str,
        timestamp: Optional[datetime] = None,
        *,
        notify: bool = False,
    ) -> None:
        """Persist telemetry data and optionally notify listeners."""

        self.save_telemetry(telemetry_data, peer_dest, timestamp=timestamp)
        if not notify:
            return
        readable = self._humanize_telemetry(telemetry_data)
        resolved_timestamp = timestamp or self._extract_timestamp(readable)
        self._notify_listener(readable, peer_dest, resolved_timestamp)

    def clear_telemetry(self) -> int:
        """Remove all telemetry entries from storage.

        Returns:
            int: Number of rows removed from the telemetry table.
        """

        with self._session_scope() as ses:
            deleted = ses.query(Telemeter).delete()
            ses.commit()
        return int(deleted or 0)

    def telemetry_stats(self) -> dict:
        """Return basic telemetry ingestion statistics."""

        total = self._ingest_count
        last_ingest_at = self._last_ingest_at
        try:
            with self._session_scope() as ses:
                total = int(ses.query(Telemeter.id).count() or 0)
                last_ingest_at = ses.query(sa_func.max(Telemeter.time)).scalar()
                if isinstance(last_ingest_at, str):
                    last_ingest_at = datetime.fromisoformat(last_ingest_at)
        except Exception:  # pragma: no cover - defensive fallback
            pass

        last_ingest = last_ingest_at.isoformat() if last_ingest_at else None
        return {
            "ingest_count": total,
            "last_ingest_at": last_ingest,
        }

    def ingest_local_payload(
        self,
        payload: dict,
        *,
        peer_dest: str,
    ) -> bytes | None:
        """Persist ``payload`` and return a msgpack encoded snapshot.

        The telemetry sampler uses this helper to ensure locally collected
        sensor data flows through the same persistence pipeline as incoming
        LXMF telemetry before broadcasting it to connected peers.
        """

        if not payload:
            return None

        self.save_telemetry(payload, peer_dest)
        return packb(payload, use_bin_type=True)

    def handle_message(self, message: LXMF.LXMessage) -> bool:
        """Handle the incoming message."""
        handled = False
        if LXMF.FIELD_TELEMETRY in message.fields:
            tel_data: dict = unpackb(
                message.fields[LXMF.FIELD_TELEMETRY], strict_map_key=False
            )
            readable = self._humanize_telemetry(tel_data)
            timestamp = self._extract_timestamp(readable)
            peer_dest = RNS.hexrep(message.source_hash, False)
            display_name, label = self._resolve_peer_label(peer_dest)
            RNS.log(f"Telemetry received from {label}")
            RNS.log(f"Telemetry decoded: {readable}")
            self.save_telemetry(tel_data, peer_dest)
            self._notify_listener(readable, message.source_hash, timestamp)
            self._record_event(
                "telemetry_received",
                f"Telemetry received from {label}",
                metadata={"identity": peer_dest, "display_name": display_name},
            )
            handled = True
        if LXMF.FIELD_TELEMETRY_STREAM in message.fields:
            tels_data = message.fields[LXMF.FIELD_TELEMETRY_STREAM]
            if isinstance(tels_data, (bytes, bytearray)):
                # Sideband sends telemetry streams as raw lists; decode msgpack
                # if a sender pre-encodes the field.
                tels_data = unpackb(tels_data, strict_map_key=False)
            for tel_data in tels_data:
                if not isinstance(tel_data, (list, tuple)) or len(tel_data) < 3:
                    RNS.log(
                        "Telemetry stream entries must include peer hash, timestamp, and payload; skipping"
                    )
                    continue

                peer_hash, raw_timestamp, payload = tel_data[:3]
                if not isinstance(peer_hash, (bytes, bytearray)):
                    RNS.log("Telemetry stream entry missing peer hash bytes; skipping")
                    continue

                peer_dest = RNS.hexrep(peer_hash, False)

                timestamp = None
                if isinstance(raw_timestamp, (int, float)):
                    timestamp = datetime.fromtimestamp(raw_timestamp)
                elif raw_timestamp is not None:
                    RNS.log(
                        "Telemetry stream timestamp must be numeric or null; skipping entry"
                    )
                    continue

                if not payload:
                    RNS.log("Telemetry payload missing; skipping entry")
                    continue

                readable = self._humanize_telemetry(payload)
                display_name, label = self._resolve_peer_label(peer_dest)
                RNS.log(f"Telemetry stream from {label} at {timestamp}: {readable}")
                self.save_telemetry(payload, peer_dest, timestamp)
                stream_timestamp = timestamp or self._extract_timestamp(readable)
                self._notify_listener(readable, peer_hash, stream_timestamp)
                self._record_event(
                    "telemetry_stream",
                    f"Telemetry stream entry from {label}",
                    metadata={"identity": peer_dest, "display_name": display_name},
                )
            handled = True

        return handled

    def handle_command(
        self, command: dict, message: LXMF.LXMessage, my_lxm_dest
    ) -> Optional[LXMF.LXMessage]:
        """Handle the incoming command."""
        request_key = self._numeric_command_key(
            command, TelemetryController.TELEMETRY_REQUEST
        )
        if request_key is not None:
            request_value = command[request_key]
            topic_id = self._extract_topic_id(command)

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
            human_readable_entries: list[dict[str, object]] = []
            with self._session_scope() as ses:
                timebase_dt = datetime.fromtimestamp(timebase)
                teles = self._load_telemetry(ses, start_time=timebase_dt)
                # Return one snapshot per peer using the most recent entry.
                teles = self._latest_by_peer(teles)
                teles = self._filter_by_topic(teles, topic_id, message)
                if teles is None:
                    return self._reply(
                        message,
                        my_lxm_dest,
                        "Telemetry request denied: sender is not subscribed to the topic.",
                    )
                packed_tels = []
                dest = RNS.Destination(
                    message.source.identity,
                    RNS.Destination.OUT,
                    RNS.Destination.SINGLE,
                    "lxmf",
                    "delivery",
                )
                for tel in teles:
                    peer_hash = self._peer_hash_bytes(tel)
                    if peer_hash is None:
                        continue
                    tel_data = self._serialize_telemeter(tel)
                    human_readable_entries.append(
                        {
                            "peer_destination": tel.peer_dest,
                            "timestamp": round(tel.time.timestamp()),
                            "telemetry": self._humanize_telemetry(tel_data),
                        }
                    )
                    packed_tels.append(
                        [
                            peer_hash,
                            round(tel.time.timestamp()),
                            packb(tel_data, use_bin_type=True),
                            self._build_appearance_payload(tel_data),
                        ]
                    )
                message = LXMF.LXMessage(
                    dest,
                    my_lxm_dest,
                    desired_method=LXMF.LXMessage.DIRECT,
                )
            # Sideband expects telemetry streams as plain lists; avoid
            # double-encoding the field so clients can iterate entries directly.
            message.fields[LXMF.FIELD_TELEMETRY_STREAM] = packed_tels
            message.fields = apply_icon_appearance(message.fields)
            readable_json = json.dumps(
                self._json_safe(human_readable_entries), default=str
            )
            print(f"Sending telemetry of {len(human_readable_entries)} clients")
            print("Telemetry response in human readeble format: " f"{readable_json}")
            self._record_event(
                "telemetry_request",
                f"Telemetry request served ({len(human_readable_entries)} entries)",
                metadata={
                    "topic_id": topic_id,
                    "timebase": timebase,
                    "entry_count": len(human_readable_entries),
                    "payload": human_readable_entries,
                },
            )
            return message
        else:
            return None

    def _serialize_telemeter(self, telemeter: Telemeter) -> dict:
        """Serialize the telemeter data."""
        telemeter_data = {}
        for sensor in telemeter.sensors:
            sensor_data = sensor.pack()
            telemeter_data[sensor.sid] = sensor_data

        # Ensure the timestamp sensor is always present so downstream
        # consumers (e.g. Sideband) can reconstitute the Telemeter.
        timestamp = int(telemeter.time.timestamp())
        time_payload = telemeter_data.get(SID_TIME)
        if not isinstance(time_payload, (int, float)):
            telemeter_data[SID_TIME] = timestamp
        else:
            telemeter_data[SID_TIME] = int(time_payload)

        return telemeter_data

    def _stream_appearance(self) -> list:
        """Return appearance metadata for telemetry stream entries."""

        return list(self.DEFAULT_STREAM_APPEARANCE)

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
        time_value = tel_data.get(SID_TIME)
        if isinstance(time_value, (int, float)):
            tel.time = datetime.fromtimestamp(int(time_value))
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
            if not self._telemeter_has_location(tel):
                continue
            peer_dest = (tel.peer_dest or "").strip()
            if not peer_dest:
                continue
            existing = latest.get(peer_dest)
            if existing is None:
                latest[peer_dest] = tel
                continue
            if existing.time is None:
                latest[peer_dest] = tel
                continue
            if tel.time and tel.time > existing.time:
                latest[peer_dest] = tel
        return sorted(
            latest.values(),
            key=lambda tel: tel.time or datetime.min,
            reverse=True,
        )

    def _build_appearance_payload(
        self, telemetry_payload: dict[int, object]
    ) -> list[object]:
        """Return the appearance payload for telemetry stream entries.

        Args:
            telemetry_payload (dict[int, object]): Serialized telemetry payload.

        Returns:
            list[object]: LXMF appearance list for stream entries.
        """

        return build_telemetry_icon_appearance_value(telemetry_payload)

    def _telemeter_has_location(self, telemeter: Telemeter) -> bool:
        """Return True when the telemeter includes usable location data."""
        for sensor in telemeter.sensors:
            if getattr(sensor, "sid", None) != SID_LOCATION:
                continue
            latitude = getattr(sensor, "latitude", None)
            longitude = getattr(sensor, "longitude", None)
            if latitude is None or longitude is None:
                return False
            return True
        return False

    def _notify_listener(
        self,
        telemetry: dict,
        peer_hash: str | bytes | None,
        timestamp: Optional[datetime],
    ) -> None:
        """Invoke the registered telemetry listener when present."""

        if self._telemetry_listener is None:
            return
        try:
            self._telemetry_listener(telemetry, peer_hash, timestamp)
        except Exception as exc:  # pragma: no cover - defensive logging
            RNS.log(f"Telemetry listener raised an exception: {exc}", RNS.LOG_WARNING)

    def _record_event(
        self,
        event_type: str,
        message: str,
        *,
        metadata: Optional[dict] = None,
    ) -> None:
        """Emit a telemetry event to the shared event log."""

        if self._event_log is None:
            return
        self._event_log.add_event(event_type, message, metadata=metadata)

    def _resolve_peer_label(self, peer_dest: str) -> tuple[str | None, str]:
        """Return display name and label for a peer destination."""

        display_name = None
        if self._api is not None and hasattr(self._api, "resolve_identity_display_name"):
            try:
                display_name = self._api.resolve_identity_display_name(peer_dest)
            except Exception:  # pragma: no cover - defensive
                display_name = None
        if display_name:
            return display_name, f"{display_name} ({peer_dest})"
        return None, peer_dest

    def _record_ingest(self, telemeter: Telemeter) -> None:
        """Update telemetry ingestion statistics."""

        self._ingest_count += 1
        if telemeter.time:
            self._last_ingest_at = telemeter.time

    @staticmethod
    def _reply(
        message: LXMF.LXMessage, my_lxm_dest, content: str
    ) -> LXMF.LXMessage:
        """Return an LXMF reply message to the sender."""

        dest = RNS.Destination(
            message.source.identity,
            RNS.Destination.OUT,
            RNS.Destination.SINGLE,
            "lxmf",
            "delivery",
        )
        return LXMF.LXMessage(
            dest,
            my_lxm_dest,
            content,
            fields=apply_icon_appearance(None),
            desired_method=LXMF.LXMessage.DIRECT,
        )

    @staticmethod
    def _extract_topic_id(command: dict) -> Optional[str]:
        """Return a topic id from a telemetry command payload."""

        return (
            command.get("TopicID")
            or command.get("topic_id")
            or command.get("topicId")
        )

    @staticmethod
    def _numeric_command_key(command: dict, index: int) -> int | str | None:
        """Return the numeric command key matching the provided index.

        Args:
            command (dict): Incoming command payload.
            index (int): Numeric index to locate.

        Returns:
            int | str | None: The matching key when present.
        """

        for key in command:
            try:
                if str(key).isdigit() and int(str(key)) == index:
                    return key
            except ValueError:
                continue
        return None

    def _filter_by_topic(
        self,
        telemeters: list[Telemeter],
        topic_id: str | None,
        message: LXMF.LXMessage,
    ) -> list[Telemeter] | None:
        """Filter telemetry entries to those subscribed to a topic."""

        if topic_id is None:
            return telemeters
        if self._api is None:
            return telemeters
        try:
            subscribers = self._api.list_subscribers_for_topic(topic_id)
        except KeyError:
            return []
        destination = self._identity_hex(message.source.identity)
        allowed = {sub.destination for sub in subscribers}
        if destination not in allowed:
            return None
        return [tel for tel in telemeters if tel.peer_dest in allowed]

    @staticmethod
    def _identity_hex(identity: RNS.Identity) -> str:
        """Return the identity hash as a lowercase hex string."""

        hash_bytes = getattr(identity, "hash", b"") or b""
        return hash_bytes.hex()

    def _extract_timestamp(self, telemetry: dict) -> Optional[datetime]:
        """Return a datetime parsed from a telemetry payload when available."""

        time_payload = telemetry.get("time")
        if isinstance(time_payload, dict):
            raw_timestamp = time_payload.get("timestamp")
            if isinstance(raw_timestamp, (int, float)):
                return datetime.fromtimestamp(int(raw_timestamp))
            iso_value = time_payload.get("iso")
            if isinstance(iso_value, str):
                try:
                    return datetime.fromisoformat(iso_value)
                except ValueError:
                    return None
        if isinstance(time_payload, (int, float)):
            return datetime.fromtimestamp(int(time_payload))
        return None

    def _peer_hash_bytes(self, telemeter: Telemeter) -> Optional[bytes]:
        """Return the peer hash for ``telemeter`` as bytes or ``None`` on failure."""

        peer_dest = (telemeter.peer_dest or "").strip()
        if not peer_dest:
            RNS.log("Telemetry entry missing peer destination; skipping")
            return None

        normalized = "".join(ch for ch in peer_dest if ch in string.hexdigits)
        if not normalized:
            RNS.log(
                f"Telemetry entry peer destination missing hex characters: {peer_dest!r}"
            )
            return None
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

    def _json_safe(self, value):
        """Return ``value`` converted into a JSON-safe structure."""

        if isinstance(value, dict):
            return {self._json_key(k): self._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._json_safe(v) for v in value]
        if isinstance(value, (bytes, bytearray)):
            return value.hex()
        return value

    def _json_key(self, key):
        """Return a JSON-safe dict key representation."""

        if isinstance(key, (str, int, float, bool)) or key is None:
            return key
        if isinstance(key, (bytes, bytearray)):
            return key.hex()
        return str(key)
