from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import time
from typing import Callable, Optional

import RNS
from reticulum_telemetry_hub.api.service import ReticulumTelemetryHubAPI
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_commands import TelemetryCommandMixin
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_queries import TelemetryQueryMixin
from reticulum_telemetry_hub.lxmf_telemetry.telemetry_serialization import (
    TelemetrySerializationMixin,
)
from reticulum_telemetry_hub.reticulum_server.event_log import EventLog

import LXMF
from msgpack import packb
from msgpack import unpackb
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance import Base
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.telemeter import (
    Telemeter,
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
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from sqlalchemy.sql.functions import count as sa_count
from sqlalchemy.sql.functions import max as sa_max

TelemetryListener = Callable[[dict, str | bytes | None, Optional[datetime]], None]


class TelemetryController(
    TelemetryQueryMixin,
    TelemetryCommandMixin,
    TelemetrySerializationMixin,
):
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

    _POOL_SIZE = 8
    _POOL_OVERFLOW = 16
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
        self._ensure_indexes()
        self._session_cls = sessionmaker(bind=self._engine, expire_on_commit=False)
        self._telemetry_listeners: set[TelemetryListener] = set()
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

    def _ensure_indexes(self) -> None:
        """Create hot-path indexes for telemetry snapshot queries."""

        statements = (
            "CREATE INDEX IF NOT EXISTS idx_telemeter_peer_time ON Telemeter(peer_dest, time DESC);",
            "CREATE INDEX IF NOT EXISTS idx_telemeter_time ON Telemeter(time DESC);",
            "CREATE INDEX IF NOT EXISTS idx_sensor_telemeter_id ON Sensor(telemeter_id);",
            "CREATE INDEX IF NOT EXISTS idx_sensor_telemeter_sid ON Sensor(telemeter_id, sid);",
            (
                "CREATE INDEX IF NOT EXISTS idx_lxmf_propagation_peer_propagation_id "
                "ON LXMFPropagationPeer(propagation_id);"
            ),
        )
        try:
            with self._engine.begin() as conn:
                for statement in statements:
                    conn.exec_driver_sql(statement)
        except OperationalError as exc:
            RNS.log(f"Failed creating telemetry indexes: {exc}", RNS.LOG_WARNING)

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

    def register_listener(
        self,
        listener: TelemetryListener,
    ) -> Callable[[], None]:
        """Register a callback invoked when telemetry is ingested.

        Returns:
            Callable[[], None]: Callback that unsubscribes the listener.
        """

        self._telemetry_listeners.add(listener)

        def _unsubscribe() -> None:
            """Remove the registered listener."""

            self._telemetry_listeners.discard(listener)

        return _unsubscribe

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
                total = int(ses.query(sa_count(Telemeter.id)).scalar() or 0)
                last_ingest_at = ses.query(sa_max(Telemeter.time)).scalar()
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

