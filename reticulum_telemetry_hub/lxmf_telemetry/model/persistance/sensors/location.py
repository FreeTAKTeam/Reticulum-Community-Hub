from sqlalchemy import Column
from reticulum_telemetry_hub.lxmf_telemetry.model.persistance.sensors.sensor import (
    Sensor,
)
from .sensor_enum import SID_LOCATION
import struct
import RNS
from sqlalchemy import Integer, ForeignKey, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional
from datetime import datetime


class Location(Sensor):
    __tablename__ = "Location"

    id: Mapped[int] = mapped_column(ForeignKey("Sensor.id"), primary_key=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    altitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    speed: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bearing: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    accuracy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_update: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def __init__(self):
        super().__init__(stale_time=15)
        self.sid = SID_LOCATION
        self.latitude = None
        self.longitude = None
        self.altitude = None
        self.speed = None
        self.bearing = None
        self.accuracy = None
        self.last_update = None

    def pack(self):
        try:
            latitude = self._require_float(self.latitude, "latitude")
            longitude = self._require_float(self.longitude, "longitude")
            altitude = self._normalize_altitude(self.altitude)
            speed = self._require_float(self.speed, "speed")
            bearing = self._require_float(self.bearing, "bearing")
            accuracy = self._require_float(self.accuracy, "accuracy")
            return [
                struct.pack("!i", int(round(latitude, 6) * 1e6)),
                struct.pack("!i", int(round(longitude, 6) * 1e6)),
                struct.pack("!I", int(round(altitude, 2) * 1e2)),
                struct.pack("!I", int(round(speed, 2) * 1e2)),
                struct.pack("!I", int(round(bearing, 2) * 1e2)),
                struct.pack("!H", int(round(accuracy, 2) * 1e2)),
                self._serialize_last_update(),
            ]
        except (KeyError, ValueError, struct.error, TypeError) as e:
            RNS.log(
                "An error occurred while packing location sensor data. "
                "The contained exception was: " + str(e),
                RNS.LOG_ERROR,
            )
            return None

    def unpack(self, packed):
        try:
            if packed is None:
                return None
            else:
                self.latitude = struct.unpack("!i", packed[0])[0] / 1e6
            self.longitude = struct.unpack("!i", packed[1])[0] / 1e6
            self.altitude = struct.unpack("!I", packed[2])[0] / 1e2
            self.speed = struct.unpack("!I", packed[3])[0] / 1e2
            self.bearing = struct.unpack("!I", packed[4])[0] / 1e2
            self.accuracy = struct.unpack("!H", packed[5])[0] / 1e2
            self.last_update = datetime.fromtimestamp(packed[6])
            return {
                "latitude": self.latitude,
                "longitude": self.longitude,
                "altitude": self.altitude,
                "speed": self.speed,
                "bearing": self.bearing,
                "accuracy": self.accuracy,
                "last_update_iso": self.last_update.isoformat(),
                "last_update_timestamp": self.last_update.timestamp(),
            }
        except (struct.error, IndexError):
            return None

    def _require_float(self, value: Optional[float], field_name: str) -> float:
        if value is None:
            raise ValueError(f"{field_name} is not set on Location sensor")
        return float(value)

    def _serialize_last_update(self) -> float:
        if self.last_update is None:
            raise ValueError("last_update is not set on Location sensor")
        if isinstance(self.last_update, datetime):
            return self.last_update.timestamp()
        if isinstance(self.last_update, (int, float)):
            return float(self.last_update)
        raise TypeError("last_update must be datetime or a unix timestamp")

    def _normalize_altitude(self, value: Optional[float]) -> float:
        """Return a safe altitude value, replacing invalid sentinels with 0."""
        altitude = self._require_float(value, "altitude")
        # Sideband sometimes surfaces the 0xffffffff sentinel as 42949672.95;
        # treat anything in that range as "no altitude" to avoid absurd UI values.
        if altitude >= 4.294e7:
            return 0.0
        return altitude

    __mapper_args__ = {"polymorphic_identity": SID_LOCATION, "with_polymorphic": "*"}
